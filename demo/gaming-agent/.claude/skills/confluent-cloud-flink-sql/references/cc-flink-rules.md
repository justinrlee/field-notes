# Confluent Cloud for Apache Flink SQL — AI Rules

This project uses **Confluent Cloud for Apache Flink**, not open-source (OSS) Apache Flink.
The two environments share the same SQL grammar but have significant behavioral, architectural,
and syntactic differences. Apply every rule below before generating any Flink SQL, DDL, or
configuration advice.

> **Source notes:** Rules derived from the Confluent Cloud Flink documentation and from
> `dialect-traps.md` (same folder), a curated trap table
> reviewed against live CC compute pools. Where the skill and this file conflict, the skill's
> dialect-traps.md is the tighter authority (it has live repro evidence).

---

## 1. Catalog / Database Model

Confluent Cloud maps its infrastructure hierarchy directly to Flink SQL concepts:

| Confluent Cloud | Flink SQL concept |
|-----------------|-------------------|
| Environment     | Catalog           |
| Kafka cluster   | Database          |
| Kafka topic     | Table             |
| Schema Registry | Table schema      |

- **Every Kafka topic is already a table.** Tables are automatically inferred from topics and
  their Schema Registry schemas. You almost never need to write `CREATE TABLE` for an existing topic.
- Use three-part identifiers when referencing tables across clusters:
  `catalog_name.db_name.table_name` (e.g., `my_env.my_cluster.orders`).
- `SHOW CATALOGS` lists environments; `SHOW DATABASES` lists Kafka clusters;
  `SHOW TABLES` lists Kafka topics.
- **No `CREATE CATALOG` or `CREATE DATABASE`** — these are managed by Confluent Cloud infrastructure,
  not by Flink SQL. `CATALOG` and `DATABASE` commands are read-only (`SHOW`, `USE`).

---

## 2. Table Creation and Lifecycle

### CREATE TABLE creates real Kafka resources

In Confluent Cloud Flink, `CREATE TABLE` is **not metadata-only**. It provisions:
1. A new Kafka topic (named after the table).
2. Key and value schema subjects in Schema Registry.

Use `CREATE TABLE` only to:
- Define a custom schema, serialization format, or changelog mode.
- Create a derived table via `CREATE TABLE AS SELECT (CTAS)`.
- Configure non-default Kafka topic properties (retention, partitions, etc.).

### No temporary tables or temporary views

Confluent Cloud does not support `CREATE TEMPORARY TABLE` (every table maps to a real Kafka
topic) and does not support `CREATE TEMPORARY VIEW`. Use a persistent `CREATE VIEW` or a
CTE (`WITH v AS (...)`) instead.

### DROP TABLE is destructive

`DROP TABLE` **permanently deletes** the underlying Kafka topic and all its data.
With the default `TopicNameStrategy`, it also deletes the key and value Schema Registry subjects.
This is different from OSS Flink, where `DROP TABLE` only removes catalog metadata.
**Never suggest `DROP TABLE` as a safe way to "reset" a table.**

### SHOW CREATE TABLE output is not re-runnable

In Confluent Cloud Flink, re-executing the output of `SHOW CREATE TABLE` against an existing table
produces a Schema Registry subject mismatch error — not a clean "table already exists" error.
Treat `SHOW CREATE TABLE` output as documentation only, not as an idempotent script.

---

### CTE placement — INSERT INTO comes first

In all Flink dialects (OSS and CC), the CTE clause must come **after** `INSERT INTO`, not before it:

```sql
-- CORRECT
INSERT INTO my_sink
WITH enriched AS (
  SELECT * FROM source WHERE status = 'active'
)
SELECT * FROM enriched;

-- WRONG — parse error in all Flink dialects
WITH enriched AS (
  SELECT * FROM source WHERE status = 'active'
)
INSERT INTO my_sink SELECT * FROM enriched;
```

---

## 3. Connector Model

### Always use `'connector' = 'confluent'`

OSS Flink uses `'connector' = 'kafka'` or `'connector' = 'upsert-kafka'`.
Confluent Cloud uses a **single unified connector**:

```sql
-- CORRECT for Confluent Cloud
CREATE TABLE my_table (...) WITH ('connector' = 'confluent', 'changelog.mode' = 'upsert');

-- WRONG — do not use in Confluent Cloud
CREATE TABLE my_table (...) WITH ('connector' = 'kafka');
CREATE TABLE my_table (...) WITH ('connector' = 'upsert-kafka');
```

When porting OSS DDL, replace both `'connector' = 'kafka'` and
`'connector' = 'upsert-kafka'` with `'connector' = 'confluent'` and set
`'changelog.mode'` explicitly.

The default value of `connector` is `confluent`, so it can be omitted for standard
Kafka-backed tables.

### Connector values for external (read-only) tables

| Use case         | `connector` value  |
|------------------|--------------------|
| Standard Kafka   | `confluent` (default) |
| Fake/sample data | `faker`            |
| MongoDB          | `mongodb`          |
| Elasticsearch    | `elastic`          |
| Pinecone         | `pinecone`         |
| Confluent JDBC   | `confluent-jdbc`   |
| REST endpoint    | `rest`             |
| Couchbase        | `couchbase`        |
| Azure Cosmos DB  | `cosmosdb`         |
| Amazon S3 Vectors| `s3vectors`        |

---

## 4. Unsupported Runtime Features

The following OSS Flink capabilities are **not available** in Confluent Cloud Flink at all:

- **DataStream API** (Java/Scala) — not supported. The CC replacement for `ProcessFunction` is a
  Process Table Function (PTF) in the Table API, callable from SQL. Table API + PTF are GA in
  Java; the Python Table API is Open Preview with no PTF support yet.
- **Savepoints / `STOP WITH SAVEPOINT`** — not exposed on CC. Savepoints are used internally
  but not accessible. **Statement deletion = state loss.** Use `prevent_destroy` in Terraform
  for production statements.
- **Savepoint-based statement upgrade** — not available. You cannot transfer state from one
  statement to another.
- **`SET 'execution.checkpointing.*'`** — CC manages checkpointing entirely; these options are
  not user-settable and will error if you attempt to set them.

---

## 5. Serialization Formats and Schema Registry

### Default format is Avro with Schema Registry

Unlike OSS Flink (which defaults to plain JSON), Confluent Cloud Flink defaults to
`avro-registry` for both key and value formats when Schema Registry is involved.

### Format option names

| Format                   | `key.format` / `value.format` value |
|--------------------------|--------------------------------------|
| Avro + SR                | `avro-registry`                      |
| JSON Schema + SR         | `json-registry`                      |
| Protobuf + SR            | `proto-registry`                     |
| Raw bytes                | `raw`                                |
| Debezium CDC + Avro      | `avro-debezium-registry`             |
| Debezium CDC + JSON      | `json-debezium-registry`             |
| Debezium CDC + Protobuf  | `proto-debezium-registry`            |

**Do not use** `'format' = 'avro'`, `'format' = 'json'`, `'format' = 'csv'`,
`'format' = 'debezium-json'`, or `'format' = 'canal-json'` — these OSS format strings
are not valid for Confluent Cloud native Kafka tables.

**Naming trap:** CC uses format-first naming (`json-debezium-registry`); OSS uses
debezium-first (`debezium-json`). When porting CDC pipelines, rename accordingly.

### Example

```sql
CREATE TABLE events (
  `id`    BIGINT,
  `name`  STRING,
  PRIMARY KEY (`id`) NOT ENFORCED
) WITH (
  'key.format'   = 'avro-registry',
  'value.format' = 'avro-registry'
);
```

### Schema ID encoding

The `id-encoding` option key embeds the format name:
`'value.<format>.id-encoding'` and `'key.<format>.id-encoding'`.

```sql
-- JSON Schema with clean payload (schema ID in header)
CREATE TABLE clean_output (...) WITH (
  'value.format'                    = 'json-registry',
  'value.json-registry.id-encoding' = 'header'
);

-- Avro with standard wire-format prefix
CREATE TABLE avro_output (...) WITH (
  'value.format'                     = 'avro-registry',
  'value.avro-registry.id-encoding'  = 'payload'   -- this is the default
);
```

- `payload` (default): 5-byte Confluent wire-format prefix (magic byte + 4-byte schema ID).
- `header`: Schema ID in Kafka record header; payload contains clean format bytes.

This is a **write-only** option. On reads, CC resolves schema via: header → payload prefix → SR fallback.

---

## 6. Changelog Modes

Set with `'changelog.mode'` in `WITH` options. Three values:

| Mode      | Meaning                                                       | Kafka encoding                           |
|-----------|---------------------------------------------------------------|------------------------------------------|
| `append`  | Insert-only; every row is an independent fact                 | Each value is a plain `+I`               |
| `upsert`  | Rows with the same PK are related; supports `+I`, `+U`, `-D` | Null value = delete; requires a PK       |
| `retract` | Full changelog: `+I`, `-U`, `+U`, `-D`                        | `op` header encodes change type          |

Default for inferred tables: `append` (uncompacted), `upsert` (compacted),
`retract` (Debezium envelope detected).

For a manually created table: default is `append` unless overridden.

**Upsert mode requires a PRIMARY KEY.** The bucket key must equal the primary key.

---

## 7. DDL — Supported and Unsupported Statements

### Supported DDL

`CREATE TABLE`, `CREATE TABLE AS SELECT (CTAS)`, `CREATE MATERIALIZED TABLE`,
`CREATE FUNCTION` (UDFs), `CREATE VIEW` (local/temporary), `CREATE MODEL`,
`ALTER TABLE` (limited), `ALTER MATERIALIZED TABLE`, `DROP TABLE`, `DROP VIEW`,
`DROP MATERIALIZED TABLE`, `DROP FUNCTION`, `DESCRIBE`, `DESCRIBE EXTENDED`,
`SHOW TABLES`, `SHOW DATABASES`, `SHOW CATALOGS`, `SHOW FUNCTIONS`, `SHOW JOBS`,
`SHOW CREATE TABLE`, `SHOW CREATE MATERIALIZED TABLE`,
`USE CATALOG`, `USE [database]`, `EXPLAIN`, `SET`, `RESET`.

### NOT supported in Confluent Cloud Flink

- `ANALYZE TABLE`
- `CALL` statements
- `CREATE CATALOG`, `DROP CATALOG`, `ALTER CATALOG`
- `CREATE DATABASE`, `DROP DATABASE`, `ALTER DATABASE`
- `DELETE` statements
- `JAR` statements (`ADD JAR`, `REMOVE JAR`, `SHOW JARS`)
- `LOAD` / `UNLOAD` statements
- `TRUNCATE TABLE`
- `UPDATE` statements
- Processing-time functions: `PROCTIME()`, `TUMBLE_PROCTIME`, `HOP_PROCTIME`,
  `SESSION_PROCTIME`, `CUMULATE_PROCTIME`
- `CREATE TEMPORARY TABLE` — all tables are persistent Kafka topics
- `CREATE TEMPORARY VIEW` — use a persistent `CREATE VIEW` or a CTE instead
- `CREATE TEMPORARY FUNCTION` — functions must be persistent
- DataStream API (Java/Scala) — not supported; use Table API + PTF
- Savepoints / `STOP WITH SAVEPOINT` — not user-accessible on CC

### ALTER TABLE — limited and uses MODIFY for watermarks

In Confluent Cloud Flink, `ALTER TABLE` supports only:
- Changing the watermark strategy — uses the `MODIFY` keyword, not `ADD`.
- Adding a metadata column.
- Changing a WITH property value (e.g., `error-handling.mode`).
- Overriding key/value column types for schemaless topics.

```sql
-- CORRECT: MODIFY for watermark changes
ALTER TABLE orders MODIFY WATERMARK FOR order_time AS order_time - INTERVAL '5' SECOND;

-- WRONG: ADD is not valid for watermarks on CC
ALTER TABLE orders ADD WATERMARK FOR order_time AS order_time - INTERVAL '5' SECOND;
```

It does **not** support renaming columns, changing column types, or dropping columns
(those require stopping statements, dropping, and recreating the table).

---

## 8. UDFs (User-Defined Functions)

### UDFs require an uploaded artifact

`CREATE FUNCTION` on CC **must** include a `USING JAR` clause pointing to an artifact
uploaded via `confluent flink artifact create`. A plain `AS 'com.example.MyClass'` without
`USING JAR` will fail.

```sql
-- CORRECT
CREATE FUNCTION my_func AS 'com.example.MyFunc'
  USING JAR 'confluent-artifact://<artifact-id>';

-- WRONG — will fail on CC
CREATE FUNCTION my_func AS 'com.example.MyFunc';
```

For UDFs that need external network access, also declare `USING CONNECTIONS`:

```sql
CREATE FUNCTION my_func AS 'com.example.MyFunc'
  USING JAR 'confluent-artifact://<artifact-id>'
  USING CONNECTIONS ('my_connection');
```

### Supported and unsupported UDF types

| UDF type                      | CC support           |
|-------------------------------|----------------------|
| Scalar UDF                    | ✅ Supported (Java)  |
| Table function (UDTF)         | ✅ Supported (Java)  |
| Aggregate function (UDAF)     | ❌ Not supported     |
| Table aggregate function      | ❌ Not supported     |
| Python scalar/table functions | Open Preview only    |

### UDF sandbox restrictions

CC UDFs run in a sandbox — no filesystem access, no arbitrary socket connections without a
declared `CREATE CONNECTION` + `USING CONNECTIONS` clause.

---

## 9. Partitioning and Bucketing

### DISTRIBUTED BY (preferred)

The `DISTRIBUTED BY` clause maps to Kafka partitions. `n BUCKETS` = `n` partitions.

```sql
-- 4 Kafka partitions, keyed by user_id
CREATE TABLE user_events (
  user_id BIGINT,
  event   STRING
) DISTRIBUTED BY (user_id) INTO 4 BUCKETS;
```

- Default bucket count is 6 when not specified.
- For upsert mode: bucket key must equal the primary key.
- For append/retract: bucket key can be a subset of columns.

### PRIMARY KEY implies distribution

A `PRIMARY KEY` constraint automatically distributes the table by the key column(s),
creating a key schema in Schema Registry.

```sql
CREATE TABLE users (
  user_id   BIGINT,
  user_name STRING,
  PRIMARY KEY (user_id) NOT ENFORCED
);
```

### PARTITIONED BY — deprecated

Use `DISTRIBUTED BY` instead. `PARTITIONED BY` still works but is deprecated.

---

## 10. Watermarks and Event Time

### Default watermark strategy

Every table in Confluent Cloud Flink automatically has a default watermark strategy on the
`$rowtime` system column with a fixed out-of-orderness tolerance of 180 milliseconds.
You do **not** need to define a watermark strategy unless you need a custom one.

This is shown as `WATERMARK FOR $rowtime AS SOURCE_WATERMARK()` in DDL output.
The `SOURCE_WATERMARK()` function emits approximately every 200ms.

OSS Flink requires explicit watermark definitions for every table; Confluent Cloud does not.

### Custom watermark strategies

Override the default with `WATERMARK FOR` in `CREATE TABLE`, or change it later with `ALTER TABLE`:

```sql
-- Strictly ascending
WATERMARK FOR order_time AS order_time

-- 5-second bounded out-of-orderness
WATERMARK FOR order_time AS order_time - INTERVAL '5' SECOND
```

The watermark column must be `TIMESTAMP(3)` and a top-level column.

### Progressive idleness detection

Confluent Cloud Flink automatically detects idle partitions (default: starts at 10s, up to 5 min).
An idle partition does not block watermark advancement. Control with `sql.tables.scan.idle-timeout`.

---

## 11. System Column: `$rowtime`

Every Confluent Cloud Flink table has built-in system columns:

| Column      | Type                       | Notes |
|-------------|----------------------------|-------|
| `$rowtime`  | `TIMESTAMP_LTZ(3) NOT NULL` | Kafka record timestamp |
| `$headers`  | `MAP<STRING, BYTES>`        | Kafka record headers |

- **Not shown in** `SELECT *`, `DESCRIBE`, or `SHOW CREATE TABLE` output.
- Visible in `DESCRIBE EXTENDED`.
- **Must be backquoted** when used in SQL because `$` is not a normal identifier character:
  `` SELECT `$rowtime`, `$headers` FROM my_table ``
- `$rowtime` can be aliased in a CTE without losing the time-attribute property:
  `` WITH t AS (SELECT `$rowtime` AS event_time, ...) SELECT ... FROM TABLE(TUMBLE(TABLE t, DESCRIPTOR(event_time), ...)) ``
- `$rowtime` can be qualified with a table alias: `o.$rowtime` or `` o.`$rowtime` `` both work.
- To write the Kafka timestamp to a sink, use the `timestamp` metadata column, not `$rowtime`.

Access headers:
```sql
SELECT
  `$rowtime` AS event_time,
  `$headers`['correlation-id'] AS cid
FROM my_table;
```

---

## 12. Reserved Words — Must Backquote

The following are reserved keywords in CC Flink SQL. Using them as bare identifiers causes
parse errors. **Always backquote them** in column definitions, ROW type aliases, SELECT
lists, and aliases:

```
timestamp  value     time      offset    partition  row
table      order     group     select    from       where
having     join      on        as        set        start
end        interval  date      year      month      day
hour       minute    second
```

```sql
-- FAILS: reserved words as bare identifiers
CREATE TABLE t (timestamp TIMESTAMP(3), value STRING);

-- WORKS: backquoted
CREATE TABLE t (`timestamp` TIMESTAMP(3), `value` STRING);

-- Also applies inside ROW types
CAST(... AS ROW<`timestamp` STRING, `value` STRING>)
```

**Not reserved** (safe to use bare, though backquoting is always harmless): `payload`,
`name`, `key`, `type`, `data`.

**System columns** also need backticks (the `$` prefix is not a normal identifier start):
```sql
SELECT `$rowtime`, `$headers`['x-trace-id'] FROM my_table;
```

JSON path strings are NOT affected — `'$.timestamp'` inside `JSON_VALUE(...)` is a string
literal, not an identifier, and needs no backquotes.

---

## 13. Metadata Columns

Access Kafka record metadata with the `METADATA` keyword. Common fields:

| Metadata key     | Type                     | Access              | Description                          |
|------------------|--------------------------|---------------------|--------------------------------------|
| `timestamp`      | `TIMESTAMP_LTZ(3) NOT NULL` | readable/writable | Kafka record timestamp               |
| `offset`         | `BIGINT NOT NULL`        | readable (VIRTUAL)  | Partition offset                     |
| `partition`      | `INT NOT NULL`           | readable (VIRTUAL)  | Partition ID                         |
| `topic`          | `STRING NOT NULL`        | readable (VIRTUAL)  | Topic name                           |
| `headers`        | `MAP NOT NULL`           | readable/writable   | Kafka record headers                 |
| `raw-key`        | `BYTES NOT NULL`         | readable            | Raw key bytes                        |
| `raw-value`      | `BYTES NOT NULL`         | readable            | Raw value bytes                      |
| `leader-epoch`   | `INT NULL`               | readable            | Leader epoch                         |
| `timestamp-type` | `STRING NOT NULL`        | readable            | `CreateTime` / `LogAppendTime`       |

Read-only fields must be declared `VIRTUAL` to be excluded from `INSERT INTO`:

```sql
CREATE TABLE t (
  user_id    BIGINT,
  event_time TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
  part       BIGINT METADATA VIRTUAL,
  off        BIGINT METADATA VIRTUAL
);
```

---

## 14. Array Unnesting

CC Flink SQL rejects the `LATERAL TABLE(UNNEST(...))` syntax. Use `CROSS JOIN UNNEST(...)`:

```sql
-- FAILS on CC — parse error
SELECT order_id, item
FROM orders LATERAL TABLE(UNNEST(items)) AS T(item);

-- WORKS on CC
SELECT order_id, item
FROM orders
CROSS JOIN UNNEST(items) AS T(item);

-- Also works: CROSS JOIN UNNEST on a JSON array
SELECT order_id, signal_str
FROM input_topic
CROSS JOIN UNNEST(
  JSON_QUERY(CAST(val AS STRING), 'lax $.signals[*]' RETURNING ARRAY<STRING>)
) AS T(signal_str);
```

Plain `LATERAL (subquery)` (without `TABLE`/`UNNEST`) is supported on CC.

---

## 15. Windowing TVF Syntax

Confluent Cloud Flink supports **only** the Table-Valued Function (TVF) windowing syntax.
The older Group Window Aggregation syntax (`TUMBLE_START`, `TUMBLE_END`, etc.) is **not supported**.

### Supported window types: TUMBLE, HOP, CUMULATE, SESSION

```sql
-- Tumble window
SELECT window_start, window_end, COUNT(*)
FROM TUMBLE(
  TABLE orders,
  DESCRIPTOR($rowtime),
  INTERVAL '10' MINUTES
)
GROUP BY window_start, window_end;

-- Hop window
SELECT window_start, window_end, SUM(amount)
FROM HOP(
  TABLE orders,
  DESCRIPTOR($rowtime),
  INTERVAL '5' MINUTES,   -- slide
  INTERVAL '10' MINUTES   -- size
)
GROUP BY window_start, window_end;

-- Cumulate window
SELECT window_start, window_end, COUNT(*)
FROM CUMULATE(
  TABLE orders,
  DESCRIPTOR($rowtime),
  INTERVAL '1' MINUTES,   -- step
  INTERVAL '1' HOUR       -- max size
)
GROUP BY window_start, window_end;
```

- Always pass `$rowtime` (or another event-time column) as the time descriptor.
- Window TVFs add `window_start`, `window_end`, `window_time` columns to the output.
- Supported time units: `SECOND`, `MINUTE`, `HOUR`, `DAY`. `MONTH` and `YEAR` are **not** supported.
- Window boundaries align to clock-based boundaries (e.g., hour windows align at :00).
- `SESSION` windows are not supported in batch mode.

### Window TVF wrapping with `TABLE(...)`

Both these forms are valid on CC:

```sql
-- Direct FROM (no TABLE() wrapper)
SELECT ... FROM TUMBLE(TABLE orders, DESCRIPTOR($rowtime), INTERVAL '10' MINUTES)
GROUP BY window_start, window_end;

-- With explicit TABLE() wrapper
SELECT ... FROM TABLE(TUMBLE(TABLE orders, DESCRIPTOR($rowtime), INTERVAL '10' MINUTES))
GROUP BY window_start, window_end;
```

### Do NOT use these OSS Flink windowing forms

```sql
-- NOT valid in Confluent Cloud Flink:
GROUP BY TUMBLE(event_time, INTERVAL '10' MINUTES)
GROUP BY HOP(event_time, INTERVAL '5' MINUTES, INTERVAL '10' MINUTES)
SELECT TUMBLE_START(event_time, INTERVAL '1' HOUR), TUMBLE_END(...)
```

---

## 16. Statement Lifecycle and Background vs. Foreground Queries

- In Confluent Cloud Flink, every submitted SQL query creates a **statement resource** — a managed,
  long-running object.
- The SQL text of a statement is **immutable** after submission. To change a query, stop the
  statement and create a new one.
- **Background statements**: `INSERT INTO ... SELECT ...` — write to a Kafka topic continuously.
- **Foreground statements**: `SELECT ...` without `INSERT INTO` — results stream to the client.
  If there is no consumer for 5 minutes, the statement is moved to `STOPPED`.
- There is **no `CANCEL JOB` syntax** as in OSS Flink, and no `STOP WITH SAVEPOINT`.
  Use the Confluent CLI, REST API, or Console to stop a statement.
- Statements in terminal states are retained for 30 days, then automatically deleted.

### EXPLAIN before creating statements

Run `EXPLAIN` on any non-trivial query before submitting it as a statement. This validates
syntax and type compatibility without consuming CFUs:

```sql
EXPLAIN SELECT * FROM my_table WHERE status = 'active';
EXPLAIN PLAN FOR INSERT INTO output SELECT * FROM input JOIN ref ON input.id = ref.id;
```

### Materialized tables (preferred for production pipelines)

`CREATE MATERIALIZED TABLE` is the preferred pattern for long-running production queries.
It combines a table definition and a continuous query in a single persistent object that
can be evolved in place:

```sql
CREATE MATERIALIZED TABLE order_summaries
AS
SELECT customer_id, COUNT(*) AS order_count, SUM(price) AS total
FROM examples.marketplace.orders
GROUP BY customer_id;
```

---

## 17. Configuration Options (SET)

Confluent Cloud uses different `SET` option names than OSS Flink. Use these names:

| Confluent Cloud option                                | OSS Flink equivalent                       |
|-------------------------------------------------------|--------------------------------------------|
| `sql.current-catalog`                                 | `table.builtin-catalog-name`               |
| `sql.current-database`                                | `table.builtin-database-name`              |
| `sql.local-time-zone`                                 | `table.local-time-zone`                    |
| `sql.state-ttl`                                       | `table.exec.state.ttl`                     |
| `sql.tables.scan.startup.mode`                        | `scan.startup.mode`                        |
| `sql.tables.scan.startup.timestamp-millis`            | `scan.startup.timestamp-millis`            |
| `sql.tables.scan.bounded.mode`                        | `scan.bounded.mode`                        |
| `sql.tables.scan.bounded.timestamp-millis`            | `scan.bounded.timestamp-millis`            |
| `sql.tables.scan.idle-timeout`                        | `table.exec.source.idle-timeout`           |
| `sql.tables.scan.watermark-alignment.max-allowed-drift` | `scan.watermark.alignment.max-drift`     |
| `client.results-timeout`                              | `table.exec.async-lookup.timeout`          |
| `sql.snapshot.mode`                                   | (no equivalent — Confluent-specific)       |
| `sql.dry-run`                                         | (no equivalent — Confluent-specific)       |

```sql
-- Correct Confluent Cloud syntax
SET 'sql.local-time-zone' = 'America/New_York';
SET 'sql.state-ttl' = '7 d';

-- Wrong — OSS Flink option names not supported
SET 'table.local-time-zone' = 'America/New_York';
```

---

## 18. Scan Startup and Bounded Modes

### scan.startup.mode (table-level WITH option)

- `earliest-offset` (default) — read from the beginning of the topic.
- `latest-offset` — start from the latest offset.
- `timestamp` — start from a user-supplied per-partition timestamp
  (requires `scan.startup.timestamp-millis`).

### scan.bounded.mode (table-level WITH option)

Makes a table behave like a bounded (batch) source:
- `unbounded` (default) — continuous streaming.
- `latest-offset` — stop at offsets current at consumption start.
- `timestamp` — stop at a specific epoch millisecond
  (requires `scan.bounded.timestamp-millis`).

---

## 19. Compute Pools and CFUs

- Compute resources are measured in **CFUs (Confluent Flink Units)**.
- A compute pool is provisioned per environment + region; statements in the same pool share resources.
- Default pools are auto-created on first use, shared across users in the environment, and cap at 50 CFUs.
- A single statement can use up to 50 CFUs (the full pool capacity).
- **Autopilot** (auto-scaling) adjusts parallelism automatically — you typically don't need to set parallelism manually.
- To isolate production from ad hoc queries, create separate compute pools.
- Snapshot (batch) queries should run in a separate pool from streaming production jobs.

---

## 20. Key WITH Options Reference

| Option                        | Default          | Purpose                                         |
|-------------------------------|------------------|-------------------------------------------------|
| `changelog.mode`              | `append`         | `append`, `upsert`, or `retract`                |
| `connector`                   | `confluent`      | Usually omit; set to others for external tables |
| `value.format`                | `avro-registry`  | Serialization format for value                  |
| `key.format`                  | `avro-registry`  | Serialization format for key (if PK defined)    |
| `scan.startup.mode`           | `earliest-offset`| Where in the topic to start reading             |
| `scan.bounded.mode`           | `unbounded`      | Stream vs. bounded (batch) behavior             |
| `kafka.retention.time`        | `0` (infinite)   | Topic retention                                 |
| `kafka.cleanup-policy`        | `delete`/`compact`| `delete`, `compact`, or `delete-compact`       |
| `error-handling.mode`         | `fail`           | `fail`, `ignore`, or `log` (DLQ)                |
| `late-handling.mode`          | `pass-through`   | `pass-through` or `filter` for late events      |
| `value.fields-include`        | `EXCEPT_KEY`     | Whether PK fields appear in the value schema    |

---

## 21. Common Mistakes to Avoid

1. **Using `'connector' = 'kafka'`** — always use `'connector' = 'confluent'`.
2. **Using `'format' = 'json'` or `'format' = 'avro'`** — use `'value.format' = 'json-registry'`
   or `'value.format' = 'avro-registry'`.
3. **Adding `WATERMARK FOR`** when the default `$rowtime` watermark is sufficient.
4. **Using Group Window Aggregation syntax** (`GROUP BY TUMBLE(...)`) — use TVF syntax instead.
5. **Using `PROCTIME()`** — processing-time semantics are not supported; use event time with `$rowtime`.
6. **Using `CREATE TEMPORARY TABLE`** — not supported; all tables are persistent.
7. **Using `CREATE TEMPORARY VIEW`** — not supported; use persistent `CREATE VIEW` or a CTE.
8. **Treating `DROP TABLE` as safe/metadata-only** — it deletes the Kafka topic and all data.
9. **Copying OSS configuration key names** (e.g., `table.exec.state.ttl`) — use Confluent equivalents.
10. **Declaring `CREATE CATALOG` / `CREATE DATABASE`** — these are infrastructure-managed.
11. **Using `CANCEL JOB <id>` or `STOP WITH SAVEPOINT`** — neither is available on CC.
12. **Expecting `SHOW CREATE TABLE` output to be re-executable** — it produces schema mismatch errors.
13. **Using `LATERAL TABLE(UNNEST(...))`** — parse error on CC; use `CROSS JOIN UNNEST(...)`.
14. **Placing a CTE before `INSERT INTO`** — Flink requires `INSERT INTO t WITH cte AS (...) SELECT ...`.
15. **Using bare reserved words as identifiers** — `timestamp`, `value`, `offset`, `partition`, etc.
    must be backquoted: `` `timestamp` ``, `` `value` ``, etc.
16. **Writing `ALTER TABLE ... ADD WATERMARK`** — use `MODIFY`, not `ADD`, for watermarks on CC.
17. **Writing `CREATE FUNCTION f AS '...'` without `USING JAR`** — CC UDFs require an uploaded artifact.
18. **Using `SET 'execution.checkpointing.*'`** — CC manages checkpointing; these options error.
