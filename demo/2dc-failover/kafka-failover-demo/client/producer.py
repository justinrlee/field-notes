"""Producer role: sends sequence-numbered messages at an adjustable rate.

Messages go to the topic's partitions in turn (0, 1, ..., PARTITIONS-1, 0, ...),
chosen explicitly rather than by key, so every partition and every consumer in
the group gets traffic.

Each message carries (producer_id, run_id, partition, seq). seq counts per
partition: it starts at 1 and increases by one per message that librdkafka
accepted into its queue for that partition. Kafka keeps order within a
partition, so the consumer can detect gaps (lost messages) and duplicates
exactly. run_id changes on every process start, so a restarted producer begins
fresh sequences instead of looking like a huge duplicate run.

A message is PENDING from the moment produce() accepts it until its delivery
report arrives. During a gateway outage, messages stay pending in librdkafka's
queue and are sent once the connection returns, unless message.timeout.ms
expires first (that's what the "fragile" profile demonstrates).
"""

from __future__ import annotations

import functools
import json
import threading
import time
import uuid
from typing import Any

from confluent_kafka import KafkaException, Producer

from state import DemoState

MAX_RATE = 200.0


class DemoProducer:
    def __init__(self, state: DemoState, config: dict[str, Any], *, topic: str,
                 producer_id: str, rate: float, partitions: int):
        self.state = state
        self.topic = topic
        self.producer_id = producer_id
        self.run_id = uuid.uuid4().hex[:8]
        self._rate = 0.0
        self.partitions = partitions
        self._next_partition = 0
        self._next_seq = [1] * partitions   # per partition
        self._seq_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

        conf = dict(config)
        conf.update({
            "client.id": producer_id,
            "error_cb": self._on_error,
            "stats_cb": self._on_stats,
        })
        self._producer = Producer(conf)
        self.set_rate(rate, announce=False)

    # -------------------------------------------------------------- lifecycle

    def start(self) -> None:
        for target, name in ((self._poll_loop, "poll"), (self._generate_loop, "generate")):
            thread = threading.Thread(target=target, name=f"producer-{name}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout)
        # Bounded: during an outage this returns with messages still queued.
        self._producer.flush(timeout)

    # ---------------------------------------------------------------- control

    def set_rate(self, rate: float, *, announce: bool = True) -> float:
        self._rate = max(0.0, min(MAX_RATE, float(rate)))
        self.state.set_rate(self._rate, announce=announce)
        return self._rate

    def send_one(self) -> bool:
        """Returns False when the local queue is full (backpressure)."""
        # The seq lock covers produce() and on_queued() so seq numbers enter the
        # queue, and the UI, strictly in order. The partition and its seq only
        # advance on success, so a refused send never creates a false gap.
        with self._seq_lock:
            partition = self._next_partition
            seq = self._next_seq[partition]
            msg_id = f"{self.producer_id}-{self.run_id}-p{partition}-{seq}"
            value = json.dumps({
                "producer_id": self.producer_id,
                "run_id": self.run_id,
                "partition": partition,
                "seq": seq,
                "msg_id": msg_id,
                "produced_at": time.time(),
            })
            try:
                self._producer.produce(
                    self.topic,
                    key=self.producer_id,   # a label only: `partition` decides placement
                    partition=partition,
                    value=value,
                    on_delivery=functools.partial(self._on_delivery, msg_id, seq, partition),
                )
            except BufferError:
                self.state.on_buffer_full()
                return False
            except KafkaException as exc:
                # e.g. message too large; not connectivity-related.
                self.state.on_kafka_error("produce", str(exc), False)
                return False
            self._next_seq[partition] += 1
            self._next_partition = (partition + 1) % self.partitions
            self.state.on_queued(msg_id, seq, partition=partition)
        return True

    def burst(self, count: int) -> int:
        sent = 0
        for _ in range(count):
            if not self.send_one():
                break
            sent += 1
        return sent

    # ------------------------------------------------------------------ loops

    def _poll_loop(self) -> None:
        # Serves delivery reports, error_cb and stats_cb on this thread.
        while not self._stop.is_set():
            self._producer.poll(0.1)

    def _generate_loop(self) -> None:
        next_at = time.monotonic()
        while not self._stop.is_set():
            rate = self._rate
            if rate <= 0:
                self._stop.wait(0.2)
                next_at = time.monotonic()
                continue
            self.send_one()
            next_at += 1.0 / rate
            delay = next_at - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_at = time.monotonic()  # fell behind; don't burst to catch up

    # -------------------------------------------------------------- callbacks

    def _on_delivery(self, msg_id: str, seq: int, partition: int, err, msg) -> None:
        if err is not None:
            self.state.on_delivered(msg_id, seq, partition=partition, error=err.str())
        else:
            self.state.on_delivered(msg_id, seq, partition=partition, offset=msg.offset())

    def _on_error(self, err) -> None:
        self.state.on_kafka_error(err.name(), err.str(), err.fatal())

    def _on_stats(self, stats_json: str) -> None:
        self.state.on_stats(json.loads(stats_json))
