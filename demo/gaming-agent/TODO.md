# TODO.md — things the user runs

Claude writes code but **does not run anything** (see `DESIGN.md` §0). This file is the
checklist of everything that needs to be executed, with pass criteria. Run each section after
Claude finishes the matching build step, then report results back. Claude appends new items as
it writes more code.

## One-time prerequisites

- [ ] `cp terraform/terraform.tfvars.example terraform/terraform.tfvars` and fill in the 4
      credentials + `identifier`/`region`. (AWS IAM user needs Bedrock model access granted in
      the console for the configured Claude model.)
- [ ] `python3 -m venv venv && ./venv/bin/pip install -r requirements.txt`
- [ ] `colima start` (only before building the tools JAR, step 5)
- [ ] Streamlit headless: `printf '[general]\nemail = ""\n' > ~/.streamlit/credentials.toml`

## Step 1 — Scaffold

- [ ] `cd terraform && terraform fmt -recursive && terraform init -backend=false && terraform validate`
      → "The configuration is valid."
      (Claude previously ran this once before the no-run rule was set; it passed. Re-run to confirm.)
- [ ] `bash -n start-*.sh stop-all.sh status.sh` → no output.

## Step 2 — Source tables + generator

Code written: `terraform/flink.tf` (3 source tables), `producer/{gamedata,kafka_io,generate_events}.py`,
`scripts/verify_topics.py`. None of it has been run.

- [ ] Static checks:
      `cd terraform && terraform fmt -recursive && terraform init && terraform validate`
      and `./venv/bin/python -m py_compile producer/*.py scripts/verify_topics.py`
- [ ] `cd terraform && terraform apply` (also writes `../.env`). If `player_profiles` failed earlier
      (raw key error), the failed statement is tainted; a plain re-apply recreates it.
- [ ] Confirm the 3 `create-table-player-*` statements are `COMPLETED` (Flink workspace, or the
      REST pattern in the fraud repo's AGENTS.md §2).
- [ ] In a Flink workspace: `SHOW CREATE TABLE player_profiles;` → expect `changelog.mode = upsert`,
      PRIMARY KEY (`player_id`), key format avro-registry. In Schema Registry, expect subjects
      `player_profiles-key`, `player_profiles-value`, `player_combat_events-value`,
      `player_activity-value`.
- [ ] Seed profiles: `./venv/bin/python producer/generate_events.py --seed-only`, then
      `./venv/bin/python scripts/verify_topics.py --from-beginning --seconds 20 player_profiles`
      → 53 distinct keys (45 simulated + 8 `demo-*`), no deserialization errors.
- [ ] `./start-producer.sh` (leave running ~2 min), then
      `./venv/bin/python scripts/verify_topics.py --seconds 40 player_combat_events player_activity player_profiles`
      → all 3 topics receive messages. Combat should be mostly `DAMAGE_TAKEN` with only a few
      `DEATH`/`REVIVE`; activity a mix of `LOGIN`/`STORE_VIEW`/`QUEST_*`/`LOGOUT`; profiles arrive on
      the heartbeat (every ~5 s all 53 re-emitted) plus occasional level-ups/purchases.
      (Producer stdout is buffered when backgrounded — verify by consuming, not by `run/producer.log`.)
- [ ] No `demo-*` player appears in combat/activity:
      `verify_topics.py --filter player_id=demo-whale player_combat_events` → 0 messages.
- [ ] Sanity check in Flink that normal play is below the future filter (informal):
      `SELECT player_id, COUNT(*) FROM player_combat_events WHERE event_type = 'DEATH' GROUP BY player_id;`
      — no player should be accumulating deaths in bursts. Report anything surprising.

If something fails, tell Claude which. Likely suspects: (a) `CREATE TABLE player_profiles` rejecting
an option (`key.format`, `value.fields-include`, `kafka.cleanup-policy`) → drop/adjust that
option; (b) Avro serialization errors on nullable/array fields → compare the registered schema
(`player_profiles-value`) against `PROFILE_SCHEMA` in `producer/kafka_io.py`.

## Step 3 — Enrichment prototype

Code written: `sql/prototypes/03-enrichment.sql` (SQL only; not part of Terraform yet). Needs the
Step 2 checks passing and the producer running (`./start-producer.sh`).

- [ ] Open a Flink workspace on the demo environment/cluster and run each numbered block of
      `sql/prototypes/03-enrichment.sql` as its own statement, in order (0, Q1, Q2, Q3a–d, Q4).
- [x] Q1 reported: works (115 DEATH rows in 5 min, profile columns filled; `monthly_cap` null = no cap). First ~dozens of rows had `lag_s` 200–280 s (backlog read from earliest offsets), then `lag_s` < 20 s steady.
- [ ] Q2/Q3a first attempt failed (session window planned as `GroupAggregate`, updating changelog). SQL revised
      (group only by `player_id` + window cols; `game_id` via `MAX()`), with a new **Q2-pre `EXPLAIN`** block.
      Re-run: Q2-pre first (paste the plan's window node + changelogMode, or the error), then Q2, then Q3.
- [x] Q2 (after fix) reported: runs; `lag_s` ~15 s; `monthly_cap` null (expected for uncapped players).
- [ ] Heartbeat default is now 5 s (was 20 s). Restart the producer, re-run Q2, and report whether `lag_s` drops
      (expect roughly 5–8 s if the heartbeat was the bottleneck). Then run Q3. To check caps:
      `SELECT `player_id`, `monthly_cap`, `spend_30d` FROM `player_profiles` WHERE `monthly_cap` IS NOT NULL;` → 4 rows
      (3 simulated capped players + `demo-capped`).
- [x] Q5 (reported): windowed query alone `lag_s` 3–8 s. So the window/watermark is fine; the earlier 15–40 s was contention and/or the join (see Step 4 re-check).
- [x] Q2 with 5 s heartbeat: `lag_s` ~25 s (no better than 15 s with the 20 s heartbeat → heartbeat is NOT the main bottleneck).
- [x] Q3 reported: scratch table has `$rowtime` as `*ROWTIME*` (default `SOURCE_WATERMARK()`), `window_time` is a plain
      `TIMESTAMP_LTZ(3)` (time attribute lost); `$rowtime` runs ~40 s AFTER `window_time` (it is write time, not event time);
      3c temporal join on `$rowtime` runs but `lag_s` ~3 min.
- [x] Q3 re-run with read-uncommitted (reported): `$rowtime` is a time attribute but is write time; `kafka_ts - window_time` is 15–40 s and
      rows land in batches (e.g. 12 rows stamped 22:14:43.33, 5 at 22:15:09.45, 8 at 22:15:22.30); 3c temporal join on `$rowtime` adds
      another 10–20 s. **Decision: join inside the windowing query (Q2 shape); `player_struggle_enriched` is a projection stage.**
- [ ] Remaining open item: the window itself fires 15–40 s after `window_time` (so ~30–50 s after the last event). Q5 below decides the fix.
- [x] (superseded by the line above) Isolation level: the scratch CTAS in the first Q3 run lacked `kafka.consumer.isolation-level = read-uncommitted`, so 3b/3c
      likely waited on checkpoint commits (explains much of the ~40 s `$rowtime` offset and the ~3 min lag). SQL fixed. Drop the old
      `scratch_windowed` (stop the CTAS first), re-run 3a/3b/3c, and report the new `kafka_ts - window_time` gap and 3c `lag_s`.
      (Q1/Q2/Q5 read only producer-written source tables, so this does not explain Q2's 25 s.)
- [ ] Q5 (new): stop all other prototype statements, then run block Q5 alone and report steady-state `lag_s` and the
      `SET;` output. (Pool is 10 CFU; concurrent prototype statements may be inflating every lag number.)
- [ ] Report back, per block: works / fails (paste the error verbatim), and the typical `lag_s`.
      Specifically:
  - **Q1** — temporal join of raw events to `player_profiles` returns DEATH rows with profile columns?
  - **Q2** — join on `window_time` inside the windowing query works? → enrichment can live in `player_encounters`.
  - **Q3** — does `$rowtime` on the scratch (materialized) table give a working temporal join? Is
    `window_time` still a time attribute there, and does `$rowtime` ≈ `window_time` or wall-clock? →
    decides whether `player_struggle_enriched` can be a separate stage.
  - **Q4** — does output dry up when profiles stop heartbeating?
- [ ] Clean up Q3: stop the `scratch_windowed` CTAS statement, then run: DROP TABLE `scratch_windowed`;
      (deletes the scratch topic; fine, it's ours).

Decision table (Claude picks based on your results):
| Q2 | Q3 | Pipeline shape |
|----|----|----|
| ok | ok | `player_encounters` → `player_struggle_moments` → separate `player_struggle_enriched` (join on `$rowtime`) — matches DESIGN. |
| ok | fails | Join inside `player_encounters`; `player_struggle_enriched` becomes a plain projection/prompt-formatting stage. |
| fails | — | Fallback: option 2 (regular join; discouraged by the skill — unbounded state, changelog clash), then option 3 (`get_player_profile` agent tool). |

## Step 4 — Encounters → struggle moments + trigger UI

Code written: `terraform/flink.tf` (`player_encounters`, `player_struggle_moments`),
`game-trigger/app.py` + `game-trigger/templates/index.html`. Not run.

Before applying, clean up the prototypes (they share the 10-CFU pool with the real pipeline and inflate latency):
- [ ] Stop every prototype statement (Q1/Q2/Q3/Q5 SELECTs and the `scratch_windowed` CTAS), then
      run: DROP TABLE `scratch_windowed`;
- [ ] `cd terraform && terraform fmt -recursive && terraform validate && terraform apply`
- [ ] `player_encounters` and `player_struggle_moments` statements are `RUNNING` (not FAILED). If creating
      `player_encounters` fails, paste the error — likeliest causes: the planner falling back to an updating
      `GroupAggregate` (extra GROUP BY key), or `ARRAY` columns through the join. (`EXPLAIN` of the query in the
      workspace shows `changelogMode=[I]` throughout when it is right.)
- [ ] With the producer running (`./start-producer.sh`; it must be on, its heartbeat feeds the join):
      `SELECT * FROM player_encounters;` → one row per player scene, profile columns filled in, `deaths` ≤ 2.
- [ ] Normal play stays quiet: after ~10 min, `SELECT COUNT(*) FROM player_struggle_moments;` → 0
      (a stream, so watch it; it should not increase). If a simulated player appears, send me the row.
- [ ] `pip install -r requirements.txt` (venv), then `./start-game-trigger.sh` → http://localhost:8080
- [ ] Press each button (one at a time; each burst takes about 30 s) and check, in a workspace:
      `SELECT player_id, trigger_reason, deaths, single_killer, killer_id, quest_fails, store_views, tier, is_minor, monthly_cap,
              TIMESTAMPDIFF(SECOND, TO_TIMESTAMP_LTZ(last_death_ts, 3), CURRENT_TIMESTAMP) AS secs_since_last_death
       FROM player_struggle_moments;`
  | Button | Expect in `player_struggle_moments` |
  |---|---|
  | Boss wall | `demo-boss-wall`, `BOSS_WALL`, deaths 5, `single_killer` true, `killer_id` cinder_wyrm |
  | Gear gap | `demo-gear-gap`, `GEAR_GAP`, deaths 4, store_views 2 |
  | Rage-quit risk | `demo-rage-quit`, `RAGE_QUIT_RISK`, deaths 4, quest_fails 1, logouts 1 |
  | Same struggle, two profiles | two rows: `demo-f2p` (tier F2P) and `demo-whale` (tier whale), both `BOSS_WALL` |
  | Guardrail: minor / capped | `demo-minor` (`is_minor` true) / `demo-capped` (`monthly_cap` 100, spend_30d 100), `BOSS_WALL` |
  | Control | **no row** for `demo-veteran` (check `player_encounters` instead: a row with deaths 2) |
- [ ] Report the typical `secs_since_last_death` (this is the latency the demo cares about; includes the 12 s gap).
- [ ] Clean latency re-check of the prototype question: with only the real pipeline running (prototypes stopped), what is
      `secs_since_last_death` now? Earlier prototype runs (Q2 ~25 s lag, Q5 3–8 s) were taken with other statements competing,
      so this separates "pool contention" from "join cost".

## Step 5 — Tools + agent

Code written: `tools-udf/` (Maven project + 3 Java tools), `terraform/agent.tf` (artifact, functions, tools,
agent, `player_struggle_enriched`, `player_offer_recommendations`). Not built, not applied. **Finish Step 4 verification
first** (the pipeline up to `player_struggle_moments` must work).

Build the JAR once (local JDK 17 or 21 + Maven; the pom compiles for Java 11, which Confluent Cloud needs):
- [ ] `brew install maven` if `mvn -v` fails. `build.sh` prefers JDK 21 (then 17) via `/usr/libexec/java_home` even if Maven's default is
      newer (e.g. 27); its first lines print the JDK it is using. Override with `export JAVA_HOME=...` if needed.
- [ ] `cd tools-udf && ./build.sh` → prints three classes under `io/confluent/gamingdemo/`
      (`GetOfferCatalog`, `CheckOfferEligibility`, `CreateOffer`, plus `Catalog`). Send me any compile error.
- [ ] Commit `tools-udf/target/gaming-tools.jar` (the `.gitignore` un-ignores it): `git add tools-udf/target/gaming-tools.jar`.
- [x] JAR built (user). `terraform/agent.tf.pending` was renamed to `terraform/agent.tf`.

Then deploy and verify:
- [ ] `cd terraform && terraform fmt -recursive && terraform validate && terraform apply`
- [ ] DDL statements `create-fn-*`, `create-tool-*`, `create-agent-offer-*` are `COMPLETED`; `player_struggle_enriched` and
      `player_offer_recommendations` are `RUNNING`. Likely failure points (send the error verbatim):
      `JSON_STRING(owned_skus)` unsupported; `CURRENT_TIMESTAMP` rejected in the results query; the multi-line prompt
      string; tool `description` length.
- [ ] `SELECT player_id, trigger_reason, prompt_text FROM player_struggle_enriched;` — read one `prompt_text`: it should be
      readable multi-line text with real newlines and every field filled (`owned_skus` as a JSON array).
- [ ] Press buttons (one at a time) and watch
      `SELECT player_id, trigger_reason, offer_type, sku, discount_pct, price, channel, suppressed, suppress_reason, rationale,
              TIMESTAMPDIFF(SECOND, TO_TIMESTAMP_LTZ(last_death_ts, 3), offered_at) AS secs_last_death_to_offer
       FROM player_offer_recommendations;`
  | Button | Expect |
  |---|---|
  | Boss wall | `paid_offer`, `fire_resist_bundle` (counters `cinder_wyrm`), discount 0–30, `suppressed` false |
  | Gear gap | `paid_offer`, `reactor_suit_mk2` (or `weapon_mod_kit`) |
  | Rage-quit risk | `free_gift` or `hint`, **not** `paid_offer`; channel `push` |
  | Two profiles | `demo-f2p`: discount ~20–30%; `demo-whale`: ~0–10% (and not the SKUs it owns) |
  | Guardrail: minor | `suppressed` **true**, reason mentions `player_is_minor`, offer_type `free_gift`/`hint` |
  | Guardrail: capped | `suppressed` **true**, reason `monthly_cap_reached`, free alternative |
  | Control | nothing |
- [ ] Report `secs_last_death_to_offer` (the headline latency) and any row where `offer_type` or `suppressed` is wrong.
- Regression checks: if `player_offer_recommendations` goes FAILED after a few minutes, the agent hardening regressed
  (prompt, `handle_exception`, `max_consecutive_failures`). If a `latest`-offset consumer stops seeing new `player_encounters`
  rows while inputs grow, the 5 s idle-timeout regressed (session options only apply at creation).

## Step 6 — Dashboard

Code written: `dashboard/app.py` (Streamlit, :8501). Not run. Needs Steps 4–5 working and the Streamlit credentials file
from the prerequisites (`~/.streamlit/credentials.toml` with an empty email).

- [ ] `python3 -m py_compile dashboard/app.py` (venv python), then `./start-dashboard.sh`
      and `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501/_stcore/health` → `200`
      (`./start-all.sh` also starts the producer and trigger UI).
- [ ] Open http://localhost:8501 (dashboard) and http://localhost:8080 (trigger). The dashboard reads from `latest`, so keep the
      producer running and press buttons AFTER the dashboard is up.
- [ ] Check, with the producer running and no buttons pressed: the event counters, **Encounters** table and **Live event feed**
      fill; struggle moments, popups and decisions stay empty.
- [ ] Press **Boss wall**, wait ~30–60 s: a row appears in Struggle moments, then Agent decisions, and a blue **popup card**
      ("Died to Cinder Wyrm 5×? …, −N%, $price") appears. **Avg: last death → offer** is populated and the latency bar chart
      shows a bar.
- [ ] Press **Guardrail: minor** and **Guardrail: spend-capped**: an amber **popup** (“Blocked by guardrail: …”, with a free
      alternative) and a **SUPPRESSED** chip in the decisions table. **Rage-quit risk**: a green/teal free gift or hint card.
- [ ] Filters: the Game dropdown and the player text box narrow every panel (try `demo-whale`).
- [ ] Report: anything blank/broken, the typical "Secs" value, and whether the popup cards read well enough for a live demo.
- Likely trouble: a field that arrives as an unexpected type (send the traceback from `run/dashboard.log`; Streamlit swallows
  some errors into the page itself); `offered_at` showing as `—` latency (timestamp logical type).

## Run-time gotchas

- Changing a plain Flink statement's SQL needs `terraform apply -replace="module.<name>.confluent_flink_statement.this"`.
- Python stdout is buffered when backgrounded; verify by consuming topics.
- `terraform apply` needs your Confluent + AWS credentials.
- Tear down: `cd terraform && terraform destroy`.
