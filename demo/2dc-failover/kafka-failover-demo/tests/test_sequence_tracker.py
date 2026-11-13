"""Unit tests for consumer.SequenceTracker. Needs the confluent-kafka package
installed (consumer.py imports it) but no broker."""

from consumer import SequenceTracker


def test_first_message_from_a_run():
    tracker = SequenceTracker()
    assert tracker.observe("p", "run1", 0, 42) == ("first", 0)


def test_in_order():
    tracker = SequenceTracker()
    tracker.observe("p", "run1", 0, 1)
    assert tracker.observe("p", "run1", 0, 2) == ("ok", 0)
    assert tracker.observe("p", "run1", 0, 3) == ("ok", 0)


def test_gap_reports_missing_count_and_moves_on():
    tracker = SequenceTracker()
    tracker.observe("p", "run1", 0, 1)
    assert tracker.observe("p", "run1", 0, 5) == ("gap", 3)
    assert tracker.observe("p", "run1", 0, 6) == ("ok", 0)


def test_repeat_and_replay_are_duplicates():
    tracker = SequenceTracker()
    for seq in (1, 2, 3):
        tracker.observe("p", "run1", 0, seq)
    assert tracker.observe("p", "run1", 0, 3) == ("duplicate", 0)
    assert tracker.observe("p", "run1", 0, 2) == ("duplicate", 0)
    # A replay doesn't move the high-water mark back.
    assert tracker.observe("p", "run1", 0, 4) == ("ok", 0)


def test_producers_and_runs_are_tracked_separately():
    tracker = SequenceTracker()
    tracker.observe("p1", "run1", 0, 10)
    assert tracker.observe("p2", "run1", 0, 1) == ("first", 0)
    # A restarted producer (new run_id) starts over without looking like a replay.
    assert tracker.observe("p1", "run2", 0, 1) == ("first", 0)
    assert tracker.observe("p1", "run1", 0, 11) == ("ok", 0)
    assert tracker.observe("p1", "run2", 0, 2) == ("ok", 0)


def test_partitions_are_tracked_separately():
    """Each partition carries its own sequence, so interleaved partitions
    with the same seq numbers are neither gaps nor duplicates."""
    tracker = SequenceTracker()
    for seq in (1, 2, 3):
        for partition in range(6):
            expected = "first" if seq == 1 else "ok"
            assert tracker.observe("p", "run1", partition, seq) == (expected, 0)
    # A gap on one partition doesn't affect the others.
    assert tracker.observe("p", "run1", 2, 6) == ("gap", 2)
    assert tracker.observe("p", "run1", 3, 4) == ("ok", 0)
