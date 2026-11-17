# AGENTS.md

Guidance for working in this repository.

## What this is

A Confluent Cloud demo for a multi-tenant game infrastructure provider: a player is struggling
(e.g. dying repeatedly to one boss), Flink spots it, enriches it with who the player is, and a
**Streaming Agent** (Bedrock Claude) picks the best intervention — usually a relevant offer, but
sometimes a free hint/gift instead (minor, spend cap, recent offer). Lead with player
experience and responsible monetization; the "agent refused to upsell a minor" moment is the
point. Same shape as the fraud demo: input topics → Flink windowing/filter/enrichment → LLM
agent → results topic → dashboard.

**`DESIGN.md` is the starting plan, not a spec.** Once code exists, the code is the source of
truth; update or retire `DESIGN.md` accordingly. Build order is in `DESIGN.md` §10.

**Reference implementation:** `../fraud-agent`
(`confluentinc/demo-confluent-fraud-agent`). Its `AGENTS.md` documents the gotchas this repo
inherits; platform files here were copied from it and renamed.

## Status

- [x] Step 1 — scaffold (platform Terraform, scripts, config) — deployed
- [x] Step 2 — source tables + generator — verified by the user
- [x] Step 3 — enrichment prototype (`sql/prototypes/03-enrichment.sql`) — decided: temporal join inside `player_encounters`
- [x] Step 4 — `player_encounters` + `player_struggle_moments` + trigger UI — verified (normal play quiet, buttons produce expected rows; ~20 s last death → moment, dominated by the 12 s session gap)
- [x] Step 5 — Java tools, agent, enriched + recommendations (`tools-udf/`, `terraform/agent.tf`) — deployed, spot-checked by the user
- [x] Step 6 — dashboard written (`dashboard/app.py`); user verification pending in `TODO.md`
- [x] Demo walkthrough doc written (`demo.md`, no screenshots yet)
- Stretch items (MCP-backed catalog API, ARIMA baseline, `player_offers` consumer) intentionally not planned.

## Repository map

| Path | Purpose |
|------|---------|
| `terraform/main.tf` | **Platform only.** Env, cluster, Schema Registry, compute pool (10 CFU), service account, API keys, ACLs, `locals` (prefix `<identifier>-gaming-agent`, Bedrock endpoint, catalog/database). |
| `terraform/flink.tf` | Bedrock connection, `flink_common` locals, `CREATE MODEL offer_model`. **Scenario Flink objects (source tables, materialized tables, tools, agent) go here too** (or a `scenario.tf`) — keep `main.tf` platform-only. |
| `terraform/connect.tf` | Writes the repo-root `.env` consumed by the local apps. |
| `terraform/variables.tf`, `terraform.tfvars.example` | Inputs: Confluent key/secret, AWS Bedrock key/secret, `identifier`, `region`, `bedrock_model_id`. |
| `terraform/modules/flink-statement/` | Thin wrapper around `confluent_flink_statement`. |
| `producer/gamedata.py` | Games (zones/bosses/enemies/SKUs), personas, simulated roster, and the 8 fixed `demo-*` players. **Boss/zone/SKU ids must match the UDF catalog** (step 5). |
| `producer/kafka_io.py` | `.env` loading, Avro schemas (must match the `CREATE TABLE`s), Avro+SASL producer, `produce_event`/`produce_profile`. Reused by the trigger UI. |
| `producer/generate_events.py` | Normal-play simulator (stays below the struggle filter); seeds + heartbeats profiles. Flags: `--speed`, `--heartbeat-secs`, `--seed-only`, `--duration`, `--rng-seed`. |
| `sql/prototypes/` | Throwaway Flink SQL the user runs in a workspace to answer design questions (not deployed by Terraform). |
| `tools-udf/` | Maven project for the 3 mock agent tools (`get_offer_catalog`, `check_offer_eligibility`, `create_offer`) + `build.sh` (local JDK 17/21 + Maven; compiles for Java 11). The built `target/gaming-tools.jar` is committed. |
| `terraform/agent.tf` | Step 5 Terraform: tools JAR artifact, functions, tools, agent, `player_struggle_enriched`, `player_offer_recommendations`. |
| `scripts/verify_topics.py` | Consumes Avro topics and prints counts/samples (for the user to run). |
| `game-trigger/` | FastAPI trigger UI on :8080 (`app.py`, `templates/index.html`): 7 buttons driving the `demo-*` players; imports `producer/gamedata.py` + `kafka_io.py`. Burst pace via `TRIGGER_PACE_S` (default 6 s between deaths; keep well under the 12 s session gap). |
| `dashboard/app.py` | Streamlit on :8501: metrics, mock in-game popup cards (paid / free gift / hint / **suppressed**), latency chart (seconds from last death to offer), decisions, struggle moments, encounters, live feed; game + player filters. Consumes from `latest`, `read_uncommitted`, fragment refresh. |
| `start-*.sh`, `stop-all.sh`, `status.sh` | Background service management; logs and PIDs in `run/`. |
| `.streamlit/config.toml` | Dark theme for the dashboard. |
| `images/architecture.svg` | Architecture diagram (sources → input topics → Flink stages → agent + tools → dashboard), embedded in `demo.md`. Hand-written SVG; edit the file directly. |
| `summary.md` | Data walkthrough: what's in each topic, how the producer generates it, each pipeline stage and why, with the fraud-repo analogue for each. |
| `README.md` | Overview, prerequisites, deploy/run/tear-down steps, repo map. |
| `demo.md` | ~20-minute presenter walkthrough: Stream Lineage tour, Flink pipeline, then the six trigger scenarios with expected results, the latency story, and likely Q&A. |
| `TODO.md` | Everything the user must run (deploy, verify, prototype), with pass criteria. |

Deliberately **not** carried over from the fraud repo: `flink_archive.tf`, `app_old.py`,
`generate_events_small.py`, `generate_events_local.py`, `agent/models.py`, fraud-specific users,
and the fraud tools JAR. Keep the platform/scenario seam clean so a shared `platform` Terraform
module and `common/` Python package can be extracted once a third scenario exists.

## Working agreement: write, don't run

Claude writes and edits files only. **Do not run** `terraform` (any subcommand), the producer,
trigger UI, dashboard, `start-*.sh` / `stop-all.sh` / `status.sh`, Docker/Maven builds,
`pip install`, or anything that touches Confluent Cloud. Put every run/verify step (commands +
pass criteria) in `TODO.md` for the user. See `DESIGN.md` §0.

## Flink SQL skill

Before writing any Flink SQL / DDL, load the **`confluent-cloud-flink-sql`** skill
(`.claude/skills/confluent-cloud-flink-sql/`, adapted from a Bob skill): Confluent Cloud Flink is
not OSS Flink. Start with `references/dialect-traps.md`. Its run/verify steps are converted into
`TODO.md` items here (Claude doesn't run anything). Prefer an event-time temporal join over a regular
join for profile enrichment, and use `SESSION(TABLE t PARTITION BY key, ...)` for per-player sessions.

## Conventions & constraints (inherited — see the fraud repo's AGENTS.md for detail)

- **Inputs.** Only the 4 credentials + `identifier`/`region` (+ optional `bedrock_model_id`).
  Don't add user-facing variables without reason. Never commit `terraform.tfvars` or `.env`.
- **Bedrock model id lives in the connection endpoint URL**, not in `CREATE MODEL`.
- **`player_profiles` is an upsert/compacted table** (PK `player_id`, **Avro** key, `value.fields-include = all`; a `raw` key is rejected unless the column is named `key`). The producer keys the event topics by `player_id` as a plain string and `player_profiles` with an Avro `{player_id}` key (`build_key_serializers`). The generator re-emits profiles every ~5 s (watermark heartbeat for the temporal join).
- **Read-uncommitted everywhere.** Flink sinks write transactionally and commit on checkpoint, so any reader left at the default (read-committed) sees rows only after the commit — seconds to minutes late. Every Flink table here sets `'kafka.consumer.isolation-level' = 'read-uncommitted'` (source tables in `WITH`, materialized tables in `table_options`, CTAS in `WITH`), and every Python consumer sets `"isolation.level": "read_uncommitted"` (`scripts/verify_topics.py`, the dashboard).
- **Topic = Flink table name**, snake_case, Avro, **Flink owns the schema**. Producer encodes
  with `use.latest.version=True` / `auto.register.schemas=False`; physical columns only (the
  computed `event_time` is not in the value schema).
- **Time attributes survive only on base tables.** Windowing (and probably temporal joins) on a
  materialized-table timestamp column fails — keep them in the first query.
- **Materialized tables** update in place when `query` changes; plain `confluent_flink_statement`s
  (agent, tools, model) need `terraform apply -replace="module.<name>.confluent_flink_statement.this"`.
  Omit `columns` blocks on materialized tables (provider 2.87.0 sends a type string the API rejects).
  `session_options` apply only at creation.
- **Pin `sql.tables.scan.idle-timeout = '5 s'`** in `session_options` of the windowing
  materialized table, or output bursts then dries up as the statement ages.
- **Harden the agent:** hardened prompt, `handle_exception = 'continue'`,
  `max_consecutive_failures = '5'`, otherwise `CREATE AGENT` fails after 3 bad runs.
- **Flink SQL string literals don't process backslash escapes.**
- **Agent tools can't call `localhost`** (agent runs in Confluent Cloud). v1 = mock Java UDFs
  with the catalog baked into the JAR; v2 = MCP server via a connection (syntax unverified —
  check `confluentinc/quickstart-streaming-agents` first).
- **Dashboard:** `st.fragment(run_every=…)`, not `st.rerun()` loops; consume from `latest` with a
  fresh group id; coerce JSON-array strings back to lists. Streamlit headless needs
  `~/.streamlit/credentials.toml` with an empty email and `--server.headless true`.
- **Backgrounded Python stdout is buffered** — verify by consuming topics, not reading logs.
- **Docker runtime is colima** (`colima start` before building the tools JAR).
- Reference for verified Streaming Agents syntax: `confluentinc/quickstart-streaming-agents`
  (checked out locally at `/Users/justin/git/justinrlee/confluentinc-quickstart-streaming-agents`).
