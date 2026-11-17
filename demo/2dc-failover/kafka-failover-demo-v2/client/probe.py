"""Connectivity probe: one metadata request per second through the gateway.

This is the source of truth for connected vs retrying. It is more predictable
than inferring state from error callbacks, and the metadata response carries
the cluster ID, which powers the "which cluster am I on" indicator. It also
reports when the demo topic is missing or not readable, which otherwise shows
up only as a producer that never delivers or a consumer that never receives.

Open question (PLAN.md, Phase 3): whether Confluent Gateway passes the backing
cluster's ID through unchanged. If it doesn't, the ID won't change on
switchover and a fallback is needed.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient

from state import DemoState


def _error_text(exc: KafkaException) -> str:
    err = exc.args[0] if exc.args else None
    return err.str() if hasattr(err, "str") else str(exc)


class Probe:
    def __init__(self, state: DemoState, config: dict[str, Any], *, topic: str,
                 min_partitions: int | None = None,
                 interval_s: float = 1.0, timeout_s: float = 1.5):
        self.state = state
        self.topic = topic
        self.min_partitions = min_partitions   # producers write to partitions 0..N-1
        self.interval_s = interval_s
        self.timeout_s = timeout_s
        self._admin = AdminClient(dict(config))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="probe", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                # No topic argument: avoids any chance of triggering topic auto-creation.
                metadata = self._admin.list_topics(timeout=self.timeout_s)
                latency_ms = round((time.monotonic() - started) * 1000)
                self.state.on_probe_ok(metadata.cluster_id, latency_ms,
                                       topic_problem=self._topic_problem(metadata))
            except KafkaException as exc:
                self.state.on_probe_fail(_error_text(exc))
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.0, self.interval_s - elapsed))

    def _topic_problem(self, metadata) -> str | None:
        # A full metadata response leaves out topics the client may not
        # describe, so "missing" and "not authorized" can look the same.
        topic = metadata.topics.get(self.topic)
        if topic is None:
            return f"Topic {self.topic} doesn't exist, or this client isn't allowed to see it"
        if topic.error is not None:
            return f"Topic {self.topic}: {topic.error.str()}"
        if self.min_partitions and len(topic.partitions) < self.min_partitions:
            return (f"Topic {self.topic} has {len(topic.partitions)} partitions, but this producer "
                    f"writes to {self.min_partitions} (PARTITIONS)")
        return None
