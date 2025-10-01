-- Build tables

-- Append by default
-- In Confluent Cloud, `$rowtime` is a special field that contains the timestamp of the message; we're simulating that here by pulling from the Kafka-specific metadata field `timestamp`

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
    'topic' = 'flink-shoe_products',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.format' = 'raw',
    'key.fields' = 'key',
    'value.fields-include' = 'EXCEPT_KEY',
    'value.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent'
);

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
    'topic' = 'flink-shoe_customers',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.format' = 'raw',
    'key.fields' = 'key',
    'value.fields-include' = 'EXCEPT_KEY',
    'value.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent'
);

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
    'topic' = 'flink-shoe_orders',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.format' = 'raw',
    'key.fields' = 'key',
    'value.fields-include' = 'EXCEPT_KEY',
    'value.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent'
);


SELECT * FROM `shoe_orders` LIMIT 10;

-- Queries Start Here

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


----- CREATE
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
    'topic' = 'cp-shoe_customers_keyed',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
    'key.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'key.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'key.format' = 'avro-confluent',
    'key.fields' = 'customer_id',
    'value.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent',
    'value.fields-include' = 'EXCEPT_KEY'
);

-------
INSERT INTO `shoe_customers_keyed`
SELECT `id`, `first_name`, `last_name`, `email`, `$rowtime`
FROM `shoe_customers`;

-------

SELECT COUNT(*) as AMOUNTROWS FROM `shoe_customers_keyed`;

SELECT * 
 FROM `shoe_customers_keyed`  
 WHERE customer_id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';

SELECT *
 FROM `shoe_customers`
 WHERE id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';

----------
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
    'topic' = 'cp-shoe_products_keyed',
    'scan.startup.mode' = 'earliest-offset',
    'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'key.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
    'key.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'key.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'key.format' = 'avro-confluent',
    'key.fields' = 'product_id',
    'value.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent',
    'value.fields-include' = 'EXCEPT_KEY'
);

----- persistent job


INSERT INTO `shoe_products_keyed` 
SELECT `id`, `brand`, `name`, `sale_price`, `rating`, `$rowtime`
FROM `shoe_products`;

----- 
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
    'topic' = 'cp-shoe_customers_keyed',
    'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
    'properties.security.protocol' = 'SASL_SSL',
    'properties.sasl.mechanism' = 'PLAIN',
    'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="KAFKA_API_KEY" password="KAFKA_API_SECRET";',
    'properties.group.id' = 'shoe-store',
    'properties.auto.offset.reset' = 'latest',
    'key.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
    'key.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'key.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'key.format' = 'avro-confluent',
    'value.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
    'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
    'value.avro-confluent.basic-auth.user-info' = 'SR_API_KEY:SR_API_SECRET',
    'value.format' = 'avro-confluent',
    'value.fields-include' = 'EXCEPT_KEY'
);

--- temporal join
SELECT
  `order_id`,
  `shoe_orders`.`$rowtime`,
  `first_name`,
  `last_name`
FROM `shoe_orders`
INNER JOIN `shoe_customers_keyed-source` FOR SYSTEM_TIME AS OF `shoe_orders`.`$rowtime`
ON `shoe_orders`.`customer_id` = `shoe_customers_keyed-source`.`customer_id`
WHERE `shoe_customers_keyed-source`.`customer_id` = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';


SELECT
    *
FROM `shoe_orders`
INNER JOIN `shoe_customers_keyed-source` FOR SYSTEM_TIME AS OF `shoe_orders`.`$rowtime`
ON `shoe_orders`.`customer_id` = `shoe_customers_keyed-source`.`customer_id` LIMIT 10;