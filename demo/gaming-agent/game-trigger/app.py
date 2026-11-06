"""FastAPI trigger UI: each button sends a scripted burst of events for a dedicated demo player.

Endpoints:
  GET  /           button UI
  GET  /scenarios  scenario list (JSON)
  POST /trigger    {"scenario": "<id>"} -> starts the burst in a background thread

Run: uvicorn app:app --host 0.0.0.0 --port 8080   (from game-trigger/; see ../start-game-trigger.sh)

Bursts are emitted in real time (events are stamped when sent) and stay inside the 12 s SESSION gap
of `player_encounters`. The producer (producer/generate_events.py) should be running: its profile
heartbeat keeps the temporal join's watermark moving. Demo players are never simulated by the
producer, so these bursts are the only events they emit.
"""

import os
import random
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "producer"))
import gamedata  # noqa: E402
import kafka_io  # noqa: E402
from kafka_io import TOPIC_ACTIVITY, TOPIC_COMBAT, now_ms  # noqa: E402

# Seconds between deaths in a burst. Must stay well under the 12 s session gap, or the burst
# splits into several windows. Lower = a faster demo.
PACE_S = float(os.environ.get("TRIGGER_PACE_S", "6"))

PLAYERS = {p["player_id"]: p for p in gamedata.build_demo_players()}

_producer = None
_serializers = None
_key_serializers = None
_running = {}  # player_id -> scenario id (guards against overlapping bursts for one player)
_lock = threading.Lock()


def short_id():
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Burst building blocks. A burst is a list of (delay_before_s, action) executed in order.
# ---------------------------------------------------------------------------

def _combat(player_id, match_id, zone_id, event_type, source_id, source_type, damage):
    player = PLAYERS[player_id]
    kafka_io.produce_event(_producer, _serializers, TOPIC_COMBAT, {
        "event_id": short_id(), "game_id": player["game_id"], "player_id": player_id,
        "match_id": match_id, "event_type": event_type, "damage_amount": damage,
        "source_id": source_id, "source_type": source_type, "zone_id": zone_id,
        "player_level": player["level"], "timestamp": now_ms(),
    })


def _activity(player_id, activity_type, item_id=None, detail=None):
    player = PLAYERS[player_id]
    kafka_io.produce_event(_producer, _serializers, TOPIC_ACTIVITY, {
        "event_id": short_id(), "game_id": player["game_id"], "player_id": player_id,
        "activity_type": activity_type, "item_id": item_id, "detail": detail, "timestamp": now_ms(),
    })


def _profile(player_id):
    kafka_io.produce_profile(_producer, _serializers, _key_serializers, PLAYERS[player_id])


def death_cycle(player_id, zone_id, source_id, source_type="BOSS"):
    """Heavy damage, a death, and a revive, with a PACE_S gap before the next cycle."""
    match_id = f"m-{short_id()[:8]}"
    steps = []
    for _ in range(2):
        dmg = random.randint(60, 140)
        steps.append((0.8, lambda d=dmg: _combat(player_id, match_id, zone_id, "DAMAGE_TAKEN", source_id, source_type, d)))
    steps.append((1.0, lambda: _combat(player_id, match_id, zone_id, "DEATH", source_id, source_type, random.randint(100, 180))))
    steps.append((1.0, lambda: _combat(player_id, match_id, zone_id, "REVIVE", source_id, source_type, 0)))
    steps.append((max(PACE_S - 2.8, 0.5), lambda: None))
    return steps


def boss_wall(player_id, deaths=5):
    p = PLAYERS[player_id]
    zone = gamedata.zone_for_level(p["game_id"], p["level"])
    steps = [(0.0, lambda: _profile(player_id))]  # fresh profile version right before the burst
    for _ in range(deaths):
        steps += death_cycle(player_id, zone["id"], zone["boss"])
    return steps


def gear_gap(player_id):
    """Low level in a high-level zone: heavy damage, deaths to varied enemies, browsing the store."""
    p = PLAYERS[player_id]
    zone = gamedata.GAMES[p["game_id"]]["zones"][-1]
    sources = [(zone["enemies"][0], "ENEMY"), (zone["enemies"][1], "ENEMY"),
               (zone["enemies"][0], "ENEMY"), (zone["boss"], "BOSS")]
    steps = [(0.0, lambda: _profile(player_id))]
    for i, (source_id, source_type) in enumerate(sources):
        steps += death_cycle(player_id, zone["id"], source_id, source_type)
        if i in (1, 3):
            sku = gamedata.GAMES[p["game_id"]]["skus"][2]["sku"]
            steps.append((0.5, lambda s=sku: _activity(player_id, "STORE_VIEW", item_id=s)))
    return steps


def rage_quit(player_id):
    """Deaths -> failed quest -> logout."""
    p = PLAYERS[player_id]
    zone = gamedata.zone_for_level(p["game_id"], p["level"])
    sources = [(zone["boss"], "BOSS"), (zone["enemies"][0], "ENEMY"), (zone["boss"], "BOSS"), (zone["enemies"][1], "ENEMY")]
    steps = [(0.0, lambda: _profile(player_id))]
    for source_id, source_type in sources:
        steps += death_cycle(player_id, zone["id"], source_id, source_type)
    steps.append((1.0, lambda: _activity(player_id, "QUEST_FAIL", detail=f"quest-{zone['id']}")))
    steps.append((2.0, lambda: _activity(player_id, "LOGOUT")))
    return steps


def control(player_id):
    """A veteran dies twice: below every threshold, must never reach the agent."""
    p = PLAYERS[player_id]
    zone = gamedata.zone_for_level(p["game_id"], p["level"])
    steps = [(0.0, lambda: _profile(player_id))]
    for _ in range(2):
        steps += death_cycle(player_id, zone["id"], zone["boss"])
    return steps


# Each scenario: the demo players it drives and the burst builder for each.
SCENARIOS = {
    "boss_wall": dict(
        title="Boss wall", players=["demo-boss-wall"], build=boss_wall,
        blurb="5 deaths to the same boss in ~30 s. Expect a counter item for that boss.",
    ),
    "gear_gap": dict(
        title="Gear gap", players=["demo-gear-gap"], build=gear_gap,
        blurb="Level 14 in the top zone: heavy damage, deaths, store views. Expect a gear upgrade bundle.",
    ),
    "rage_quit": dict(
        title="Rage-quit risk", players=["demo-rage-quit"], build=rage_quit,
        blurb="Deaths, a failed quest, then logout. Expect a FREE comeback gift or hint, not a paid item.",
    ),
    "two_profiles": dict(
        title="Same struggle, two profiles", players=["demo-f2p", "demo-whale"], build=boss_wall,
        blurb="Identical boss wall for an F2P player and a whale. Expect different offers.",
    ),
    "guardrail_minor": dict(
        title="Guardrail: minor", players=["demo-minor"], build=boss_wall,
        blurb="Boss wall on a minor. Expect suppressed=true and a free alternative.",
    ),
    "guardrail_capped": dict(
        title="Guardrail: spend-capped", players=["demo-capped"], build=boss_wall,
        blurb="Boss wall on a player at their monthly cap. Expect suppressed=true and a free alternative.",
    ),
    "control": dict(
        title="Control: veteran dies twice", players=["demo-veteran"], build=control,
        blurb="Two deaths only. Expect nothing to reach the agent (the filter working).",
    ),
}


def _run_burst(scenario_id, player_id, steps):
    try:
        for delay, action in steps:
            time.sleep(delay)
            action()
        _producer.flush(10)
        print(f"[{scenario_id}] burst for {player_id} complete", flush=True)
    except Exception as exc:  # noqa: BLE001 - surfaced in the log, never crash the web app
        print(f"[{scenario_id}] burst for {player_id} FAILED: {exc}", flush=True)
    finally:
        with _lock:
            _running.pop(player_id, None)


@asynccontextmanager
async def lifespan(_app):
    global _producer, _serializers, _key_serializers
    _producer = kafka_io.make_producer("gaming-trigger-web")
    _serializers = kafka_io.build_serializers()
    _key_serializers = kafka_io.build_key_serializers()
    yield
    _producer.flush(10)


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


class TriggerRequest(BaseModel):
    scenario: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    scenarios = [
        dict(id=sid, title=s["title"], blurb=s["blurb"], players=s["players"])
        for sid, s in SCENARIOS.items()
    ]
    return templates.TemplateResponse("index.html", {"request": request, "scenarios": scenarios, "pace": PACE_S})


@app.get("/scenarios")
async def scenarios():
    return {sid: dict(title=s["title"], players=s["players"]) for sid, s in SCENARIOS.items()}


@app.post("/trigger")
async def trigger(req: TriggerRequest):
    scenario = SCENARIOS.get(req.scenario)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"unknown scenario {req.scenario!r}")
    with _lock:
        busy = [p for p in scenario["players"] if p in _running]
        if busy:
            raise HTTPException(status_code=409, detail=f"burst already running for {', '.join(busy)}")
        for player_id in scenario["players"]:
            _running[player_id] = req.scenario
    for player_id in scenario["players"]:
        steps = scenario["build"](player_id)
        threading.Thread(target=_run_burst, args=(req.scenario, player_id, steps), daemon=True).start()
    seconds = int(sum(d for d, _ in scenario["build"](scenario["players"][0])))
    return {"status": "started", "scenario": req.scenario, "players": scenario["players"], "approx_seconds": seconds}
