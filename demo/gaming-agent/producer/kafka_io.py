"""Kafka / Schema Registry plumbing shared by the generator (and, later, the trigger UI).

Config comes from the repo-root `.env` written by `terraform apply`. Serialization is Avro
against the schema Flink already registered (`use.latest.version`, no auto-register), so the
field names below must match the CREATE TABLE columns in terraform/flink.tf. Physical columns
only: the computed `event_time` columns are not in the value schema.
"""

import os
import time

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext, StringSerializer
from dotenv import load_dotenv

# Home-directory defaults first, then the project root (takes precedence).
load_dotenv(os.path.expanduser("~/.env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

BOOTSTRAP = os.environ["BOOTSTRAP_SERVERS"]
KAFKA_API_KEY = os.environ["KAFKA_API_KEY"]
KAFKA_API_SECRET = os.environ["KAFKA_API_SECRET"]
SR_URL = os.environ["SCHEMA_REGISTRY_URL"]
SR_API_KEY = os.environ["SCHEMA_REGISTRY_API_KEY"]
SR_API_SECRET = os.environ["SCHEMA_REGISTRY_API_SECRET"]

# Topic names match the Flink tables created by Terraform.
TOPIC_COMBAT = "player_combat_events"
TOPIC_ACTIVITY = "player_activity"
TOPIC_PROFILES = "player_profiles"

# Record name "<topic>_value", namespace org.apache.flink.avro.generated.record, field order
# matching the CREATE TABLE column order. Nullable Flink columns are ["null", T] unions.
NAMESPACE = "org.apache.flink.avro.generated.record"

COMBAT_SCHEMA = """{
  "type": "record", "name": "player_combat_events_value", "namespace": "%s",
  "fields": [
    {"name": "event_id", "type": "string"},
    {"name": "game_id", "type": "string"},
    {"name": "player_id", "type": "string"},
    {"name": "match_id", "type": "string"},
    {"name": "event_type", "type": "string"},
    {"name": "damage_amount", "type": "int"},
    {"name": "source_id", "type": "string"},
    {"name": "source_type", "type": "string"},
    {"name": "zone_id", "type": "string"},
    {"name": "player_level", "type": "int"},
    {"name": "timestamp", "type": "long"}
  ]
}""" % NAMESPACE

ACTIVITY_SCHEMA = """{
  "type": "record", "name": "player_activity_value", "namespace": "%s",
  "fields": [
    {"name": "event_id", "type": "string"},
    {"name": "game_id", "type": "string"},
    {"name": "player_id", "type": "string"},
    {"name": "activity_type", "type": "string"},
    {"name": "item_id", "type": ["null", "string"], "default": null},
    {"name": "detail", "type": ["null", "string"], "default": null},
    {"name": "timestamp", "type": "long"}
  ]
}""" % NAMESPACE

PROFILE_SCHEMA = """{
  "type": "record", "name": "player_profiles_value", "namespace": "%s",
  "fields": [
    {"name": "player_id", "type": "string"},
    {"name": "game_id", "type": "string"},
    {"name": "player_class", "type": "string"},
    {"name": "level", "type": "int"},
    {"name": "tier", "type": "string"},
    {"name": "lifetime_spend", "type": "double"},
    {"name": "spend_30d", "type": "double"},
    {"name": "monthly_cap", "type": ["null", "double"], "default": null},
    {"name": "is_minor", "type": "boolean"},
    {"name": "region", "type": "string"},
    {"name": "owned_skus", "type": {"type": "array", "items": "string"}},
    {"name": "last_purchase_ts", "type": ["null", "long"], "default": null},
    {"name": "updated_at", "type": "long"}
  ]
}""" % NAMESPACE

# player_profiles has an Avro key (PRIMARY KEY `player_id`); Flink registers it under the
# `player_profiles-key` subject. The event topics have no key columns, so their keys are plain strings.
PROFILE_KEY_SCHEMA = """{
  "type": "record", "name": "player_profiles_key", "namespace": "%s",
  "fields": [
    {"name": "player_id", "type": "string"}
  ]
}""" % NAMESPACE

# Columns of the value schema for player_profiles (used to project in-memory player state).
PROFILE_FIELDS = [
    "player_id", "game_id", "player_class", "level", "tier", "lifetime_spend", "spend_30d",
    "monthly_cap", "is_minor", "region", "owned_skus", "last_purchase_ts",
]


def now_ms():
    return int(time.time() * 1000)


def delivery_report(err, msg):
    if err is not None:
        print(f"  ERROR: Message delivery failed: {err}", flush=True)


def build_serializers():
    """Returns {topic: value serializer}; the profile key serializer is built by build_key_serializers()."""
    sr = SchemaRegistryClient({
        "url": SR_URL,
        "basic.auth.user.info": f"{SR_API_KEY}:{SR_API_SECRET}",
    })
    conf = {"auto.register.schemas": False, "use.latest.version": True}
    return {
        TOPIC_COMBAT: AvroSerializer(sr, COMBAT_SCHEMA, conf=conf),
        TOPIC_ACTIVITY: AvroSerializer(sr, ACTIVITY_SCHEMA, conf=conf),
        TOPIC_PROFILES: AvroSerializer(sr, PROFILE_SCHEMA, conf=conf),
    }


def build_key_serializers():
    """Avro key serializers for topics whose Flink table has a PRIMARY KEY (just player_profiles)."""
    sr = SchemaRegistryClient({
        "url": SR_URL,
        "basic.auth.user.info": f"{SR_API_KEY}:{SR_API_SECRET}",
    })
    conf = {"auto.register.schemas": False, "use.latest.version": True}
    return {TOPIC_PROFILES: AvroSerializer(sr, PROFILE_KEY_SCHEMA, conf=conf)}


def make_producer(client_id="gaming-demo-producer"):
    return Producer({
        "bootstrap.servers": BOOTSTRAP,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": KAFKA_API_KEY,
        "sasl.password": KAFKA_API_SECRET,
        "client.id": client_id,
    })


_string_key_serializer = StringSerializer("utf_8")


def produce_event(producer, serializers, topic, event, key_serializers=None):
    """Serialize `event` (a dict matching the topic's schema) and produce it keyed by player_id.

    Keying by player_id keeps one player's events in one partition (ordering). player_profiles
    needs an Avro key ({"player_id": ...}); pass `key_serializers` from build_key_serializers().
    Every other topic uses a plain string key.
    """
    value = serializers[topic](event, SerializationContext(topic, MessageField.VALUE))
    ctx = SerializationContext(topic, MessageField.KEY)
    if key_serializers and topic in key_serializers:
        key = key_serializers[topic]({"player_id": event["player_id"]}, ctx)
    else:
        key = _string_key_serializer(event["player_id"], ctx)
    producer.produce(topic=topic, key=key, value=value, callback=delivery_report)


def produce_profile(producer, serializers, key_serializers, player):
    """Upsert a player's profile (projected from the in-memory player dict)."""
    event = {k: player[k] for k in PROFILE_FIELDS}
    event["owned_skus"] = list(event["owned_skus"])
    event["updated_at"] = now_ms()
    produce_event(producer, serializers, TOPIC_PROFILES, event, key_serializers)
