"""Preflight: checks that the clients can use the gateway, before the demo starts.

Uses the same settings as the clients (.env, KAFKA_CFG_*). On the EC2 instance:

    ./run.sh preflight

Prints one PASS, FAIL or INFO line per check. Exits 0 when nothing failed.

Checks
- the bootstrap address resolves and accepts TCP connections;
- a metadata request through it succeeds (prints the cluster ID it reports);
- every broker address in that metadata resolves and accepts TCP connections
  from this machine. The gateway advertises one address per broker, and a client that
  reaches the bootstrap address but not these can't produce or consume;
- the demo topic exists, has the expected partition count, and every
  partition has a leader.

Environment: KAFKA_BOOTSTRAP, TOPIC (default orders), PARTITIONS (default 6,
the number of partitions the producers write to), KAFKA_CFG_* as for the
clients.
"""

from __future__ import annotations

import os
import socket
import sys
import time

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient

import profiles

TOPIC = os.environ.get("TOPIC", "orders")
EXPECTED_PARTITIONS = int(os.environ.get("PARTITIONS", "6"))
METADATA_TIMEOUT_S = 10
TCP_TIMEOUT_S = 3

failures = 0


def line(tag: str, what: str, detail: str = "") -> None:
    print(f"{tag:<5} {what}" + (f": {detail}" if detail else ""), flush=True)


def check(ok: bool, what: str, detail: str = "") -> bool:
    global failures
    if not ok:
        failures += 1
    line("PASS" if ok else "FAIL", what, detail)
    return ok


def split_address(address: str) -> tuple[str, int]:
    host, _, port = address.strip().rpartition(":")
    return host.strip("[]"), int(port)


def check_tcp(label: str, host: str, port: int) -> bool:
    try:
        resolved = sorted({info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
    except socket.gaierror as exc:
        return check(False, f"{label} {host}:{port} resolves", str(exc))
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT_S):
            pass
    except OSError as exc:
        return check(False, f"{label} {host}:{port} accepts connections",
                     f"{exc} (resolves to {', '.join(resolved)})")
    elapsed_ms = round((time.monotonic() - started) * 1000)
    return check(True, f"{label} {host}:{port} reachable",
                 f"resolves to {', '.join(resolved)}, connected in {elapsed_ms} ms")


def main() -> int:
    if not profiles.BOOTSTRAP:
        check(False, "KAFKA_BOOTSTRAP is set", "put the gateway route address in .env (see .env.example)")
        return 1

    config = profiles.base_config()
    line("INFO", "bootstrap.servers", config["bootstrap.servers"])
    line("INFO", "security.protocol", str(config.get("security.protocol", "plaintext (default)")))
    overrides = profiles.override_names()
    line("INFO", "KAFKA_CFG_* overrides", ", ".join(overrides) if overrides else "none")

    for address in config["bootstrap.servers"].split(","):
        try:
            host, port = split_address(address)
        except ValueError:
            check(False, f"bootstrap address {address!r} is host:port")
            continue
        check_tcp("bootstrap", host, port)

    try:
        metadata = AdminClient(config).list_topics(timeout=METADATA_TIMEOUT_S)
    except KafkaException as exc:
        err = exc.args[0] if exc.args else exc
        check(False, "metadata request", err.str() if hasattr(err, "str") else str(err))
        return 1
    brokers = sorted(metadata.brokers.values(), key=lambda b: b.id)
    check(True, "metadata request",
          f"cluster ID {metadata.cluster_id}, controller {metadata.controller_id}, {len(brokers)} broker(s)")

    check(bool(brokers), "metadata lists at least one broker")
    for broker in brokers:
        check_tcp(f"broker {broker.id}", broker.host, broker.port)

    topic = metadata.topics.get(TOPIC)
    if topic is None:
        check(False, f"topic {TOPIC} exists", "not in metadata: missing, or this client may not describe it")
    elif topic.error is not None:
        check(False, f"topic {TOPIC} readable", topic.error.str())
    else:
        count = len(topic.partitions)
        # Producers write to partitions 0..PARTITIONS-1, so more is fine; fewer isn't.
        check(count >= EXPECTED_PARTITIONS, f"topic {TOPIC} has at least {EXPECTED_PARTITIONS} partitions",
              f"found {count}")
        leaderless = sorted(p.id for p in topic.partitions.values()
                            if p.error is not None or p.leader < 0)
        check(not leaderless, f"every partition of {TOPIC} has a leader",
              f"no leader for partition(s) {', '.join(map(str, leaderless))}" if leaderless else "")

    print()
    if failures:
        print(f"{failures} check(s) failed.", flush=True)
        return 1
    print("All checks passed. Record the cluster ID above: the UIs should show the same one.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
