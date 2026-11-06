# ---------------------------------------------------------------------------
# STEP 5: UDF tools, the offer agent, the enriched prompt stage, and the results table.
# Needs tools-udf/target/gaming-tools.jar (built with tools-udf/build.sh and committed).
# ---------------------------------------------------------------------------

locals {
  # A real newline for use inside Flink SQL string literals ('${local.nl}'). Terraform heredocs do
  # NOT process "\n", but a double-quoted string does.
  nl = "\n"
}

# Pre-built UDF tools JAR (committed to the repo) uploaded as a Flink artifact.
# Demo users need no Java/Maven toolchain; Terraform just uploads the binary.
resource "confluent_flink_artifact" "tools" {
  display_name   = "${local.prefix}-tools-${random_id.suffix.hex}"
  cloud          = local.cloud_provider
  region         = local.aws_region
  content_format = "JAR"
  artifact_file  = "${path.module}/../tools-udf/target/gaming-tools.jar"
  environment {
    id = confluent_environment.main.id
  }
}

output "tools_artifact_id" {
  value       = confluent_flink_artifact.tools.id
  description = "Flink artifact id for the UDF tools JAR"
}

# ------------------------ Functions (from JAR) -----------------------------

module "fn_catalog" {
  source           = "./modules/flink-statement"
  organization_id  = local.flink_common.organization_id
  environment_id   = local.flink_common.environment_id
  compute_pool_id  = local.flink_common.compute_pool_id
  principal_id     = local.flink_common.principal_id
  rest_endpoint    = local.flink_common.rest_endpoint
  flink_api_key    = local.flink_common.flink_api_key
  flink_api_secret = local.flink_common.flink_api_secret
  catalog          = local.flink_common.catalog
  database         = local.flink_common.database
  statement_name   = "create-fn-catalog-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE FUNCTION `get_offer_catalog`
    AS 'io.confluent.gamingdemo.GetOfferCatalog'
    USING JAR 'confluent-artifact://${confluent_flink_artifact.tools.id}';
  EOT
  depends_on       = [confluent_flink_artifact.tools]
}

module "fn_eligibility" {
  source           = "./modules/flink-statement"
  organization_id  = local.flink_common.organization_id
  environment_id   = local.flink_common.environment_id
  compute_pool_id  = local.flink_common.compute_pool_id
  principal_id     = local.flink_common.principal_id
  rest_endpoint    = local.flink_common.rest_endpoint
  flink_api_key    = local.flink_common.flink_api_key
  flink_api_secret = local.flink_common.flink_api_secret
  catalog          = local.flink_common.catalog
  database         = local.flink_common.database
  statement_name   = "create-fn-eligibility-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE FUNCTION `check_offer_eligibility`
    AS 'io.confluent.gamingdemo.CheckOfferEligibility'
    USING JAR 'confluent-artifact://${confluent_flink_artifact.tools.id}';
  EOT
  depends_on       = [confluent_flink_artifact.tools]
}

module "fn_create_offer" {
  source           = "./modules/flink-statement"
  organization_id  = local.flink_common.organization_id
  environment_id   = local.flink_common.environment_id
  compute_pool_id  = local.flink_common.compute_pool_id
  principal_id     = local.flink_common.principal_id
  rest_endpoint    = local.flink_common.rest_endpoint
  flink_api_key    = local.flink_common.flink_api_key
  flink_api_secret = local.flink_common.flink_api_secret
  catalog          = local.flink_common.catalog
  database         = local.flink_common.database
  statement_name   = "create-fn-create-offer-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE FUNCTION `create_offer`
    AS 'io.confluent.gamingdemo.CreateOffer'
    USING JAR 'confluent-artifact://${confluent_flink_artifact.tools.id}';
  EOT
  depends_on       = [confluent_flink_artifact.tools]
}

# --------------------------------- Tools -----------------------------------

module "tool_catalog" {
  source           = "./modules/flink-statement"
  organization_id  = local.flink_common.organization_id
  environment_id   = local.flink_common.environment_id
  compute_pool_id  = local.flink_common.compute_pool_id
  principal_id     = local.flink_common.principal_id
  rest_endpoint    = local.flink_common.rest_endpoint
  flink_api_key    = local.flink_common.flink_api_key
  flink_api_secret = local.flink_common.flink_api_secret
  catalog          = local.flink_common.catalog
  database         = local.flink_common.database
  statement_name   = "create-tool-catalog-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TOOL `get_offer_catalog_tool`
    USING FUNCTION `get_offer_catalog`
    WITH (
      'type' = 'function',
      'description' = 'List the SKUs this game sells that are relevant to the player''s struggle, ranked by relevance, plus free options. Arguments, in order: game_id, player_class, level (integer), zone_id, source_id (the boss or enemy killing the player). Returns JSON with paid_skus (each has sku, price, relevance) and free_options.'
    );
  EOT
  depends_on       = [module.fn_catalog]
}

module "tool_eligibility" {
  source           = "./modules/flink-statement"
  organization_id  = local.flink_common.organization_id
  environment_id   = local.flink_common.environment_id
  compute_pool_id  = local.flink_common.compute_pool_id
  principal_id     = local.flink_common.principal_id
  rest_endpoint    = local.flink_common.rest_endpoint
  flink_api_key    = local.flink_common.flink_api_key
  flink_api_secret = local.flink_common.flink_api_secret
  catalog          = local.flink_common.catalog
  database         = local.flink_common.database
  statement_name   = "create-tool-eligibility-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TOOL `check_offer_eligibility_tool`
    USING FUNCTION `check_offer_eligibility`
    WITH (
      'type' = 'function',
      'description' = 'Guardrail check: is a PAID offer allowed for this player? Arguments, in order, ALL strings copied exactly from the input: player_id, is_minor (true or false), spend_30d (number), monthly_cap (number, or none), last_purchase_ts (epoch ms, or never). Returns JSON with paid_offers_allowed (boolean), reasons, cooldown_active, remaining_monthly_budget.'
    );
  EOT
  depends_on       = [module.fn_eligibility]
}

module "tool_create_offer" {
  source           = "./modules/flink-statement"
  organization_id  = local.flink_common.organization_id
  environment_id   = local.flink_common.environment_id
  compute_pool_id  = local.flink_common.compute_pool_id
  principal_id     = local.flink_common.principal_id
  rest_endpoint    = local.flink_common.rest_endpoint
  flink_api_key    = local.flink_common.flink_api_key
  flink_api_secret = local.flink_common.flink_api_secret
  catalog          = local.flink_common.catalog
  database         = local.flink_common.database
  statement_name   = "create-tool-create-offer-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TOOL `create_offer_tool`
    USING FUNCTION `create_offer`
    WITH (
      'type' = 'function',
      'description' = 'Create the offer, free gift, or hint for the player. Arguments, in order: player_id, sku (a catalog sku, or free_boss_hint, or free_comeback_gift), discount_pct (integer 0-30; ignored for free items), ttl_seconds (integer), channel (in_game_popup, push, or email). Returns JSON with status CREATED or REJECTED.'
    );
  EOT
  depends_on       = [module.fn_create_offer]
}

# --------------------------------- Agent -----------------------------------
# Hardened like the fraud agent: decide first, tool calls in a fixed order, never reverse a call, final
# message = the single JSON object only; handle_exception = 'continue' and max_consecutive_failures = '5'
# so a bad run is skipped instead of failing the whole statement after 3.
module "agent" {
  source           = "./modules/flink-statement"
  organization_id  = local.flink_common.organization_id
  environment_id   = local.flink_common.environment_id
  compute_pool_id  = local.flink_common.compute_pool_id
  principal_id     = local.flink_common.principal_id
  rest_endpoint    = local.flink_common.rest_endpoint
  flink_api_key    = local.flink_common.flink_api_key
  flink_api_secret = local.flink_common.flink_api_secret
  catalog          = local.flink_common.catalog
  database         = local.flink_common.database
  statement_name   = "create-agent-offer-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE AGENT `offer_agent`
    USING MODEL `offer_model`
    USING PROMPT 'You are a live-ops retention agent for a multi-tenant game platform. A rule-based Flink filter has
    flagged a PLAYER STRUGGLE MOMENT: a player who is struggling and may quit. Your job is to pick the single
    best intervention. Responsible monetization comes first: a player who feels exploited quits and never
    comes back, so selling is the exception, not the goal. A free hint or gift is often the right answer.

    You receive a plain-text description of ONE struggle moment: the trigger reason (BOSS_WALL, GEAR_GAP,
    or RAGE_QUIT_RISK), the player and their account (tier, is_minor, spend, monthly cap, owned items),
    and the encounter (zone, deaths, who killed them, quest fails, store views, logout seen, recent activity).

    TOOLS - FOLLOW THIS ORDER:
    1. FIRST, in one step, call BOTH check_offer_eligibility_tool and get_offer_catalog_tool. Copy their
       arguments exactly from the input (use the zone, the killer_id as source_id, and the profile values).
       Pass monthly_cap as the string none when the input says none, and last_purchase_ts as never when
       it says never.
    2. THEN decide, using only what those two tools returned.
    3. THEN call create_offer_tool AT MOST ONCE, for the single intervention you chose. Call it for a paid
       offer, a free gift, or a hint. Do not call it at all only if you decide there is nothing to offer.
    Once you call a tool, treat it as final: never reconsider it, apologize for it, or reverse it in text.

    DECISION RULES (in priority order):
    1. If paid_offers_allowed is false (a minor, the monthly cap reached, or a cooldown): you MUST NOT sell.
       Set suppressed=true and suppress_reason to the reason(s) from the tool. Instead give a FREE
       alternative: offer_type hint (sku free_boss_hint) or free_gift (sku free_comeback_gift).
    2. If the trigger is RAGE_QUIT_RISK (the player is about to quit): prefer a FREE intervention,
       free_gift or hint, even if paid offers are allowed. Do not try to sell to someone who is leaving
       in frustration. suppressed=false in this case.
    3. Otherwise (BOSS_WALL or GEAR_GAP and paid offers are allowed): offer ONE paid SKU from paid_skus.
       - BOSS_WALL: choose a SKU whose relevance is counters_source (it counters the boss killing them).
       - GEAR_GAP: choose a SKU whose relevance is gear_upgrade_for_level_gap.
       - Never offer a SKU the player already owns (see owned_skus). If none fit, give a free hint.
       - The final price (price after discount) must be at most remaining_monthly_budget when that is not null.
       - Discount by who the player is: an F2P player (lifetime spend 0) gets a meaningful discount,
         20 to 30 percent, as a first-purchase nudge. A high-spend player (whale) gets 0 to 10 percent,
         because they do not need a discount and heavy discounting devalues the item. Never exceed 30.
    4. Choose the channel: push if logout seen is greater than 0, otherwise in_game_popup.
       Use ttl_seconds 900 for popups and 3600 for push.

    CRITICAL RULES:
    - Copy the EXACT player_id string from the input. Do NOT change it.
    - offer_type must be one of: paid_offer, free_gift, hint, none.
    - For free items: price 0, discount_pct 0. For paid offers: price is the catalog price after the discount.
    - suppressed is true ONLY when a paid offer was blocked by the eligibility tool (rule 1).
    - Your FINAL message must be ONLY the single JSON object below: no preamble, no commentary, no
      self-corrections, no markdown, no code fences. Put all explanation inside "rationale", nowhere else.
    {"player_id": "<copy from input>", "offer_type": "paid_offer"|"free_gift"|"hint"|"none", "sku": "<sku or null>", "discount_pct": <0-30 integer>, "price": <number>, "channel": "in_game_popup"|"push"|"email", "suppressed": <true|false>, "suppress_reason": "<reason or empty string>", "rationale": "<one or two sentences a game designer would find sensible>", "confidence": <0.0-1.0>}'
    USING TOOLS `get_offer_catalog_tool`, `check_offer_eligibility_tool`, `create_offer_tool`
    WITH (
      'max_iterations' = '8',
      'handle_exception' = 'continue',
      'max_consecutive_failures' = '5'
    );
  EOT
  depends_on = [
    module.model,
    module.tool_catalog,
    module.tool_eligibility,
    module.tool_create_offer,
  ]
}

# ---------------------- player_struggle_enriched ----------------------------
# Formats each struggle moment (already enriched with the profile inside player_encounters) into the
# agent's prompt text. A plain projection stage, kept as its own node so the lineage shows the step.

resource "confluent_flink_materialized_table" "player_struggle_enriched" {
  organization {
    id = local.flink_common.organization_id
  }
  environment {
    id = local.flink_common.environment_id
  }
  compute_pool {
    id = local.flink_common.compute_pool_id
  }
  principal {
    id = local.flink_common.principal_id
  }
  rest_endpoint = local.flink_common.rest_endpoint
  credentials {
    key    = local.flink_common.flink_api_key
    secret = local.flink_common.flink_api_secret
  }

  display_name = "player_struggle_enriched"
  kafka_cluster {
    id = confluent_kafka_cluster.standard.id
  }

  constraints {
    name     = "player_struggle_enriched_pk"
    type     = "PRIMARY_KEY"
    columns  = ["player_id"]
    enforced = false
  }

  distribution {
    kind         = "HASH"
    keys         = ["player_id"]
    bucket_count = 6
  }

  table_options = {
    "changelog.mode"                 = "append"
    "kafka.consumer.isolation-level" = "read-uncommitted"
  }

  session_options = {
    "sql.current-catalog"  = local.flink_common.catalog
    "sql.current-database" = local.flink_common.database
  }

  query = <<-EOT
    SELECT
      `player_id`, `game_id`, `trigger_reason`, `zone_id`,
      `deaths`, `single_killer`, `killer_id`, `quest_fails`, `store_views`, `logouts`,
      `tier`, `is_minor`, `monthly_cap`, `spend_30d`, `lifetime_spend`,
      `window_end`, `first_event_ts`, `last_event_ts`, `last_death_ts`,
      CONCAT(
        'PLAYER STRUGGLE MOMENT', '${local.nl}',
        'trigger_reason: ', `trigger_reason`, '${local.nl}',
        'player_id: ', `player_id`, '${local.nl}',
        'game_id: ', `game_id`, '${local.nl}',
        'player_class: ', `player_class`, '${local.nl}',
        'level: ', CAST(`level` AS STRING), '${local.nl}',
        'region: ', `region`, '${local.nl}',
        'tier: ', `tier`, '${local.nl}',
        'is_minor: ', CAST(`is_minor` AS STRING), '${local.nl}',
        'lifetime_spend: ', CAST(`lifetime_spend` AS STRING), '${local.nl}',
        'spend_30d: ', CAST(`spend_30d` AS STRING), '${local.nl}',
        'monthly_cap: ', COALESCE(CAST(`monthly_cap` AS STRING), 'none'), '${local.nl}',
        'owned_skus: ', JSON_STRING(`owned_skus`), '${local.nl}',
        'last_purchase_ts: ', COALESCE(CAST(`last_purchase_ts` AS STRING), 'never'), '${local.nl}',
        'zone_id: ', COALESCE(`zone_id`, 'unknown'), '${local.nl}',
        'deaths: ', CAST(`deaths` AS STRING), '${local.nl}',
        'all_deaths_to_one_source: ', CAST(`single_killer` AS STRING), '${local.nl}',
        'killer_id: ', COALESCE(`killer_id`, 'none'), '${local.nl}',
        'damage_taken: ', CAST(`damage_taken` AS STRING), '${local.nl}',
        'quest_fails: ', CAST(`quest_fails` AS STRING), '${local.nl}',
        'store_views: ', CAST(`store_views` AS STRING), '${local.nl}',
        'logout_seen: ', CAST(`logouts` AS STRING), '${local.nl}',
        'recent_activity: ', `activity`
      ) AS `prompt_text`
    FROM `player_struggle_moments`
  EOT

  depends_on = [confluent_flink_materialized_table.player_struggle_moments]
}

# -------------------- player_offer_recommendations --------------------------
# Runs the agent per struggle moment and parses its JSON reply (REGEXP_EXTRACT then JSON_VALUE), like the
# fraud demo. No PRIMARY KEY/distribution block: the AI_RUN_AGENT output is plain append, round-robin.
# `offered_at` (wall clock at emit) minus `last_death_ts` is the dashboard's latency metric.

resource "confluent_flink_materialized_table" "player_offer_recommendations" {
  organization {
    id = local.flink_common.organization_id
  }
  environment {
    id = local.flink_common.environment_id
  }
  compute_pool {
    id = local.flink_common.compute_pool_id
  }
  principal {
    id = local.flink_common.principal_id
  }
  rest_endpoint = local.flink_common.rest_endpoint
  credentials {
    key    = local.flink_common.flink_api_key
    secret = local.flink_common.flink_api_secret
  }

  display_name = "player_offer_recommendations"
  kafka_cluster {
    id = confluent_kafka_cluster.standard.id
  }

  table_options = {
    "changelog.mode"                 = "append"
    "kafka.consumer.isolation-level" = "read-uncommitted"
  }

  session_options = {
    "sql.current-catalog"  = local.flink_common.catalog
    "sql.current-database" = local.flink_common.database
  }

  query = <<-EOT
    WITH `scored` AS (
      SELECT
        e.`player_id`, e.`game_id`, e.`trigger_reason`, e.`zone_id`, e.`deaths`, e.`killer_id`,
        e.`quest_fails`, e.`store_views`, e.`logouts`,
        e.`tier`, e.`is_minor`, e.`monthly_cap`, e.`spend_30d`, e.`lifetime_spend`,
        e.`window_end`, e.`first_event_ts`, e.`last_event_ts`, e.`last_death_ts`,
        e.`prompt_text`,
        CAST(r.`response` AS STRING) AS `raw_response`,
        REGEXP_EXTRACT(CAST(r.`response` AS STRING), '\{[\s\S]*\}', 0) AS `json_text`
      FROM `player_struggle_enriched` e,
      LATERAL TABLE(AI_RUN_AGENT(`offer_agent`, e.`prompt_text`, e.`player_id`)) r
    )
    SELECT
      `player_id`, `game_id`, `trigger_reason`, `zone_id`,
      JSON_VALUE(`json_text`, '$.offer_type') AS `offer_type`,
      JSON_VALUE(`json_text`, '$.sku') AS `sku`,
      CAST(JSON_VALUE(`json_text`, '$.discount_pct') AS INT) AS `discount_pct`,
      CAST(JSON_VALUE(`json_text`, '$.price') AS DOUBLE) AS `price`,
      JSON_VALUE(`json_text`, '$.channel') AS `channel`,
      COALESCE(CAST(JSON_VALUE(`json_text`, '$.suppressed') AS BOOLEAN), FALSE) AS `suppressed`,
      COALESCE(JSON_VALUE(`json_text`, '$.suppress_reason'), '') AS `suppress_reason`,
      COALESCE(JSON_VALUE(`json_text`, '$.rationale'), '') AS `rationale`,
      CAST(JSON_VALUE(`json_text`, '$.confidence') AS DOUBLE) AS `confidence`,
      `deaths`, `killer_id`, `quest_fails`, `store_views`, `logouts`,
      `tier`, `is_minor`, `monthly_cap`, `spend_30d`, `lifetime_spend`,
      `window_end`, `first_event_ts`, `last_event_ts`, `last_death_ts`,
      CURRENT_TIMESTAMP AS `offered_at`,
      `prompt_text`, `raw_response`
    FROM `scored`
  EOT

  depends_on = [
    module.agent,
    confluent_flink_materialized_table.player_struggle_enriched,
  ]
}
