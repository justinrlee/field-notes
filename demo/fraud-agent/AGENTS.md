# AGENTS.md

Guidance for working in this repository.

## What this is

Real-time fraud detection running entirely on **Confluent Cloud**. Streaming user
activity is windowed by **Confluent Cloud for Apache Flink**, scored per user by an **ARIMA**
anomaly detector (`ML_DETECT_ANOMALIES`), and only the statistically anomalous sessions are
analyzed by a **Streaming Agent** (Confluent Intelligence) backed by **AWS Bedrock (Claude)**,
which emits fraud verdicts. A local Python **producer** generates synthetic events, a local
**fraud-trigger** web UI injects fraud on demand, and a local **Streamlit dashboard**
visualizes everything.

Everything except the producer, fraud-trigger, and dashboard runs in Confluent Cloud. There is
**no local Kafka/Flink** — the previous Docker/PyFlink implementation was removed.

## Architecture / data flow

```
producer / fraud-trigger (local, Avro+SASL)
  → transactions · user_logins · account_changes (topics, created by Flink CREATE TABLE)
  → [user_activity_scored]  UNION ALL the 3 streams → 3s event-time SESSION window per user
        → per-session stats + text profile → ML_DETECT_ANOMALIES (ARIMA on avg_amount, per user)
  → [user_activity_anomalous]           WHERE is_anomaly AND avg_amount > upper_bound
  → [user_activity_anomalous_enriched]  prepends ARIMA context to profile_text
  → [fraud_analysis_results]  AI_RUN_AGENT(fraud_detection_agent, enriched_profile_text, user_id)
        [Bedrock Claude + 3 UDF tools] → parse JSON verdict
  → dashboard (local, Avro+SASL; consumes all of the above)
```

The four pipeline stages are **Flink materialized tables**
(`confluent_flink_materialized_table`), each owning its table definition *and* continuous
query, so they are chained tables/topics that show as nodes in Stream Lineage. Source tables,
`CREATE MODEL`, functions, tools, and the agent are plain `confluent_flink_statement`s via the
`terraform/modules/flink-statement` wrapper. Everything is defined inline in `terraform/flink.tf`.

ARIMA is deliberately a **pre-filter**: it flags unusual spending, the agent then does
contextual analysis (geo-impossibility, account takeover, etc.) and decides actions. See
`ARIMA_ENHANCEMENT.md` for the design history (why windowing happens before ARIMA / time
attribute pitfalls); it is partly historical — the code is the source of truth.

## Repository map

| Path | Purpose |
|------|---------|
| `terraform/main.tf` | Env, cluster, Schema Registry, compute pool (10 CFU), service account, API keys, ACLs, and `locals` (prefix, Bedrock endpoint, catalog/database). |
| `terraform/flink.tf` | Bedrock connection, tools artifact upload, source tables (`tbl_*` modules), the 4 materialized tables (`user_activity_scored` → `user_activity_anomalous` → `user_activity_anomalous_enriched` → `fraud_analysis_results`), `CREATE MODEL`, `CREATE FUNCTION`/`CREATE TOOL` ×3, and `CREATE AGENT` (`module.agent`). |
| `terraform/flink_archive.tf` | **Fully commented-out** legacy pipeline (pre-materialized-table `CREATE TABLE`/`INSERT` statements incl. `fraud_alerts`). Reference only; slated for removal. |
| `terraform/connect.tf` | Writes the repo-root `.env` consumed by the local apps. |
| `terraform/variables.tf` | Inputs: Confluent key/secret, AWS Bedrock IAM key/secret, plus `identifier`, `region`, `bedrock_model_id` (see Conventions). |
| `terraform/modules/flink-statement/` | Thin reusable wrapper around `confluent_flink_statement`. |
| `tools-udf/` | Java UDF tools (`flag_transaction`, `freeze_account`, `notify_user`) + the committed `target/fraud-tools.jar`. |
| `producer/generate_events.py` | Synthetic event generator (Avro + SASL_SSL). 50 users with spending profiles; modes: default (normal only), `--fraud`, `--both` (fraud after cycle 50), `--single-fraud`. |
| `producer/generate_events_small.py` | Variant with only 10 users. |
| `producer/generate_events_local.py` | **Work in progress.** Variant for a local/self-managed Kafka + Schema Registry (mTLS, env-configured topics, self-registering schema). Not wired into `.env`/Terraform; not a supported entry point. |
| `fraud-trigger/` | FastAPI web UI (port 8080) with 6 buttons (3 fraud scenarios × `user-049`/`user-050`) that send fraud events straight to Kafka for on-demand demos. Has its own README + `requirements.txt`. |
| `dashboard/app.py` | Streamlit dashboard (Avro + SASL_SSL). Sections: metrics, Activity Monitor charts, Recent Fraud Analysis, Anomalous User Activity, Scored User Windows, Live Event Feed; user-ID filter; "ARIMA scoring active/pending" indicator. |
| `dashboard/app_old.py` | Previous dashboard version, kept for reference. |
| `start-all.sh` `start-producer.sh` `start-dashboard.sh` `start-fraud-trigger.sh` `stop-all.sh` `status.sh` | Background service management; logs and PID files in `run/`. See `RUNNING.md`. |
| `agent/models.py` | Pydantic data-model reference only — not imported at runtime. |
| `demo.md` | ~15-min presenter walkthrough (Stream Lineage → Flink job → dashboard); screenshots in `images/demo/`. Linked from the README. Text matches the current pipeline, but the screenshots predate it (earlier `activity_profiles`/`fraud_alerts` flow); the demo notes this. |
| `RUNNING.md` | Quick reference for the start/stop/status scripts. |

## Commands

```bash
# Deploy everything (also writes .env)
cd terraform && terraform init && terraform apply

# Run apps (after deploy)
pip install -r requirements.txt
./start-all.sh [--both|--fraud|--single-fraud]   # producer + fraud-trigger (:8080) + dashboard (:8501)
./status.sh ; ./stop-all.sh
# or individually:
python producer/generate_events.py
streamlit run dashboard/app.py

# Tear down
cd terraform && terraform destroy

# Validate Terraform without credentials
cd terraform && terraform fmt -recursive && terraform validate

# Rebuild the tools JAR (maintainers only; needs Docker — colima/Docker Desktop)
cd tools-udf && ./build.sh    # then commit target/fraud-tools.jar
```

## Key conventions & constraints

- **Inputs.** Required secrets are the 4 credentials (Confluent key/secret, AWS key/secret).
  `identifier` (name prefix) and `region` have no default and are set in `terraform.tfvars`;
  `bedrock_model_id` defaults to a `global.` Sonnet 4.5 inference profile (use a regional
  `us.`/`eu.`… id for other regions — see `terraform.tfvars.example`). Sizing and resource
  names are fixed in `terraform/main.tf`. Don't add user-facing variables without reason.
- **Bedrock model id lives in the connection endpoint URL** (`local.bedrock_model_id` →
  `local.bedrock_endpoint`), NOT in `CREATE MODEL`.
- **Topic = Flink table name**, snake_case: sources `transactions`, `user_logins`,
  `account_changes`; pipeline `user_activity_scored`, `user_activity_anomalous`,
  `user_activity_anomalous_enriched`, `fraud_analysis_results`. The dashboard `TOPICS` list and
  the SQL must stay in sync if renaming.
- **Avro, Flink owns the schema.** Source tables are created by Flink (`CREATE TABLE`,
  default avro-registry, 6 buckets). The producer serializes with `use.latest.version=True` /
  `auto.register.schemas=False` so it encodes against Flink's registered schema. Producer
  Avro field names/order must match the table columns; physical columns only (the computed
  `event_time` is not in the value schema).
- **Windowing lives in `user_activity_scored`.** It unions the 3 streams and applies an
  event-time `SESSION` window (3s gap, partitioned by `user_id`). SESSION (not `TUMBLE`) so a
  fraud burst is never split across windows. `event_time` is a computed
  `TO_TIMESTAMP_LTZ(`timestamp`, 3)` column with a 5s watermark. Time attributes survive only
  on base tables — windowing a CTAS/materialized-table timestamp column fails (see
  `ARIMA_ENHANCEMENT.md`), which is why windowing + ARIMA are in one query.
- **ARIMA runs on per-session `avg_amount`** via `ML_DETECT_ANOMALIES ... OVER (PARTITION BY
  user_id ORDER BY window_time ...)` (`minTrainingSize` 50, `maxTrainingSize` 128,
  `confidencePercentage` 99.95, no STL). Until a user has ≥50 sessions the model produces no
  anomalies, so **nothing reaches the agent until baselines build** (hence `--both` starts fraud
  at cycle 50, and the dashboard's "ARIMA scoring pending: not enough history" indicator).
  `user_activity_anomalous` keeps only `is_anomaly AND avg_amount > upper_bound` (spend spikes,
  not dips). The producer's `fraud_target` users (`user-049`/`user-050`) have low baselines so
  fraud on them is very anomalous.
- **Materialized tables are updatable in place.** Changing a `query` on a
  `confluent_flink_materialized_table` doesn't need `-replace` (unlike plain statements).
  They omit `columns` blocks on purpose: provider 2.87.0 sends a flat type string the REST API
  rejects (500); schemas are inferred from the query. Each sets `session_options` for
  catalog/database; `changelog.mode = append` and read-uncommitted isolation.
- **Agent output is parsed from free text.** `AI_RUN_AGENT` returns a `response` STRING; the
  `fraud_analysis_results` query extracts the JSON object via `REGEXP_EXTRACT` then
  `JSON_VALUE`/`JSON_QUERY`. `actions_taken` / `flagged_transaction_ids` are stored as
  JSON-array strings; the dashboard coerces them back to lists. Columns also carry the ARIMA
  context (`expected_amount`, `upper_bound`, `lower_bound`, `window_total`, …).
- **The 3 agent tools are mocks** (return a confirmation string, no side effect) but are
  genuinely invoked by the agent. Editing them means editing Java + rebuilding the JAR.
- **Flink SQL string literals don't process backslash escapes** — regex like `'\{[\s\S]*\}'`
  is passed literally to the Java regex engine (intended).
- **Dashboard styling:** custom CSS in `app.py` (`CUSTOM_CSS`) plus `.streamlit/config.toml`
  (dark base theme). Timestamps are rendered as `` `inline code` ``, so their color comes from
  Streamlit's theme `codeTextColor`/`codeBackgroundColor` (not set → built-in defaults, green on
  dark grey), not from `CUSTOM_CSS`. Dashboard live panels refresh via `st.fragment(run_every=…)`,
  not `st.rerun()` loops (stale-row bug otherwise — see the comment in `app.py`).
- **Dashboard consumes from `latest`** with a fresh group id each run, so it only shows data
  produced after it starts.

## Gotchas

- **The agent statement stalls on malformed model output if not hardened.** `CREATE AGENT`
  fails the whole statement after `max_consecutive_failures` (default **3**) consecutive bad
  agent runs — e.g. when Claude calls a tool then reverses it / "no tools needed" / emits
  non-JSON. Mitigated on `module.agent` (`flink.tf`) by: (a) a hardened prompt (decide score
  first, make all tool calls up front, never reverse a call, final message = the single JSON
  object only), (b) `handle_exception = 'continue'` (skip a bad row instead of counting it as
  a failure), and (c) `max_consecutive_failures = '5'`. **Symptom if regressed:** `fraud_analysis_results`
  goes FAILED after a few minutes and the dashboard's analysis table stops updating, even though Bedrock access is
  fine. (`handle_exception` wasn't in the docs at time of writing but is accepted by the API.)
- **Watermark idle-timeout is required for steady alerts.** Confluent Cloud's default
  "progressive idleness" grows the idle-partition timeout with statement age (10s → up to
  5 min). With 6-partition topics and a producer that only touches some users per cycle, the
  session-window watermark stalls as the statement ages → output arrives as an early burst then
  dries up. Fixed by pinning `sql.tables.scan.idle-timeout = '5 s'` in `session_options` of the
  **windowing** table (`user_activity_scored` in `flink.tf` — that's where the SESSION window
  is). Session options apply only at creation. **Symptom if regressed:** `user_activity_scored`
  grows fast at first, then stops while input topics keep filling. Output still arrives in small
  batches (window-firing is inherently batchy over keyed bursty data) — that's expected.
- **Changing a plain Flink statement's SQL or `properties` needs replace, not in-place update**
  (applies to `module.*` statements such as `module.agent`; the provider errors "stopped
  attribute must be updated…"). Use `terraform apply -replace="module.<name>.confluent_flink_statement.this"`.
  Materialized tables are the exception — edit `query` and apply (but `session_options` only
  take effect on create). A replaced INSERT/CTAS reprocesses from earliest (duplicate rows; fine
  for the demo).
- **ARIMA needs history.** `minTrainingSize = 50` sessions per user; the first alerts come only
  after a user has that many windows. After a redeploy, run the producer a while before
  expecting `user_activity_anomalous` / `fraud_analysis_results` output.
- **Streamlit's first-run email prompt blocks headless/background runs.** Write
  `~/.streamlit/credentials.toml` with `[general]\nemail = ""` and run with
  `--server.headless true`, then open `http://localhost:8501` manually.
- **You can't `terraform apply` without the user's Confluent + AWS credentials.** Validate
  with `terraform validate`.
- **Bedrock model access:** the IAM user must have model access granted in the Bedrock
  console for the configured Claude model in `us-east-1`.
- **Producer/consumer Python stdout is buffered** when backgrounded — absence of printed
  cycles ≠ failure. Verify by consuming topics, not by reading producer stdout.
- **Docker runtime here is colima**, not Docker Desktop (`colima start` before `build.sh`).
- **Pushing:** this working clone's `origin` is `justinrlee/demo-confluent-fraud-agent`; the upstream is
  `confluentinc/demo-confluent-fraud-agent`. Work on a branch. For the Confluent repo always
  push with **`git push-external`** (never bare `git push` — it's blocked); it runs a
  proprietary-code check + Airlock push.
- Reference material: the official `confluentinc/quickstart-streaming-agents` repo (esp.
  `lab4-pubsec-fraud-agents`, `lab3`) is the source for verified CC Streaming Agents syntax.

## Testing / verifying end-to-end

All checks below assume `terraform apply` has run (so `.env` exists) and the venv is set up
(`python3 -m venv venv && ./venv/bin/pip install -r requirements.txt`). Use `./venv/bin/python`
and load `.env` for connection config.

### 1. Static checks (no credentials needed)
```bash
cd terraform && terraform fmt -recursive && terraform validate
python3 -m py_compile producer/generate_events.py dashboard/app.py
unzip -l tools-udf/target/fraud-tools.jar   # 3 classes: FlagTransaction/FreezeAccount/NotifyUser
```

### 2. Deploy and confirm all statements are healthy
```bash
cd terraform && terraform init && terraform apply -auto-approve   # writes ../.env
```
Confirm Flink statements via the REST API (the CLI session often expires). Pull the Flink key
+ endpoint from state, then list statement phases — DDL (`create-table-*`, `create-model-*`,
`create-fn-*`, `create-tool-*`, `create-agent-*`) should be `COMPLETED`, and the four
materialized-table statements (`user_activity_scored`, `user_activity_anomalous`,
`user_activity_anomalous_enriched`, `fraud_analysis_results`) should be `RUNNING` (their
statement names are provider-generated; look for those table names). Materialized tables can
also be inspected via `confluent_flink_materialized_table` in `terraform show`.
```bash
cd terraform && terraform show -json > /tmp/tf.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/tf.json")); res={}
def walk(m):
    for r in m.get("resources",[]): res.setdefault(r["type"]+"."+r["name"], r["values"])
    for c in m.get("child_modules",[]): walk(c)
walk(d["values"]["root_module"])
fk=res["confluent_api_key.flink"]; reg=next(v for k,v in res.items() if "flink_region" in k)
print("FLINK_KEY="+fk["id"]); print("FLINK_SECRET="+fk["secret"]); print("FLINK_REST="+reg["rest_endpoint"])
print("ENV="+res["confluent_environment.main"]["id"]); print("ORG="+res["confluent_organization.main"]["id"])
PY
# then (substitute the printed values):
curl -s -u "$FLINK_KEY:$FLINK_SECRET" \
  "$FLINK_REST/sql/v1/organizations/$ORG/environments/$ENV/statements?page_size=50" \
  | python3 -c "import sys,json;[print(s['name'].ljust(40),s['status']['phase'],'|',(s['status'].get('detail') or '')[:80]) for s in json.load(sys.stdin)['data']]"
```

### 3. Run the producer, then verify data + alerts flow
```bash
./venv/bin/python producer/generate_events.py --both   # leave running (background ok)
```
Use `--both` (or the fraud-trigger UI): ARIMA needs ≥50 sessions per user before it flags
anything, and the default mode produces no fraud. Consume the topics to confirm input is
flowing AND verdicts are produced. Save as
`/tmp/verify.py` and run with `./venv/bin/python /tmp/verify.py`:
```python
import os, json, collections, time
from dotenv import load_dotenv
from confluent_kafka import Consumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext
load_dotenv(".env")
c=Consumer({"bootstrap.servers":os.environ["BOOTSTRAP_SERVERS"],"security.protocol":"SASL_SSL",
 "sasl.mechanisms":"PLAIN","sasl.username":os.environ["KAFKA_API_KEY"],
 "sasl.password":os.environ["KAFKA_API_SECRET"],"group.id":f"v{time.time()}","auto.offset.reset":"earliest"})
c.subscribe(["transactions","user_logins","account_changes","user_activity_scored","user_activity_anomalous","fraud_analysis_results"])
sr=SchemaRegistryClient({"url":os.environ["SCHEMA_REGISTRY_URL"],
 "basic.auth.user.info":f'{os.environ["SCHEMA_REGISTRY_API_KEY"]}:{os.environ["SCHEMA_REGISTRY_API_SECRET"]}'})
d=AvroDeserializer(sr); cnt=collections.Counter(); hi=[]; end=time.time()+40
while time.time()<end:
    m=c.poll(1.0)
    if not m or m.error(): continue
    v=d(m.value(),SerializationContext(m.topic(),MessageField.VALUE)); cnt[m.topic()]+=1
    if m.topic()=="fraud_analysis_results" and v.get("risk_score",0)>=60: hi.append(v)
c.close(); print(dict(cnt))
for a in hi[:5]: print(a["risk_score"], a["user_id"], a["actions_taken"], "-", a["reasoning"][:80])
```
**Pass criteria:** all three input topics and `user_activity_scored` increase;
`user_activity_anomalous` and `fraud_analysis_results` start increasing once baselines are built
and fraud is injected; the injected scenarios yield high-risk verdicts (geo-impossible ≈90,
account-takeover ≈95) with `actions_taken` like `["freeze_account","notify_user"]` and a copied
`flagged_transaction_ids`.

In the Flink workspace you can also eyeball each stage directly:
```sql
SELECT * FROM user_activity_scored;                        -- one row per user per session window, with ARIMA bounds
SELECT * FROM user_activity_anomalous;                     -- sessions ARIMA flagged
SELECT * FROM fraud_analysis_results WHERE risk_score >= 70;   -- the high-risk verdicts
```

### 4. Confirm output keeps flowing (watermark / idle-timeout regression check)
A `latest`-offset consumer should keep seeing NEW `user_activity_scored` rows over a 60–90s
window (in small batches). If counts stall while `transactions` keeps growing, the idle-timeout fix has
regressed — see Gotchas. Topic partition counts / totals:
```bash
# get_watermark_offsets per partition summed = total messages; expect user_activity_scored to grow
```

### 5. Dashboard
```bash
printf '[general]\nemail = ""\n' > ~/.streamlit/credentials.toml   # one-time, skips prompt
./venv/bin/streamlit run dashboard/app.py --server.headless true --server.port 8501
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501/_stcore/health   # 200
```
Open `http://localhost:8501`. The dashboard reads from `latest`, so it shows data produced
after it starts — keep the producer running and allow ~1 min for a window-firing batch.

### 6. Teardown
```bash
cd terraform && terraform destroy -auto-approve
```
