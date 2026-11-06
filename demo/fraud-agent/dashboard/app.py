import json
import os
import threading
import time
from collections import deque
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext
from dotenv import load_dotenv

# Load connection config: home directory defaults first, then project root (with precedence)
load_dotenv(os.path.expanduser("~/.env"))  # Optional defaults, continues if missing
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)  # Project-specific overrides

KAFKA_BOOTSTRAP = os.environ["BOOTSTRAP_SERVERS"]
KAFKA_API_KEY = os.environ["KAFKA_API_KEY"]
KAFKA_API_SECRET = os.environ["KAFKA_API_SECRET"]
SR_URL = os.environ["SCHEMA_REGISTRY_URL"]
SR_API_KEY = os.environ["SCHEMA_REGISTRY_API_KEY"]
SR_API_SECRET = os.environ["SCHEMA_REGISTRY_API_SECRET"]

TOPICS = ["transactions", "user_logins", "account_changes", "fraud_analysis_results", "user_activity_scored", "user_activity_anomalous_enriched", "user_activity_anomalous"]
MAX_EVENTS = 10000
MAX_ACTIVITY_EVENTS = 5000
TIMESERIES_BUCKETS = 30
BUCKET_SECONDS = 10
REFRESH_SECONDS = 2

st.set_page_config(
    page_title="Fraud Detection Dashboard v2",
    page_icon=":shield:",
    layout="wide",
)

CUSTOM_CSS = """
<style>
    [data-testid="stMainBlockContainer"] { padding-top: 0 !important; }
    [data-testid="stHeader"] { display: none !important; }
    header[data-testid="stHeader"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    .block-container { padding-top: 0 !important; }
    div[data-testid="stVerticalBlock"] > div:first-child { padding-top: 0 !important; }
    div[data-testid="stMetric"] {
        background: #1a1a2e;
        border: 1px solid #2a2a4a;
        border-left: 4px solid #4fc3f7;
        border-radius: 8px;
        padding: 15px 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    div[data-testid="stMetric"] label {
        color: #8888aa !important;
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        color: #e8e8f0 !important;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: 600;
        color: #c0c0e0;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid #2a2a4a;
    }
    .severity-critical {
        background: #d32f2f; color: white; padding: 3px 10px;
        border-radius: 4px; font-weight: 600; font-size: 0.8rem;
    }
    .severity-high {
        background: #e65100; color: white; padding: 3px 10px;
        border-radius: 4px; font-weight: 600; font-size: 0.8rem;
    }
    .severity-medium {
        background: #f9a825; color: #1a1a2e; padding: 3px 10px;
        border-radius: 4px; font-weight: 600; font-size: 0.8rem;
    }
    .severity-low {
        background: #2e7d32; color: white; padding: 3px 10px;
        border-radius: 4px; font-weight: 600; font-size: 0.8rem;
    }
    .topic-dot {
        display: inline-block; width: 10px; height: 10px;
        border-radius: 50%; margin-right: 6px;
    }
    .action-chip {
        display: inline-block; padding: 2px 8px; margin: 0 4px 2px 0;
        border-radius: 4px; font-family: "Source Code Pro", monospace;
        font-size: 0.8em; font-weight: 600; color: white;
    }
    .action-freeze_account { background: #d32f2f; }
    .action-flag_transaction { background: #e65100; }
    .action-notify_user { background: #0277bd; }
    .action-other { background: #546e7a; }
    .ts-highlight {
        color: #ff9800; background: #1a1a2e; padding: 2px 6px;
        border-radius: 4px; font-family: "Source Code Pro", monospace;
        font-size: 0.85em;
    }
</style>
"""

TOPIC_COLORS = {
    "transactions": "#4fc3f7",
    "user_logins": "#81c784",
    "account_changes": "#ffb74d",
    "fraud_analysis_results": "#ef5350",
    "user_activity_scored": "#ff6f00",
    "user_activity_anomalous_enriched": "#ff6f00",
}


def create_consumer():
    return Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": KAFKA_API_KEY,
        "sasl.password": KAFKA_API_SECRET,
        "client.id": "fraud-demo-dashboard-v2",
        "group.id": f"dashboard-streamlit-cc-v2-{int(time.time())}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
        "fetch.min.bytes": 1,              # Don't wait to fill batches
        "fetch.wait.max.ms": 100,          # Max 100ms fetch wait
        "session.timeout.ms": 10000,       # 10s session timeout
        "isolation.level": "read_uncommitted",  # Don't wait for transactional commits
    })


def create_avro_deserializer():
    """Generic Avro deserializer — resolves each message's writer schema from
    Schema Registry by id, so one instance decodes all five topics."""
    sr = SchemaRegistryClient({
        "url": SR_URL,
        "basic.auth.user.info": f"{SR_API_KEY}:{SR_API_SECRET}",
    })
    return AvroDeserializer(sr)


def get_bucket_key():
    now = time.time()
    return int(now // BUCKET_SECONDS) * BUCKET_SECONDS


def _coerce_list(value):
    """fraud_analysis_results stores actions_taken / flagged_transaction_ids as JSON-array
    strings; turn them back into Python lists for display."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [value]
        except json.JSONDecodeError:
            return [value]
    return []


def process_message(topic, value, batch, key=None):
    ts = datetime.now().strftime("%H:%M:%S")
    
    # Try to get user_id from key first, then fall back to value
    user_id = "N/A"
    if key and isinstance(key, dict):
        user_id = key.get("user_id", "N/A")
    if user_id == "N/A":
        user_id = value.get("user_id", "N/A")

    if topic == "transactions":
        summary = f"${value.get('amount', 0):.2f} at {value.get('merchant', '?')} — {value.get('location', '?')}"
    elif topic == "user_logins":
        summary = f"{value.get('location', '?')} via {value.get('device_id', '?')}"
    elif topic == "account_changes":
        summary = f"{value.get('field_changed', '?')}: {value.get('old_value', '?')} → {value.get('new_value', '?')}"
    elif topic == "user_activity_scored":
        txn_count = value.get('txn_count', 0)
        total_amount = value.get('total_amount', 0)
        is_anomaly = value.get('is_anomaly')
        anomaly_status = "ANOMALY" if is_anomaly else "normal" if is_anomaly is not None else "pending"
        summary = f"{txn_count} txns, ${total_amount:.2f} total [{anomaly_status}]"
    elif topic == "user_activity_anomalous":
        txn_count = value.get('txn_count', 0)
        total_amount = value.get('total_amount', 0)
        expected = value.get('expected_amount', 0)
        upper_bound = value.get('upper_bound', 0)
        lower_bound = value.get('lower_bound', 0)
        summary = f"ANOMALY: {txn_count} txns, ${total_amount:.2f} (expected ${expected:.2f})"
    elif topic == "user_activity_anomalous_enriched":
        window_total = value.get('window_total', 0)
        expected = value.get('expected_amount', 0)
        txn_count = value.get('txn_count', 0)
        avg_amount = value.get('avg_amount', 0)
        summary = f"{txn_count} txns, avg ${avg_amount:.2f} [Window total=${window_total:.2f}, expected=${expected:.2f}]"
    elif topic == "fraud_analysis_results":
        value["actions_taken"] = _coerce_list(value.get("actions_taken"))
        value["flagged_transaction_ids"] = _coerce_list(value.get("flagged_transaction_ids"))
        summary = f"Risk {value.get('risk_score', '?')}: {str(value.get('reasoning', '?'))[:100]}"
    else:
        summary = str(value)[:80]

    batch.append((topic, ts, user_id, summary, value))


def kafka_polling_thread(state, lock):
    consumer = create_consumer()
    consumer.subscribe(TOPICS)
    deserialize = create_avro_deserializer()
    try:
        while True:
            batch = []
            for _ in range(100):
                msg = consumer.poll(0.1)
                if msg is None:
                    break
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        pass
                    continue
                if msg.value() is None:
                    continue
                try:
                    value = deserialize(
                        msg.value(), SerializationContext(msg.topic(), MessageField.VALUE)
                    )
                    # Deserialize key if present
                    key = None
                    if msg.key() is not None:
                        try:
                            key = deserialize(
                                msg.key(), SerializationContext(msg.topic(), MessageField.KEY)
                            )
                        except Exception:
                            pass  # Key deserialization failed, continue with None
                except Exception:
                    continue
                if value is not None:
                    process_message(msg.topic(), value, batch, key)

            if not batch:
                time.sleep(0.2)
                continue

            bucket = get_bucket_key()

            with lock:
                for topic, ts, user_id, summary, value in batch:
                    state["counters"][topic] = state["counters"].get(topic, 0) + 1
                    if user_id != "N/A":
                        state["users"].add(user_id)

                    if topic in ["transactions", "user_logins", "account_changes"]:
                        state["events"].appendleft({
                            "time": ts,
                            "topic": topic,
                            "user_id": user_id,
                            "summary": summary,
                        })

                    if topic == "user_activity_scored":
                        state["scored_windows"].appendleft({"time": ts, "user_id": user_id, **value})
                        # Check if ARIMA scoring is active (is_anomaly is not null)
                        is_anomaly = value.get("is_anomaly")
                        if is_anomaly is not None:
                            state["arima_scoring_active"] = True
                    
                    if topic == "user_activity_anomalous":
                        state["anomalous_activity"].appendleft({"time": ts, "user_id": user_id, **value})
                    
                    if topic == "fraud_analysis_results":
                        state["alerts"].appendleft({"time": ts, **value})

                        # Categorize severity based on risk_score
                        risk_score = value.get("risk_score", 0)
                        if risk_score >= 80:
                            severity = "Critical"
                        elif risk_score >= 60:
                            severity = "High"
                        elif risk_score >= 40:
                            severity = "Medium"
                        else:
                            severity = "Low"

                        # Initialize user entry if needed
                        if user_id not in state["user_alert_counts"]:
                            state["user_alert_counts"][user_id] = {
                                "Critical": 0,
                                "High": 0,
                                "Medium": 0,
                                "Low": 0
                            }

                        # Increment severity count
                        state["user_alert_counts"][user_id][severity] += 1

                        state["risk_history"].appendleft({
                            "time": ts,
                            "score": value.get("risk_score", 0),
                            "user_id": user_id,
                        })

                    ts_buckets = state["timeseries"]
                    if not ts_buckets or ts_buckets[0]["bucket"] != bucket:
                        ts_buckets.appendleft({
                            "bucket": bucket,
                            "transactions": 0,
                            "user_logins": 0,
                            "account_changes": 0,
                            "user_activity_anomalous_enriched": 0,
                            "fraud_analysis_results": 0,
                        })
                    ts_buckets[0][topic] = ts_buckets[0].get(topic, 0) + 1
    finally:
        consumer.close()


def get_shared_state():
    if "initialized" not in st.session_state:
        st.session_state.state = {
            "events": deque(maxlen=MAX_EVENTS),
            "alerts": deque(maxlen=MAX_ACTIVITY_EVENTS),
            "anomalous_activity": deque(maxlen=MAX_ACTIVITY_EVENTS),
            "scored_windows": deque(maxlen=MAX_ACTIVITY_EVENTS),
            "counters": {},
            "users": set(),
            "timeseries": deque(maxlen=TIMESERIES_BUCKETS),
            "risk_history": deque(maxlen=MAX_ACTIVITY_EVENTS),
            "user_alert_counts": {},
            "arima_scoring_active": False,
        }
        st.session_state.lock = threading.Lock()
        t = threading.Thread(
            target=kafka_polling_thread,
            args=(st.session_state.state, st.session_state.lock),
            daemon=True,
        )
        t.start()
        st.session_state.initialized = True

    return st.session_state.state, st.session_state.lock


def severity_label(score):
    if score >= 80:
        return "critical", "CRITICAL"
    elif score >= 60:
        return "high", "HIGH"
    elif score >= 40:
        return "medium", "MEDIUM"
    return "low", "LOW"


def actions_html(actions):
    if not actions:
        return "—"
    known = {"freeze_account", "flag_transaction", "notify_user"}
    return "".join(
        f'<span class="action-chip action-{a if a in known else "other"}">{a}</span>'
        for a in actions
    )


def render_metrics(state):
    txn = state["counters"].get("transactions", 0)
    login = state["counters"].get("user_logins", 0)
    changes = state["counters"].get("account_changes", 0)
    anomalies = state["counters"].get("anomalous_transactions", 0)
    alerts = state["counters"].get("fraud_alerts", 0)
    unique = len(state["users"])

    anomaly_rate = (anomalies / txn * 100) if txn > 0 else 0

    alerts_list = list(state["alerts"])
    risk_scores = [a.get("risk_score", 0) for a in alerts_list]
    high_risk = sum(1 for s in risk_scores if s >= 70)
    avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0

    c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
    c1.metric("Transactions", f"{txn:,}")
    c2.metric("Logins", f"{login:,}")
    c3.metric("Acct Changes", f"{changes:,}")
    c4.metric("ARIMA Anomalies", f"{anomalies:,}")
    c5.metric("Anomaly Rate", f"{anomaly_rate:.1f}%")
    c6.metric("Fraud Alerts", f"{alerts:,}")
    c7.metric("High Risk", high_risk)
    c8.metric("Unique Users", unique)

    return alerts_list, avg_risk


def render_charts(state):
    st.markdown('<p class="section-header">Activity Monitor</p>', unsafe_allow_html=True)

    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.caption("Alerts by User (Top 5)")
        user_counts = state["user_alert_counts"]
        if user_counts:
            # Sort users by severity priority: Critical desc, High desc, Medium desc, Low desc
            sorted_users = sorted(
                user_counts.items(),
                key=lambda x: (x[1]["Critical"], x[1]["High"], x[1]["Medium"], x[1]["Low"]),
                reverse=True
            )[:5]

            # Build DataFrame with one row per user-severity combination
            data = []
            user_order = []
            for user_id, severity_counts in sorted_users:
                total = sum(severity_counts.values())
                user_label = f"{user_id} ({total})"
                user_order.append(user_label)

                for severity in ["Critical", "High", "Medium", "Low"]:
                    count = severity_counts[severity]
                    if count > 0:  # Only include non-zero severities
                        data.append({
                            "User": user_label,
                            "Severity": severity,
                            "Count": count,
                            "UserID": user_id  # For tooltip
                        })

            if data:
                df = pd.DataFrame(data)

                # Define severity order and colors
                severity_order = ["Critical", "High", "Medium", "Low"]
                severity_colors = {
                    "Critical": "#d32f2f",    # Dark red
                    "High": "#f57c00",        # Orange
                    "Medium": "#fbc02d",      # Yellow
                    "Low": "#388e3c"          # Green
                }

                # Create stacked bar chart
                chart = (
                    alt.Chart(df)
                    .mark_bar(cornerRadiusEnd=4, opacity=0.85)
                    .encode(
                        x=alt.X("Count:Q", title="Alert Count", axis=alt.Axis(labelColor="#8888aa", gridColor="#2a2a4a")),
                        y=alt.Y(
                            "User:N",
                            sort=user_order,  # Maintain severity-based sort order
                            title=None,
                            axis=alt.Axis(labelColor="#c0c0e0")
                        ),
                        color=alt.Color(
                            "Severity:N",
                            scale=alt.Scale(
                                domain=severity_order,
                                range=[severity_colors[s] for s in severity_order]
                            ),
                            legend=alt.Legend(title="Severity", orient="right")
                        ),
                        order=alt.Order("SeverityOrder:Q"),  # Stack in correct order
                        tooltip=[
                            alt.Tooltip("UserID:N", title="User"),
                            alt.Tooltip("Severity:N", title="Severity"),
                            alt.Tooltip("Count:Q", title="Count")
                        ]
                    )
                    .transform_calculate(
                        # Add numeric order for stacking (Critical=0, High=1, Medium=2, Low=3)
                        SeverityOrder="{'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}[datum.Severity]"
                    )
                    .properties(height=max(len(user_order) * 45, 120))
                )
                st.altair_chart(chart.configure_view(stroke=None), width='stretch')
        else:
            st.info("No fraud alerts yet...")

    with chart_right:
        st.caption("Fraud Alert Risk Scores")
        risk_data = list(state["risk_history"])
        if risk_data:
            risk_data.reverse()
            df = pd.DataFrame(risk_data)
            df["severity"] = df["score"].apply(
                lambda s: "Critical" if s >= 80 else "High" if s >= 60 else "Medium" if s >= 40 else "Low"
            )
            points = (
                alt.Chart(df)
                .mark_circle(size=120, opacity=0.85)
                .encode(
                    x=alt.X("time:N", title=None, axis=alt.Axis(labelAngle=-45, labelColor="#8888aa", gridColor="#2a2a4a")),
                    y=alt.Y("score:Q", title="Risk Score", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(labelColor="#8888aa", gridColor="#2a2a4a")),
                    color=alt.Color(
                        "severity:N",
                        scale=alt.Scale(
                            domain=["Critical", "High", "Medium", "Low"],
                            range=["#ef5350", "#ff8c00", "#ffd700", "#44bb44"],
                        ),
                        legend=alt.Legend(orient="bottom", title=None, labelColor="#c0c0e0"),
                    ),
                    tooltip=["time", "user_id", "score", "severity"],
                )
                .properties(height=300)
            )
            rule = (
                alt.Chart(pd.DataFrame({"y": [70]}))
                .mark_rule(color="#ef5350", strokeDash=[4, 4], opacity=0.5)
                .encode(y="y:Q")
            )
            st.altair_chart((points + rule).configure_view(stroke=None), width='stretch')
        else:
            st.info("Waiting for fraud alerts...")


def render_alerts_table(alerts_list):
    st.markdown('<p class="section-header">Recent Fraud Analysis (fraud_analysis_results)</p>', unsafe_allow_html=True)
    if not alerts_list:
        st.info("No fraud alerts yet. Waiting for the Flink agent to produce alerts...")
        return

    widths = [1, 1.3, 0.8, 1, 4, 2]
    header = st.columns(widths)
    for col, title in zip(header, ["Severity", "User", "Score", "Time", "Reasoning", "Actions"]):
        col.markdown(f"**{title}**")

    for a in alerts_list[:15]:
        score = a.get("risk_score", 0)
        cls, label = severity_label(score)
        user = a.get("user_id", "?")
        reasoning = a.get("reasoning", "")[:150]
        actions = actions_html(a.get("actions_taken", []))
        alert_time = a.get("time", "")

        cols = st.columns(widths)
        with cols[0]:
            st.markdown(f'<span class="severity-{cls}">{label}</span>', unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f"**{user}**")
        with cols[2]:
            st.markdown(f"Score: **{score}**")
        with cols[3]:
            st.markdown(f'<span class="ts-highlight">{alert_time}</span>', unsafe_allow_html=True)
        with cols[4]:
            st.markdown(f"{reasoning}")
        with cols[5]:
            st.markdown(actions, unsafe_allow_html=True)


def render_anomalous_activity(anomalous_list, user_filter=""):
    st.markdown('<p class="section-header">Anomalous User Activity (user_activity_anomalous, filtered)</p>', unsafe_allow_html=True)
    if not anomalous_list:
        st.info("No anomalous activity detected yet...")
        return

    # Apply user filter if provided
    if user_filter:
        filtered = [a for a in anomalous_list if user_filter.lower() in a.get("user_id", "").lower()]
    else:
        filtered = anomalous_list
    
    # Return early if no matches after filtering
    if not filtered:
        st.info(f"No anomalous activity found for user filter: '{user_filter}'")
        return

    widths = [1, 1.3, 1, 1.5, 1.5, 1.8, 4]
    header = st.columns(widths)
    for col, title in zip(header, ["Time", "User", "Txns", "Total $", "Average $", "Average $ Range", "Details"]):
        col.markdown(f"**{title}**")

    for a in filtered[:15]:
        user = a.get("user_id", "?")
        txn_count = a.get("txn_count", 0)
        total = a.get("total_amount", 0)
        avg = a.get("avg_amount", 0)
        lower = a.get("lower_bound")
        upper = a.get("upper_bound")
        if lower is not None and upper is not None:
            range_str = f"${lower:.2f} - ${upper:.2f}"
        else:
            range_str = "—"
        profile = a.get("profile_text", "")[:100]
        alert_time = a.get("time", "")

        cols = st.columns(widths)
        with cols[0]:
            st.markdown(f'<span class="ts-highlight">{alert_time}</span>', unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f"**{user}**")
        with cols[2]:
            st.text(txn_count)
        with cols[3]:
            st.markdown(f"**${total:.2f}**")
        with cols[4]:
            st.text(f"${avg:.2f}")
        with cols[5]:
            st.text(range_str)
        with cols[6]:
            st.text(profile)


def render_scored_windows(scored_list, user_filter=""):
    st.markdown('<p class="section-header">Scored User Windows (user_activity_scored, filtered)</p>', unsafe_allow_html=True)
    if not scored_list:
        st.info("No scored windows yet...")
        return

    # Apply user filter if provided
    if user_filter:
        filtered = [s for s in scored_list if user_filter.lower() in s.get("user_id", "").lower()]
    else:
        filtered = scored_list
    
    # Return early if no matches after filtering
    if not filtered:
        st.info(f"No scored windows found for user filter: '{user_filter}'")
        return

    widths = [1, 1.3, 1, 1.5, 1.5, 1.8, 1.2, 4]
    header = st.columns(widths)
    for col, title in zip(header, ["Time", "User", "Txns", "Total $", "Average $", "Average $ Range", "Status", "Details"]):
        col.markdown(f"**{title}**")

    for s in filtered[:20]:
        user = s.get("user_id", "?")
        txn_count = s.get("txn_count", 0)
        total = s.get("total_amount", 0)
        avg = s.get("avg_amount", 0)
        lower = s.get("lower_bound")
        upper = s.get("upper_bound")
        if lower is not None and upper is not None:
            range_str = f"${lower:.2f} - ${upper:.2f}"
        else:
            range_str = "—"
        is_anomaly = s.get("is_anomaly")
        if is_anomaly is True:
            status = "🔴 ANOMALY"
        elif is_anomaly is False:
            status = "🟢 Normal"
        else:
            status = "⏳ Pending"
        profile = s.get("profile_text", "")[:100]
        alert_time = s.get("time", "")

        cols = st.columns(widths)
        with cols[0]:
            st.markdown(f"`{alert_time}`")
        with cols[1]:
            st.markdown(f"**{user}**")
        with cols[2]:
            st.text(txn_count)
        with cols[3]:
            st.text(f"${total:.2f}")
        with cols[4]:
            st.text(f"${avg:.2f}")
        with cols[5]:
            st.text(range_str)
        with cols[6]:
            st.markdown(status)
        with cols[7]:
            st.text(profile)


def render_event_feed(events_snapshot, user_filter=""):
    st.markdown('<p class="section-header">Live Event Feed (transactions, user_logins, account_changes)</p>', unsafe_allow_html=True)
    
    if not events_snapshot:
        st.info("No events yet. Make sure the producer is running...")
        return

    # Filter to only show transactions, account_changes, user_logins
    allowed_topics = ["transactions", "account_changes", "user_logins"]
    filtered_events = [e for e in events_snapshot if e["topic"] in allowed_topics]

    # Apply user filter if provided
    if user_filter:
        filtered_events = [e for e in filtered_events if user_filter.lower() in e["user_id"].lower()]
    
    # Return early if no matches after filtering
    if not filtered_events:
        st.info(f"No events found for user filter: '{user_filter}'")
        return

    header = st.columns([1, 1.5, 2, 6])
    header[0].markdown("**Time**")
    header[1].markdown("**Topic**")
    header[2].markdown("**User**")
    header[3].markdown("**Details**")

    for e in filtered_events[:50]:
        topic = e["topic"]
        color = TOPIC_COLORS.get(topic, "#999")
        cols = st.columns([1, 1.5, 2, 6])
        with cols[0]:
            st.text(e["time"])
        with cols[1]:
            st.markdown(
                f'<span class="topic-dot" style="background:{color}"></span>{topic}',
                unsafe_allow_html=True,
            )
        with cols[2]:
            st.text(e["user_id"])
        with cols[3]:
            st.text(e["summary"])


# The live panels refresh via fragments (run_every) rather than a `time.sleep(); st.rerun()`
# loop. The frontend positions elements by index and only prunes leftovers from earlier runs
# when a run finishes normally; a script that always ends in st.rerun() never does, so when
# the user filter changed how many rows a section emitted, stale rows from the old layout
# stayed on screen (duplicate feed panels, rows inheriting another table's extra columns).
@st.fragment(run_every=REFRESH_SECONDS)
def render_arima_status(state, lock):
    with lock:
        arima_active = state["arima_scoring_active"]
    if arima_active:
        st.markdown('<span style="color: #4fc3f7; font-size: 0.85rem; font-weight: 600;">✓ ARIMA scoring active</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span style="color: #fbc02d; font-size: 0.85rem; font-weight: 600;">⏳ ARIMA scoring pending: not enough history</span>', unsafe_allow_html=True)


@st.fragment(run_every=REFRESH_SECONDS)
def render_dashboard(state, lock):
    user_filter = st.session_state.get("user_filter", "")

    with lock:
        snapshot = {
            "counters": dict(state["counters"]),
            "users": set(state["users"]),
            "alerts": list(state["alerts"]),
            "anomalous_activity": list(state["anomalous_activity"]),
            "scored_windows": list(state["scored_windows"]),
            "events": list(state["events"]),
            "timeseries": list(state["timeseries"]),
            "risk_history": list(state["risk_history"]),
            "user_alert_counts": dict(state["user_alert_counts"]),
        }

    alerts_list, avg_risk = render_metrics(snapshot)

    st.markdown("")
    render_charts(snapshot)

    st.markdown("")
    render_alerts_table(alerts_list)

    st.markdown("")
    render_anomalous_activity(snapshot["anomalous_activity"], user_filter)

    st.markdown("")
    render_scored_windows(snapshot["scored_windows"], user_filter)

    st.markdown("")
    render_event_feed(snapshot["events"], user_filter)


def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    state, lock = get_shared_state()

    # Header with ARIMA status and filter
    title_col, status_col, filter_col = st.columns([2, 1.5, 1])
    with title_col:
        st.markdown("## :shield: Fraud Detection Dashboard v2")
    with status_col:
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        render_arima_status(state, lock)
    with filter_col:
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        st.text_input("Filter Events by User ID", value="", key="user_filter", label_visibility="collapsed", placeholder="Filter by User ID")

    render_dashboard(state, lock)


if __name__ == "__main__":
    main()
