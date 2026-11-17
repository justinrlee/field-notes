"""Consume Avro topics for a while and print per-topic counts plus a few sample rows.

Usage (from repo root, after `terraform apply` wrote .env):
  ./venv/bin/python scripts/verify_topics.py player_combat_events player_activity player_profiles
  ./venv/bin/python scripts/verify_topics.py --from-beginning --seconds 20 player_profiles
  ./venv/bin/python scripts/verify_topics.py --samples 5 --filter player_id=demo-whale player_profiles

Default is `latest` offsets for --seconds (30) so it shows what is flowing now. Use
--from-beginning to read what is already in the topic (e.g. the compacted profiles).
For upsert topics it also prints the number of DISTINCT message keys seen.
"""

import argparse
import collections
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "producer"))
import kafka_io  # noqa: E402  (loads .env and exposes connection settings)

from confluent_kafka import Consumer  # noqa: E402
from confluent_kafka.schema_registry import SchemaRegistryClient  # noqa: E402
from confluent_kafka.schema_registry.avro import AvroDeserializer  # noqa: E402
from confluent_kafka.serialization import MessageField, SerializationContext  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topics", nargs="+")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--from-beginning", action="store_true")
    ap.add_argument("--samples", type=int, default=2, help="sample rows to print per topic")
    ap.add_argument("--filter", default=None, help="only count/sample rows where field=value")
    args = ap.parse_args()

    field, _, wanted = (args.filter or "").partition("=")

    consumer = Consumer({
        "bootstrap.servers": kafka_io.BOOTSTRAP,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": kafka_io.KAFKA_API_KEY,
        "sasl.password": kafka_io.KAFKA_API_SECRET,
        "group.id": f"verify-{time.time()}",
        "auto.offset.reset": "earliest" if args.from_beginning else "latest",
        # Flink-written topics are transactional; do not wait for the commit (see AGENTS.md).
        "isolation.level": "read_uncommitted",
    })
    consumer.subscribe(args.topics)
    sr = SchemaRegistryClient({
        "url": kafka_io.SR_URL,
        "basic.auth.user.info": f"{kafka_io.SR_API_KEY}:{kafka_io.SR_API_SECRET}",
    })
    deserialize = AvroDeserializer(sr)

    counts = collections.Counter()
    keys = collections.defaultdict(set)
    samples = collections.defaultdict(list)
    by_type = collections.defaultdict(collections.Counter)
    end = time.time() + args.seconds
    while time.time() < end:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        row = deserialize(msg.value(), SerializationContext(msg.topic(), MessageField.VALUE))
        if row is None:
            continue
        if field and str(row.get(field)) != wanted:
            continue
        counts[msg.topic()] += 1
        if msg.key() is not None:
            keys[msg.topic()].add(msg.key())
        for type_field in ("event_type", "activity_type"):
            if type_field in row:
                by_type[msg.topic()][row[type_field]] += 1
        if len(samples[msg.topic()]) < args.samples:
            samples[msg.topic()].append(row)
    consumer.close()

    for topic in args.topics:
        print(f"\n== {topic}: {counts[topic]} messages, {len(keys[topic])} distinct keys")
        if by_type[topic]:
            print("   by type:", dict(by_type[topic]))
        for row in samples[topic]:
            print("   ", row)


if __name__ == "__main__":
    main()
