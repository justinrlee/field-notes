# ---------------------------------------------------------------------------
# Bedrock connection (IAM user creds, fixed region). The Claude model id is
# encoded in the endpoint URL (see locals in main.tf).
# ---------------------------------------------------------------------------
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

  display_name   = "bedrock-fraud-connection"
  type           = "BEDROCK"
  endpoint       = local.bedrock_endpoint
  aws_access_key = var.aws_access_key_id
  aws_secret_key = var.aws_secret_access_key

  depends_on = [
    confluent_api_key.flink,
    confluent_role_binding.app_manager_env_admin,
  ]
}

# ---------------------------------------------------------------------------
# Pre-built UDF tools JAR (committed to the repo) uploaded as a Flink artifact.
# Demo users need no Java/Maven toolchain — Terraform just uploads the binary.
# ---------------------------------------------------------------------------
resource "confluent_flink_artifact" "tools" {
  display_name   = "${local.prefix}-tools-${random_id.suffix.hex}"
  cloud          = local.cloud_provider
  region         = local.aws_region
  content_format = "JAR"
  artifact_file  = "${path.module}/../tools-udf/target/fraud-tools.jar"
  environment {
    id = confluent_environment.main.id
  }
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

# ----------------------------- Source tables -------------------------------
# Created by Flink so the topics + Avro value schemas exist before the producer
# runs and before the detection statement is deployed. `timestamp` is epoch ms;
# event_time is a computed time attribute used for the session window.

module "tbl_transactions" {
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
  statement_name   = "create-table-transactions-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TABLE `transactions` (
      `user_id` STRING NOT NULL,
      `transaction_id` STRING NOT NULL,
      `amount` DOUBLE NOT NULL,
      `merchant` STRING NOT NULL,
      `merchant_category` STRING NOT NULL,
      `location` STRING NOT NULL,
      `timestamp` BIGINT NOT NULL,
      `event_time` AS TO_TIMESTAMP_LTZ(`timestamp`, 3),
      WATERMARK FOR `event_time` AS `event_time` - INTERVAL '5' SECOND
    ) DISTRIBUTED INTO 6 BUCKETS
    WITH (
      'kafka.consumer.isolation-level' = 'read-uncommitted'
    );
  EOT
}

module "tbl_user_logins" {
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
  statement_name   = "create-table-user-logins-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TABLE `user_logins` (
      `user_id` STRING NOT NULL,
      `ip_address` STRING NOT NULL,
      `device_id` STRING NOT NULL,
      `location` STRING NOT NULL,
      `timestamp` BIGINT NOT NULL,
      `event_time` AS TO_TIMESTAMP_LTZ(`timestamp`, 3),
      WATERMARK FOR `event_time` AS `event_time` - INTERVAL '5' SECOND
    ) DISTRIBUTED INTO 6 BUCKETS
    WITH (
      'kafka.consumer.isolation-level' = 'read-uncommitted'
    );
  EOT
}

module "tbl_account_changes" {
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
  statement_name   = "create-table-account-changes-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TABLE `account_changes` (
      `user_id` STRING NOT NULL,
      `field_changed` STRING NOT NULL,
      `old_value` STRING NOT NULL,
      `new_value` STRING NOT NULL,
      `timestamp` BIGINT NOT NULL,
      `event_time` AS TO_TIMESTAMP_LTZ(`timestamp`, 3),
      WATERMARK FOR `event_time` AS `event_time` - INTERVAL '5' SECOND
    ) DISTRIBUTED INTO 6 BUCKETS
    WITH (
      'kafka.consumer.isolation-level' = 'read-uncommitted'
    );
  EOT
}

# Materialized-table: a single declarative CTAS-style object owning both the table definition and the
# continuous query, updatable in place (no `-replace` needed to change `query`).
resource "confluent_flink_materialized_table" "user_activity_scored" {
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

  display_name = "user_activity_scored"
  kafka_cluster {
    id = confluent_kafka_cluster.standard.id
  }

  # Schema is left to be inferred from `query` rather than declared via a `columns` block.
  # Provider 2.87.0's `columns_physical` only exposes `column_physical_type` as a flat SQL
  # type string (e.g. "STRING NOT NULL"), but the materialized-tables REST API expects a
  # structured type object (`{"type":"VARCHAR","nullable":false,"length":...}`); sending the
  # flat string causes an unhandled 500 on create (confirmed by POSTing the exact request
  # body Terraform logged, both with and without the `columns` block, directly against the
  # Flink REST API). Confirmed as a provider bug, not a query issue: dropping `columns`
  # succeeds and Confluent's inferred schema is actually tighter than the hand-written one
  # (e.g. `profile_text`/`*_count` inferred NOT NULL, correctly, since COALESCE/COUNT never
  # produce null here). Revisit adding an explicit schema once the provider supports it.

  constraints {
    name     = "user_activity_scored_pk"
    type     = "PRIMARY_KEY"
    columns  = ["user_id"]
    enforced = false
  }

  distribution {
    kind         = "HASH"
    keys         = ["user_id"]
    bucket_count = 6
  }

  table_options = {
    "changelog.mode"                 = "append"
    "kafka.consumer.isolation-level" = "read-uncommitted"
  }

  # Session-scoped (SQL SET) config, applied only at creation. Pins the idle-partition
  # watermark timeout so the SESSION window below doesn't stall as the job ages (see
  # AGENTS.md Gotchas: "Watermark idle-timeout is required for steady alerts"), and sets
  # the catalog/database context so unqualified table names below resolve correctly.
  session_options = {
    "sql.current-catalog"          = local.flink_common.catalog
    "sql.current-database"         = local.flink_common.database
    "sql.tables.scan.idle-timeout" = "5 s"
  }

  query = <<-EOT
    WITH `unified` AS (
      SELECT `user_id`, 'transaction' AS `event_type`, `event_time`,
             `amount`,
             CONCAT('- txn ', `transaction_id`, ': $', CAST(`amount` AS STRING),
                    ' at ', `merchant`, ' (', `merchant_category`, ') in ', `location`) AS `line`
      FROM `transactions`
      UNION ALL
      SELECT `user_id`, 'login' AS `event_type`, `event_time`,
             CAST(NULL AS DOUBLE) AS `amount`,
             CONCAT('- login from ', `location`, ' via ', `device_id`, ' (ip ', `ip_address`, ')') AS `line`
      FROM `user_logins`
      UNION ALL
      SELECT `user_id`, 'account_change' AS `event_type`, `event_time`,
             CAST(NULL AS DOUBLE) AS `amount`,
             CONCAT('- ', `field_changed`, ' changed from "', `old_value`, '" to "', `new_value`, '"') AS `line`
      FROM `account_changes`
    ),
    `windowed_sessions` AS (
      SELECT
        `user_id`,
        `window_start`,
        `window_end`,
        `window_time`,
        COUNT(CASE WHEN `event_type` = 'transaction' THEN 1 END) AS `txn_count`,
        SUM(CASE WHEN `event_type` = 'transaction' THEN CAST(`amount` AS DOUBLE) END) AS `total_amount`,
        CAST(ROUND(AVG(CASE WHEN `event_type` = 'transaction' THEN CAST(`amount` AS DOUBLE) END), 2) AS DOUBLE) AS `avg_amount`,
        MAX(CASE WHEN `event_type` = 'transaction' THEN CAST(`amount` AS DOUBLE) END) AS `max_amount`,
        COUNT(CASE WHEN `event_type` = 'login' THEN 1 END) AS `login_count`,
        COUNT(CASE WHEN `event_type` = 'account_change' THEN 1 END) AS `account_change_count`,
        CONCAT(
          'User: ', `user_id`, '\n\n',
          'Transactions:\n', COALESCE(LISTAGG(CASE WHEN `event_type` = 'transaction' THEN `line` END, '\n'), '  (none)'), '\n\n',
          'Logins:\n', COALESCE(LISTAGG(CASE WHEN `event_type` = 'login' THEN `line` END, '\n'), '  (none)'), '\n\n',
          'Account changes:\n', COALESCE(LISTAGG(CASE WHEN `event_type` = 'account_change' THEN `line` END, '\n'), '  (none)')
        ) AS `profile_text`
      FROM TABLE(
        SESSION(TABLE `unified` PARTITION BY `user_id`, DESCRIPTOR(`event_time`), INTERVAL '3' SECONDS)
      )
      GROUP BY `user_id`, `window_start`, `window_end`, `window_time`
    ),
    `anomaly_detection` AS (
      SELECT
        `user_id`,
        `window_start`,
        `window_end`,
        `window_time`,
        `txn_count`,
        `total_amount`,
        `avg_amount`,
        `max_amount`,
        `login_count`,
        `account_change_count`,
        `profile_text`,
        ML_DETECT_ANOMALIES(
          `avg_amount`,
          `window_time`,
          JSON_OBJECT(
            'minTrainingSize' VALUE 50,
            'maxTrainingSize' VALUE 128,
            'confidencePercentage' VALUE 99.95,
            'enableStl' VALUE FALSE
          )
        ) OVER (
          PARTITION BY `user_id`
          ORDER BY `window_time`
          RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS `anomaly_result`
      FROM `windowed_sessions`
    )
    SELECT
      `user_id`,
      `window_start`,
      `window_end`,
      `window_time`,
      `txn_count`,
      `total_amount`,
      `avg_amount`,
      `max_amount`,
      `login_count`,
      `account_change_count`,
      `profile_text`,
      CAST(ROUND(`anomaly_result`.`forecast_value`, 2) AS DOUBLE) AS `expected_amount`,
      `anomaly_result`.`upper_bound`,
      `anomaly_result`.`lower_bound`,
      `anomaly_result`.`is_anomaly`
    FROM `anomaly_detection`
  EOT

  depends_on = [
    module.tbl_transactions,
    module.tbl_user_logins,
    module.tbl_account_changes,
  ]
}

resource "confluent_flink_materialized_table" "user_activity_anomalous" {
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

  display_name = "user_activity_anomalous"
  kafka_cluster {
    id = confluent_kafka_cluster.standard.id
  }

  # No explicit `columns` block: provider 2.87.0's `columns_physical` sends a flat SQL type
  # string where the REST API expects a structured type object, causing an unhandled 500 on
  # create (confirmed empirically against pair #1 above). Schema is inferred from `query`.

  constraints {
    name     = "user_activity_anomalous_pk"
    type     = "PRIMARY_KEY"
    columns  = ["user_id"]
    enforced = false
  }

  distribution {
    kind         = "HASH"
    keys         = ["user_id"]
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
    SELECT *
    FROM `user_activity_scored`
    WHERE `is_anomaly` = TRUE
      AND `avg_amount` > `upper_bound`
  EOT

  depends_on = [confluent_flink_materialized_table.user_activity_scored]
}

resource "confluent_flink_materialized_table" "user_activity_anomalous_enriched" {
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

  display_name = "user_activity_anomalous_enriched"
  kafka_cluster {
    id = confluent_kafka_cluster.standard.id
  }

  constraints {
    name     = "user_activity_anomalous_enriched_pk"
    type     = "PRIMARY_KEY"
    columns  = ["user_id"]
    enforced = false
  }

  distribution {
    kind         = "HASH"
    keys         = ["user_id"]
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
      `user_id`,
      `window_start` AS `profile_start`,
      `window_start` AS `arima_window_start`,
      `window_end` AS `profile_end`,
      `window_end` AS `arima_window_end`,
      `txn_count`,
      `total_amount` AS `window_total`,
      `avg_amount`,
      `expected_amount`,
      `upper_bound`,
      `lower_bound`,
      CONCAT(
        'STATISTICAL ANOMALY DETECTED (ARIMA on session average transaction amount)\n',
        'Anomalous session: ', CAST(`window_start` AS STRING), ' to ', CAST(`window_end` AS STRING), '\n',
        'Session total: $', CAST(`total_amount` AS STRING), ' across ', CAST(`txn_count` AS STRING), ' transactions\n',
        'Average per transaction: $', CAST(`avg_amount` AS STRING),
        ' (expected avg: $', CAST(`expected_amount` AS STRING),
        ', threshold: $', CAST(`upper_bound` AS STRING), ')\n\n',
        `profile_text`
      ) AS `enriched_profile_text`
    FROM `user_activity_anomalous`
  EOT

  depends_on = [confluent_flink_materialized_table.user_activity_anomalous]
}

# Fraud detection on anomalous user activity. Riskiest of the four conversions: the query
# invokes the streaming agent via `LATERAL TABLE(AI_RUN_AGENT(...))`, a construct Confluent's
# docs never explicitly confirm as supported inside a materialized table's query (their own
# quickstart-streaming-agents examples only ever use it inside plain CREATE TABLE AS SELECT).
# No `constraints`/`distribution` block, matching the original CREATE TABLE, which declared
# no PRIMARY KEY and plain round-robin `DISTRIBUTED INTO 6 BUCKETS` (no HASH key to derive).
resource "confluent_flink_materialized_table" "fraud_analysis_results" {
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

  display_name = "fraud_analysis_results"
  kafka_cluster {
    id = confluent_kafka_cluster.standard.id
  }

  table_options = {
    "kafka.consumer.isolation-level" = "read-uncommitted"
  }

  session_options = {
    "sql.current-catalog"  = local.flink_common.catalog
    "sql.current-database" = local.flink_common.database
  }

  query = <<-EOT
    WITH `scored` AS (
      SELECT
        p.`user_id`,
        p.`profile_start`,
        p.`arima_window_start`,
        p.`profile_end`,
        p.`arima_window_end`,
        p.`window_total`,
        p.`expected_amount`,
        p.`upper_bound`,
        p.`lower_bound`,
        p.`enriched_profile_text`,
        CAST(r.`response` AS STRING) AS `raw_response`,
        REGEXP_EXTRACT(CAST(r.`response` AS STRING), '\{[\s\S]*\}', 0) AS `json_text`
      FROM `user_activity_anomalous_enriched` p,
      LATERAL TABLE(AI_RUN_AGENT(`fraud_detection_agent`, p.`enriched_profile_text`, p.`user_id`)) r
    )
    SELECT
      `user_id`,
      COALESCE(CAST(JSON_VALUE(`json_text`, '$.risk_score') AS INT), 0) AS `risk_score`,
      COALESCE(JSON_VALUE(`json_text`, '$.reasoning'), '') AS `reasoning`,
      COALESCE(JSON_QUERY(`json_text`, '$.actions_taken'), '[]') AS `actions_taken`,
      COALESCE(JSON_QUERY(`json_text`, '$.flagged_transaction_ids'), '[]') AS `flagged_transaction_ids`,
      `raw_response`,
      `profile_start`,
      `profile_end`,
      `enriched_profile_text`,
      `arima_window_start`,
      `arima_window_end`,
      `window_total`,
      `expected_amount`,
      `upper_bound`,
      `lower_bound`
    FROM `scored`
  EOT

  depends_on = [
    module.agent,
    confluent_flink_materialized_table.user_activity_anomalous_enriched,
  ]
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
  statement_name   = "create-model-fraud-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE MODEL `fraud_model`
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

# ------------------------ Functions (from JAR) -----------------------------
module "fn_flag" {
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
  statement_name   = "create-fn-flag-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE FUNCTION `flag_transaction`
    AS 'io.confluent.frauddemo.FlagTransaction'
    USING JAR 'confluent-artifact://${confluent_flink_artifact.tools.id}';
  EOT
  depends_on       = [confluent_flink_artifact.tools]
}

module "fn_freeze" {
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
  statement_name   = "create-fn-freeze-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE FUNCTION `freeze_account`
    AS 'io.confluent.frauddemo.FreezeAccount'
    USING JAR 'confluent-artifact://${confluent_flink_artifact.tools.id}';
  EOT
  depends_on       = [confluent_flink_artifact.tools]
}

module "fn_notify" {
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
  statement_name   = "create-fn-notify-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE FUNCTION `notify_user`
    AS 'io.confluent.frauddemo.NotifyUser'
    USING JAR 'confluent-artifact://${confluent_flink_artifact.tools.id}';
  EOT
  depends_on       = [confluent_flink_artifact.tools]
}

# --------------------------------- Tools -----------------------------------
module "tool_flag" {
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
  statement_name   = "create-tool-flag-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TOOL `flag_transaction_tool`
    USING FUNCTION `flag_transaction`
    WITH (
      'type' = 'function',
      'description' = 'Flag a specific transaction as potentially fraudulent for manual review. Arguments: transaction_id, reason.'
    );
  EOT
  depends_on       = [module.fn_flag]
}

module "tool_freeze" {
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
  statement_name   = "create-tool-freeze-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TOOL `freeze_account_tool`
    USING FUNCTION `freeze_account`
    WITH (
      'type' = 'function',
      'description' = 'Temporarily freeze a user account due to suspected fraud. Arguments: user_id, reason.'
    );
  EOT
  depends_on       = [module.fn_freeze]
}

module "tool_notify" {
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
  statement_name   = "create-tool-notify-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE TOOL `notify_user_tool`
    USING FUNCTION `notify_user`
    WITH (
      'type' = 'function',
      'description' = 'Send a fraud alert notification to the user. Arguments: user_id, message.'
    );
  EOT
  depends_on       = [module.fn_notify]
}

# --------------------------------- Agent -----------------------------------
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
  statement_name   = "create-agent-fraud-${random_id.suffix.hex}"
  statement        = <<-EOT
    CREATE AGENT `fraud_detection_agent`
    USING MODEL `fraud_model`
    USING PROMPT 'You are a real-time fraud detection analyst receiving activity profiles PRE-FILTERED by windowed ARIMA anomaly detection.

    IMPORTANT: These profiles have already been flagged by a statistical ARIMA model that analyzes 3-second spending windows.
    ARIMA detected that the user''s total spending in a 3-second window was anomalously high compared to their historical baseline.
    Each transaction shows: [WINDOW ANOMALY: total=$X, expected=$Y] where total > expected indicates unusual spending velocity.

    Your job is CONTEXTUAL ANALYSIS. The ARIMA model only sees aggregate spending patterns — you see the full picture:
    - Does the spending burst make sense given the user''s other activity?
    - Are there supporting fraud signals beyond just the spending velocity?
    - Is this likely a legitimate high-value shopping spree or actual fraud?

    You receive a plain-text activity profile for ONE user over a short time window with:
    - Transactions from an ARIMA-flagged 15-second window (with window total and expected amount)
    - Recent logins (location, device, ip)
    - Recent account changes (field, old value, new value)

    Analyze for these fraud signals IN ADDITION TO the ARIMA spending anomaly:
    1. Geographic impossibility: login and transaction in distant cities within minutes
    2. Account takeover: email/password change followed by rapid high-value purchases
    3. Device/IP anomalies: new devices combined with other signals
    4. Merchant patterns: unusual merchant types or rapid merchant switching
    5. Contextual mismatch: ARIMA flagged it but the context suggests legitimate behavior (e.g. holiday shopping)

    SCORING GUIDE - use the FULL range:
    - 90-100: ARIMA spending anomaly + multiple strong fraud signals (e.g. geo-impossible + account takeover)
    - 70-89: ARIMA spending anomaly + one strong fraud signal (e.g. geo-impossible travel or account takeover)
    - 45-69: ARIMA spending anomaly with weak supporting signals (e.g. new device or unusual merchants)
    - 20-44: ARIMA spending anomaly but context suggests legitimate (e.g. planned shopping from usual location)
    - 0-19: ARIMA anomaly appears to be false positive (should be rare)

    TOOLS - DECIDE THE SCORE FIRST, THEN ACT. Determine risk_score before calling any tool, and
    only call the tools the score warrants below. Make every tool call up front. Once you call a
    tool, treat it as final: never reconsider it, apologize for it, or reverse it in text.
    - If risk_score >= 80: call freeze_account_tool(user_id, reason) and notify_user_tool(user_id, message)
    - If risk_score 50-79: call flag_transaction_tool(transaction_id, reason) for each suspicious transaction and notify_user_tool(user_id, message)
    - If risk_score 20-49: call notify_user_tool(user_id, message)
    - If risk_score < 20: do NOT call any tool.
    Record the tools you actually called in "actions_taken".

    CRITICAL RULES:
    - Copy the EXACT "user_id" string from the input. Do NOT change it.
    - Copy EXACT "transaction_id" strings from the input into "flagged_transaction_ids". Do NOT invent IDs.
    - If no transactions exist, set "flagged_transaction_ids" to an empty list.
    - Your FINAL message must be ONLY the single JSON object below: no preamble, no commentary, no
      self-corrections, no markdown, no code fences. Put all explanation inside "reasoning", nowhere else.
    {"user_id": "<copy from input>", "risk_score": <0-100 integer>, "reasoning": "<one or two sentences>", "actions_taken": ["freeze_account"|"flag_transaction"|"notify_user"], "flagged_transaction_ids": ["<copied transaction ids>"]}'
    USING TOOLS `flag_transaction_tool`, `freeze_account_tool`, `notify_user_tool`
    WITH (
      'max_iterations' = '6',
      'handle_exception' = 'continue',
      'max_consecutive_failures' = '5'
    );
  EOT
  depends_on = [
    module.model,
    module.tool_flag,
    module.tool_freeze,
    module.tool_notify,
  ]
}
