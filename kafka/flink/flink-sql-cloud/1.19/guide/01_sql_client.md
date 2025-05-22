# Part 1: Flink SQL CLI with local Flink cluster

## Start a local Flink cluster

Edit `~/flink/conf/config.yaml`, and make these changes:

* Set `.taskmanager.numberOfTaskSlots` to `8`

Note: exposing JobManager (port 8081) to the Internet is a major security vulnerability. Only do this if your EC2 instance is locked down from a firewall perspective so that it can only be accessed from your workstation IP.

* Set `.rest.bind-address` to `0.0.0.0`

Start the cluster (`~/flink/bin` should already be in your PATH)

```bash
start-cluster.sh
```

Run this to verify it's up and running;

```bash
ss -plunt | grep 8081
```

(Optional) If you modified `.rest.bind-address` to `0.0.0.0`, you can also open up the UI at port 8081 in a browser.

Start the SQL Client (run from home directory)

```bash
sql-client.sh \
  --jar flink-sql-connector-kafka-3.3.0-1.19-cp1.jar \
  --jar flink-sql-avro-confluent-registry-1.19.2-cp2.jar \
  --jar kafka-clients-7.9.1-ce.jar
```

## Run various SQL queries to interact with Confluent Cloud

For each of the queries in this section, you must replace these four variables with your corresponding credentials:

### Register Flink SQL Tables

The `kafka` and `upsert-kafka` Flink Connectors effectively overlay a SQL table structure on a topic in Kafka.

The configuration of each of these has these approximate components:

* table name: Flink-internal reference to the table
* table structure (each column approximately maps to a field in either the Kafka message key or value)
* watermark configuration (see Flink docs for this)
* connector information:
    * `kafka` treats the messages in a topic approximately as a series of events that happened (append-only table, effectively)
        * when reading/writing from a Kafka topic, each message is a processed an individual event
    * `upsert-kafka` supports a logical key
        * when reading from a Kafka topic, the key is used as the identifier for what the event describes (similar to a RDBMS table key). messages with the same key are treated as 'modifying' the properties of that object.
        * when writing to a kafka topic... (need to understand this better)
    * `topic` indicate what underlying topic we are referring to
    * `scan.startup.mode` indicates how where to start consuming
    * `properties.X` values provides information about how to communicate with Kafka (in our case, SASL_SSL/PLAIN, which means the SASL "PLAIN" mechanism wrapped in TLS/SSL)
    * `group.id` indicates what group ID to use (when consuming from Kafka) (TODO: understand how client IDs are generated, for both produce and consume)
    * `key.format` indicates how to deserialize or serialize the Kafka message key
    * `value.format` indicates how to deserialize or serialize the Kafka message body
    * there are a number of formats supported; we are using `avro-confluent` for our message values, and either `raw` or `avro-confluent` for our message keys
    * `[|key.|value.]avro-confluent` indicates how to communicate with Schema registry when using the `avro-confluent` format
    * On both consume and produce, `key.fields` when used with `raw` indicates what table column maps to the kafka message key
    * On produce, `key.fields` when used with `avro-confluent` indicates that message key should be written in Avro, with a fieldname indicated by the value of `key.fields` (and the value of the value populated by the value of the column) <- TODO rewrite this, this is garbage
    * On consume with the `upsert-kafka` connector and `avro-confluent` key format, indicates that messages coming in have a key formatted with avro
    * TODO: document `fields-include`


TODO: See if there's a way to do the logic without the rekey. Maybe use `upsert-kafka` directly on raw topics?

Run each query, one at a time, to see what it does. Each query must end with a semicolon.

```sql
-- Build tables

-- Append by default
-- In Confluent Cloud, `$rowtime` is a special field that contains the timestamp of the message; we're simulating that here by pulling from the Kafka-specific metadata field `timestamp`
-- METADATA FROM allows us to read a property of the Kafka message (rather than the key or value) and use that as a column in the table
-- Read other documentation to understand how watermarking works
CREATE TABLE `shoe_products` (
    `key` VARCHAR(2147483647), -- or VARBINARY
    `id` VARCHAR(2147483647),
    `brand` VARCHAR(2147483647),
    `name` VARCHAR(2147483647),
    `sale_price` INT,
    `rating` DOUBLE,
    `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
    WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'shoe-products',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'KAFKA_BOOTSTRAP_SERVER',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.format' = 'raw',
    'key.fields' = 'key',
    'value.fields-include' = 'EXCEPT_KEY',
    'value.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent'
);

-- Verify we're able to actually read the table
SELECT * FROM shoe_products LIMIT 10;

-- In Confluent Cloud, `$rowtime` is a special field that contains the timestamp of the message; we're simulating that here by pulling from the Kafka-specific metadata field `timestamp`
CREATE TABLE `shoe_customers` (
    `key` VARCHAR(2147483647), -- or VARBINARY
    `id` VARCHAR(2147483647),
    `first_name` VARCHAR(2147483647),
    `last_name` VARCHAR(2147483647),
    `email` VARCHAR(2147483647),
    `phone` VARCHAR(2147483647),
    `street_address` VARCHAR(2147483647),
    `state` VARCHAR(2147483647),
    `zip_code` VARCHAR(2147483647),
    `country` VARCHAR(2147483647),
    `country_code` VARCHAR(2147483647),
    `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
    WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'shoe-customers',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'KAFKA_BOOTSTRAP_SERVER',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.format' = 'raw',
    'key.fields' = 'key',
    'value.fields-include' = 'EXCEPT_KEY',
    'value.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent'
);

-- Verify we're able to actually read the table
SELECT * FROM shoe_customers LIMIT 10;


-- In Confluent Cloud, `$rowtime` is a special field that contains the timestamp of the message; we're simulating that here by pulling from the Kafka-specific metadata field `timestamp`
-- `ts` is a field in the message value
CREATE TABLE `shoe_orders` (
    `key` VARCHAR(2147483647), -- or VARBINARY
    `order_id` BIGINT,
    `product_id` VARCHAR(2147483647),
    `customer_id` VARCHAR(2147483647),
    `ts` TIMESTAMP(3),
    `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
    WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'shoe-orders',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'KAFKA_BOOTSTRAP_SERVER',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.format' = 'raw',
    'key.fields' = 'key',
    'value.fields-include' = 'EXCEPT_KEY',
    'value.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent'
);

-- Verify we're able to actually read the table
SELECT * FROM `shoe_orders` LIMIT 10;

-- Exploration queries start here

SELECT * FROM `shoe_customers`
WHERE `state` = 'Texas' AND `last_name` LIKE 'B%' LIMIT 10;

SELECT order_id, product_id, customer_id, $rowtime
FROM `shoe_orders`
WHERE customer_id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a'
LIMIT 10;

SELECT COUNT(id) AS num_customers FROM shoe_customers;

SELECT COUNT(DISTINCT id) AS num_customers FROM shoe_customers;


SELECT brand as brand_name, 
    COUNT(DISTINCT name) as models_by_brand, 
    ROUND(AVG(rating),2) as avg_rating,
    MAX(sale_price)/100 as max_price
FROM `shoe_products`
GROUP BY brand;

SELECT
 window_end,
 COUNT(DISTINCT order_id) AS num_orders
FROM TABLE(
   TUMBLE(TABLE `shoe_orders`, DESCRIPTOR(`$rowtime`), INTERVAL '1' MINUTES))
GROUP BY window_start, window_end;


SELECT
 window_start, window_end,
 COUNT(DISTINCT order_id) AS num_orders
FROM TABLE(
   HOP(TABLE `shoe_orders`, DESCRIPTOR(`$rowtime`), INTERVAL '5' MINUTES, INTERVAL '10' MINUTES))
GROUP BY window_start, window_end;


----- Create destination table for the first rekey
--- don't forget to create the topic directly in Kafka (Flink will not do it for you)
--- Flink 1.19 does not have "DISTRIBUTED BY HASH"
--- preserve source message timestamps

-- key: avro
-- value: avro
-- customer_id in only value
-- topic created manually (out of band), not created by Flink
-- schema registed automatically by Flink
CREATE TABLE `shoe_customers_keyed` (
    `customer_id` VARCHAR(2147483647) NOT NULL,
    `first_name` VARCHAR(2147483647),
    `last_name` VARCHAR(2147483647),
    `email` VARCHAR(2147483647),
    `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
    WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'shoe-customers-keyed',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'KAFKA_BOOTSTRAP_SERVER',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'key.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'key.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'key.format' = 'avro-confluent',
    'key.fields' = 'customer_id',
    'value.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent',
    'value.fields-include' = 'EXCEPT_KEY'
);

------- This will start a 'persistent' job on the Flink cluster; this job will persist even after the SQL client is terminated
--- To see running jobs, run `show jobs`
--- To stop a job, run `stop job 'xyz'` (note that the job ID must be wrapped in single quotes)

INSERT INTO `shoe_customers_keyed`
SELECT `id`, `first_name`, `last_name`, `email`, `$rowtime`
FROM `shoe_customers`;

------- Take a look at the destination rekeyed topic, both via Kafka, and also via Flink

SELECT COUNT(*) as AMOUNTROWS FROM `shoe_customers_keyed`;

SELECT * 
 FROM `shoe_customers_keyed`  
 WHERE customer_id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';

SELECT *
 FROM `shoe_customers`
 WHERE id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';

----- Create destination table for the second rekey
--- don't forget to create the topic directly in Kafka (Flink will not do it for you)

CREATE TABLE `shoe_products_keyed`(
    `product_id` STRING NOT NULL,
    `brand` STRING,
    `model` STRING,
    `sale_price` INT,
    `rating` DOUBLE,
    `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
    WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'shoe-products-keyed',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'KAFKA_BOOTSTRAP_SERVER',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'key.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'key.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'key.format' = 'avro-confluent',
    'key.fields' = 'product_id',
    'value.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent',
    'value.fields-include' = 'EXCEPT_KEY'
);

----- persistent job for second rekey


INSERT INTO `shoe_products_keyed` 
SELECT `id`, `brand`, `name`, `sale_price`, `rating`, `$rowtime`
FROM `shoe_products`;

--------------------------------------------------

----- Because we're trying to do a temporal join, we need a Flink primary key on the table (not a kafka key). 
--- I can't figure out how to get this to work with the same Flink table, so we create a second Flink table referencing the same Kafka topic
CREATE TABLE `shoe_customers_keyed-source` (
    `customer_id` VARCHAR(2147483647) NOT NULL,
    `first_name` VARCHAR(2147483647),
    `last_name` VARCHAR(2147483647),
    `email` VARCHAR(2147483647),
    `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
    PRIMARY KEY (`customer_id`) NOT ENFORCED,
    WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
) WITH (
    'connector' = 'upsert-kafka',
    'topic' = 'shoe-customers-keyed',
    'properties.bootstrap.servers' = 'KAFKA_BOOTSTRAP_SERVER',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'properties.auto.offset.reset' = 'latest',
    'key.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'key.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'key.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'key.format' = 'avro-confluent',
    'value.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent',
    'value.fields-include' = 'EXCEPT_KEY'
);

--- again, for products

CREATE TABLE `shoe_products_keyed-source` (
    `product_id` STRING NOT NULL,
    `brand` STRING,
    `model` STRING,
    `sale_price` INT,
    `rating` DOUBLE,
    `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
    PRIMARY KEY (`product_id`) NOT ENFORCED,
    WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
) WITH (
    'connector' = 'upsert-kafka',
    'topic' = 'shoe-products-keyed',
    'properties.bootstrap.servers' = 'KAFKA_BOOTSTRAP_SERVER',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'key.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'key.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'key.format' = 'avro-confluent',
    'value.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent',
    'value.fields-include' = 'EXCEPT_KEY'
);

--- do the temporal join
SELECT
  `order_id`,
  `shoe_orders`.`$rowtime`,
  `first_name`,
  `last_name`
FROM `shoe_orders`
INNER JOIN `shoe_customers_keyed-source` FOR SYSTEM_TIME AS OF `shoe_orders`.`$rowtime`
ON `shoe_orders`.`customer_id` = `shoe_customers_keyed-source`.`customer_id`
WHERE `shoe_customers_keyed-source`.`customer_id` = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';


--- do a more generic temporal join

SELECT
    *
FROM `shoe_orders`
INNER JOIN `shoe_customers_keyed-source` FOR SYSTEM_TIME AS OF `shoe_orders`.`$rowtime`
ON `shoe_orders`.`customer_id` = `shoe_customers_keyed-source`.`customer_id` LIMIT 10;

------- create a destination table for the enrichment
--- don't forget to create the topic directly in Kafka (Flink will not do it for you)

CREATE TABLE `shoe_orders_enriched` (
    `order_id` BIGINT,
    `first_name` VARCHAR(2147483647),
    `last_name` VARCHAR(2147483647),
    `email` VARCHAR(2147483647),
    `sale_price` INT,
    `brand` VARCHAR(2147483647),
    `model` VARCHAR(2147483647),
    `ordertime` TIMESTAMP(3)
) WITH (
    'connector' = 'kafka',
    'topic' = 'shoe-orders-enriched',
    'properties.bootstrap.servers' = 'KAFKA_BOOTSTRAP_SERVER',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'key.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'key.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'key.format' = 'avro-confluent',
    'key.fields' = 'order_id',
    'value.avro-confluent.url' = 'SCHEMA_REGISTRY_ENDPOINT',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent',
    'value.fields-include' = 'ALL'
)

INSERT INTO `shoe_orders_enriched`
SELECT
  `order_id`,
  `first_name`,
  `last_name`,
  `email`,
  `sale_price`,
  `brand`,
  `model`,
  `shoe_orders`.`$rowtime`
FROM `shoe_orders`
INNER JOIN `shoe_customers_keyed-source` FOR SYSTEM_TIME AS OF `shoe_orders`.`$rowtime`
ON `shoe_orders`.`customer_id` = `shoe_customers_keyed-source`.`customer_id`
INNER JOIN `shoe_products_keyed-source` FOR SYSTEM_TIME AS OF `shoe_orders`.`$rowtime`
ON `shoe_orders`.`product_id` = `shoe_products_keyed-source`.`product_id`;
```