"""Generates synthetic transaction, login, and account change events.

Modes:
  (default)      - Normal user activity only, continuously
  --fraud        - Fraud scenarios only, continuously
  --single-fraud - Generate one fraud event and exit
  --both         - Normal + fraud after cycle 50 (for ARIMA baseline building)

Run this after `terraform apply` (which writes .env) and alongside the Streamlit dashboard.
"""

import argparse
import os
import random
import sys
import time
import uuid
from datetime import datetime

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext, StringSerializer
from dotenv import load_dotenv

# Load Terraform-generated connection config.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BOOTSTRAP = os.environ["BOOTSTRAP_SERVERS"]
KAFKA_API_KEY = os.environ["KAFKA_API_KEY"]
KAFKA_API_SECRET = os.environ["KAFKA_API_SECRET"]
SR_URL = os.environ["SCHEMA_REGISTRY_URL"]
SR_API_KEY = os.environ["SCHEMA_REGISTRY_API_KEY"]
SR_API_SECRET = os.environ["SCHEMA_REGISTRY_API_SECRET"]

# Topic names match the Flink tables created by Terraform.
TOPIC_TRANSACTIONS = "transactions"
TOPIC_LOGINS = "user_logins"
TOPIC_ACCOUNT_CHANGES = "account_changes"

# Avro value schemas matching the Flink-generated schemas (record name
# "<topic>_value", namespace org.apache.flink.avro.generated.record, field order
# matching the CREATE TABLE column order). The serializer uses the schema already
# registered by Flink (use.latest.version), so these are mainly documentation.
NAMESPACE = "org.apache.flink.avro.generated.record"

TRANSACTION_SCHEMA = """{
  "type": "record", "name": "transactions_value", "namespace": "%s",
  "fields": [
    {"name": "user_id", "type": "string"},
    {"name": "transaction_id", "type": "string"},
    {"name": "amount", "type": "double"},
    {"name": "merchant", "type": "string"},
    {"name": "merchant_category", "type": "string"},
    {"name": "location", "type": "string"},
    {"name": "timestamp", "type": "long"}
  ]
}""" % NAMESPACE

LOGIN_SCHEMA = """{
  "type": "record", "name": "user_logins_value", "namespace": "%s",
  "fields": [
    {"name": "user_id", "type": "string"},
    {"name": "ip_address", "type": "string"},
    {"name": "device_id", "type": "string"},
    {"name": "location", "type": "string"},
    {"name": "timestamp", "type": "long"}
  ]
}""" % NAMESPACE

ACCOUNT_CHANGE_SCHEMA = """{
  "type": "record", "name": "account_changes_value", "namespace": "%s",
  "fields": [
    {"name": "user_id", "type": "string"},
    {"name": "field_changed", "type": "string"},
    {"name": "old_value", "type": "string"},
    {"name": "new_value", "type": "string"},
    {"name": "timestamp", "type": "long"}
  ]
}""" % NAMESPACE

USERS = [f"user-{i:03d}" for i in range(0, 10)]  # Increased from 10 to 200 for ARIMA baseline
DEVICES = ["iphone-15", "pixel-8", "macbook-pro", "windows-desktop", "ipad-air"]
MERCHANTS = [
    ("Starbucks", "food_and_drink"),
    ("Amazon", "online_retail"),
    ("Walmart", "grocery"),
    ("Shell Gas", "fuel"),
    ("Netflix", "subscription"),
    ("Best Buy", "electronics"),
    ("Target", "retail"),
    ("Uber", "transportation"),
]
CITIES = [
    ("San Francisco, CA", "198.51.100.1"),
    ("New York, NY", "203.0.113.10"),
    ("Tokyo, Japan", "192.0.2.50"),
    ("London, UK", "198.51.100.99"),
    ("Chicago, IL", "203.0.113.42"),
    ("Sydney, Australia", "192.0.2.100"),
]

# User profiles for realistic spending baselines (ARIMA learns per-user patterns)
USER_PROFILES = {
    "low_spender": {
        "users": USERS[:7],  # 70% of users
        "avg_amount": 35.0,
        "std_amount": 15.0,
        "txn_per_cycle": 2,
    },
    "medium_spender": {
        "users": USERS[7:8],  # 20% of users
        "avg_amount": 150.0,
        "std_amount": 50.0,
        "txn_per_cycle": 3,
    },
    "high_spender": {
        "users": USERS[8:9],  # 9% of users - should NOT trigger anomalies
        "avg_amount": 800.0,
        "std_amount": 200.0,
        "txn_per_cycle": 5,
    },
    "fraud_target": {
        "users": USERS[9:10],  # 1% of users - normally low, so fraud is very anomalous
        "avg_amount": 40.0,
        "std_amount": 20.0,
        "txn_per_cycle": 2,
    },
}


def get_user_profile(user_id):
    """Get the spending profile for a user."""
    for profile_type, config in USER_PROFILES.items():
        if user_id in config["users"]:
            return profile_type, config
    return "low_spender", USER_PROFILES["low_spender"]


def now_ms():
    return int(time.time() * 1000)


def delivery_report(err, msg):
    if err is not None:
        print(f"  ERROR: Message delivery failed: {err}")


def build_serializers():
    sr = SchemaRegistryClient({
        "url": SR_URL,
        "basic.auth.user.info": f"{SR_API_KEY}:{SR_API_SECRET}",
    })
    # Serialize against the schema Flink already registered for each subject.
    conf = {"auto.register.schemas": False, "use.latest.version": True}
    return {
        TOPIC_TRANSACTIONS: AvroSerializer(sr, TRANSACTION_SCHEMA, conf=conf),
        TOPIC_LOGINS: AvroSerializer(sr, LOGIN_SCHEMA, conf=conf),
        TOPIC_ACCOUNT_CHANGES: AvroSerializer(sr, ACCOUNT_CHANGE_SCHEMA, conf=conf),
    }


def make_producer():
    return Producer({
        "bootstrap.servers": BOOTSTRAP,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": KAFKA_API_KEY,
        "sasl.password": KAFKA_API_SECRET,
        "client.id": "fraud-demo-producer",
    })


_key_serializer = StringSerializer("utf_8")


def produce_event(producer, serializers, topic, event):
    value = serializers[topic](event, SerializationContext(topic, MessageField.VALUE))
    key = _key_serializer(event["user_id"], SerializationContext(topic, MessageField.KEY))
    producer.produce(topic=topic, key=key, value=value, callback=delivery_report)
    # Removed per-message poll() - now using periodic polling in main loop for better performance


def make_transaction(user_id, amount=None, merchant=None, location=None):
    m = merchant or random.choice(MERCHANTS)
    loc = location or random.choice(CITIES[:3])
    return {
        "user_id": user_id,
        "transaction_id": str(uuid.uuid4())[:8],
        "amount": amount or round(random.uniform(3, 150), 2),
        "merchant": m[0],
        "merchant_category": m[1],
        "location": loc[0],
        "timestamp": now_ms(),
    }


def make_login(user_id, location=None, device=None):
    loc = location or random.choice(CITIES[:3])
    return {
        "user_id": user_id,
        "ip_address": loc[1],
        "device_id": device or random.choice(DEVICES[:3]),
        "location": loc[0],
        "timestamp": now_ms(),
    }


def make_account_change(user_id, field="preferences", old_val="default", new_val="custom"):
    return {
        "user_id": user_id,
        "field_changed": field,
        "old_value": old_val,
        "new_value": new_val,
        "timestamp": now_ms(),
    }


def normal_activity(producer, serializers, user_id):
    """Normal user: login from one city, purchases matching their profile baseline."""
    profile_type, config = get_user_profile(user_id)
    city = random.choice(CITIES[:3])

    login = make_login(user_id, location=city)
    produce_event(producer, serializers, TOPIC_LOGINS, login)
    print(f"  [{profile_type}] {user_id} login from {city[0]}")

    # Generate transactions with Gaussian distribution around user's baseline
    for _ in range(config["txn_per_cycle"]):
        # Normal distribution around user's average, ensuring minimum $5
        amount = max(5.0, random.gauss(config["avg_amount"], config["std_amount"]))
        txn = make_transaction(user_id, amount=round(amount, 2), location=city)
        produce_event(producer, serializers, TOPIC_TRANSACTIONS, txn)
        print(f"  [{profile_type}] {user_id} txn ${txn['amount']:.2f} at {txn['merchant']}")


def fraud_geo_impossible(producer, serializers, user_id):
    """Login from Tokyo, purchase from NYC seconds later."""
    login = make_login(user_id, location=CITIES[2])  # Tokyo
    produce_event(producer, serializers, TOPIC_LOGINS, login)
    print(f"  [FRAUD:geo] {user_id} login from Tokyo")

    txn = make_transaction(
        user_id,
        amount=round(random.uniform(500, 2000), 2),
        merchant=("Best Buy", "electronics"),
        location=CITIES[1],  # New York
    )
    produce_event(producer, serializers, TOPIC_TRANSACTIONS, txn)
    print(f"  [FRAUD:geo] {user_id} txn ${txn['amount']:.2f} in New York (impossible travel)")


def fraud_account_takeover(producer, serializers, user_id):
    """Email change -> password change -> large purchase."""
    change1 = make_account_change(user_id, "email", "user@old.com", "hacker@temp.com")
    produce_event(producer, serializers, TOPIC_ACCOUNT_CHANGES, change1)
    print(f"  [FRAUD:takeover] {user_id} email changed")

    time.sleep(0.5)

    change2 = make_account_change(user_id, "password", "****", "****")
    produce_event(producer, serializers, TOPIC_ACCOUNT_CHANGES, change2)
    print(f"  [FRAUD:takeover] {user_id} password changed")

    time.sleep(0.5)

    txn = make_transaction(
        user_id,
        amount=round(random.uniform(1000, 5000), 2),
        merchant=("Amazon", "online_retail"),
    )
    produce_event(producer, serializers, TOPIC_TRANSACTIONS, txn)
    print(f"  [FRAUD:takeover] {user_id} large purchase ${txn['amount']:.2f} after credential changes")


def fraud_velocity(producer, serializers, user_id):
    """Many rapid transactions across different merchants."""
    login = make_login(user_id, location=CITIES[0])
    produce_event(producer, serializers, TOPIC_LOGINS, login)
    print(f"  [FRAUD:velocity] {user_id} login from {CITIES[0][0]}")

    time.sleep(0.3)

    for i in range(6):
        txn = make_transaction(
            user_id,
            amount=round(random.uniform(200, 800), 2),
            merchant=MERCHANTS[i % len(MERCHANTS)],
        )
        produce_event(producer, serializers, TOPIC_TRANSACTIONS, txn)
        print(f"  [FRAUD:velocity] {user_id} rapid txn #{i+1} ${txn['amount']:.2f} at {txn['merchant']}")
        time.sleep(0.2)


FRAUD_SCENARIOS = [fraud_geo_impossible, fraud_account_takeover, fraud_velocity]


def parse_args():
    """Parse command-line arguments to determine generation mode."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic fraud detection events for Confluent Cloud"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--fraud",
        action="store_true",
        help="Generate fraud scenarios only (continuous loop)"
    )
    mode_group.add_argument(
        "--single-fraud",
        action="store_true",
        help="Generate a single fraud event and exit"
    )
    mode_group.add_argument(
        "--both",
        action="store_true",
        help="Generate both normal and fraud events (fraud starts after cycle 50)"
    )
    return parser.parse_args()


def generate_normal_cycle(producer, serializers, cycle):
    """Generate one cycle of normal user activity."""
    print(f"--- Cycle {cycle} ({datetime.now().strftime('%H:%M:%S')}) ---")

    random.shuffle(USERS)

    # 80% of users do normal activity
    for idx, user_id in enumerate(USERS[:]):
        normal_activity(producer, serializers, user_id)

        # Periodic polling
        if idx % 50 == 0:
            producer.poll(0)

    producer.poll(0)


def generate_fraud_cycle(producer, serializers, cycle):
    """Generate one cycle of fraud scenarios."""
    print(f"--- Fraud Cycle {cycle} ({datetime.now().strftime('%H:%M:%S')}) ---")

    fraud_target_users = USER_PROFILES["fraud_target"]["users"]

    # Generate 2 fraud scenarios per cycle
    for _ in range(2):
        fraud_user = random.choice(fraud_target_users)
        fraud_fn = random.choice(FRAUD_SCENARIOS)
        fraud_fn(producer, serializers, fraud_user)

    producer.poll(0)


def generate_mixed_cycle(producer, serializers, cycle):
    """Generate one cycle of normal + fraud (after cycle 50)."""
    print(f"--- Cycle {cycle} ({datetime.now().strftime('%H:%M:%S')}) ---")

    random.shuffle(USERS)
    fraud_target_users = USER_PROFILES["fraud_target"]["users"]

    # Normal activity
    for idx, user_id in enumerate(USERS[:160]):
        normal_activity(producer, serializers, user_id)

        if idx % 50 == 0:
            producer.poll(0)

    # Add fraud after cycle 50 (ARIMA baseline)
    if cycle > 50:
        for _ in range(2):
            fraud_user = random.choice(fraud_target_users)
            fraud_fn = random.choice(FRAUD_SCENARIOS)
            fraud_fn(producer, serializers, fraud_user)
    else:
        print(f"  [baseline building] {50 - cycle} cycles until fraud scenarios start")

    producer.poll(0)


def generate_single_fraud(producer, serializers):
    """Generate a single fraud event and exit."""
    print(f"Generating single fraud event at {datetime.now().strftime('%H:%M:%S')}")
    print(USER_PROFILES)

    fraud_target_users = USER_PROFILES["fraud_target"]["users"]
    fraud_user = random.choice(fraud_target_users)
    fraud_fn = random.choice(FRAUD_SCENARIOS)

    print(f"Selected scenario: {fraud_fn.__name__} for user {fraud_user}")
    fraud_fn(producer, serializers, fraud_user)

    producer.poll(0)
    print("Fraud event generated.")


def main():
    args = parse_args()

    print(f"Connecting to Confluent Cloud at {BOOTSTRAP}...")
    producer = make_producer()
    serializers = build_serializers()
    print("Connected.\n")

    # Determine mode
    if args.single_fraud:
        print("Mode: Single fraud event\n")
        try:
            generate_single_fraud(producer, serializers)
        finally:
            print("Flushing messages...")
            producer.flush()
            print("Done.")
        return  # Exit after single fraud

    # Continuous modes
    if args.fraud:
        cycle_fn = generate_fraud_cycle
        print("Mode: Continuous fraud generation (Ctrl+C to stop)\n")
    elif args.both:
        cycle_fn = generate_mixed_cycle
        print("Mode: Mixed (normal + fraud after cycle 50) (Ctrl+C to stop)\n")
    else:
        cycle_fn = generate_normal_cycle
        print("Mode: Normal transactions only (Ctrl+C to stop)\n")

    cycle = 0

    try:
        while True:
            cycle += 1
            cycle_fn(producer, serializers, cycle)

            wait = random.uniform(5.0, 8.0)
            print(f"\nCycle complete, waiting {wait:.1f}s...\n")
            time.sleep(wait)
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
    finally:
        print("Flushing remaining messages...")
        producer.flush()
        print("Producer stopped.")


if __name__ == "__main__":
    main()
