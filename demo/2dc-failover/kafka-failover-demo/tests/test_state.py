"""Unit tests for client/state.py. No Kafka, no broker, no web server."""

from __future__ import annotations

import asyncio
import logging

import pytest

import state as state_mod
from state import MAX_MESSAGES, SUBSCRIBER_QUEUE_SIZE, DemoState, missing_stats_fields


class Clock:
    def __init__(self, start_ms: int = 1_000_000):
        self.ms = start_ms

    def __call__(self) -> int:
        return self.ms

    def advance(self, seconds: float) -> None:
        self.ms += int(seconds * 1000)


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(state_mod, "now_ms", c)
    return c


@pytest.fixture
def loop():
    lp = asyncio.new_event_loop()
    yield lp
    lp.close()


def make_state(role: str = "producer", **kwargs) -> DemoState:
    return DemoState(client_id=f"{role}-test", role=role, profile="tuned", topic="orders",
                     settings={}, **kwargs)


def drain(loop: asyncio.AbstractEventLoop) -> None:
    """Run every callback already handed to the loop with call_soon_threadsafe."""
    loop.run_until_complete(asyncio.sleep(0))


def queued(queue: asyncio.Queue) -> list[tuple[int, dict]]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def kinds(st: DemoState) -> list[str]:
    return [entry["kind"] for entry in st.timeline]


def broker(state: str = "UP", connects: int = 1, source: str = "learned", nodeid: int = 1) -> dict:
    return {"state": state, "connects": connects, "source": source, "nodeid": nodeid}


def stats(brokers: dict | None = None, **extra) -> dict:
    return {"brokers": brokers or {}, "msg_cnt": 0, "msg_max": 100_000, **extra}


# ------------------------------------------------------------ outage state machine


def test_starts_connecting_then_connects(clock):
    st = make_state()
    assert st.connection["state"] == "connecting"

    clock.advance(2)
    st.on_probe_ok("cluster-a", 4)

    conn = st.connection
    assert conn["state"] == "connected"
    assert conn["since"] == clock.ms
    assert conn["outage_started"] is None
    assert conn["last_outage_ms"] is None
    assert conn["probe_latency_ms"] == 4
    assert kinds(st) == ["connected", "cluster"]


def test_outage_and_recovery(clock):
    st = make_state()
    st.on_probe_ok("cluster-a", 3)

    clock.advance(1)
    started = clock.ms
    st.on_probe_fail("Local: Timed out")
    conn = st.connection
    assert conn["state"] == "retrying"
    assert conn["outage_started"] == started
    assert conn["attempts"] == 0
    assert conn["last_error"] == "Local: Timed out"
    assert conn["probe_latency_ms"] is None
    assert kinds(st)[-1] == "outage"
    assert st.timeline[-1]["text"].startswith("Lost connection to Kafka")

    # Repeated failures during the same outage don't add timeline entries.
    before = len(st.timeline)
    for _ in range(5):
        clock.advance(1)
        st.on_probe_fail("Local: Timed out")
    assert len(st.timeline) == before
    assert st.connection["outage_started"] == started

    clock.advance(15)
    st.on_probe_ok("cluster-a", 5)
    conn = st.connection
    assert conn["state"] == "connected"
    assert conn["outage_started"] is None
    assert conn["last_outage_ms"] == 20_000
    assert conn["last_error"] is None
    assert st.timeline[-1] == {"ts": clock.ms, "kind": "recovered", "text": "Reconnected after 20.0 s"}


def test_unreachable_at_startup_is_not_called_a_lost_connection(clock):
    st = make_state()
    st.on_probe_fail("Connection refused")
    assert st.connection["state"] == "retrying"
    assert st.timeline[-1]["text"].startswith("Can't reach Kafka yet")


def test_all_brokers_down_error_starts_outage_before_probe_notices(clock):
    st = make_state()
    st.on_probe_ok("cluster-a", 3)

    st.on_kafka_error("_TRANSPORT", "broker:9092/1: Disconnected", False)
    assert st.connection["state"] == "connected"
    assert st.connection["last_error"] == "broker:9092/1: Disconnected"

    st.on_kafka_error("_ALL_BROKERS_DOWN", "1/1 brokers are down", False)
    assert st.connection["state"] == "retrying"


def test_fatal_error_goes_on_timeline(clock):
    st = make_state()
    st.on_kafka_error("_FENCED", "Producer fenced", True)
    assert st.timeline[-1]["kind"] == "fatal"
    assert st.connection["state"] == "connecting"


def test_cluster_change_is_announced(clock):
    st = make_state()
    st.on_probe_ok("cluster-a", 3)
    st.on_probe_ok("cluster-a", 3)
    assert kinds(st).count("cluster") == 1

    st.on_probe_fail("down")
    st.on_probe_ok("cluster-b", 3)
    assert st.connection["cluster_id"] == "cluster-b"
    assert st.timeline[-1] == {"ts": clock.ms, "kind": "cluster",
                               "text": "Cluster changed from cluster-a to cluster-b"}


def test_topic_problem_is_reported_once_and_cleared(clock):
    st = make_state()
    st.on_probe_ok("cluster-a", 3, topic_problem="Topic orders doesn't exist")
    assert st.connection["state"] == "connected"
    assert st.connection["topic_problem"] == "Topic orders doesn't exist"
    assert kinds(st) == ["connected", "topic", "cluster"]

    st.on_probe_ok("cluster-a", 3, topic_problem="Topic orders doesn't exist")
    assert kinds(st).count("topic") == 1

    st.on_probe_ok("cluster-a", 3)
    assert st.connection["topic_problem"] is None
    assert st.timeline[-1] == {"ts": clock.ms, "kind": "info", "text": "Topic orders is available"}


def test_topic_problem_survives_an_outage(clock):
    """A failed probe says nothing about the topic, so the last answer stands."""
    st = make_state()
    st.on_probe_ok("cluster-a", 3, topic_problem="Topic orders doesn't exist")
    st.on_probe_fail("down")
    assert st.connection["topic_problem"] == "Topic orders doesn't exist"


def test_topic_problem_change_reaches_subscribers(clock, loop):
    st = make_state()
    st.on_probe_ok("cluster-a", 3)
    st.attach_loop(loop)
    queue = st.subscribe()
    st.on_probe_ok("cluster-a", 3, topic_problem="Topic orders: Broker: Topic authorization failed")
    drain(loop)
    connection_events = [env["data"] for _, env in queued(queue) if env["type"] == "connection"]
    assert connection_events[-1]["topic_problem"] == "Topic orders: Broker: Topic authorization failed"


def test_attempts_count_largest_increase_on_one_broker(clock):
    st = make_state()
    st.on_stats(stats({"broker:9092/1": broker(connects=3),
                       "GroupCoordinator": broker(connects=1, source="logical", nodeid=-1)}))
    st.on_probe_ok("cluster-a", 3)
    st.on_probe_fail("down")

    st.on_stats(stats({"broker:9092/1": broker("CONNECT", connects=7),
                       "GroupCoordinator": broker("CONNECT", connects=3, source="logical", nodeid=-1)}))
    # 4 more attempts on the broker, 2 on the coordinator: 4, not 6.
    assert st.connection["attempts"] == 4


def test_attempts_include_broker_first_seen_during_outage(clock):
    st = make_state()
    st.on_stats(stats({"broker:9092/1": broker(connects=1)}))
    st.on_probe_fail("down")
    st.on_stats(stats({"broker:9092/1": broker("DOWN", connects=2),
                       "broker:9092/bootstrap": broker("DOWN", connects=5, source="configured", nodeid=-1)}))
    assert st.connection["attempts"] == 5


def test_attempts_reset_for_each_outage(clock):
    st = make_state()
    st.on_stats(stats({"b": broker(connects=1)}))
    st.on_probe_fail("down")
    st.on_stats(stats({"b": broker("DOWN", connects=9)}))
    assert st.connection["attempts"] == 8

    st.on_probe_ok("cluster-a", 3)
    st.on_stats(stats({"b": broker(connects=10)}))
    st.on_probe_fail("down")
    assert st.connection["attempts"] == 0
    st.on_stats(stats({"b": broker("DOWN", connects=12)}))
    assert st.connection["attempts"] == 2


def test_attempts_not_updated_while_connected(clock):
    st = make_state()
    st.on_probe_ok("cluster-a", 3)
    st.on_stats(stats({"b": broker(connects=50)}))
    assert st.connection["attempts"] == 0


def test_internal_broker_is_ignored(clock):
    st = make_state()
    st.on_stats(stats({
        ":0/internal": broker("INIT", connects=0, source="internal", nodeid=-1),
        "broker:9092/1": broker("UP", connects=1),
    }))
    assert list(st.brokers) == ["broker:9092/1"]
    assert st.brokers["broker:9092/1"] == {"state": "UP", "nodeid": 1, "source": "learned"}


def test_stats_fill_buffer_and_group(clock):
    producer = make_state("producer")
    producer.on_stats(stats(msg_cnt=12, msg_max=2000))
    assert producer.buffer == {"msg_cnt": 12, "msg_max": 2000}

    consumer = make_state("consumer")
    consumer.on_stats(stats(cgrp={"state": "up", "join_state": "steady",
                                  "assignment_size": 3, "rebalance_cnt": 1}))
    assert consumer.group == {"state": "up", "join_state": "steady",
                              "assignment_size": 3, "rebalance_cnt": 1}
    assert consumer.buffer == {"msg_cnt": 0, "msg_max": None}


# ------------------------------------------------------------ producer messages


def test_delivery_before_queued_keeps_delivered_state(clock):
    st = make_state()
    st.on_delivered("p-r-1", 1, partition=2, offset=40)
    metrics = st._metrics_view()
    assert metrics["counters"]["pending"] == 0   # never negative mid-race

    st.on_queued("p-r-1", 1)
    message = st.messages["p-r-1"]
    assert message["state"] == "acked"
    assert (message["partition"], message["offset"]) == (2, 40)
    counters = st._metrics_view()["counters"]
    assert (counters["queued"], counters["acked"], counters["pending"]) == (1, 1, 0)


def test_failure_before_queued_keeps_failed_state(clock):
    st = make_state()
    st.on_delivered("p-r-1", 1, error="Local: Message timed out")
    st.on_queued("p-r-1", 1)
    assert st.messages["p-r-1"]["state"] == "failed"
    assert st.messages["p-r-1"]["error"] == "Local: Message timed out"


def test_normal_delivery_flow(clock):
    st = make_state()
    st.on_queued("p-r-1", 1)
    st.on_queued("p-r-2", 2)
    assert st._metrics_view()["counters"]["pending"] == 2
    st.on_delivered("p-r-1", 1, partition=0, offset=0)
    st.on_delivered("p-r-2", 2, error="Local: Message timed out")
    counters = st._metrics_view()["counters"]
    assert (counters["acked"], counters["failed"], counters["pending"]) == (1, 1, 0)
    assert [m["state"] for m in st.messages.values()] == ["acked", "failed"]


def test_failure_and_backpressure_timeline_is_one_entry_per_episode(clock):
    st = make_state()
    for seq in range(1, 6):
        st.on_queued(f"m{seq}", seq)
        st.on_delivered(f"m{seq}", seq, error="Local: Message timed out")
    assert kinds(st).count("failed") == 1
    st.on_delivered("m6", 6, partition=0, offset=1)
    st.on_delivered("m7", 7, error="Local: Message timed out")
    assert kinds(st).count("failed") == 2

    for _ in range(5):
        st.on_buffer_full()
    assert kinds(st).count("backpressure") == 1
    assert st.counters["buffer_full"] == 5
    st.on_queued("m8", 8)
    st.on_buffer_full()
    assert kinds(st).count("backpressure") == 2


def test_tiles_are_evicted_oldest_first(clock):
    st = make_state()
    total = MAX_MESSAGES + 25
    for seq in range(1, total + 1):
        st.on_queued(f"m{seq}", seq)
    assert len(st.messages) == MAX_MESSAGES
    assert next(iter(st.messages)) == "m26"
    assert "m25" not in st.messages
    assert st._dirty <= set(st.messages)


def test_late_delivery_for_evicted_tile_updates_counters_only(clock):
    st = make_state()
    for seq in range(1, MAX_MESSAGES + 11):
        st.on_queued(f"m{seq}", seq)
    st.on_delivered("m3", 3, partition=0, offset=3)
    assert "m3" not in st.messages
    assert len(st.messages) == MAX_MESSAGES
    assert st.counters["acked"] == 1


def test_evicted_tile_check_is_per_partition(clock):
    """Producers number messages per partition, so "already scrolled out of the
    UI" must compare seqs within one partition, not across all of them."""
    st = make_state()
    total = MAX_MESSAGES + 10
    for n in range(total):
        partition, seq = n % 6, n // 6 + 1
        st.on_queued(f"m{n}", seq, partition=partition)
    # Evicted: n = 0..9, i.e. seq 1 on partitions 0-5 and seq 2 on partitions 0-3.
    assert "m0" not in st.messages and "m10" in st.messages

    st.on_delivered("m0", 1, partition=0, offset=0)
    assert "m0" not in st.messages   # late report for an evicted tile: counters only
    assert st.counters["acked"] == 1

    # A report that beats its on_queued (the race) on partition 4, seq 2: higher
    # than anything evicted from partition 4, so it gets a tile even though
    # partition 0 already lost its seq 2.
    st.on_delivered("race", 2, partition=4, offset=7)
    assert st.messages["race"]["state"] == "acked"
    assert st.messages["race"]["partition"] == 4


def test_failure_timeline_names_the_partition(clock):
    st = make_state()
    st.on_queued("m1", 1, partition=3)
    st.on_delivered("m1", 1, partition=3, error="Broker: Invalid request")
    assert st.timeline[-1]["text"] == "Message 1 on partition 3 was not delivered: Broker: Invalid request"


def test_flush_sends_only_dirty_tiles_still_present(clock, loop):
    st = make_state()
    st.attach_loop(loop)
    queue = st.subscribe()
    for seq in range(1, MAX_MESSAGES + 51):
        st.on_queued(f"m{seq}", seq)
    st.flush()
    drain(loop)
    events = [env for _, env in queued(queue)]
    updates = [env for env in events if env["type"] == "messages"][0]["data"]["updates"]
    ids = {m["id"] for m in updates}
    assert len(ids) == MAX_MESSAGES
    assert "m1" not in ids
    assert events[-1]["type"] == "metrics"

    st.flush()
    drain(loop)
    assert [env["type"] for _, env in queued(queue)] == ["metrics"]


# ------------------------------------------------------------ consumer


def test_consumer_counters_and_streaks(clock):
    st = make_state("consumer")
    st.on_consumed(producer_id="p", seq=1, verdict="first", missing=0, partition=0, offset=0)
    st.on_consumed(producer_id="p", seq=2, verdict="ok", missing=0, partition=0, offset=1)
    st.on_consumed(producer_id="p", seq=6, verdict="gap", missing=3, partition=0, offset=2)
    st.on_consumed(producer_id="p", seq=4, verdict="duplicate", missing=0, partition=0, offset=3)
    st.on_consumed(producer_id="p", seq=5, verdict="duplicate", missing=0, partition=0, offset=4)
    st.on_consumed(producer_id="p", seq=7, verdict="ok", missing=0, partition=0, offset=5)
    st.on_consumed(producer_id="p", seq=7, verdict="duplicate", missing=0, partition=0, offset=6)

    c = st.counters
    assert (c["consumed"], c["gaps"], c["missing"], c["duplicates"]) == (7, 1, 3, 3)
    assert kinds(st).count("gap") == 1
    assert kinds(st).count("duplicate") == 2
    # Every delivery gets its own tile, including redeliveries of the same seq.
    assert len(st.messages) == 7


def test_assignment_counts_rebalances(clock):
    st = make_state("consumer")
    st.on_assignment("assigned", [2, 0, 1])
    st.on_assignment("revoked", [0, 1, 2])
    st.on_assignment("assigned", [])
    assert st.counters["rebalances"] == 2
    assert st.timeline[0]["text"] == "Partitions assigned: 0, 1, 2"
    assert st.timeline[-1]["text"] == "Partitions assigned: none"


# ------------------------------------------------------------ fan-out and snapshots


def test_events_reach_subscribers_in_seq_order(clock, loop):
    st = make_state()
    st.attach_loop(loop)
    queue = st.subscribe()
    st.add_timeline("info", "one")
    st.on_probe_ok("cluster-a", 3)
    st.flush()
    drain(loop)

    items = queued(queue)
    seqs = [seq for seq, _ in items]
    assert seqs == sorted(seqs) == list(range(1, len(items) + 1))
    assert [env["type"] for _, env in items] == [
        "timeline", "timeline", "connection", "timeline", "connection", "metrics"]
    assert all(env["client_id"] == "producer-test" for _, env in items)


def test_unsubscribed_queue_gets_nothing(clock, loop):
    st = make_state()
    st.attach_loop(loop)
    queue = st.subscribe()
    st.unsubscribe(queue)
    st.add_timeline("info", "hello")
    drain(loop)
    assert queue.empty()


def test_no_loop_attached_is_harmless(clock):
    st = make_state()
    st.add_timeline("info", "before the app starts")
    st.flush()
    assert st.snapshot_with_seq()[0] == 0


def test_snapshot_seq_marks_events_already_included(clock, loop):
    """An event emitted before the snapshot but fanned out after it must be
    recognisable as already included, so the SSE stream can skip it."""
    st = make_state()
    st.attach_loop(loop)
    queue = st.subscribe()
    st.add_timeline("info", "emitted, not yet fanned out")
    floor, snap = st.snapshot_with_seq()
    assert snap["timeline"][-1]["text"] == "emitted, not yet fanned out"

    st.add_timeline("info", "after the snapshot")
    drain(loop)
    items = queued(queue)
    fresh = [env["data"]["text"] for seq, env in items if seq > floor]
    assert fresh == ["after the snapshot"]


def test_subscriber_overflow_resyncs_with_snapshot(clock, loop):
    st = make_state()
    st.attach_loop(loop)
    slow = st.subscribe()
    extra = 5
    for i in range(SUBSCRIBER_QUEUE_SIZE + extra):
        st.add_timeline("info", f"entry {i}")
    last_seq = st.snapshot_with_seq()[0]
    drain(loop)

    items = queued(slow)
    first_seq, first = items[0]
    # The backlog was replaced by one snapshot ...
    assert first["type"] == "snapshot"
    assert first_seq == last_seq
    assert first["data"]["timeline"][-1]["text"] == f"entry {SUBSCRIBER_QUEUE_SIZE + extra - 1}"
    # ... and every event queued after it is already reflected in it.
    assert all(seq <= first_seq for seq, _ in items[1:])
    assert len(items) < SUBSCRIBER_QUEUE_SIZE

    # Afterwards the subscriber receives new events normally.
    st.add_timeline("info", "fresh")
    drain(loop)
    seq, env = queued(slow)[-1]
    assert seq > first_seq and env["data"]["text"] == "fresh"


def test_overflow_of_one_subscriber_does_not_affect_another(clock, loop):
    st = make_state()
    st.attach_loop(loop)
    slow = st.subscribe()
    fast = st.subscribe()
    for i in range(SUBSCRIBER_QUEUE_SIZE - 1):
        st.add_timeline("info", f"entry {i}")
    drain(loop)
    queued(fast)   # this subscriber keeps up
    for i in range(3):
        st.add_timeline("info", f"more {i}")
    drain(loop)

    assert queued(slow)[0][1]["type"] == "snapshot"
    assert [env["type"] for _, env in queued(fast)] == ["timeline"] * 3


def test_snapshot_shape(clock):
    st = make_state()
    snap = st.snapshot()
    assert set(snap) == {"client", "connection", "metrics", "messages", "timeline", "server_time"}
    assert set(snap["metrics"]) == {"counters", "buffer", "brokers", "group", "rate", "connection"}
    assert set(snap["connection"]) == {
        "state", "since", "outage_started", "last_outage_ms", "attempts",
        "last_error", "probe_latency_ms", "cluster_id", "topic_problem"}
    assert "pending" in snap["metrics"]["counters"]


# ------------------------------------------------------------ DEBUG_STATS


def real_producer_stats() -> dict:
    """Trimmed librdkafka producer statistics payload (STATISTICS.md shape)."""
    return {
        "name": "producer-tuned#producer-1", "client_id": "producer-tuned", "type": "producer",
        "ts": 1, "time": 1, "msg_cnt": 3, "msg_size": 300, "msg_max": 100000,
        "brokers": {
            ":0/internal": {"name": ":0/internal", "nodeid": -1, "source": "internal",
                            "state": "INIT", "connects": 0},
            "broker:9092/1": {"name": "broker:9092/1", "nodeid": 1, "source": "learned",
                              "state": "UP", "connects": 1},
        },
    }


def test_missing_stats_fields():
    payload = real_producer_stats()
    assert missing_stats_fields(payload, "producer") == []
    assert missing_stats_fields(payload, "consumer") == ["cgrp.state", "cgrp.join_state"]

    payload["cgrp"] = {"state": "up", "join_state": "steady"}
    assert missing_stats_fields(payload, "consumer") == []

    del payload["brokers"]["broker:9092/1"]["connects"]
    del payload["msg_max"]
    assert missing_stats_fields(payload, "producer") == ["brokers.*.connects", "msg_max"]


def test_missing_stats_fields_with_only_internal_broker():
    payload = real_producer_stats()
    del payload["brokers"]["broker:9092/1"]
    assert missing_stats_fields(payload, "producer") == ["brokers.*.state", "brokers.*.connects"]


def test_debug_stats_logs_first_and_first_up_payload_once(clock, caplog):
    caplog.set_level(logging.INFO, logger="demo.stats")
    st = make_state(debug_stats=True)
    connecting = real_producer_stats()
    connecting["brokers"]["broker:9092/1"]["state"] = "CONNECT"

    st.on_stats(connecting)
    st.on_stats(connecting)
    st.on_stats(real_producer_stats())
    st.on_stats(real_producer_stats())

    payload_lines = [r.getMessage() for r in caplog.records if "stats payload:" in r.getMessage()]
    assert len(payload_lines) == 2
    assert "first stats payload" in payload_lines[0]
    assert "first with a broker UP" in payload_lines[1]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_debug_stats_warns_about_missing_fields(clock, caplog):
    caplog.set_level(logging.INFO, logger="demo.stats")
    st = make_state("consumer", debug_stats=True)
    st.on_stats(real_producer_stats())
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "cgrp.state" in warnings[0] and "cgrp.join_state" in warnings[0]


def test_debug_stats_off_logs_nothing(clock, caplog):
    caplog.set_level(logging.INFO, logger="demo.stats")
    make_state().on_stats(real_producer_stats())
    assert not caplog.records
