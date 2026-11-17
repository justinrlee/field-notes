# Data walkthrough: what's in each topic and how the pipeline works

A guided tour of the data, for someone who knows the fraud demo (`../fraud-agent`) but not this one. It follows the data in the order it moves: the three input topics (what they hold and how the producer generates them), then each pipeline stage (what it does and why), then one worked example. The code is the source of truth: `producer/` for the data, `terraform/flink.tf` and `terraform/agent.tf` for the pipeline.

## The big picture, against the fraud demo

| | Fraud demo | This demo |
|---|---|---|
| Event streams that get windowed | 3 (`transactions`, `user_logins`, `account_changes`) | **2** (`player_combat_events`, `player_activity`) |
| Third input | none (everything is a windowed event) | **`player_profiles`**, a state topic used as a lookup, not windowed |
| What decides "worth the LLM?" | ARIMA anomaly detection on spending | A **rule-based filter** (no ARIMA, no warm-up) |
| Enrichment | ARIMA context added to the text | The player's profile joined **inside the window query** |
| Agent output | risk score and actions | an **offer decision**: paid offer, free gift, hint, or suppressed |

```
producer / trigger UI
  → player_combat_events ┐
  → player_activity ─────┴─► [player_encounters]  ◄── lookup ── player_profiles
                               session window + profile join
                             → [player_struggle_moments]       rule-based filter
                             → [player_struggle_enriched]      builds the agent's prompt text
                             → [player_offer_recommendations]  AI_RUN_AGENT → parsed decision
                             → dashboard
```

## The three input topics

All three are written by `producer/generate_events.py`. Every event is stamped with the real send time. Each topic is keyed by `player_id`, so one player's events stay in order.

### `player_combat_events`
One row per combat event.

- **Fields:** `event_id`, `game_id`, `player_id`, `match_id`, `event_type` (`DAMAGE_TAKEN`, `DEATH` or `REVIVE`), `damage_amount`, `source_id` (the boss, enemy or PvP opponent), `source_type` (`BOSS`, `ENEMY` or `PVP_PLAYER`), `zone_id`, `player_level`, `timestamp`.
- **How it's generated:** each player plays a short "scene" every 30–120 seconds: a few fights, each with 1–3 damage events. A fight sometimes ends in a death, followed by a revive. A fight is against a boss 15% of the time, otherwise a regular enemy. In Starlane Arena, 30% of fights are against another player. The zone is the highest one the player's level has unlocked.
- **Sample row (illustrative):** `DAMAGE_TAKEN, 47, source ash_cultist, zone cinder_depths`.

### `player_activity`
Everything else a player does.

- **Fields:** `event_id`, `game_id`, `player_id`, `activity_type`, `item_id` (nullable), `detail` (nullable), `timestamp`.
- **Activity types:**
  - `LOGIN`: `detail` is the region.
  - `LOGOUT`.
  - `STORE_VIEW` and `ITEM_EQUIP`: `item_id` is a SKU.
  - `QUEST_COMPLETE` and `QUEST_FAIL`: `detail` is `quest-<zone>`.
  - `PURCHASE`: `item_id` is the SKU, `detail` is the price.
- **How it's generated:** these come out of the same scenes. A scene has at most one quest outcome. Purchases are rare, and the capped persona stops buying when it reaches its cap. A player logs out after 4–8 scenes.

### `player_profiles`
A different kind of topic: a **compacted upsert topic** keyed by `player_id` that holds each player's latest state. Flink uses it as a lookup table, not as a stream to window.

- **Fields:** `player_class`, `level`, `tier` (F2P, spender or whale), `lifetime_spend`, `spend_30d`, `monthly_cap` (null means no cap), `is_minor`, `region`, `owned_skus`, `last_purchase_ts`, `updated_at`.
- **How it's generated:** the producer seeds all 53 profiles at startup: 45 simulated players (15 per game across 6 personas: 6 casual, 4 grinder, 2 veteran, 1 whale, 1 minor, 1 capped) plus 8 fixed `demo-*` players. It re-sends all profiles every 5 seconds so the join's watermark keeps moving. It also upserts a profile when a player levels up or buys something. Restarting the producer resets every profile to its starting values.

### Why normal play never triggers the agent
Normal play is deliberately kept below the filter. A scene is capped at 2 deaths and 1 failed quest, and a player's scenes are at least 25 seconds apart, which is longer than the 12-second window gap, so two scenes never merge into one encounter. The 8 `demo-*` players are not simulated at all. They only act when you press a button in the trigger UI.

## The pipeline, stage by stage

Each stage is a Flink materialized table, so it is both a topic and a node in the lineage graph.

### 1. `player_encounters` (fraud analogue: `user_activity_scored`)
- **What it does:** it unions the two event streams and groups each player's events into a **session window** that closes after 12 seconds of quiet. One window is one "encounter". For each window it computes deaths, damage taken, quest fails, store views, logouts, who the killer was, and the first, last and last-death timestamps. It then **joins the player's profile as it was at that moment** (an event-time temporal join).
- **Why a window:** it turns a stream of events into a unit that a rule or an LLM can judge, such as "5 deaths to one boss in one stretch". It is a session window, not a fixed tumbling one, so a burst never gets split.
- **Why the join is inside this query:** time attributes are lost on materialized-table outputs, and a join in a later stage measured about 10–20 seconds slower. The profile fields travel with the encounter from here on.
- **`single_killer`:** true when every death in the window came from the same source. It is computed by comparing the minimum and maximum killer ids across the window's `DEATH` events, which avoids nested aggregates.
- **Reading the topic:** one row per player per encounter. `player_id` is stored only in the Kafka **key**, not in the value, because the table has a primary key. Any consumer must read the key (the dashboard merges it into the row).
- **Latency note:** the 12-second gap is most of the delay between the last death and the encounter appearing.

### 2. `player_struggle_moments` (fraud analogue: `user_activity_anomalous`)
- **What it does:** a plain `WHERE` filter on encounters. A row passes if there were:
  - 3 or more deaths all to one source, or
  - 4 or more deaths together with a failed quest, or
  - 4 or more deaths together with a store view.
- **`trigger_reason`:** a tag added by a `CASE`. It is `RAGE_QUIT_RISK` for deaths plus a failed quest, `GEAR_GAP` for deaths plus a store view, and otherwise `BOSS_WALL`. It is a hint for the prompt and the dashboard, not a decision.
- **Why:** this is the cost and relevance control. Only real struggles reach the LLM. In the fraud demo, ARIMA did this job; a rule filter needs no history and no warm-up, which is why this demo works the moment it starts. Thresholds are in the query and can be changed in place.
- **Reading the topic:** same shape as encounters, plus `trigger_reason`. `player_id` is again only in the key.

### 3. `player_struggle_enriched` (fraud analogue: `user_activity_anomalous_enriched`)
- **What it does:** a projection that builds `prompt_text`, the readable multi-line description the agent is given: the trigger, the player, the account (tier, minor status, spend, monthly cap, owned items) and the encounter. It also carries forward the columns the dashboard needs.
- **Why:** it keeps prompt formatting separate from the decision and gives the lineage graph a visible step. The profile data was already joined in stage 1, so this stage is only formatting.

### 4. `player_offer_recommendations` (fraud analogue: `fraud_analysis_results`)
- **What it does:** `AI_RUN_AGENT(offer_agent, prompt_text, player_id)` runs the agent on each moment. A regex extracts the JSON object from the agent's reply and `JSON_VALUE` parses it into columns: `offer_type` (`paid_offer`, `free_gift`, `hint`, or `none`), `sku`, `discount_pct`, `price`, `channel`, `suppressed`, `suppress_reason`, `rationale`, `confidence`. It also adds `offered_at`, the wall-clock time the row was produced.
- **The agent (`offer_agent`):** Claude on Amazon Bedrock with three tools.
  - It first calls `check_offer_eligibility` (the guardrail: is a paid offer allowed for a minor, a capped player, or a recent buyer?) and `get_offer_catalog` (SKUs relevant to this boss or zone, plus free options).
  - It then decides, and calls `create_offer` at most once.
  - If paid offers aren't allowed, it must set `suppressed = true`, give the reason, and offer something free.
  - Rage-quit risk gets a free gift or hint even when paid offers are allowed. F2P players get a meaningful discount, and whales get little or none.
- **Latency metric:** the dashboard shows `offered_at` minus `last_death_ts`.
- **Reading the topic:** this table has no primary key, so `player_id` is in the value.

### What is mock
The three tools are Java functions with the catalog built into a committed JAR. `create_offer` has no real side effect. The "cooldown" in the eligibility check is a proxy: a purchase in the last 15 minutes. The data is entirely synthetic.

## One worked example: the Boss wall button
1. The trigger UI sends 5 cycles for `demo-boss-wall` (Ember Throne, level 32). Each cycle is 2 damage events, a death and a revive, about 6 seconds apart: 20 combat events in about 30 seconds.
2. They fall into **one** session window, because no gap is longer than 12 seconds. The encounter shows 5 deaths, `single_killer` true, killer `cinder_wyrm`, zone `cinder_depths`.
3. The join adds the profile: a spender, level 32, not a minor, no cap, 9.99 spent in the last 30 days, owns `healing_potion_10`.
4. The filter passes it as `BOSS_WALL`.
5. The enriched stage builds the prompt. The agent calls the eligibility and catalog tools, then proposes a relevant item such as the fire-resist bundle, at a modest discount.
6. The decision lands in `player_offer_recommendations`, and the dashboard shows the popup card.

The exact item and discount are the agent's choice, so they can vary from run to run. The other buttons follow the same path but end differently: the two guardrail buttons come back suppressed, Rage-quit comes back free, and Control never passes the filter.

## Where to look in the code
| What | Where |
|---|---|
| Event, scene and persona generation | `producer/generate_events.py`, `producer/gamedata.py` |
| Topic schemas (Avro, must match the tables) | `producer/kafka_io.py`, `terraform/flink.tf` |
| Windowing, join and filter | `terraform/flink.tf` (`player_encounters`, `player_struggle_moments`) |
| Prompt text, agent, tools, decision parsing | `terraform/agent.tf`, `tools-udf/` |
| Button scenarios | `game-trigger/app.py` |
