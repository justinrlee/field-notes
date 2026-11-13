"""Kafka client configuration profiles.

Two profiles let the demo show the difference side by side:

- "tuned":   rides out a gateway outage of several minutes without losing data.
- "fragile": gives up on undelivered messages after 30 s, so failures appear
             within demo time. (librdkafka's real default message.timeout.ms is
             300000, i.e. 5 minutes; it's shortened here so the audience doesn't
             have to wait that long.)

Any librdkafka property can be added or overridden with an environment variable
named KAFKA_CFG_<PROPERTY>, where dots become underscores. For example:
    KAFKA_CFG_SECURITY_PROTOCOL=SASL_SSL   ->  security.protocol=SASL_SSL
Overrides apply to every client handle (producer, consumer and admin probe).
"""

from __future__ import annotations

import os
from typing import Any

# Required. app.py and preflight.py refuse to start without it.
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "").strip()

# Connection behaviour shared by every handle in the process.
BASE: dict[str, Any] = {
    "bootstrap.servers": BOOTSTRAP,
    # Reconnect quickly and visibly: start at 500 ms, back off to at most 5 s.
    "reconnect.backoff.ms": 500,
    "reconnect.backoff.max.ms": 5000,
    # Give up on a single TCP connection attempt quickly while the gateway is down.
    "socket.connection.setup.timeout.ms": 5000,
}

PROFILES: dict[str, dict[str, dict[str, Any]]] = {
    "tuned": {
        "producer": {
            "acks": "all",
            "enable.idempotence": True,
            # Keep undelivered messages for up to 10 minutes before failing them.
            "message.timeout.ms": 600_000,
            "queue.buffering.max.messages": 100_000,
        },
        "consumer": {
            "auto.offset.reset": "latest",
            "session.timeout.ms": 45_000,
            "max.poll.interval.ms": 600_000,
        },
    },
    "fragile": {
        "producer": {
            "acks": "all",
            "enable.idempotence": False,
            "message.timeout.ms": 30_000,
            # Small buffer so backpressure (BufferError) shows up during the outage.
            "queue.buffering.max.messages": 2_000,
        },
        "consumer": {
            "auto.offset.reset": "latest",
            "session.timeout.ms": 10_000,
        },
    },
}

# Settings shown in the UI. Whitelisted so credentials never reach the browser.
DISPLAY_KEYS = {
    "producer": [
        "bootstrap.servers", "message.timeout.ms", "enable.idempotence", "acks",
        "queue.buffering.max.messages", "reconnect.backoff.ms", "reconnect.backoff.max.ms",
    ],
    "consumer": [
        "bootstrap.servers", "session.timeout.ms", "max.poll.interval.ms",
        "auto.offset.reset", "reconnect.backoff.ms", "reconnect.backoff.max.ms",
    ],
}


def _env_overrides() -> dict[str, str]:
    prefix = "KAFKA_CFG_"
    return {
        key[len(prefix):].lower().replace("_", "."): value
        for key, value in os.environ.items()
        if key.startswith(prefix)
    }


def override_names() -> list[str]:
    """librdkafka properties set through KAFKA_CFG_*. Names only: values may be secrets."""
    return sorted(_env_overrides())


def base_config() -> dict[str, Any]:
    """Connection and security settings only. Used by the admin probe."""
    return {**BASE, **_env_overrides()}


def role_config(role: str, profile: str) -> dict[str, Any]:
    """Full config for the producer or consumer handle."""
    return {
        **BASE,
        **PROFILES[profile][role],
        # Stats every second drive the broker list, buffer gauge and attempt count.
        "statistics.interval.ms": 1000,
        **_env_overrides(),
    }


def describe(role: str, profile: str) -> dict[str, Any]:
    config = role_config(role, profile)
    return {key: config[key] for key in DISPLAY_KEYS[role] if key in config}
