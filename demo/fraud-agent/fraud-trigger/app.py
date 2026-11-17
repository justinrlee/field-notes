"""FastAPI web interface for manually triggering fraud scenarios.

Endpoints:
  GET /       - Serve the button UI
  POST /trigger - Trigger a fraud scenario for a specific user

Run: uvicorn app:app --host 0.0.0.0 --port 8080
"""

import os
import random
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext, StringSerializer
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Load connection config: home directory defaults first, then project root (with precedence)
load_dotenv(os.path.expanduser("~/.env"))  # Optional defaults, continues if missing
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)  # Project-specific overrides

BOOTSTRAP = os.environ["BOOTSTRAP_SERVERS"]
KAFKA_API_KEY = os.environ["KAFKA_API_KEY"]
KAFKA_API_SECRET = os.environ["KAFKA_API_SECRET"]
SR_URL = os.environ["SCHEMA_REGISTRY_URL"]
SR_API_KEY = os.environ["SCHEMA_REGISTRY_API_KEY"]
SR_API_SECRET = os.environ["SCHEMA_REGISTRY_API_SECRET"]

# Topic names
TOPIC_TRANSACTIONS = "transactions"
TOPIC_LOGINS = "user_logins"
TOPIC_ACCOUNT_CHANGES = "account_changes"

# Avro schemas matching Flink-generated schemas
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

# City data: (location, ip_address)
CITIES = [
    ("San Francisco, CA", "198.51.100.1"),
    ("New York, NY", "203.0.113.10"),
    ("Tokyo, Japan", "192.0.2.50"),
    ("London, UK", "198.51.100.99"),
    ("Chicago, IL", "203.0.113.42"),
    ("Sydney, Australia", "192.0.2.100"),
]

# Merchants: (name, category)
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

# Global state for persistent producer
_producer = None
_serializers = None
_key_serializer = StringSerializer("utf_8")
_delivery_errors = []


def delivery_report(err, msg):
    """Kafka producer delivery callback."""
    if err is not None:
        _delivery_errors.append(str(err))
        print(f"ERROR: Message delivery failed: {err}")


def now_ms():
    """Current timestamp in milliseconds."""
    return int(time.time() * 1000)


def build_serializers():
    """Build Avro serializers for all three topics."""
    sr = SchemaRegistryClient({
        "url": SR_URL,
        "basic.auth.user.info": f"{SR_API_KEY}:{SR_API_SECRET}",
    })
    conf = {"auto.register.schemas": False, "use.latest.version": True}
    return {
        TOPIC_TRANSACTIONS: AvroSerializer(sr, TRANSACTION_SCHEMA, conf=conf),
        TOPIC_LOGINS: AvroSerializer(sr, LOGIN_SCHEMA, conf=conf),
        TOPIC_ACCOUNT_CHANGES: AvroSerializer(sr, ACCOUNT_CHANGE_SCHEMA, conf=conf),
    }


def make_producer():
    """Create Kafka producer."""
    return Producer({
        "bootstrap.servers": BOOTSTRAP,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": KAFKA_API_KEY,
        "sasl.password": KAFKA_API_SECRET,
        "client.id": "fraud-trigger-web",
    })


def produce_event(topic, event):
    """Produce an event to Kafka."""
    value = _serializers[topic](event, SerializationContext(topic, MessageField.VALUE))
    key = _key_serializer(event["user_id"], SerializationContext(topic, MessageField.KEY))
    _producer.produce(topic=topic, key=key, value=value, callback=delivery_report)


def make_transaction(user_id, amount=None, merchant=None, location=None):
    """Create a transaction event."""
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


def make_login(user_id, location=None):
    """Create a login event."""
    loc = location or random.choice(CITIES[:3])
    return {
        "user_id": user_id,
        "ip_address": loc[1],
        "device_id": "web-trigger",
        "location": loc[0],
        "timestamp": now_ms(),
    }


def make_account_change(user_id, field="preferences", old_val="default", new_val="custom"):
    """Create an account change event."""
    return {
        "user_id": user_id,
        "field_changed": field,
        "old_value": old_val,
        "new_value": new_val,
        "timestamp": now_ms(),
    }


def _generate_geo_impossible(user_id):
    """Fraud scenario: Login from Tokyo, purchase from NYC seconds later."""
    login = make_login(user_id, location=CITIES[2])  # Tokyo
    produce_event(TOPIC_LOGINS, login)
    print(f"[FRAUD:geo] {user_id} login from Tokyo")

    txn = make_transaction(
        user_id,
        amount=round(random.uniform(500, 2000), 2),
        merchant=("Best Buy", "electronics"),
        location=CITIES[1],  # New York
    )
    produce_event(TOPIC_TRANSACTIONS, txn)
    print(f"[FRAUD:geo] {user_id} txn ${txn['amount']:.2f} in New York (impossible travel)")
    return 2  # 2 events


def _generate_account_takeover(user_id):
    """Fraud scenario: Email change -> password change -> large purchase."""
    change1 = make_account_change(user_id, "email", "user@old.com", "hacker@temp.com")
    produce_event(TOPIC_ACCOUNT_CHANGES, change1)
    print(f"[FRAUD:takeover] {user_id} email changed")

    time.sleep(0.5)

    change2 = make_account_change(user_id, "password", "****", "****")
    produce_event(TOPIC_ACCOUNT_CHANGES, change2)
    print(f"[FRAUD:takeover] {user_id} password changed")

    time.sleep(0.5)

    txn = make_transaction(
        user_id,
        amount=round(random.uniform(1000, 5000), 2),
        merchant=("Amazon", "online_retail"),
    )
    produce_event(TOPIC_TRANSACTIONS, txn)
    print(f"[FRAUD:takeover] {user_id} large purchase ${txn['amount']:.2f} after credential changes")
    return 3  # 3 events


def _generate_velocity(user_id):
    """Fraud scenario: Many rapid transactions across different merchants."""
    login = make_login(user_id, location=CITIES[0])
    produce_event(TOPIC_LOGINS, login)
    print(f"[FRAUD:velocity] {user_id} login from {CITIES[0][0]}")

    time.sleep(0.3)

    for i in range(6):
        txn = make_transaction(
            user_id,
            amount=round(random.uniform(200, 800), 2),
            merchant=MERCHANTS[i % len(MERCHANTS)],
        )
        produce_event(TOPIC_TRANSACTIONS, txn)
        print(f"[FRAUD:velocity] {user_id} rapid txn #{i+1} ${txn['amount']:.2f} at {txn['merchant']}")
        time.sleep(0.2)

    return 7  # 1 login + 6 transactions


# Map scenario names to generator functions
SCENARIO_GENERATORS = {
    "geo_impossible": _generate_geo_impossible,
    "account_takeover": _generate_account_takeover,
    "velocity": _generate_velocity,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize persistent producer on startup, flush on shutdown."""
    global _producer, _serializers

    print(f"Initializing Kafka producer (connecting to {BOOTSTRAP})...")
    _producer = make_producer()
    _serializers = build_serializers()
    print("Producer initialized.\n")

    yield

    print("\nShutting down, flushing producer...")
    _producer.flush(timeout=10)
    print("Producer flushed.")


app = FastAPI(lifespan=lifespan, title="Fraud Trigger API")
templates = Jinja2Templates(directory="templates")


class TriggerRequest(BaseModel):
    """Request to trigger a fraud scenario."""
    scenario: Literal["geo_impossible", "account_takeover", "velocity"]
    user: Literal["user-049", "user-050"]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the button UI."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/trigger")
async def trigger_fraud(req: TriggerRequest):
    """Trigger a fraud scenario for the specified user."""
    global _delivery_errors
    _delivery_errors = []  # Reset error list

    print(f"\n=== Triggering {req.scenario} for {req.user} ===")

    try:
        # Generate the fraud scenario
        generator = SCENARIO_GENERATORS[req.scenario]
        events_sent = generator(req.user)

        # Wait for all messages to be acknowledged
        remaining = _producer.flush(timeout=10)

        if remaining > 0:
            raise HTTPException(
                status_code=504,
                detail=f"Timeout: {remaining} messages not acknowledged after 10s"
            )

        if _delivery_errors:
            raise HTTPException(
                status_code=500,
                detail=f"Delivery failures: {', '.join(_delivery_errors)}"
            )

        print(f"=== Success: {events_sent} events acknowledged ===\n")

        return {
            "status": "success",
            "events_sent": events_sent,
            "scenario": req.scenario,
            "user": req.user,
        }

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(e))
