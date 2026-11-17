"""Demo client: one Kafka client (producer or consumer) plus its own web UI.

The browser talks only to this process, never to Kafka or the gateway, so the
UI keeps updating while the gateway is down. That is the point of the demo.

Environment
    ROLE             producer | consumer                 (default producer)
    PROFILE          tuned | fragile                     (default tuned)
    CLIENT_ID        name shown in the UI                (default <role>-<hostname>)
    TOPIC            demo topic                          (default orders)
    GROUP_ID         consumer group                      (default demo-consumers)
    RATE             initial producer messages/second    (default 5)
    PARTITIONS       partitions a producer spreads over   (default 6)
    KAFKA_BOOTSTRAP  gateway route address               (required)
    KAFKA_CFG_*      extra librdkafka properties, see profiles.py
    DEBUG_STATS      1 logs librdkafka statistics payloads at startup and
                     checks the fields state.on_stats reads   (default 0)

Run with ../run.sh <client>, which sets ROLE, PROFILE and CLIENT_ID per client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import profiles
from state import FLUSH_INTERVAL_S, DemoState

ROLE = os.environ.get("ROLE", "producer")
PROFILE = os.environ.get("PROFILE", "tuned")
CLIENT_ID = os.environ.get("CLIENT_ID", f"{ROLE}-{socket.gethostname()}")
TOPIC = os.environ.get("TOPIC", "orders")
GROUP_ID = os.environ.get("GROUP_ID", "demo-consumers")
INITIAL_RATE = float(os.environ.get("RATE", "5"))
PARTITIONS = int(os.environ.get("PARTITIONS", "6"))
STATIC_DIR = Path(__file__).parent / "static"
DEBUG_STATS = os.environ.get("DEBUG_STATS", "0").lower() in ("1", "true", "yes")
SSE_KEEPALIVE_S = 15

# uvicorn configures only its own loggers; this makes the demo's INFO lines visible.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if not profiles.BOOTSTRAP:
    raise SystemExit("KAFKA_BOOTSTRAP is not set. Put the gateway route address in .env (see .env.example).")
if ROLE not in ("producer", "consumer"):
    raise SystemExit(f"ROLE must be producer or consumer, got {ROLE!r}")
if PROFILE not in profiles.PROFILES:
    raise SystemExit(f"PROFILE must be one of {sorted(profiles.PROFILES)}, got {PROFILE!r}")

state = DemoState(
    client_id=CLIENT_ID, role=ROLE, profile=PROFILE, topic=TOPIC,
    settings=profiles.describe(ROLE, PROFILE), debug_stats=DEBUG_STATS,
)
worker = None  # DemoProducer | DemoConsumer, set in lifespan


async def _flush_loop() -> None:
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_S)
        state.flush()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global worker
    state.attach_loop(asyncio.get_running_loop())

    from probe import Probe
    probe = Probe(state, profiles.base_config(), topic=TOPIC,
                  min_partitions=PARTITIONS if ROLE == "producer" else None)

    config = profiles.role_config(ROLE, PROFILE)
    if ROLE == "producer":
        from producer import DemoProducer
        worker = DemoProducer(state, config, topic=TOPIC, producer_id=CLIENT_ID, rate=INITIAL_RATE,
                              partitions=PARTITIONS)
    else:
        from consumer import DemoConsumer
        worker = DemoConsumer(state, config, topic=TOPIC, group_id=GROUP_ID, client_id=CLIENT_ID)

    state.add_timeline("info", f"Started {ROLE} with the {PROFILE} profile on topic {TOPIC}")
    probe.start()
    worker.start()
    flusher = asyncio.create_task(_flush_loop())
    try:
        yield
    finally:
        flusher.cancel()
        # Both bounded, so Ctrl-C exits within seconds even when Kafka is
        # unreachable.
        await asyncio.gather(asyncio.to_thread(worker.stop), asyncio.to_thread(probe.stop))


app = FastAPI(lifespan=lifespan)
# Lets the operator console (another origin) read this client's event stream.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict:
    """Process health. Stays 200 during a Kafka outage, on purpose: the app is
    healthy, it's only waiting. Kafka connectivity is reported, not judged."""
    return {"status": "ok", "client_id": CLIENT_ID, "kafka": state.connection["state"]}


@app.get("/api/state")
async def get_state() -> dict:
    return state.snapshot()


def _sse(env: dict) -> str:
    return f"data: {json.dumps(env, separators=(',', ':'))}\n\n"


@app.get("/api/events")
async def events() -> StreamingResponse:
    # Disconnects end the stream without polling: Starlette cancels the
    # generator when the client goes away, or the next write (at the latest the
    # keepalive) fails. Either way the finally block unsubscribes.
    async def stream():
        # Subscribe and snapshot with no await in between, so no event can fall
        # between them. Events already reflected in the snapshot can still be
        # queued; their seq is <= floor and they are skipped.
        queue = state.subscribe()
        floor, snap = state.snapshot_with_seq()
        try:
            yield "retry: 2000\n\n"
            yield _sse(state.envelope("snapshot", snap))
            while True:
                try:
                    seq, env = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_S)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if env["type"] == "snapshot":
                    floor = seq   # overflow resync replaced this stream's backlog
                elif seq <= floor:
                    continue
                yield _sse(env)
        finally:
            state.unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _require_producer():
    if ROLE != "producer" or worker is None:
        raise HTTPException(status_code=404, detail="This client is not a producer")
    return worker


@app.post("/api/send")
async def send(count: int = 1) -> dict:
    producer = _require_producer()
    count = max(1, min(1000, count))
    sent = await asyncio.to_thread(producer.burst, count)
    return {"requested": count, "queued": sent, "refused": count - sent}


class RateBody(BaseModel):
    rate: float


@app.post("/api/rate")
async def set_rate(body: RateBody) -> dict:
    producer = _require_producer()
    return {"rate": producer.set_rate(body.rate)}
