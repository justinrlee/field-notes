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
- Every emitted event gets a sequence number, assigned and scheduled under the
  lock, so events reach the loop in sequence order. Subscriber queues hold
  (seq, envelope) pairs. A stream remembers the seq of the snapshot it sent and
  skips queued events at or below it; otherwise an event already reflected in
  the snapshot (a timeline entry, say) would be shown twice.

Nothing in this module talks to Kafka, so the UI keeps working while Kafka is
unreachable. Keep it that way.

Event envelope sent to the browser (see PLAN.md, "Event contract"):
    {"type": <snapshot|connection|metrics|messages|timeline>,
     "client_id": str, "ts": epoch_ms, "data": {...}}
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import OrderedDict, deque
from typing import Any

FLUSH_INTERVAL_S = 0.2
MAX_MESSAGES = 600          # message tiles kept for the UI
MAX_TIMELINE = 200
SUBSCRIBER_QUEUE_SIZE = 500

log = logging.getLogger("demo.stats")

COUNTER_NAMES = (
    # producer
    "queued", "acked", "failed", "buffer_full",
    # consumer
    "consumed", "gaps", "missing", "duplicates", "rebalances",
)


def now_ms() -> int:
    return int(time.time() * 1000)


# librdkafka statistics fields read by DemoState.on_stats (STATISTICS.md).
# "brokers.*" means every entry of the brokers object.
STATS_FIELDS = {
    "producer": ("brokers.*.state", "brokers.*.connects", "msg_cnt", "msg_max"),
    "consumer": ("brokers.*.state", "brokers.*.connects", "cgrp.state", "cgrp.join_state"),
}


def missing_stats_fields(stats: dict[str, Any], role: str) -> list[str]:
    """Field paths from STATS_FIELDS[role] that this payload lacks. A broker
    field counts as missing if any non-internal broker lacks it, or if there
    are no such brokers to check."""
    missing = []
    for path in STATS_FIELDS[role]:
        parts = path.split(".")
        if parts[0] == "brokers":
            brokers = [b for b in (stats.get("brokers") or {}).values()
                       if b.get("source") != "internal"]
            if not brokers or any(parts[2] not in b for b in brokers):
                missing.append(path)
            continue
        node: Any = stats
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                missing.append(path)
                break
            node = node[part]
    return missing


class DemoState:
    def __init__(self, *, client_id: str, role: str, profile: str, topic: str,
                 settings: dict[str, Any], debug_stats: bool = False):
        self.client_id = client_id
        self.role = role
        self.debug_stats = debug_stats
        self.client = {
            "client_id": client_id, "role": role, "profile": profile,
            "topic": topic, "settings": settings,
        }
        self.rate: float | None = None

        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self._seq = 0   # last event sequence number handed out

        self.connection: dict[str, Any] = {
            "state": "connecting",     # connecting | connected | retrying
            "since": now_ms(),         # when the current state began
            "outage_started": None,
            "last_outage_ms": None,    # duration of the most recent outage
            "attempts": 0,             # reconnect attempts during this outage
            "last_error": None,
            "probe_latency_ms": None,
            "cluster_id": None,
            "topic_problem": None,     # why the demo topic can't be used, if it can't
        }
        self.counters = dict.fromkeys(COUNTER_NAMES, 0)
        self.buffer: dict[str, Any] = {"msg_cnt": 0, "msg_max": None}
        self.brokers: dict[str, dict] = {}
        self.group: dict[str, Any] | None = None

        self.messages: OrderedDict[str, dict] = OrderedDict()
        self._dirty: set[str] = set()
        self._max_evicted_seq: dict[int | None, int] = {}   # per partition
        self.timeline: deque[dict] = deque(maxlen=MAX_TIMELINE)

        # librdkafka's per-broker "connects" counts every connection attempt,
        # failed or not. The outage attempt count is the largest increase on any
        # one broker since the outage began; summing would count each attempt
        # once per broker handle (bootstrap, learned, group coordinator).
        self._connects: dict[str, int] = {}
        self._connects_baseline: dict[str, int] = {}
        self._stats_logged: set[str] = set()
        # Streak flags keep the timeline readable: one entry per episode, not per message.
        self._buffer_full_streak = False
        self._failure_streak = False
        self._duplicate_streak = False

    # ------------------------------------------------------------------ wiring

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        """Loop thread only. The queue receives (seq, envelope) pairs."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Loop thread only."""
        self._subscribers.discard(queue)

    def envelope(self, type_: str, data: Any) -> dict:
        return {"type": type_, "client_id": self.client_id, "ts": now_ms(), "data": data}

    def _emit(self, type_: str, data: Any) -> None:
        with self._lock:
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            self._seq += 1
            # Scheduled while holding the lock, so the loop sees events in seq order.
            loop.call_soon_threadsafe(self._fanout, self._seq, self.envelope(type_, data))

    def _fanout(self, seq: int, env: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait((seq, env))
            except asyncio.QueueFull:
                # A slow or backgrounded tab fell behind. Replace its backlog
                # with a fresh snapshot instead of dropping events silently.
                while not queue.empty():
                    queue.get_nowait()
                snap_seq, snap = self.snapshot_with_seq()
                queue.put_nowait((snap_seq, self.envelope("snapshot", snap)))

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
            self._connects_baseline = dict(self._connects)
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

    def on_probe_ok(self, cluster_id: str | None, latency_ms: int, *,
                    topic_problem: str | None = None) -> None:
        with self._lock:
            self.connection["probe_latency_ms"] = latency_ms
            self.connection["last_error"] = None
            self._transition_locked("connected")
            old_problem = self.connection["topic_problem"]
            if topic_problem != old_problem:
                self.connection["topic_problem"] = topic_problem
                if topic_problem:
                    self._timeline_locked("topic", topic_problem)
                elif old_problem:
                    self._timeline_locked("info", f"Topic {self.client['topic']} is available")
                self._emit("connection", self._connection_view())
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
        librdkafka's STATISTICS.md; DEBUG_STATS=1 logs a real payload and any
        field this method expects but didn't find."""
        if self.debug_stats:
            self._log_stats(stats)
        brokers: dict[str, dict] = {}
        connects: dict[str, int] = {}
        for name, broker in (stats.get("brokers") or {}).items():
            # ":0/internal" is librdkafka's internal queue handle, not a
            # connection. It never leaves INIT and would read as "down".
            if broker.get("source") == "internal":
                continue
            brokers[name] = {
                "state": broker.get("state"),
                "nodeid": broker.get("nodeid"),
                "source": broker.get("source"),
            }
            connects[name] = int(broker.get("connects", 0))
        cgrp = stats.get("cgrp")
        with self._lock:
            self.brokers = brokers
            self._connects = connects
            if self.connection["state"] == "retrying":
                self.connection["attempts"] = max(
                    (count - self._connects_baseline.get(name, 0) for name, count in connects.items()),
                    default=0,
                )
            if self.role == "producer":
                self.buffer = {"msg_cnt": stats.get("msg_cnt", 0), "msg_max": stats.get("msg_max")}
            if cgrp:
                self.group = {
                    "state": cgrp.get("state"),
                    "join_state": cgrp.get("join_state"),
                    "assignment_size": cgrp.get("assignment_size"),
                    "rebalance_cnt": cgrp.get("rebalance_cnt"),
                }

    def _log_stats(self, stats: dict[str, Any]) -> None:
        """Logs the first payload, and the first one with a broker UP (the
        first usually arrives before any connection is established)."""
        brokers = (stats.get("brokers") or {}).values()
        moments = ["first"]
        if any(b.get("state") == "UP" for b in brokers):
            moments.append("first with a broker UP")
        new = [m for m in moments if m not in self._stats_logged]
        if not new:
            return
        self._stats_logged.update(new)
        log.info("%s: %s stats payload: %s", self.client_id, new[-1], json.dumps(stats, sort_keys=True))
        missing = missing_stats_fields(stats, self.role)
        if missing:
            log.warning("%s: stats payload lacks fields on_stats reads: %s",
                        self.client_id, ", ".join(missing))
        else:
            log.info("%s: stats payload has every field on_stats reads: %s",
                     self.client_id, ", ".join(STATS_FIELDS[self.role]))

    # ---------------------------------------------------------------- producer

    def _put_message(self, key: str, message: dict) -> None:
        self.messages[key] = message
        self._dirty.add(key)
        while len(self.messages) > MAX_MESSAGES:
            old_key, old = self.messages.popitem(last=False)
            self._dirty.discard(old_key)
            partition = old.get("partition")
            self._max_evicted_seq[partition] = max(
                self._max_evicted_seq.get(partition, 0), int(old.get("seq") or 0))

    def on_queued(self, msg_id: str, seq: int, *, partition: int | None = None) -> None:
        with self._lock:
            self.counters["queued"] += 1
            self._buffer_full_streak = False
            if msg_id in self.messages:
                return  # delivery report already arrived (rare race); keep its state
            self._put_message(msg_id, {"id": msg_id, "seq": seq, "partition": partition,
                                       "state": "queued", "ts": now_ms()})

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
                    where = f" on partition {partition}" if partition is not None else ""
                    self._timeline_locked("failed", f"Message {seq}{where} was not delivered: {error}")
                self._failure_streak = True

            message = self.messages.get(msg_id)
            if message is None:
                if seq <= self._max_evicted_seq.get(partition, 0):
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
                    "gap", f"{missing} message(s) from {producer_id} on partition {partition} "
                           f"never arrived (before seq {seq})")
            if verdict == "duplicate":
                self.counters["duplicates"] += 1
                if not self._duplicate_streak:
                    self._timeline_locked(
                        "duplicate", f"Duplicate or replayed messages from {producer_id}, "
                                     f"starting at seq {seq} on partition {partition}")
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
            if updates:
                self._emit("messages", {"updates": updates})
            self._emit("metrics", self._metrics_view())

    def snapshot(self) -> dict[str, Any]:
        return self.snapshot_with_seq()[1]

    def snapshot_with_seq(self) -> tuple[int, dict[str, Any]]:
        """The snapshot plus the seq of the last event it already reflects."""
        with self._lock:
            return self._seq, {
                "client": self.client,
                "connection": self._connection_view(),
                "metrics": self._metrics_view(),
                "messages": [dict(m) for m in self.messages.values()],
                "timeline": list(self.timeline),
                "server_time": now_ms(),
            }
