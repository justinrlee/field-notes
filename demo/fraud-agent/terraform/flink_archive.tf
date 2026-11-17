
# # Sink table the detection statement writes alerts into; the dashboard consumes it.
# module "tbl_fraud_alerts" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "create-table-fraud-alerts-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     CREATE TABLE `fraud_alerts` (
#       `user_id` STRING NOT NULL,
#       `risk_score` INT NOT NULL,
#       `reasoning` STRING NOT NULL,
#       `actions_taken` STRING NOT NULL,
#       `flagged_transaction_ids` STRING NOT NULL,
#       `raw_response` STRING NOT NULL,
#       `profile_start` TIMESTAMP_LTZ(3),
#       `profile_end` TIMESTAMP_LTZ(3),
#       `enriched_profile_text` STRING,
#       `arima_window_start` TIMESTAMP_LTZ(3),
#       `arima_window_end` TIMESTAMP_LTZ(3),
#       `window_total` DOUBLE,
#       `expected_amount` DOUBLE,
#       `upper_bound` DOUBLE,
#       `lower_bound` DOUBLE
#     ) DISTRIBUTED INTO 1 BUCKETS
#     WITH (
#       'kafka.consumer.isolation-level' = 'read-uncommitted'
#     );
#   EOT
# }


# # ----------------------- User Sessions (Combined) -------------------------
# # Combines SESSION windowing from activity_profiles with transaction aggregates
# # from arima_scored_windows. Provides enriched session data for downstream
# # processing with both narrative context and metrics.

# module "tbl_user_sessions" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "create-table-user-sessions-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     CREATE TABLE `user_sessions` (
#       `user_id` STRING NOT NULL,
#       `window_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `window_end` TIMESTAMP_LTZ(3),
#       `window_time` TIMESTAMP_LTZ(3),
#       `txn_count` BIGINT,
#       `total_amount` DOUBLE,
#       `avg_amount` DOUBLE,
#       `max_amount` DOUBLE,
#       `login_count` BIGINT,
#       `account_change_count` BIGINT,
#       `profile_text` STRING,
#       PRIMARY KEY (`user_id`) NOT ENFORCED
#     ) DISTRIBUTED INTO 1 BUCKETS
#     WITH (
#       'changelog.mode' = 'append',
#       'kafka.consumer.isolation-level' = 'read-uncommitted'
#     );
#   EOT
# }

# module "insert_user_sessions" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   extra_properties = {
#     "sql.tables.scan.idle-timeout" = "5 s"
#   }
#   statement_name = "insert-user-sessions-${random_id.suffix.hex}"
#   statement      = <<-EOT
#     INSERT INTO `user_sessions`
#     WITH `unified` AS (
#       SELECT `user_id`, 'transaction' AS `event_type`, `event_time`,
#              `amount`,
#              CONCAT('- txn ', `transaction_id`, ': $', CAST(`amount` AS STRING),
#                     ' at ', `merchant`, ' (', `merchant_category`, ') in ', `location`) AS `line`
#       FROM `transactions`
#       UNION ALL
#       SELECT `user_id`, 'login' AS `event_type`, `event_time`,
#              CAST(NULL AS DOUBLE) AS `amount`,
#              CONCAT('- login from ', `location`, ' via ', `device_id`, ' (ip ', `ip_address`, ')') AS `line`
#       FROM `user_logins`
#       UNION ALL
#       SELECT `user_id`, 'account_change' AS `event_type`, `event_time`,
#              CAST(NULL AS DOUBLE) AS `amount`,
#              CONCAT('- ', `field_changed`, ' changed from "', `old_value`, '" to "', `new_value`, '"') AS `line`
#       FROM `account_changes`
#     )
#     SELECT
#       `user_id`,
#       `window_start`,
#       `window_end`,
#       `window_time`,
#       COUNT(CASE WHEN `event_type` = 'transaction' THEN 1 END) AS `txn_count`,
#       SUM(CASE WHEN `event_type` = 'transaction' THEN CAST(`amount` AS DOUBLE) END) AS `total_amount`,
#       CAST(ROUND(AVG(CASE WHEN `event_type` = 'transaction' THEN CAST(`amount` AS DOUBLE) END), 2) AS DOUBLE) AS `avg_amount`,
#       MAX(CASE WHEN `event_type` = 'transaction' THEN CAST(`amount` AS DOUBLE) END) AS `max_amount`,
#       COUNT(CASE WHEN `event_type` = 'login' THEN 1 END) AS `login_count`,
#       COUNT(CASE WHEN `event_type` = 'account_change' THEN 1 END) AS `account_change_count`,
#       CONCAT(
#         'User: ', `user_id`, '\n\n',
#         'Transactions:\n', COALESCE(LISTAGG(CASE WHEN `event_type` = 'transaction' THEN `line` END, '\n'), '  (none)'), '\n\n',
#         'Logins:\n', COALESCE(LISTAGG(CASE WHEN `event_type` = 'login' THEN `line` END, '\n'), '  (none)'), '\n\n',
#         'Account changes:\n', COALESCE(LISTAGG(CASE WHEN `event_type` = 'account_change' THEN `line` END, '\n'), '  (none)')
#       ) AS `profile_text`
#     FROM TABLE(
#       SESSION(TABLE `unified` PARTITION BY `user_id`, DESCRIPTOR(`event_time`), INTERVAL '3' SECONDS)
#     )
#     GROUP BY `user_id`, `window_start`, `window_end`, `window_time`;
#   EOT
#   depends_on = [
#     module.tbl_transactions,
#     module.tbl_user_logins,
#     module.tbl_account_changes,
#     module.tbl_user_sessions,
#   ]
# }


# # ARIMA scoring on user_sessions (scores all sessions)
# module "tbl_user_sessions_scored" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "create-table-user-sessions-scored-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     CREATE TABLE `user_sessions_scored` (
#       `user_id` STRING NOT NULL,
#       `window_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `window_end` TIMESTAMP_LTZ(3),
#       `window_time` TIMESTAMP_LTZ(3),
#       `txn_count` BIGINT,
#       `total_amount` DOUBLE,
#       `avg_amount` DOUBLE,
#       `max_amount` DOUBLE,
#       `login_count` BIGINT,
#       `account_change_count` BIGINT,
#       `profile_text` STRING,
#       `expected_amount` DOUBLE,
#       `upper_bound` DOUBLE,
#       `lower_bound` DOUBLE,
#       `is_anomaly` BOOLEAN,
#       PRIMARY KEY (`user_id`) NOT ENFORCED
#     ) DISTRIBUTED INTO 1 BUCKETS
#     WITH (
#       'changelog.mode' = 'append',
#       'kafka.consumer.isolation-level' = 'read-uncommitted'
#     );
#   EOT
# }

# module "insert_user_sessions_scored" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "insert-user-sessions-scored-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     INSERT INTO `user_sessions_scored`
#     WITH `anomaly_detection` AS (
#       SELECT
#         `user_id`,
#         `window_start`,
#         `window_end`,
#         `window_time`,
#         `txn_count`,
#         `total_amount`,
#         `avg_amount`,
#         `max_amount`,
#         `login_count`,
#         `account_change_count`,
#         `profile_text`,
#         ML_DETECT_ANOMALIES(
#           `avg_amount`,
#           `window_time`,
#           JSON_OBJECT(
#             'minTrainingSize' VALUE 32,
#             'maxTrainingSize' VALUE 128,
#             'confidencePercentage' VALUE 99.5,
#             'enableStl' VALUE FALSE
#           )
#         ) OVER (
#           PARTITION BY `user_id`
#           ORDER BY `window_time`
#           RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
#         ) AS `anomaly_result`
#       FROM `user_sessions`
#     )
#     SELECT
#       `user_id`,
#       `window_start`,
#       `window_end`,
#       `window_time`,
#       `txn_count`,
#       `total_amount`,
#       `avg_amount`,
#       `max_amount`,
#       `login_count`,
#       `account_change_count`,
#       `profile_text`,
#       CAST(ROUND(`anomaly_result`.`forecast_value`, 2) AS DOUBLE) AS `expected_amount`,
#       `anomaly_result`.`upper_bound`,
#       `anomaly_result`.`lower_bound`,
#       `anomaly_result`.`is_anomaly`
#     FROM `anomaly_detection`;
#   EOT
#   depends_on = [module.insert_user_sessions, module.tbl_user_sessions_scored]
# }

# # Filter to only anomalous sessions
# module "tbl_user_sessions_anomalous" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "create-table-user-sessions-anomalous-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     CREATE TABLE `user_sessions_anomalous` (
#       `user_id` STRING NOT NULL,
#       `window_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `window_end` TIMESTAMP_LTZ(3),
#       `window_time` TIMESTAMP_LTZ(3),
#       `txn_count` BIGINT,
#       `total_amount` DOUBLE,
#       `avg_amount` DOUBLE,
#       `max_amount` DOUBLE,
#       `login_count` BIGINT,
#       `account_change_count` BIGINT,
#       `profile_text` STRING,
#       `expected_amount` DOUBLE,
#       `upper_bound` DOUBLE,
#       `lower_bound` DOUBLE,
#       `is_anomaly` BOOLEAN,
#       PRIMARY KEY (`user_id`) NOT ENFORCED
#     ) DISTRIBUTED INTO 1 BUCKETS
#     WITH (
#       'changelog.mode' = 'append',
#       'kafka.consumer.isolation-level' = 'read-uncommitted'
#     );
#   EOT
# }

# module "insert_user_sessions_anomalous" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "insert-user-sessions-anomalous-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     INSERT INTO `user_sessions_anomalous`
#     SELECT
#       `user_id`,
#       `window_start`,
#       `window_end`,
#       `window_time`,
#       `txn_count`,
#       `total_amount`,
#       `avg_amount`,
#       `max_amount`,
#       `login_count`,
#       `account_change_count`,
#       `profile_text`,
#       `expected_amount`,
#       `upper_bound`,
#       `lower_bound`,
#       `is_anomaly`
#     FROM `user_sessions_scored`
#     WHERE `is_anomaly` = TRUE
#       AND `avg_amount` > `upper_bound`;
#   EOT
#   depends_on = [module.insert_user_sessions_scored, module.tbl_user_sessions_anomalous]
# }

# # ----------------------- Anomaly Detection (ARIMA) ------------------------
# # Detects anomalous spending patterns by windowing transactions into 15-second
# # tumbling windows per user, aggregating spend metrics, and running ARIMA on
# # the aggregates. This pattern matches the Confluent reference architecture.

# # Stage 1: Score ALL windows with ARIMA (includes is_anomaly boolean)
# module "tbl_arima_scored_windows" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "create-table-arima-scored-windows-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     CREATE TABLE `arima_scored_windows` (
#       `user_id` STRING NOT NULL,
#       `window_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `window_end` TIMESTAMP_LTZ(3),
#       `txn_count` BIGINT,
#       `total_amount` DOUBLE,
#       `avg_amount` DOUBLE,
#       `max_amount` DOUBLE,
#       `expected_amount` DOUBLE,
#       `upper_bound` DOUBLE,
#       `lower_bound` DOUBLE,
#       `is_anomaly` BOOLEAN,
#       PRIMARY KEY (`user_id`) NOT ENFORCED
#     ) DISTRIBUTED INTO 1 BUCKETS
#     WITH (
#       'changelog.mode' = 'append',
#       'kafka.consumer.isolation-level' = 'read-uncommitted'
#     );
#   EOT
# }

# module "insert_arima_scored_windows" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "insert-arima-scored-windows-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     INSERT INTO `arima_scored_windows`
#     WITH `windowed_spending` AS (
#       SELECT
#         `window_start`,
#         `window_end`,
#         `window_time`,
#         `user_id`,
#         COUNT(*) AS `txn_count`,
#         SUM(CAST(`amount` AS DOUBLE)) AS `total_amount`,
#         CAST(ROUND(AVG(CAST(`amount` AS DOUBLE)), 2) AS DOUBLE) AS `avg_amount`,
#         MAX(CAST(`amount` AS DOUBLE)) AS `max_amount`
#       FROM TABLE(
#         SESSION(TABLE `transactions` PARTITION BY `user_id`, DESCRIPTOR(`event_time`), INTERVAL '3' SECONDS)
#       )
#       GROUP BY `window_start`, `window_end`, `window_time`, `user_id`
#     ),
#     `anomaly_detection` AS (
#       SELECT
#         `user_id`,
#         `window_start`,
#         `window_end`,
#         `window_time`,
#         `txn_count`,
#         `total_amount`,
#         `avg_amount`,
#         `max_amount`,
#         ML_DETECT_ANOMALIES(
#           `avg_amount`,
#           `window_time`,
#           JSON_OBJECT(
#             'minTrainingSize' VALUE 32,
#             'maxTrainingSize' VALUE 128,
#             'confidencePercentage' VALUE 99.5,
#             'enableStl' VALUE FALSE
#           )
#         ) OVER (
#           PARTITION BY `user_id`
#           ORDER BY `window_time`
#           RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
#         ) AS `anomaly_result`
#       FROM `windowed_spending`
#     )
#     SELECT
#       `user_id`,
#       `window_start`,
#       `window_end`,
#       `txn_count`,
#       `total_amount`,
#       `avg_amount`,
#       `max_amount`,
#       CAST(ROUND(`anomaly_result`.`forecast_value`, 2) AS DOUBLE) AS `expected_amount`,
#       `anomaly_result`.`upper_bound`,
#       `anomaly_result`.`lower_bound`,
#       `anomaly_result`.`is_anomaly`
#     FROM `anomaly_detection`;
#   EOT
#   depends_on       = [module.tbl_transactions, module.tbl_arima_scored_windows]
# }

# # Stage 2: Filter to only anomalous windows (is_anomaly=true AND above threshold)
# module "tbl_anomalous_windows" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "create-table-anomalous-windows-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     CREATE TABLE `anomalous_windows` (
#       `user_id` STRING NOT NULL,
#       `window_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `window_end` TIMESTAMP_LTZ(3),
#       `txn_count` BIGINT,
#       `total_amount` DOUBLE,
#       `avg_amount` DOUBLE,
#       `max_amount` DOUBLE,
#       `expected_amount` DOUBLE,
#       `upper_bound` DOUBLE,
#       `lower_bound` DOUBLE,
#       `is_anomaly` BOOLEAN,
#       WATERMARK FOR `window_start` AS `window_start`,
#       PRIMARY KEY (`user_id`) NOT ENFORCED
#     ) DISTRIBUTED INTO 1 BUCKETS
#     WITH (
#       'changelog.mode' = 'append',
#       'kafka.consumer.isolation-level' = 'read-uncommitted'
#     );
#   EOT
# }

# module "insert_anomalous_windows" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "insert-anomalous-windows-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     INSERT INTO `anomalous_windows`
#     SELECT
#       `user_id`,
#       `window_start`,
#       `window_end`,
#       `txn_count`,
#       `total_amount`,
#       `avg_amount`,
#       `max_amount`,
#       `expected_amount`,
#       `upper_bound`,
#       `lower_bound`,
#       `is_anomaly`
#     FROM `arima_scored_windows`
#     WHERE `is_anomaly` = TRUE
#       AND `total_amount` > `upper_bound`;
#   EOT
#   depends_on       = [module.insert_arima_scored_windows, module.tbl_anomalous_windows]
# }


# # ----------------------- Activity profiles (windowing) ---------------------
# # Unions the 3 differently-shaped streams into a common (user_id, event_type,
# # event_time, line) shape, then builds one per-user activity profile per 3s
# # event-time SESSION window. Materialized as its own table/topic so it's
# # queryable (SELECT * FROM activity_profiles) and shows up as a node in Stream
# # Lineage between the source topics and the agent.
# #
# # NOTE: This processes ALL users (not pre-filtered). ARIMA filtering happens
# # later via join to anomalous_windows.
# module "tbl_activity_profiles" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "create-table-activity-profiles-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     CREATE TABLE `activity_profiles` (
#       `user_id` STRING NOT NULL,
#       `window_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `window_end` TIMESTAMP_LTZ(3),
#       `profile_text` STRING,
#       PRIMARY KEY (`user_id`) NOT ENFORCED
#     ) DISTRIBUTED INTO 1 BUCKETS
#     WITH (
#       'changelog.mode' = 'append',
#       'kafka.consumer.isolation-level' = 'read-uncommitted'
#     );
#   EOT
# }

# module "insert_activity_profiles" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   # Pin a small fixed watermark idle-timeout. Confluent Cloud's default
#   # "progressive idleness" grows the idle timeout with statement age (up to 5
#   # min), which stalls the session windows over time when the producer leaves
#   # some partitions idle between cycles. A fixed 5s keeps the watermark
#   # advancing so windows close and profiles flow continuously.
#   extra_properties = {
#     "sql.tables.scan.idle-timeout" = "5 s"
#   }
#   statement_name = "insert-activity-profiles-${random_id.suffix.hex}"
#   statement      = <<-EOT
#     INSERT INTO `activity_profiles`
#     WITH `unified` AS (
#       SELECT `user_id`, 'transaction' AS `event_type`, `event_time`,
#              CONCAT('- txn ', `transaction_id`, ': $', CAST(`amount` AS STRING),
#                     ' at ', `merchant`, ' (', `merchant_category`, ') in ', `location`) AS `line`
#       FROM `transactions`
#       UNION ALL
#       SELECT `user_id`, 'login' AS `event_type`, `event_time`,
#              CONCAT('- login from ', `location`, ' via ', `device_id`, ' (ip ', `ip_address`, ')') AS `line`
#       FROM `user_logins`
#       UNION ALL
#       SELECT `user_id`, 'account_change' AS `event_type`, `event_time`,
#              CONCAT('- ', `field_changed`, ' changed from "', `old_value`, '" to "', `new_value`, '"') AS `line`
#       FROM `account_changes`
#     )
#     SELECT
#       `user_id`,
#       `window_start`,
#       `window_end`,
#       CONCAT(
#         'User: ', `user_id`, '\n\n',
#         'Transactions:\n', COALESCE(LISTAGG(CASE WHEN `event_type` = 'transaction' THEN `line` END, '\n'), '  (none)'), '\n\n',
#         'Logins:\n', COALESCE(LISTAGG(CASE WHEN `event_type` = 'login' THEN `line` END, '\n'), '  (none)'), '\n\n',
#         'Account changes:\n', COALESCE(LISTAGG(CASE WHEN `event_type` = 'account_change' THEN `line` END, '\n'), '  (none)')
#       ) AS `profile_text`
#     FROM TABLE(
#       SESSION(TABLE `unified` PARTITION BY `user_id`, DESCRIPTOR(`event_time`), INTERVAL '3' SECONDS)
#     )
#     GROUP BY `user_id`, `window_start`, `window_end`;
#   EOT
#   depends_on = [
#     module.tbl_transactions,
#     module.tbl_user_logins,
#     module.tbl_account_changes,
#     module.tbl_activity_profiles,
#   ]
# }

# # ------------------- Filter profiles to anomalous windows -----------------
# # Joins activity_profiles (all users, session-windowed) to anomalous_windows
# # (ARIMA-detected spending anomalies) to keep only profiles that overlap with
# # an anomalous window. This combines session-based burst detection with
# # statistical anomaly detection.
# module "tbl_anomalous_profiles" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "create-table-anomalous-profiles-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     CREATE TABLE `anomalous_profiles` (
#       `user_id` STRING NOT NULL,
#       `profile_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `arima_window_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `profile_end` TIMESTAMP_LTZ(3),
#       `profile_text` STRING,
#       `arima_window_end` TIMESTAMP_LTZ(3),
#       `txn_count` BIGINT,
#       `window_total` DOUBLE,
#       `avg_amount` DOUBLE,
#       `expected_amount` DOUBLE,
#       `upper_bound` DOUBLE,
#       `lower_bound` DOUBLE,
#       PRIMARY KEY (`user_id`) NOT ENFORCED
#     ) DISTRIBUTED INTO 1 BUCKETS
#     WITH (
#       'changelog.mode' = 'append',
#       'kafka.consumer.isolation-level' = 'read-uncommitted'
#     );
#   EOT
# }

# module "insert_anomalous_profiles" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   extra_properties = {
#     "sql.tables.scan.idle-timeout" = "5 s"
#   }
#   statement_name   = "insert-anomalous-profiles-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     INSERT INTO `anomalous_profiles`
#     SELECT
#       p.`user_id`,
#       p.`window_start` AS `profile_start`,
#       w.`window_start` AS `arima_window_start`,
#       p.`window_end` AS `profile_end`,
#       p.`profile_text`,
#       w.`window_end` AS `arima_window_end`,
#       w.`txn_count`,
#       w.`total_amount` AS `window_total`,
#       w.`avg_amount`,
#       w.`expected_amount`,
#       w.`upper_bound`,
#       w.`lower_bound`
#     FROM `activity_profiles` p
#     INNER JOIN `anomalous_windows` w
#       ON p.`user_id` = w.`user_id`
#       AND p.`window_start` BETWEEN w.`window_start` - INTERVAL '5' SECOND AND w.`window_start` + INTERVAL '5' SECOND
#   EOT
#   depends_on = [
#     module.insert_activity_profiles,
#     module.insert_anomalous_windows,
#     module.tbl_anomalous_profiles,
#   ]
# }

# # ----------------- Enrich profiles with ARIMA context ---------------------
# # Prepends ARIMA anomaly context (window stats, expected amounts, thresholds)
# # to the profile text so the agent sees both the statistical anomaly signal
# # and the detailed activity context.
# module "tbl_anomalous_profiles_enriched" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "create-table-enriched-profiles-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     CREATE TABLE `anomalous_profiles_enriched` (
#       `user_id` STRING NOT NULL,
#       `profile_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `arima_window_start` TIMESTAMP_LTZ(3) NOT NULL,
#       `profile_end` TIMESTAMP_LTZ(3),
#       `arima_window_end` TIMESTAMP_LTZ(3),
#       `txn_count` BIGINT,
#       `window_total` DOUBLE,
#       `avg_amount` DOUBLE,
#       `expected_amount` DOUBLE,
#       `upper_bound` DOUBLE,
#       `lower_bound` DOUBLE,
#       `enriched_profile_text` STRING,
#       PRIMARY KEY (`user_id`) NOT ENFORCED
#     ) DISTRIBUTED INTO 1 BUCKETS
#     WITH (
#       'changelog.mode' = 'append',
#       'kafka.consumer.isolation-level' = 'read-uncommitted'
#     );
#   EOT
# }

# module "insert_anomalous_profiles_enriched" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "insert-enriched-profiles-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     INSERT INTO `anomalous_profiles_enriched`
#     SELECT
#       `user_id`,
#       `profile_start`,
#       `arima_window_start`,
#       `profile_end`,
#       `arima_window_end`,
#       `txn_count`,
#       `window_total`,
#       `avg_amount`,
#       `expected_amount`,
#       `upper_bound`,
#       `lower_bound`,
#       CONCAT(
#         'STATISTICAL ANOMALY DETECTED (ARIMA on session average transaction amount)\n',
#         'Anomalous session: ', CAST(`arima_window_start` AS STRING), ' to ', CAST(`arima_window_end` AS STRING), '\n',
#         'Session total: $', CAST(`window_total` AS STRING), ' across ', CAST(`txn_count` AS STRING), ' transactions\n',
#         'Average per transaction: $', CAST(`avg_amount` AS STRING),
#         ' (expected avg: $', CAST(`expected_amount` AS STRING),
#         ', threshold: $', CAST(`upper_bound` AS STRING), ')\n\n',
#         `profile_text`
#       ) AS `enriched_profile_text`
#     FROM `anomalous_profiles`;
#   EOT
#   depends_on = [
#     module.insert_anomalous_profiles,
#     module.tbl_anomalous_profiles_enriched,
#   ]
# }

# # ----------------------- Detection (agent) ---------------------------------
# # Reads each ARIMA-filtered, enriched activity profile, runs the Streaming
# # Agent on it, and parses the agent's JSON verdict into the fraud_alerts
# # columns. Only profiles that overlap with ARIMA-detected anomalies are
# # analyzed.
# module "detect" {
#   source           = "./modules/flink-statement"
#   organization_id  = local.flink_common.organization_id
#   environment_id   = local.flink_common.environment_id
#   compute_pool_id  = local.flink_common.compute_pool_id
#   principal_id     = local.flink_common.principal_id
#   rest_endpoint    = local.flink_common.rest_endpoint
#   flink_api_key    = local.flink_common.flink_api_key
#   flink_api_secret = local.flink_common.flink_api_secret
#   catalog          = local.flink_common.catalog
#   database         = local.flink_common.database
#   statement_name   = "detect-fraud-${random_id.suffix.hex}"
#   statement        = <<-EOT
#     INSERT INTO `fraud_alerts`
#     WITH `scored` AS (
#       SELECT
#         p.`user_id`,
#         p.`profile_start`,
#         p.`arima_window_start`,
#         p.`profile_end`,
#         p.`arima_window_end`,
#         p.`window_total`,
#         p.`expected_amount`,
#         p.`upper_bound`,
#         p.`lower_bound`,
#         p.`enriched_profile_text`,
#         CAST(r.`response` AS STRING) AS `raw_response`,
#         REGEXP_EXTRACT(CAST(r.`response` AS STRING), '\{[\s\S]*\}', 0) AS `json_text`
#       FROM `anomalous_profiles_enriched` p,
#       LATERAL TABLE(AI_RUN_AGENT(`fraud_detection_agent`, p.`enriched_profile_text`, p.`user_id`)) r
#     )
#     SELECT
#       `user_id`,
#       COALESCE(CAST(JSON_VALUE(`json_text`, '$.risk_score') AS INT), 0) AS `risk_score`,
#       COALESCE(JSON_VALUE(`json_text`, '$.reasoning'), '') AS `reasoning`,
#       COALESCE(JSON_QUERY(`json_text`, '$.actions_taken'), '[]') AS `actions_taken`,
#       COALESCE(JSON_QUERY(`json_text`, '$.flagged_transaction_ids'), '[]') AS `flagged_transaction_ids`,
#       `raw_response`,
#       `profile_start`,
#       `profile_end`,
#       `enriched_profile_text`,
#       `arima_window_start`,
#       `arima_window_end`,
#       `window_total`,
#       `expected_amount`,
#       `upper_bound`,
#       `lower_bound`
#     FROM `scored`;
#   EOT
#   depends_on = [
#     module.agent,
#     module.insert_anomalous_profiles_enriched,
#     module.tbl_fraud_alerts,
#   ]
# }
