# ---------------------------------------------------------------------------
# Platform-side Flink objects: Bedrock connection, shared statement args, and
# the CREATE MODEL. Scenario objects (source tables, materialized tables, UDF
# tools, agent) are added below / in their own build steps — see DESIGN.md §10.
# ---------------------------------------------------------------------------

# Bedrock connection (IAM user creds, fixed region). The Claude model id is
# encoded in the endpoint URL (see locals in main.tf).
resource "confluent_flink_connection" "bedrock" {
  organization {
    id = data.confluent_organization.main.id
  }
  environment {
    id = confluent_environment.main.id
  }
  compute_pool {
    id = confluent_flink_compute_pool.main.id
  }
  principal {
    id = confluent_service_account.app_manager.id
  }
  rest_endpoint = data.confluent_flink_region.main.rest_endpoint
  credentials {
    key    = confluent_api_key.flink.id
    secret = confluent_api_key.flink.secret
  }

  display_name   = "bedrock-gaming-connection"
  type           = "BEDROCK"
  endpoint       = local.bedrock_endpoint
  aws_access_key = var.aws_access_key_id
  aws_secret_key = var.aws_secret_access_key

  depends_on = [
    confluent_api_key.flink,
    confluent_role_binding.app_manager_env_admin,
  ]
}

# Shared args for every Flink statement (passed to the flink-statement module).
locals {
  flink_common = {
    organization_id  = data.confluent_organization.main.id
    environment_id   = confluent_environment.main.id
    compute_pool_id  = confluent_flink_compute_pool.main.id
    principal_id     = confluent_service_account.app_manager.id
    rest_endpoint    = data.confluent_flink_region.main.rest_endpoint
    flink_api_key    = confluent_api_key.flink.id
    flink_api_secret = confluent_api_key.flink.secret
    catalog          = local.catalog
    database         = local.database
  }
}

# ------------------------------- Model -------------------------------------
module "model" {
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
  statement_name   = "create-model-offer-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE MODEL `offer_model`
    INPUT (`prompt` STRING)
    OUTPUT (`response` STRING)
    WITH (
      'provider' = 'bedrock',
      'task' = 'text_generation',
      'bedrock.connection' = '${confluent_flink_connection.bedrock.display_name}',
      'bedrock.params.max_tokens' = '8192'
    );
  EOT
  depends_on       = [confluent_flink_connection.bedrock]
}

# ----------------------------- Source tables -------------------------------
# Created by Flink so the topics + Avro value schemas exist before the producer
# runs. `timestamp` / `updated_at` are epoch ms; `event_time` is a computed time
# attribute (with watermark) used for windowing and the temporal join.
# Watermark delays are kept small (2 s events, 1 s profiles) because end-to-end
# latency = session gap + watermark (see DESIGN.md §4).
#
# player_profiles is an upsert/compacted table keyed by player_id with an Avro
# key (a 'raw' key format would force the key column to be named `key`). The
# generator re-emits profiles periodically so the versioned table's watermark
# never stalls.

module "tbl_player_combat_events" {
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
  statement_name   = "create-table-player-combat-events-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TABLE `player_combat_events` (
      `event_id` STRING NOT NULL,
      `game_id` STRING NOT NULL,
      `player_id` STRING NOT NULL,
      `match_id` STRING NOT NULL,
      `event_type` STRING NOT NULL,
      `damage_amount` INT NOT NULL,
      `source_id` STRING NOT NULL,
      `source_type` STRING NOT NULL,
      `zone_id` STRING NOT NULL,
      `player_level` INT NOT NULL,
      `timestamp` BIGINT NOT NULL,
      `event_time` AS TO_TIMESTAMP_LTZ(`timestamp`, 3),
      WATERMARK FOR `event_time` AS `event_time` - INTERVAL '2' SECOND
    ) DISTRIBUTED INTO 6 BUCKETS
    WITH (
      'kafka.consumer.isolation-level' = 'read-uncommitted'
    );
  EOT
}

module "tbl_player_activity" {
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
  statement_name   = "create-table-player-activity-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TABLE `player_activity` (
      `event_id` STRING NOT NULL,
      `game_id` STRING NOT NULL,
      `player_id` STRING NOT NULL,
      `activity_type` STRING NOT NULL,
      `item_id` STRING,
      `detail` STRING,
      `timestamp` BIGINT NOT NULL,
      `event_time` AS TO_TIMESTAMP_LTZ(`timestamp`, 3),
      WATERMARK FOR `event_time` AS `event_time` - INTERVAL '2' SECOND
    ) DISTRIBUTED INTO 6 BUCKETS
    WITH (
      'kafka.consumer.isolation-level' = 'read-uncommitted'
    );
  EOT
}

module "tbl_player_profiles" {
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
  statement_name   = "create-table-player-profiles-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TABLE `player_profiles` (
      `player_id` STRING NOT NULL,
      `game_id` STRING NOT NULL,
      `player_class` STRING NOT NULL,
      `level` INT NOT NULL,
      `tier` STRING NOT NULL,
      `lifetime_spend` DOUBLE NOT NULL,
      `spend_30d` DOUBLE NOT NULL,
      `monthly_cap` DOUBLE,
      `is_minor` BOOLEAN NOT NULL,
      `region` STRING NOT NULL,
      `owned_skus` ARRAY<STRING> NOT NULL,
      `last_purchase_ts` BIGINT,
      `updated_at` BIGINT NOT NULL,
      `event_time` AS TO_TIMESTAMP_LTZ(`updated_at`, 3),
      PRIMARY KEY (`player_id`) NOT ENFORCED,
      WATERMARK FOR `event_time` AS `event_time` - INTERVAL '1' SECOND
    ) DISTRIBUTED BY HASH(`player_id`) INTO 6 BUCKETS
    WITH (
      'changelog.mode' = 'upsert',
      'kafka.cleanup-policy' = 'compact',
      'key.format' = 'avro-registry',
      'value.format' = 'avro-registry',
      'value.fields-include' = 'all',
      'kafka.consumer.isolation-level' = 'read-uncommitted'
    );
  EOT
}

# ----------------------------- Pipeline -----------------------------------
# Shape decided by the step-3 prototype (sql/prototypes/03-enrichment.sql): the profile join happens INSIDE
# the windowing query (temporal join on `window_time`), because time attributes are lost on
# materialized-table outputs and a downstream `$rowtime` join measured 10-20 s slower. So:
#   player_encounters      session window per player + temporal join to player_profiles
#   player_struggle_moments rule-based filter (the pre-filter before the LLM)
#   (step 5) player_struggle_enriched -> player_offer_recommendations

# ------------------------- player_encounters -------------------------------
# UNION ALL of the two event streams -> SESSION window per player (12 s gap) -> per-encounter
# stats -> temporal join to the player's profile as of the window. GROUP BY must be exactly the
# PARTITION BY key + window columns, or the planner falls back to an updating GroupAggregate
# (carry other columns with MAX()). `sql.tables.scan.idle-timeout` is pinned here, where the
# window/watermark lives (session options apply only at creation).
#
# Single-killer detection avoids nested aggregates: MIN/MAX of the killer ids of DEATH events;
# if they match, every death in the window was to one source (`single_killer`).
resource "confluent_flink_materialized_table" "player_encounters" {
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

  display_name = "player_encounters"
  kafka_cluster {
    id = confluent_kafka_cluster.standard.id
  }

  # No `columns` block (provider 2.87.0 sends a type string the API rejects); schema is inferred.

  constraints {
    name     = "player_encounters_pk"
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
    "sql.current-catalog"          = local.flink_common.catalog
    "sql.current-database"         = local.flink_common.database
    "sql.tables.scan.idle-timeout" = "5 s"
  }

  query = <<-EOT
    WITH `unified` AS (
      SELECT `player_id`, `game_id`, `event_time`, `timestamp`, `event_type` AS `kind`,
             `source_id`, `zone_id`, `damage_amount`, `player_level`,
             CONCAT(`event_type`, ' ', `source_id`, ' (', CAST(`damage_amount` AS STRING), ') in ', `zone_id`) AS `line`
      FROM `player_combat_events`
      UNION ALL
      SELECT `player_id`, `game_id`, `event_time`, `timestamp`, `activity_type` AS `kind`,
             CAST(NULL AS STRING) AS `source_id`, CAST(NULL AS STRING) AS `zone_id`,
             0 AS `damage_amount`, CAST(NULL AS INT) AS `player_level`,
             CONCAT(`activity_type`, COALESCE(CONCAT(' ', `item_id`), '')) AS `line`
      FROM `player_activity`
    ),
    `windowed` AS (
      SELECT
        `player_id`, MAX(`game_id`) AS `game_id`, `window_start`, `window_end`, `window_time`,
        COUNT(CASE WHEN `kind` = 'DEATH' THEN 1 END) AS `deaths`,
        SUM(`damage_amount`) AS `damage_taken`,
        MIN(CASE WHEN `kind` = 'DEATH' THEN `source_id` END) AS `killer_min`,
        MAX(CASE WHEN `kind` = 'DEATH' THEN `source_id` END) AS `killer_max`,
        MAX(`zone_id`) AS `zone_id`,
        MAX(`player_level`) AS `player_level`,
        COUNT(CASE WHEN `kind` = 'QUEST_FAIL' THEN 1 END) AS `quest_fails`,
        COUNT(CASE WHEN `kind` = 'QUEST_COMPLETE' THEN 1 END) AS `quest_completes`,
        COUNT(CASE WHEN `kind` = 'STORE_VIEW' THEN 1 END) AS `store_views`,
        COUNT(CASE WHEN `kind` = 'LOGOUT' THEN 1 END) AS `logouts`,
        COUNT(*) AS `events`,
        MIN(`timestamp`) AS `first_event_ts`,
        MAX(`timestamp`) AS `last_event_ts`,
        MAX(CASE WHEN `kind` = 'DEATH' THEN `timestamp` END) AS `last_death_ts`,
        LISTAGG(`line`, ' | ') AS `activity`
      FROM TABLE(
        SESSION(TABLE `unified` PARTITION BY `player_id`, DESCRIPTOR(`event_time`), INTERVAL '12' SECONDS)
      )
      GROUP BY `player_id`, `window_start`, `window_end`, `window_time`
    )
    SELECT
      w.`player_id`, w.`game_id`, w.`window_start`, w.`window_end`,
      w.`zone_id`, w.`player_level`,
      w.`deaths`, w.`damage_taken`,
      w.`killer_max` AS `killer_id`,
      COALESCE(w.`killer_min` = w.`killer_max`, FALSE) AS `single_killer`,
      w.`quest_fails`, w.`quest_completes`, w.`store_views`, w.`logouts`, w.`events`,
      w.`first_event_ts`, w.`last_event_ts`, w.`last_death_ts`,
      w.`activity`,
      p.`player_class`, p.`tier`, p.`level`, p.`lifetime_spend`, p.`spend_30d`,
      p.`monthly_cap`, p.`is_minor`, p.`region`, p.`owned_skus`, p.`last_purchase_ts`
    FROM `windowed` w
    JOIN `player_profiles` FOR SYSTEM_TIME AS OF w.`window_time` AS p
      ON w.`player_id` = p.`player_id`
  EOT

  depends_on = [
    module.tbl_player_combat_events,
    module.tbl_player_activity,
    module.tbl_player_profiles,
  ]
}

# ---------------------- player_struggle_moments ----------------------------
# The rule-based pre-filter before the LLM (DESIGN.md §4). Normal play can never match: simulated
# players are capped at 2 deaths and 1 quest fail per scene. `trigger_reason` is a hint for the
# prompt/dashboard, not a decision. Thresholds here are the demo's tuning knobs.
resource "confluent_flink_materialized_table" "player_struggle_moments" {
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

  display_name = "player_struggle_moments"
  kafka_cluster {
    id = confluent_kafka_cluster.standard.id
  }

  constraints {
    name     = "player_struggle_moments_pk"
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
      *,
      CASE
        WHEN `deaths` >= 4 AND `quest_fails` > 0 THEN 'RAGE_QUIT_RISK'
        WHEN `deaths` >= 4 AND `store_views` > 0 THEN 'GEAR_GAP'
        ELSE 'BOSS_WALL'
      END AS `trigger_reason`
    FROM `player_encounters`
    WHERE (`single_killer` AND `deaths` >= 3)
       OR (`deaths` >= 4 AND `quest_fails` > 0)
       OR (`deaths` >= 4 AND `store_views` > 0)
  EOT

  depends_on = [confluent_flink_materialized_table.player_encounters]
}
