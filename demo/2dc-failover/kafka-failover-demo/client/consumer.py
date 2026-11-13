"""Consumer role: reads the demo topic and checks every producer's sequences.

Producers number their messages per partition, and Kafka keeps order within a
partition, so sequences are tracked per (producer, run, partition), using the
partition the message was actually read from.

Verdicts per message (SequenceTracker.observe):
    first      first message seen from this producer run (no judgement possible)
    ok         seq == last + 1
    gap        seq >  last + 1   -> (seq - last - 1) messages never arrived
    duplicate  seq <= last       -> redelivered or replayed

Limitation: tracking is per consumer instance. When a partition moves to a
different group member during a rebalance, the new owner starts with "first"
for that partition and can't see a gap across the handover. PLAN.md (Phase 3) adds an auditor
consumer in its own single-member group to be the authority on loss/duplicates.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from confluent_kafka import Consumer, KafkaError

from state import DemoState


class SequenceTracker:
    def __init__(self) -> None:
        self._last: dict[tuple[str, str, int], int] = {}

    def observe(self, producer_id: str, run_id: str, partition: int, seq: int) -> tuple[str, int]:
        key = (producer_id, run_id, partition)
        last = self._last.get(key)
        if last is None:
            self._last[key] = seq
            return "first", 0
        if seq == last + 1:
            self._last[key] = seq
            return "ok", 0
        if seq > last + 1:
            self._last[key] = seq
            return "gap", seq - last - 1
        return "duplicate", 0


class DemoConsumer:
    def __init__(self, state: DemoState, config: dict[str, Any], *, topic: str,
                 group_id: str, client_id: str):
        self.state = state
        self.topic = topic
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tracker = SequenceTracker()
        self._awaiting_first: set[tuple[str, int]] = set()

        conf = dict(config)
        conf.update({
            "group.id": group_id,
            "client.id": client_id,
            "error_cb": self._on_error,
            "stats_cb": self._on_stats,
        })
        self._consumer = Consumer(conf)

    # -------------------------------------------------------------- lifecycle

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="consumer-poll", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        # Bounded: with Kafka unreachable, close() can block for a long time
        # while it tries to leave the group. The poll thread is a daemon, so the
        # process exits even if it's still inside close().
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    # ------------------------------------------------------------------- loop

    def _loop(self) -> None:
        self._consumer.subscribe(
            [self.topic],
            on_assign=self._on_assign,
            on_revoke=self._on_revoke,
            on_lost=self._on_lost,
        )
        try:
            while not self._stop.is_set():
                # poll() also serves error_cb, stats_cb and rebalance callbacks.
                msg = self._consumer.poll(0.5)
                if msg is None:
                    continue
                if msg.error():
                    err = msg.error()
                    if err.code() != KafkaError._PARTITION_EOF:
                        self.state.on_kafka_error(err.name(), err.str(), err.fatal())
                    continue
                self._handle(msg)
        finally:
            # May block briefly if Kafka is unreachable (leave group / commit).
            self._consumer.close()

    def _handle(self, msg) -> None:
        tp = (msg.topic(), msg.partition())
        if tp in self._awaiting_first:
            self._awaiting_first.discard(tp)
            self.state.on_resume(msg.partition(), msg.offset())
        try:
            payload = json.loads(msg.value())
            producer_id = str(payload["producer_id"])
            run_id = str(payload["run_id"])
            seq = int(payload["seq"])
        except (TypeError, ValueError, KeyError):
            self.state.add_timeline(
                "info", f"Skipped a message that isn't from a demo producer (offset {msg.offset()})")
            return
        verdict, missing = self._tracker.observe(producer_id, run_id, msg.partition(), seq)
        self.state.on_consumed(
            producer_id=producer_id, seq=seq, verdict=verdict, missing=missing,
            partition=msg.partition(), offset=msg.offset(),
        )

    # -------------------------------------------------------------- callbacks

    def _on_assign(self, consumer, partitions) -> None:
        # Not calling consumer.assign() here: the Python client applies the
        # assignment itself after this callback returns.
        self._awaiting_first.update((p.topic, p.partition) for p in partitions)
        self.state.on_assignment("assigned", [p.partition for p in partitions])

    def _on_revoke(self, consumer, partitions) -> None:
        self.state.on_assignment("revoked", [p.partition for p in partitions])

    def _on_lost(self, consumer, partitions) -> None:
        self.state.on_assignment("lost", [p.partition for p in partitions])

    def _on_error(self, err) -> None:
        self.state.on_kafka_error(err.name(), err.str(), err.fatal())

    def _on_stats(self, stats_json: str) -> None:
        self.state.on_stats(json.loads(stats_json))
