# DESIGN.md — Gaming "Player Struggle → Offer" Streaming Agent Demo

Hand-off design doc for building this repo. It was distilled from a brainstorming session in
the fraud demo repo. Treat it as the starting plan, not a spec: once code exists, the code is
the source of truth, and this doc should be updated or retired.

**Reference implementation:** `../fraud-agent`
(local clone of `confluentinc/demo-confluent-fraud-agent`). Read its `AGENTS.md` first. It
documents the architecture, conventions, and hard-won gotchas this repo reuses.

---

## 0. Working agreement: Claude writes, the user runs

Claude's job in this repo is to **write and edit files** (Terraform, Flink SQL, Java, Python,
shell scripts, docs). Claude does **not run anything**:

- no `terraform init` / `validate` / `plan` / `apply` / `destroy`
- no running the producer, trigger UI, dashboard, or any `start-*.sh` / `stop-all.sh` / `status.sh`
- no building the tools JAR (no Docker / Maven), no `pip install`, no consuming topics
- no Flink statement submission or REST calls against Confluent Cloud

Read-only inspection of local files (and syntax-free reading of the fraud reference repo) is fine.
Every step that needs something executed (validation, deploy, verification, prototyping) goes in
[`TODO.md`](TODO.md) as a checklist for the user, with the exact commands and the pass criteria.
When Claude finishes a build step, it appends the matching run/verify items to `TODO.md`.

---

## 1. Goal & audience

- **Audience:** A multi-tenant game infrastructure provider. They serve many third-party games, so the demo
  should be **multi-tenant**: one pipeline serving several games, each with its own catalog.
- **Story:** A player is struggling (e.g. dying repeatedly to the same boss) and is at risk of
  quitting. Within seconds, Confluent Cloud spots the struggle, enriches it with who the
  player is, and a Streaming Agent (Bedrock Claude) decides the best intervention. Usually
  that's a relevant product offer. **Sometimes it decides not to sell** (minor, spend cap,
  recently offered) and gives a free hint or gift instead.
- **Positioning:** Lead with player experience, retention, and **responsible monetization**.
  The guardrail moment ("the agent refused to upsell a minor") should land harder than "the
  agent sold a potion." Also push latency: an offer after the player has quit is worthless,
  which is the case for streaming over batch.
- Same architecture shape as the fraud demo: 2–3 input topics → windowing / filtering /
  enrichment in Flink → LLM agent makes a decision → results topic → dashboard.

## 2. Repo strategy (decided)

- **Separate repo** (this one), seeded by copying and adapting from the fraud repo. We are
  **not** building a config-driven generic engine. The SQL, prompt, tools, generator, trigger,
  and dashboard *are* the demo.
- Keep a clean seam between **platform** and **scenario** pieces, so a shared
  `platform` Terraform module and `common/` Python package can be extracted later (when a
  third scenario exists).

| Platform (copy ~as-is from fraud repo) | Scenario-specific (rewrite) |
|---|---|
| `terraform/main.tf`: env, cluster, Schema Registry, compute pool, service account, API keys, ACLs, locals | Source tables, materialized tables, prompt, agent (`terraform/flink.tf`) |
| Bedrock connection + `CREATE MODEL` | Agent tools (UDF JAR and/or MCP) |
| `terraform/modules/flink-statement/`, `terraform/connect.tf` (writes `.env`), `terraform/variables.tf`, `terraform.tfvars.example` | Generator personas and event shapes |
| `start-*.sh`, `stop-all.sh`, `status.sh`, `requirements.txt`, `.streamlit/config.toml` | Trigger buttons (adapt `fraud-trigger/`) |
| Avro + SASL producer/consumer config loaded from `.env` | Dashboard (adapt `dashboard/app.py`) |

Suggested file split in Terraform: keep `main.tf` platform-only, and put all scenario Flink
objects in `flink.tf` (or `scenario.tf`). Rename resource and name prefixes away from "fraud".

Don't carry over: `flink_archive.tf`, `app_old.py`, `generate_events_small.py`,
`generate_events_local.py`, `agent/models.py`, fraud-specific users (`user-049`/`user-050`).

## 3. Topics (topic = Flink table name, snake_case, Avro, Flink owns the schema)

| Topic | Kind | Fields (draft) |
|---|---|---|
| `player_combat_events` | append, high volume | `event_id`, `game_id`, `player_id`, `match_id`, `event_type` (`DAMAGE_TAKEN` / `DEATH` / `REVIVE`), `damage_amount`, `source_id` (boss/enemy/pvp player), `source_type`, `zone_id`, `player_level`, `timestamp` |
| `player_activity` | append | `event_id`, `game_id`, `player_id`, `activity_type` (`LOGIN`, `QUEST_FAIL`, `QUEST_COMPLETE`, `STORE_VIEW`, `ITEM_EQUIP`, `PURCHASE`, `LOGOUT`), `item_id`, `detail`, `timestamp` |
| `player_profiles` | **upsert / compacted, PK = `player_id`** | `game_id`, `player_class`, `level`, `tier` (F2P / spender / whale), `lifetime_spend`, `spend_30d`, `monthly_cap`, `is_minor`, `region`, `owned_skus`, `last_purchase_ts`, `updated_at` |

**As built (step 2):** `damage_amount`/`player_level`/`level` are `INT`; `item_id`, `detail`,
`monthly_cap`, `last_purchase_ts` are nullable (`monthly_cap` NULL = no cap); `owned_skus` is
`ARRAY<STRING>`; `player_profiles` has PK `player_id` with an Avro key and a 1 s watermark on
`updated_at`; event watermarks are 2 s. See `terraform/flink.tf` and `producer/kafka_io.py`.

The two event streams get windowed. The profile stream is **enrichment** (a lookup), not
another windowed feed. As in the fraud repo, `event_time` is a computed
`TO_TIMESTAMP_LTZ(timestamp, 3)` column with a watermark, and the producer encodes against
Flink's registered schema (`use.latest.version=True`, `auto.register.schemas=False`).

## 4. Pipeline (Flink materialized tables)

```
player_combat_events ┐
                     ├─UNION ALL─► [player_encounters]              SESSION window per player
player_activity ─────┘               deaths, damage_taken, top_killer_id, deaths_to_top_killer,
                                     zone, quest_fails, store_views, logout_seen, activity text
                                  ─► [player_struggle_moments]       rule-based filter
                                  ─► [player_struggle_enriched]      + player_profiles → prompt text
                                  ─► [player_offer_recommendations]  AI_RUN_AGENT(...) → parse JSON
                                  (optional) ─► player_offers        consumed by a fake game client
```

- **Window:** SESSION per `player_id` with a ~10–15 s gap, so one encounter is one window. The
  alternative is HOP (e.g. 2 min size / 15 s slide) for "rolling frustration" across several
  attempts. Latency = gap + watermark, so keep both small.
- **Filter (start rule-based):** e.g. `deaths_to_top_killer >= 3 OR (deaths >= 4 AND quest_fails > 0)`.
  Same "pre-filter before the LLM" story as ARIMA in the fraud demo, without the warm-up.
- **ARIMA (optional, stretch):** `ML_DETECT_ANOMALIES` on deaths per encounter. It gives a
  personal-baseline story ("5 deaths is normal for a new player, a red flag for a veteran"),
  but it needs ≥50 windows per player before it flags anything.
- **Agent output (JSON, parsed like the fraud repo, `REGEXP_EXTRACT` then `JSON_VALUE`):**
  `offer_type` (paid_offer / free_gift / hint / none), `sku`, `discount_pct`, `price`,
  `channel` (in_game_popup / push / email), `suppressed`, `suppress_reason`, `rationale`,
  `confidence`. Carry the encounter stats and key profile fields through as columns for the
  dashboard.

### Enrichment: the riskiest piece, so write and test it first

Options, in order of preference:

1. **Temporal join** to `player_profiles` (`FOR SYSTEM_TIME AS OF e.event_time`). Best story:
   enrichment happens in the stream and is visible in Stream Lineage. Pitfalls:
   - Time attributes are lost on materialized-table / CTAS outputs (see the fraud repo's
     `ARIMA_ENHANCEMENT.md`). The join probably needs to happen on raw events **before /
     inside** the windowing query in `player_encounters`.
   - The versioned table's watermark stalls if the profile topic goes quiet, which stalls the
     join. Fix: pin the idle-timeout and have the generator **re-emit profiles periodically**
     as a heartbeat.
2. **Regular join after windowing.** Simpler, but profile changes produce an updating
   changelog, which may clash with `changelog.mode = append`.
3. **`get_player_profile` agent tool.** Always works, but it's slower and the enrichment is no
   longer visible in Flink or Lineage. Last-resort fallback.

Claude writes the option-1 SQL (`sql/prototypes/03-enrichment.sql`, which also tests whether `$rowtime` gives a usable time attribute downstream of a materialized table — the fraud repo's notes say attributes are lost, the Bob skill's trap table says `$rowtime` survives); the user runs it and reports back (see `TODO.md`, step 3). The skill also advises against option 2 (a regular join against an upsert topic retains the whole table in state). If it
fights back, Claude switches to option 2, then 3, based on the user's findings.

## 5. Agent & tools

Split: **player data is enriched in the stream; catalog and actions are agent tools.**

- `get_offer_catalog(game_id, player_class, level, zone_id, source_id)` returns SKUs that
  counter this boss or zone, with prices. This is the "the platform exposes an API" moment.
- `check_offer_eligibility(player_id)` checks minor status, spend caps, and offer cooldown
  (the guardrail).
- `create_offer(player_id, sku, discount_pct, ttl_s, channel)` is the action (analogous to
  `freeze_account` in the fraud demo).

**Watch out:** the agent runs in Confluent Cloud, so a local FastAPI on `localhost` cannot be
reached. As far as we know, Confluent Cloud UDFs also can't make outbound network calls.

- **v1:** mock Java UDF tools with the catalog built into the JAR (same pattern as
  `tools-udf/` in the fraud repo). Reliable for the demo.
- **v2:** a real API exposed as an **MCP server** that the agent reaches through a connection
  (`CREATE TOOL ... USING CONNECTION`). Host it somewhere publicly reachable (Lambda / Cloud
  Run / ngrok for the demo). **Syntax is unverified.** Check it against
  `confluentinc/quickstart-streaming-agents` before building.

**As built (step 5):** `check_offer_eligibility(player_id, is_minor, spend_30d, monthly_cap, last_purchase_ts)` takes
the profile values as string arguments (a UDF has no state; the agent copies them from the prompt) and its "cooldown"
is a proxy: a purchase in the last 15 minutes. `create_offer` is also used for free gifts/hints (`free_comeback_gift`,
`free_boss_hint`). The tool JAR is built locally with Maven (`tools-udf/build.sh`) and committed.

Prompt: reuse the fraud repo's hardened agent prompt structure (decide first, make all tool
calls up front, never reverse a call, final message = the single JSON object only). Make the
guardrail rules explicit in the prompt (minor / cap / cooldown → `suppressed=true`, free
alternative).

## 6. Generator (`producer/`)

- About 30–60 players across 2–3 **fictional** games (avoid real game IP), each with its own
  zones, bosses, and catalog. `game_id` is on every event.
- Personas: casual, grinder, pro/veteran, whale, minor, capped spender. Each has its own death
  rate, damage, store-browsing frequency, and profile values.
- On startup, seed all profiles to `player_profiles`. Update them on events (a `PURCHASE`
  raises spend, players level up). **Re-emit profiles periodically** (watermark heartbeat;
  see §4).
- Normal play stays **below** the filter threshold, so the agent is quiet until a trigger
  button is pressed.

## 7. Trigger UI (adapt `fraud-trigger/`, FastAPI on :8080)

| Button | Burst sent | Expected agent result |
|---|---|---|
| Boss wall | 5 deaths to the same boss in ~40 s | Counter item for that boss (e.g. fire-resist bundle) |
| Gear gap | Low level in a high-level zone, heavy damage, store views | Gear upgrade bundle |
| Rage-quit risk | Deaths → failed quest → `LOGOUT` | **Free** comeback gift or hint, not a paid item |
| Same struggle, two profiles | Identical burst for a F2P player and a whale | Different offers (shows enrichment matters) |
| Guardrail: minor or capped player | Boss wall on a minor / capped profile | `suppressed=true` + reason; agent declines to sell |
| Control | A veteran dies twice | Nothing reaches the agent (shows the filter working) |

Use dedicated demo players for buttons (like `user-049`/`user-050` in the fraud repo), with
profiles chosen to make each scenario clean.

## 8. Dashboard (adapt `dashboard/app.py`, Streamlit on :8501)

- Same layout as the fraud dashboard: metrics, then live event feed, encounters, struggle
  moments, and recommendations; player/game filter.
- Add a mock **in-game popup card** (e.g. "Died to Ice Golem 4×? Frost Ward Bundle −30%"),
  plus a visible "suppressed" state for guardrail cases.
- Add a **"seconds from last death to offer"** metric, which makes the streaming-latency point.
- Consumers must set `isolation.level = read_uncommitted` (Flink sinks commit transactionally on checkpoint; the default read-committed would show results late). Every Flink table in this repo sets `kafka.consumer.isolation-level = read-uncommitted` too.
- Keep the fraud dashboard's patterns: `st.fragment(run_every=…)` (not `st.rerun()` loops),
  consume from `latest` with a fresh group id, and coerce JSON-array strings back to lists.

## 9. Gotchas to carry over (from the fraud repo's AGENTS.md; see it for detail)

Design/code constraints Claude must respect when writing files. Run-time gotchas (Streamlit
headless, buffered stdout, colima, credentials) live in `TODO.md`.

- **Agent hardening:** `CREATE AGENT` fails the statement after `max_consecutive_failures`
  bad runs. Use the hardened prompt, `handle_exception = 'continue'`, and
  `max_consecutive_failures = '5'`.
- **Watermark idle-timeout:** pin `sql.tables.scan.idle-timeout = '5 s'` in `session_options`
  of the **windowing** materialized table. Otherwise output arrives as an early burst and then
  dries up as the statement ages. Session options apply only at creation.
- **Time attributes survive only on base tables.** Windowing (and probably temporal joins) on
  a materialized-table timestamp column fails, so keep them in the first query.
- **Materialized tables** update in place when `query` changes; plain `confluent_flink_statement`s
  (agent, tools, model) need `terraform apply -replace=...`. Omit `columns` blocks on
  materialized tables (provider 2.87.0 sends a type string the API rejects).
- **Flink SQL string literals don't process backslash escapes** (regex is passed literally).
- **Bedrock model id lives in the connection endpoint URL**, not in `CREATE MODEL`.
- **Dashboard:** use `st.fragment(run_every=…)`, not `st.rerun()` loops.

## 10. Suggested build order

Each step is **Claude writes the code** → user runs the matching `TODO.md` section and reports
results. Claude does not proceed past a step whose verification failed.

1. Scaffold: copy the platform pieces, rename prefixes. Write this repo's `AGENTS.md` early.
   *(Written.)*
2. Source tables + generator (`flink.tf` source tables, `producer/generate_events.py`).
3. **Enrichment** (§4, option 1) written as its own isolated SQL. Fall back if it fights back.
4. `player_encounters` → `player_struggle_moments`, plus the trigger UI that should produce
   struggle moments (normal play shouldn't).
5. Mock UDF tools (Java source only) + agent + `player_offer_recommendations`.
6. Dashboard + popup card + latency metric.
7. Stretch: MCP-backed catalog API, ARIMA baseline, `player_offers` consumer, demo
   walkthrough doc.
