"""Streamlit dashboard: watch a player's struggle flow through the pipeline to an offer.

Consumes (Avro + SASL_SSL, from `latest` with a fresh group id, read_uncommitted):
  player_combat_events, player_activity        raw events
  player_encounters                            session windows + profile join
  player_struggle_moments                      rule-based filter (pre-LLM)
  player_offer_recommendations                 agent decisions

Panels refresh via st.fragment(run_every=...), not st.rerun() loops (see the comment above
render_dashboard). The headline metric is "seconds from last death to offer".
"""

import html
import os
import threading
import time
from collections import deque
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
from confluent_kafka import Consumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext
from dotenv import load_dotenv

# Home-directory defaults first, then the project root (takes precedence).
load_dotenv(os.path.expanduser("~/.env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

KAFKA_BOOTSTRAP = os.environ["BOOTSTRAP_SERVERS"]
KAFKA_API_KEY = os.environ["KAFKA_API_KEY"]
KAFKA_API_SECRET = os.environ["KAFKA_API_SECRET"]
SR_URL = os.environ["SCHEMA_REGISTRY_URL"]
SR_API_KEY = os.environ["SCHEMA_REGISTRY_API_KEY"]
SR_API_SECRET = os.environ["SCHEMA_REGISTRY_API_SECRET"]

T_COMBAT = "player_combat_events"
T_ACTIVITY = "player_activity"
T_ENCOUNTERS = "player_encounters"
T_MOMENTS = "player_struggle_moments"
T_RECS = "player_offer_recommendations"
TOPICS = [T_COMBAT, T_ACTIVITY, T_ENCOUNTERS, T_MOMENTS, T_RECS]

# Materialized tables with a PRIMARY KEY keep their key columns (player_id) ONLY in the Kafka key, not
# the value (value.fields-include defaults to EXCEPT_KEY). The dashboard merges the Avro key into the
# row for these topics. The event topics (plain string keys) and the recommendations table (no primary
# key) already carry player_id in the value.
AVRO_KEY_TOPICS = {T_ENCOUNTERS, T_MOMENTS}

GAMES = ["ember_throne", "starlane_arena", "tidal_rogue"]
MAX_EVENTS = 5000
MAX_ROWS = 2000
REFRESH_SECONDS = 2

TOPIC_COLORS = {
    T_COMBAT: "#ef5350",
    T_ACTIVITY: "#81c784",
    T_ENCOUNTERS: "#4fc3f7",
    T_MOMENTS: "#ffb74d",
    T_RECS: "#ba68c8",
}

st.set_page_config(page_title="Player Struggle to Offer", page_icon=":video_game:", layout="wide")

CUSTOM_CSS = """
<style>
    [data-testid="stMainBlockContainer"] { padding-top: 0 !important; }
    [data-testid="stHeader"], header[data-testid="stHeader"], [data-testid="stToolbar"] { display: none !important; }
    .block-container { padding-top: 0 !important; }
    div[data-testid="stMetric"] {
        background: #1a1a2e; border: 1px solid #2a2a4a; border-left: 4px solid #4fc3f7;
        border-radius: 8px; padding: 15px 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    div[data-testid="stMetric"] label {
        color: #8888aa !important; font-size: 0.8rem !important;
        text-transform: uppercase; letter-spacing: 0.8px;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.8rem !important; font-weight: 700 !important; color: #e8e8f0 !important;
    }
    .section-header {
        font-size: 1.3rem; font-weight: 600; color: #c0c0e0; margin-top: 1rem; margin-bottom: 0.5rem;
        padding-bottom: 0.4rem; border-bottom: 2px solid #2a2a4a;
    }
    .topic-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
    .ts-highlight {
        color: #ff9800; background: #1a1a2e; padding: 2px 6px; border-radius: 4px;
        font-family: "Source Code Pro", monospace; font-size: 0.85em;
    }
    .chip {
        display: inline-block; padding: 2px 9px; border-radius: 4px; color: white;
        font-weight: 600; font-size: 0.78rem; margin-right: 4px;
    }
    .chip-paid_offer { background: #0277bd; }
    .chip-free_gift { background: #2e7d32; }
    .chip-hint { background: #00838f; }
    .chip-none { background: #546e7a; }
    .chip-suppressed { background: #e65100; }
    .chip-BOSS_WALL { background: #8e24aa; }
    .chip-GEAR_GAP { background: #5e35b1; }
    .chip-RAGE_QUIT_RISK { background: #c62828; }
    /* Mock in-game popup */
    .popup {
        border-radius: 14px; padding: 16px 18px; min-height: 190px; color: #f4f4fa;
        box-shadow: 0 6px 18px rgba(0,0,0,0.5); border: 2px solid transparent;
    }
    .popup-paid_offer { background: linear-gradient(160deg, #1b2a49, #0d1b33); border-color: #4fc3f7; }
    .popup-free_gift { background: linear-gradient(160deg, #1b3a2a, #0d2218); border-color: #66bb6a; }
    .popup-hint { background: linear-gradient(160deg, #123a40, #0a2226); border-color: #26c6da; }
    .popup-suppressed { background: linear-gradient(160deg, #4a2c10, #2b1807); border-color: #ffa726; }
    .popup-none { background: #22242c; border-color: #546e7a; }
    .popup-tag { font-size: 0.7rem; letter-spacing: 1.2px; font-weight: 700; opacity: 0.85; text-transform: uppercase; }
    .popup-title { font-size: 1.1rem; font-weight: 700; margin: 4px 0 8px; }
    .popup-item { font-size: 1.05rem; font-weight: 600; }
    .popup-discount { background: #ffd54f; color: #3a2a00; border-radius: 4px; padding: 1px 6px; margin-left: 6px; font-size: 0.8rem; }
    .popup-price { font-size: 1.2rem; font-weight: 700; margin: 4px 0; }
    .popup-price s { opacity: 0.55; font-weight: 400; margin-right: 6px; }
    .popup-note { font-size: 0.82rem; opacity: 0.85; margin-top: 6px; }
    .popup-meta { font-size: 0.72rem; opacity: 0.6; margin-top: 8px; font-family: "Source Code Pro", monospace; }
</style>
"""


# ---------------------------------------------------------------------------
# Kafka
# ---------------------------------------------------------------------------

def create_consumer():
    return Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": KAFKA_API_KEY,
        "sasl.password": KAFKA_API_SECRET,
        "client.id": "gaming-demo-dashboard",
        "group.id": f"dashboard-streamlit-gaming-{int(time.time())}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
        "fetch.min.bytes": 1,
        "fetch.wait.max.ms": 100,
        "session.timeout.ms": 10000,
        "isolation.level": "read_uncommitted",  # Flink sinks commit on checkpoint; don't wait
    })


def create_avro_deserializer():
    """Generic Avro deserializer: resolves each message's writer schema by id, so one instance
    decodes every topic."""
    sr = SchemaRegistryClient({
        "url": SR_URL,
        "basic.auth.user.info": f"{SR_API_KEY}:{SR_API_SECRET}",
    })
    return AvroDeserializer(sr)


def _coerce_list(value):
    """Avro arrays arrive as lists already; tolerate a JSON-array string too."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith("["):
        import json
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _epoch_s(value):
    """datetime (tz-aware) or epoch-millis int -> epoch seconds; None if missing."""
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        return value.timestamp()
    return float(value) / 1000.0


def seconds_to_offer(rec):
    """Seconds from the player's last death to the moment the offer row was produced."""
    last_death = _epoch_s(rec.get("last_death_ts"))
    if last_death is None:
        return None
    offered = _epoch_s(rec.get("offered_at")) or rec.get("_arrival")
    return max(offered - last_death, 0.0)


def pretty(name):
    return str(name).replace("_", " ").title() if name else ""


def kafka_polling_thread(state, lock):
    consumer = create_consumer()
    consumer.subscribe(TOPICS)
    deserialize = create_avro_deserializer()
    try:
        while True:
            batch = []
            for _ in range(200):
                msg = consumer.poll(0.1)
                if msg is None:
                    break
                if msg.error() or msg.value() is None:
                    continue
                try:
                    value = deserialize(msg.value(), SerializationContext(msg.topic(), MessageField.VALUE))
                except Exception:
                    continue
                if value is None:
                    continue
                if msg.topic() in AVRO_KEY_TOPICS and msg.key() is not None:
                    try:
                        key = deserialize(msg.key(), SerializationContext(msg.topic(), MessageField.KEY))
                        if isinstance(key, dict):
                            value = {**key, **value}  # value wins on any overlap
                    except Exception:
                        pass  # keep the value-only row rather than dropping the message
                batch.append((msg.topic(), value))
            if not batch:
                time.sleep(0.2)
                continue

            now = time.time()
            ts = datetime.now().strftime("%H:%M:%S")
            with lock:
                for topic, value in batch:
                    state["counters"][topic] = state["counters"].get(topic, 0) + 1
                    row = {"time": ts, "_arrival": now, **value}
                    if "owned_skus" in row:
                        row["owned_skus"] = _coerce_list(row["owned_skus"])

                    if topic == T_COMBAT:
                        row["summary"] = (f"{value.get('event_type')} {value.get('damage_amount')} from "
                                          f"{value.get('source_id')} ({value.get('source_type')}) in {value.get('zone_id')}")
                        state["events"].appendleft({**row, "topic": topic})
                    elif topic == T_ACTIVITY:
                        extra = " ".join(str(x) for x in (value.get("item_id"), value.get("detail")) if x)
                        row["summary"] = f"{value.get('activity_type')} {extra}".strip()
                        state["events"].appendleft({**row, "topic": topic})
                    elif topic == T_ENCOUNTERS:
                        state["encounters"].appendleft(row)
                    elif topic == T_MOMENTS:
                        state["moments"].appendleft(row)
                    elif topic == T_RECS:
                        row["secs"] = seconds_to_offer(row)
                        state["recs"].appendleft(row)
    finally:
        consumer.close()


def get_shared_state():
    if "initialized" not in st.session_state:
        st.session_state.state = {
            "events": deque(maxlen=MAX_EVENTS),
            "encounters": deque(maxlen=MAX_ROWS),
            "moments": deque(maxlen=MAX_ROWS),
            "recs": deque(maxlen=MAX_ROWS),
            "counters": {},
        }
        st.session_state.lock = threading.Lock()
        threading.Thread(
            target=kafka_polling_thread,
            args=(st.session_state.state, st.session_state.lock),
            daemon=True,
        ).start()
        st.session_state.initialized = True
    return st.session_state.state, st.session_state.lock


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def make_filter(player_text, game):
    needle = (player_text or "").strip().lower()

    def keep(row):
        if game and game != "All" and row.get("game_id") != game:
            return False
        return not needle or needle in str(row.get("player_id", "")).lower()

    return keep


def card_kind(rec):
    if rec.get("suppressed"):
        return "suppressed"
    return rec.get("offer_type") or "none"


def popup_html(rec):
    kind = card_kind(rec)
    offer_type = rec.get("offer_type") or "none"
    sku = rec.get("sku")
    deaths = rec.get("deaths")
    killer = pretty(rec.get("killer_id"))
    secs = rec.get("secs")
    note = html.escape(str(rec.get("rationale") or ""))
    meta = f"{rec.get('player_id')} · {rec.get('game_id')}"
    if secs is not None:
        meta += f" · {secs:.0f}s after last death"

    free_name = {"free_comeback_gift": "Comeback Gift", "free_boss_hint": "Boss Hint"}.get(sku, pretty(sku))

    if kind == "suppressed":
        reason = html.escape(str(rec.get("suppress_reason") or "guardrail"))
        title = f"Struggling with {killer}?" if killer else "Rough session?"
        body = (f'<div class="popup-item">No purchase offered</div>'
                f'<div class="popup-note">Blocked by guardrail: <b>{reason}</b></div>'
                f'<div class="popup-note">Instead: <b>{html.escape(free_name or "a free hint")}</b> (free)</div>')
        tag = "Responsible monetization"
    elif offer_type == "paid_offer":
        discount = rec.get("discount_pct") or 0
        price = rec.get("price")
        title = f"Died to {killer} {deaths}×?" if killer and deaths else "Need an edge?"
        badge = f'<span class="popup-discount">−{discount}%</span>' if discount else ""
        orig = ""
        if price is not None and discount:
            orig = f"<s>${price / (1 - discount / 100):.2f}</s>"
        price_html = f'<div class="popup-price">{orig}${price:.2f}</div>' if price is not None else ""
        body = f'<div class="popup-item">{html.escape(pretty(sku))}{badge}</div>{price_html}'
        tag = "Limited offer"
    elif offer_type == "free_gift":
        title = "A little something to help"
        body = f'<div class="popup-item">{html.escape(free_name)}</div><div class="popup-price">Free</div>'
        tag = "A gift for you"
    elif offer_type == "hint":
        title = f"Tip for {killer}" if killer else "Tip"
        body = f'<div class="popup-item">{html.escape(free_name)}</div><div class="popup-price">Free</div>'
        tag = "Pro tip"
    else:
        title = "No intervention"
        body = ""
        tag = "No action"

    return (f'<div class="popup popup-{kind}"><div class="popup-tag">{tag}</div>'
            f'<div class="popup-title">{html.escape(title)}</div>{body}'
            f'<div class="popup-note">{note}</div><div class="popup-meta">{html.escape(meta)}</div></div>')


def render_metrics(snap):
    recs = snap["recs"]
    secs = [r["secs"] for r in recs if r.get("secs") is not None]
    suppressed = sum(1 for r in recs if r.get("suppressed"))
    offers = sum(1 for r in recs if r.get("offer_type") in ("paid_offer", "free_gift", "hint"))
    avg_secs = f"{sum(secs) / len(secs):.0f} s" if secs else "—"
    c = snap["counters"]
    cols = st.columns(7)
    cols[0].metric("Combat events", f"{c.get(T_COMBAT, 0):,}")
    cols[1].metric("Activity events", f"{c.get(T_ACTIVITY, 0):,}")
    cols[2].metric("Encounters", f"{c.get(T_ENCOUNTERS, 0):,}")
    cols[3].metric("Struggle moments", f"{c.get(T_MOMENTS, 0):,}")
    cols[4].metric("Interventions", f"{offers:,}")
    cols[5].metric("Suppressed (guardrail)", f"{suppressed:,}")
    cols[6].metric("Avg: last death → offer", avg_secs)


def render_popups(recs):
    st.markdown('<p class="section-header">In-game popup (what the player sees)</p>', unsafe_allow_html=True)
    if not recs:
        st.info("No recommendations yet. Press a button in the trigger UI (http://localhost:8080).")
        return
    cols = st.columns(3)
    for col, rec in zip(cols, recs[:3]):
        with col:
            st.markdown(popup_html(rec), unsafe_allow_html=True)


def render_latency_chart(recs):
    rows = [{"n": i, "secs": r["secs"], "player": r.get("player_id"), "kind": card_kind(r)}
            for i, r in enumerate(reversed(recs[:30])) if r.get("secs") is not None]
    if not rows:
        return
    st.caption("Seconds from last death to offer (most recent 30)")
    chart = (
        alt.Chart(pd.DataFrame(rows))
        .mark_bar(cornerRadiusEnd=3, opacity=0.85)
        .encode(
            x=alt.X("n:O", title=None, axis=alt.Axis(labels=False, ticks=False)),
            y=alt.Y("secs:Q", title="seconds", axis=alt.Axis(labelColor="#8888aa", gridColor="#2a2a4a")),
            color=alt.Color("kind:N", legend=alt.Legend(orient="bottom", title=None, labelColor="#c0c0e0"),
                            scale=alt.Scale(domain=["paid_offer", "free_gift", "hint", "suppressed", "none"],
                                            range=["#4fc3f7", "#66bb6a", "#26c6da", "#ffa726", "#78909c"])),
            tooltip=["player", "kind", alt.Tooltip("secs:Q", format=".1f")],
        )
        .properties(height=200)
    )
    st.altair_chart(chart.configure_view(stroke=None), width="stretch")


def chip(label, cls):
    return f'<span class="chip chip-{cls}">{html.escape(str(label))}</span>'


def render_recs_table(recs):
    st.markdown('<p class="section-header">Agent decisions (player_offer_recommendations)</p>', unsafe_allow_html=True)
    if not recs:
        st.info("Waiting for the agent...")
        return
    widths = [0.9, 1.6, 1.3, 1.3, 2.2, 1.0, 5, 0.8]
    for col, title in zip(st.columns(widths), ["Time", "Player", "Trigger", "Decision", "Item", "Guardrail", "Rationale", "Secs"]):
        col.markdown(f"**{title}**")
    for r in recs[:15]:
        cols = st.columns(widths)
        cols[0].markdown(f'<span class="ts-highlight">{r["time"]}</span>', unsafe_allow_html=True)
        cols[1].markdown(f"**{r.get('player_id')}**  \n{r.get('game_id')} · {r.get('tier')}")
        cols[2].markdown(chip(r.get("trigger_reason"), r.get("trigger_reason")), unsafe_allow_html=True)
        cols[3].markdown(chip(r.get("offer_type") or "none", r.get("offer_type") or "none"), unsafe_allow_html=True)
        item = pretty(r.get("sku")) or "—"
        if r.get("offer_type") == "paid_offer":
            item += f"  −{r.get('discount_pct') or 0}%  ${r.get('price') or 0:.2f}"
        cols[4].markdown(item)
        if r.get("suppressed"):
            cols[5].markdown(chip("SUPPRESSED", "suppressed"), unsafe_allow_html=True)
        else:
            cols[5].markdown("—")
        reason = r.get("suppress_reason")
        cols[6].markdown((f"*{reason}.* " if reason else "") + str(r.get("rationale") or "")[:220])
        cols[7].markdown(f"{r['secs']:.0f}" if r.get("secs") is not None else "—")


def render_moments_table(moments):
    st.markdown('<p class="section-header">Struggle moments (player_struggle_moments, filtered before the LLM)</p>', unsafe_allow_html=True)
    if not moments:
        st.info("No struggle moments yet.")
        return
    widths = [0.9, 1.6, 1.4, 0.8, 1.6, 1.0, 0.8, 1.0, 1.2]
    for col, title in zip(st.columns(widths), ["Time", "Player", "Trigger", "Deaths", "Killer", "Tier", "Minor", "Cap", "Spend 30d"]):
        col.markdown(f"**{title}**")
    for m in moments[:12]:
        cols = st.columns(widths)
        cols[0].markdown(f'<span class="ts-highlight">{m["time"]}</span>', unsafe_allow_html=True)
        cols[1].markdown(f"**{m.get('player_id')}**")
        cols[2].markdown(chip(m.get("trigger_reason"), m.get("trigger_reason")), unsafe_allow_html=True)
        cols[3].text(m.get("deaths"))
        cols[4].text(pretty(m.get("killer_id")) if m.get("single_killer") else "(mixed)")
        cols[5].text(m.get("tier"))
        cols[6].text("yes" if m.get("is_minor") else "no")
        cap = m.get("monthly_cap")
        cols[7].text(f"${cap:.0f}" if cap is not None else "none")
        cols[8].text(f"${(m.get('spend_30d') or 0):.2f}")


def render_encounters_table(encounters):
    st.markdown('<p class="section-header">Encounters (player_encounters, 12 s session windows + profile join)</p>', unsafe_allow_html=True)
    if not encounters:
        st.info("No encounters yet. Make sure the producer is running...")
        return
    widths = [0.9, 1.6, 1.4, 1.2, 0.8, 1.0, 0.9, 1.0, 5]
    for col, title in zip(st.columns(widths), ["Time", "Player", "Zone", "Deaths", "Events", "Damage", "Quest ✗", "Tier", "Activity"]):
        col.markdown(f"**{title}**")
    for e in encounters[:15]:
        cols = st.columns(widths)
        cols[0].markdown(f'<span class="ts-highlight">{e["time"]}</span>', unsafe_allow_html=True)
        cols[1].markdown(f"**{e.get('player_id')}**")
        cols[2].text(e.get("zone_id") or "—")
        cols[3].text(e.get("deaths"))
        cols[4].text(e.get("events"))
        cols[5].text(e.get("damage_taken"))
        cols[6].text(e.get("quest_fails"))
        cols[7].text(e.get("tier"))
        cols[8].text(str(e.get("activity") or "")[:110])


def render_event_feed(events):
    st.markdown('<p class="section-header">Live event feed (player_combat_events, player_activity)</p>', unsafe_allow_html=True)
    if not events:
        st.info("No events yet. Make sure the producer is running...")
        return
    widths = [1, 1.8, 2, 6]
    for col, title in zip(st.columns(widths), ["Time", "Topic", "Player", "Details"]):
        col.markdown(f"**{title}**")
    for e in events[:40]:
        cols = st.columns(widths)
        cols[0].text(e["time"])
        cols[1].markdown(
            f'<span class="topic-dot" style="background:{TOPIC_COLORS.get(e["topic"], "#999")}"></span>{e["topic"]}',
            unsafe_allow_html=True)
        cols[2].text(e.get("player_id"))
        cols[3].text(e.get("summary"))


# The live panels refresh via a fragment (run_every) rather than a `time.sleep(); st.rerun()` loop.
# The frontend only prunes leftover elements from earlier runs when a run finishes normally; a script
# that always ends in st.rerun() never does, so when a filter changed how many rows a section emitted,
# stale rows from the old layout stayed on screen.
@st.fragment(run_every=REFRESH_SECONDS)
def render_dashboard(state, lock):
    keep = make_filter(st.session_state.get("player_filter", ""), st.session_state.get("game_filter", "All"))
    with lock:
        snap = {
            "counters": dict(state["counters"]),
            "events": [e for e in state["events"] if keep(e)],
            "encounters": [e for e in state["encounters"] if keep(e)],
            "moments": [m for m in state["moments"] if keep(m)],
            "recs": [r for r in state["recs"] if keep(r)],
        }

    render_metrics(snap)
    render_popups(snap["recs"])
    render_latency_chart(snap["recs"])
    render_recs_table(snap["recs"])
    render_moments_table(snap["moments"])
    render_encounters_table(snap["encounters"])
    render_event_feed(snap["events"])


def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    state, lock = get_shared_state()

    title_col, game_col, player_col = st.columns([2.2, 1, 1])
    with title_col:
        st.markdown("## :video_game: Player Struggle → Offer")
        st.caption("Confluent Cloud: Flink spots the struggle, enriches it, and a Streaming Agent decides the intervention.")
    with game_col:
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        st.selectbox("Game", ["All"] + GAMES, key="game_filter", label_visibility="collapsed")
    with player_col:
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        st.text_input("Filter by player", value="", key="player_filter", label_visibility="collapsed",
                      placeholder="Filter by player id")

    render_dashboard(state, lock)


if __name__ == "__main__":
    main()
