"""In-process state for one demo client, and fan-out of changes to browsers.

Threading model
- librdkafka callbacks (delivery reports, errors, stats) run on the producer or
  consumer poll thread and call the on_* methods. Those take self._lock.
- Browser subscribers (one asyncio.Queue per open SSE stream) live on the
  asyncio event loop. Worker threads hand events to the loop with
  loop.call_soon_threadsafe, and the subscriber set is only touched on the loop
  thread, so it needs no lock.
- Per-message updates are coalesced: workers mark messages dirty, and flush()
  runs every FLUSH_INTERVAL_S on the loop to send one batched "messages" event
  plus a "metrics" event. Connection changes and timeline entries go out
  immediately.

Nothing in this module talks to Kafka, so the UI keeps working while Kafka is
unreachable. Keep it that way.

Event envelope sent to the browser (see PLAN.md, "Event contract"):
    {"type": <snapshot|connection|metrics|messages|timeline>,
     "client_id": str, "ts": epoch_ms, "data": {...}}
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict, deque
from typing import Any

FLUSH_INTERVAL_S = 0.2
MAX_MESSAGES = 600          # message tiles kept for the UI
MAX_TIMELINE = 200
SUBSCRIBER_QUEUE_SIZE = 500

COUNTER_NAMES = (
    # producer
    "queued", "acked", "failed", "buffer_full",
    # consumer
    "consumed", "gaps", "missing", "duplicates", "rebalances",
)


def now_ms() -> int:
    return int(time.time() * 1000)


class DemoState:
    def __init__(self, *, client_id: str, role: str, profile: str, topic: str,
                 settings: dict[str, Any]):
        self.client_id = client_id
        self.role = role
        self.client = {
            "client_id": client_id, "role": role, "profile": profile,
            "topic": topic, "settings": settings,
        }
        self.rate: float | None = None

        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue] = set()

        self.connection: dict[str, Any] = {
            "state": "connecting",     # connecting | connected | retrying
            "since": now_ms(),         # when the current state began
            "outage_started": None,
            "last_outage_ms": None,    # duration of the most recent outage
            "attempts": 0,             # reconnect attempts during this outage
            "last_error": None,
            "probe_latency_ms": None,
            "cluster_id": None,
        }
        self.counters = dict.fromkeys(COUNTER_NAMES, 0)
        self.buffer: dict[str, Any] = {"msg_cnt": 0, "msg_max": None}
        self.brokers: dict[str, dict] = {}
        self.group: dict[str, Any] | None = None

        self.messages: OrderedDict[str, dict] = OrderedDict()
        self._dirty: set[str] = set()
        self._max_evicted_seq = 0
        self.timeline: deque[dict] = deque(maxlen=MAX_TIMELINE)

        self._connects_total = 0
        self._connects_baseline = 0
        # Streak flags keep the timeline readable: one entry per episode, not per message.
        self._buffer_full_streak = False
        self._failure_streak = False
        self._duplicate_streak = False

    # ------------------------------------------------------------------ wiring

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        """Loop thread only."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Loop thread only."""
        self._subscribers.discard(queue)

    def envelope(self, type_: str, data: Any) -> dict:
        return {"type": type_, "client_id": self.client_id, "ts": now_ms(), "data": data}

    def _emit(self, type_: str, data: Any) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._fanout, self.envelope(type_, data))

    def _fanout(self, env: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(env)
            except asyncio.QueueFull:
                # A slow or backgrounded tab fell behind. Replace its backlog
                # with a fresh snapshot instead of dropping events silently.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(self.envelope("snapshot", self.snapshot()))

    # ---------------------------------------------------------------- timeline

    def add_timeline(self, kind: str, text: str) -> None:
        with self._lock:
            self._timeline_locked(kind, text)

    def _timeline_locked(self, kind: str, text: str) -> None:
        entry = {"ts": now_ms(), "kind": kind, "text": text}
        self.timeline.append(entry)
        self._emit("timeline", entry)

    # -------------------------------------------------------------- connection

    def _connection_view(self) -> dict[str, Any]:
        return dict(self.connection)

    def _transition_locked(self, new_state: str, detail: str | None = None) -> None:
        conn = self.connection
        old_state = conn["state"]
        if old_state == new_state:
            return
        t = now_ms()
        if new_state == "retrying":
            conn["outage_started"] = t
            conn["attempts"] = 0
            self._connects_baseline = self._connects_total
            suffix = f" ({detail})" if detail else ""
            if old_state == "connecting":
                self._timeline_locked("outage", f"Can't reach Kafka yet{suffix}")
            else:
                self._timeline_locked("outage", f"Lost connection to Kafka{suffix}")
        elif new_state == "connected" and conn["outage_started"] is not None:
            duration = t - conn["outage_started"]
            conn["last_outage_ms"] = duration
            conn["outage_started"] = None
            self._timeline_locked("recovered", f"Reconnected after {duration / 1000:.1f} s")
        elif new_state == "connected":
            self._timeline_locked("connected", "Connected to Kafka")
        conn["state"] = new_state
        conn["since"] = t
        self._emit("connection", self._connection_view())

    def on_probe_ok(self, cluster_id: str | None, latency_ms: int) -> None:
        with self._lock:
            self.connection["probe_latency_ms"] = latency_ms
            self.connection["last_error"] = None
            self._transition_locked("connected")
            old = self.connection["cluster_id"]
            if cluster_id and cluster_id != old:
                self.connection["cluster_id"] = cluster_id
                if old:
                    self._timeline_locked("cluster", f"Cluster changed from {old} to {cluster_id}")
                else:
                    self._timeline_locked("cluster", f"Cluster ID is {cluster_id}")
                self._emit("connection", self._connection_view())

    def on_probe_fail(self, error: str) -> None:
        with self._lock:
            self.connection["last_error"] = error
            self.connection["probe_latency_ms"] = None
            self._transition_locked("retrying", "metadata request timed out")

    def on_kafka_error(self, name: str, text: str, fatal: bool) -> None:
        """From error_cb. Most librdkafka errors here are informational: the
        client keeps reconnecting by itself. Only fatal errors are terminal."""
        with self._lock:
            self.connection["last_error"] = text
            if fatal:
                self._timeline_locked("fatal", f"Fatal client error: {text}")
            if name == "_ALL_BROKERS_DOWN":
                self._transition_locked("retrying", "all broker connections are down")

    def on_stats(self, stats: dict[str, Any]) -> None:
        """From stats_cb (statistics.interval.ms). Field names follow
        librdkafka's STATISTICS.md; verify against a real payload (PLAN.md, Phase 0)."""
        brokers: dict[str, dict] = {}
        connects = 0
        for name, broker in (stats.get("brokers") or {}).items():
            brokers[name] = {"state": broker.get("state"), "nodeid": broker.get("nodeid")}
            connects += int(broker.get("connects", 0))
        cgrp = stats.get("cgrp")
        with self._lock:
            self.brokers = brokers
            self._connects_total = connects
            if self.connection["state"] == "retrying":
                self.connection["attempts"] = max(0, connects - self._connects_baseline)
            if self.role == "producer":
                self.buffer = {"msg_cnt": stats.get("msg_cnt", 0), "msg_max": stats.get("msg_max")}
            if cgrp:
                self.group = {
                    "state": cgrp.get("state"),
                    "join_state": cgrp.get("join_state"),
                    "assignment_size": cgrp.get("assignment_size"),
                    "rebalance_cnt": cgrp.get("rebalance_cnt"),
                }

    # ---------------------------------------------------------------- producer

    def _put_message(self, key: str, message: dict) -> None:
        self.messages[key] = message
        self._dirty.add(key)
        while len(self.messages) > MAX_MESSAGES:
            old_key, old = self.messages.popitem(last=False)
            self._dirty.discard(old_key)
            self._max_evicted_seq = max(self._max_evicted_seq, int(old.get("seq") or 0))

    def on_queued(self, msg_id: str, seq: int) -> None:
        with self._lock:
            self.counters["queued"] += 1
            self._buffer_full_streak = False
            if msg_id in self.messages:
                return  # delivery report already arrived (rare race); keep its state
            self._put_message(msg_id, {"id": msg_id, "seq": seq, "state": "queued", "ts": now_ms()})

    def on_buffer_full(self) -> None:
        with self._lock:
            self.counters["buffer_full"] += 1
            if not self._buffer_full_streak:
                self._timeline_locked("backpressure", "Send buffer is full, so new messages are being refused")
            self._buffer_full_streak = True

    def on_delivered(self, msg_id: str, seq: int, *, error: str | None = None,
                     partition: int | None = None, offset: int | None = None) -> None:
        with self._lock:
            if error is None:
                self.counters["acked"] += 1
                self._failure_streak = False
            else:
                self.counters["failed"] += 1
                if not self._failure_streak:
                    self._timeline_locked("failed", f"Message {seq} was not delivered: {error}")
                self._failure_streak = True

            message = self.messages.get(msg_id)
            if message is None:
                if seq <= self._max_evicted_seq:
                    return  # tile already scrolled out of the UI; counters are updated
                message = {"id": msg_id, "seq": seq}
                self._put_message(msg_id, message)
            message.update(
                state="failed" if error else "acked",
                error=error, partition=partition, offset=offset, ts=now_ms(),
            )
            self._dirty.add(msg_id)

    def set_rate(self, rate: float, *, announce: bool = True) -> None:
        with self._lock:
            self.rate = rate
            if announce:
                self._timeline_locked("rate", f"Send rate set to {rate:g} per second")

    # ---------------------------------------------------------------- consumer

    def on_consumed(self, *, producer_id: str, seq: int, verdict: str, missing: int,
                    partition: int, offset: int) -> None:
        """verdict: first | ok | gap | duplicate (see consumer.SequenceTracker)."""
        with self._lock:
            self.counters["consumed"] += 1
            if verdict == "gap":
                self.counters["gaps"] += 1
                self.counters["missing"] += missing
                self._timeline_locked(
                    "gap", f"{missing} message(s) from {producer_id} never arrived (before seq {seq})")
            if verdict == "duplicate":
                self.counters["duplicates"] += 1
                if not self._duplicate_streak:
                    self._timeline_locked(
                        "duplicate", f"Duplicate or replayed messages from {producer_id}, starting at seq {seq}")
                self._duplicate_streak = True
            else:
                self._duplicate_streak = False
            # Key by consumption count so a redelivered message gets its own tile.
            key = f"c{self.counters['consumed']}"
            self._put_message(key, {
                "id": key, "producer_id": producer_id, "seq": seq, "state": verdict,
                "partition": partition, "offset": offset, "ts": now_ms(),
            })

    def on_assignment(self, kind: str, partitions: list[int]) -> None:
        """kind: assigned | revoked | lost"""
        with self._lock:
            if kind == "assigned":
                self.counters["rebalances"] += 1
            listed = ", ".join(str(p) for p in sorted(partitions)) or "none"
            self._timeline_locked("rebalance", f"Partitions {kind}: {listed}")

    def on_resume(self, partition: int, offset: int) -> None:
        self.add_timeline("resume", f"Reading partition {partition} from offset {offset}")

    # ------------------------------------------------------------ batched views

    def _metrics_view(self) -> dict[str, Any]:
        counters = dict(self.counters)
        counters["pending"] = max(0, counters["queued"] - counters["acked"] - counters["failed"])
        return {
            "counters": counters,
            "buffer": dict(self.buffer),
            "brokers": {name: dict(b) for name, b in self.brokers.items()},
            "group": dict(self.group) if self.group else None,
            "rate": self.rate,
            "connection": self._connection_view(),
        }

    def flush(self) -> None:
        """Loop thread, every FLUSH_INTERVAL_S."""
        with self._lock:
            updates = [dict(m) for key, m in self.messages.items() if key in self._dirty]
            self._dirty.clear()
            metrics = self._metrics_view()
        if updates:
            self._emit("messages", {"updates": updates})
        self._emit("metrics", metrics)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "client": self.client,
                "connection": self._connection_view(),
                "metrics": self._metrics_view(),
                "messages": [dict(m) for m in self.messages.values()],
                "timeline": list(self.timeline),
                "server_time": now_ms(),
            }
