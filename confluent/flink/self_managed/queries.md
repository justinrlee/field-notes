```
sql-client.sh -Drest.address=jobmanager.confluent -Drest.port=8081
```

## Prep: Connectors

Based on this: https://github.com/griga23/shoe-store/tree/main

`shoe_orders`
```json
{
  "connector.class":"io.confluent.kafka.connect.datagen.DatagenConnector",
  "quickstart":"shoe_orders",
  "tasks.max":"1",
  "name":"shoe_orders",
  "kafka.topic":"shoe_orders"
}
```


shoe_products (shoes)
```json
{
  "connector.class":"io.confluent.kafka.connect.datagen.DatagenConnector",
  "quickstart":"shoes",
  "tasks.max":"1",
  "name":"shoes",
  "kafka.topic":"shoes"
}
```

shoe_customers
```json
{
  "connector.class":"io.confluent.kafka.connect.datagen.DatagenConnector",
  "quickstart":"shoe_customers",
  "tasks.max":"1",
  "name":"shoe_customers",
  "kafka.topic":"shoe_customers"
}
```

## Demo


```sql
CREATE TABLE shoes (
  `id` VARCHAR(2147483647),
  `brand` VARCHAR(2147483647),
  `name` VARCHAR(2147483647),
  `sale_price` BIGINT,
  `rating` FLOAT,
  `ts` TIMESTAMP(3) METADATA FROM 'timestamp',
  WATERMARK FOR `ts` as `ts` - INTERVAL '5' SECOND
) WITH (
  'connector' = 'kafka',
  'topic' = 'shoes',
  'properties.bootstrap.servers' = 'kafka:9071',
  'properties.group.id' = 'shoes',
  'scan.startup.mode' = 'earliest-offset',
  'value.format' = 'json',
  'value.fields-include' = 'ALL'
);
```


```sql
CREATE TABLE shoe_customers (
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
  `ts` TIMESTAMP(3) METADATA FROM 'timestamp',
  WATERMARK FOR `ts` as `ts` - INTERVAL '5' SECOND
) WITH (
  'connector' = 'kafka',
  'topic' = 'shoe_customers',
  'properties.bootstrap.servers' = 'kafka:9071',
  'properties.group.id' = 'shoe_customers',
  'scan.startup.mode' = 'earliest-offset',
  'value.format' = 'json',
  'value.fields-include' = 'ALL'
);
```


```sql
CREATE TABLE shoe_orders (
  `order_id` BIGINT,
  `product_id` VARCHAR(2147483647),
  `customer_id` VARCHAR(2147483647),
  `ts` TIMESTAMP(3) METADATA FROM 'timestamp',
  WATERMARK FOR `ts` as `ts` - INTERVAL '5' SECOND
) WITH (
  'connector' = 'kafka',
  'topic' = 'shoe_orders',
  'properties.bootstrap.servers' = 'kafka:9071',
  'properties.group.id' = 'shoe_orders',
  'scan.startup.mode' = 'earliest-offset',
  'value.format' = 'json',
  'value.fields-include' = 'ALL'
);
```


### Basic Select

```sql
SELECT * FROM shoe_customers
  WHERE `state` = 'Texas' AND `last_name` LIKE 'B%';
```

```sql
SELECT order_id, product_id, customer_id, ts
  FROM shoe_orders
  WHERE customer_id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a'
  LIMIT 10;
```

All 'shoe customer rows' (including duplicates)
```sql
SELECT COUNT(id) AS num_customers FROM shoe_customers;
```

Unique customers:

```sql
SELECT COUNT(DISTINCT id) AS num_customers FROM shoe_customers;
```

### Aggregation

```sql
SELECT brand as brand_name, 
    COUNT(DISTINCT name) as models_by_brand, 
    ROUND(AVG(rating),2) as avg_rating,
    MAX(sale_price)/100 as max_price
FROM shoes
GROUP BY brand;
```

### Time Windows

Orders per one minute interval (tumbling window)
```sql
SELECT
 window_end,
 COUNT(DISTINCT order_id) AS num_orders
FROM TABLE(
   TUMBLE(TABLE shoe_orders, DESCRIPTOR(`ts`), INTERVAL '1' MINUTES))
GROUP BY window_start, window_end;
```

Ten minute interval (hopping)
```sql
SELECT
 window_start, window_end,
 COUNT(DISTINCT order_id) AS num_orders
FROM TABLE(
   HOP(TABLE shoe_orders, DESCRIPTOR(`ts`), INTERVAL '5' MINUTES, INTERVAL '10' MINUTES))
GROUP BY window_start, window_end;
```

### Keys

ACTION: Create topic `shoe_customers_keyed`


Create destination table

```sql
CREATE TABLE shoe_customers_keyed (
  `id` VARCHAR(2147483647),
  `first_name` VARCHAR(2147483647),
  `last_name` VARCHAR(2147483647),
  `email` VARCHAR(2147483647),
  PRIMARY KEY (id) NOT ENFORCED,
  `ts` TIMESTAMP(3) METADATA FROM 'timestamp',
  WATERMARK FOR `ts` as `ts` - INTERVAL '5' SECOND
) WITH (
  'connector' = 'upsert-kafka',
  'topic' = 'shoe_customers_keyed',
  'properties.bootstrap.servers' = 'kafka:9071',
  'key.format' = 'raw',
  'value.format' = 'json',
  'value.fields-include' = 'ALL'
);
```

Insert into destination (keyed) table

```sql
INSERT INTO shoe_customers_keyed
  SELECT id, first_name, last_name, email, ts
    FROM shoe_customers;
```

Get number of customers
```sql
SELECT COUNT(*) as AMOUNTROWS FROM shoe_customers_keyed;
```

Get all 'customer' records for one customer (multiple rows)

```sql
SELECT *
 FROM shoe_customers
 WHERE id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';
```

Get same customer from keyed table:
```sql
SELECT * 
 FROM shoe_customers_keyed  
 WHERE id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';
```


Store unique products

ACTION: Create topic `shoe_products_keyed`

```sql
CREATE TABLE shoes_keyed (
  `product_id` STRING,
  `brand` STRING,
  `model` STRING,
  `sale_price` BIGINT,
  `rating` FLOAT,
  PRIMARY KEY (`product_id`) NOT ENFORCED
) WITH (
  'connector' = 'upsert-kafka',
  'topic' = 'shoes_keyed',
  'properties.bootstrap.servers' = 'kafka:9071',
  'key.format' = 'raw',
  'value.format' = 'json',
  'value.fields-include' = 'ALL'
);
```

Rekey data

```sql
SET 'table.exec.sink.not-null-enforcer'='DROP';
```

```sql
INSERT INTO shoes_keyed
  SELECT id, brand, `name`, sale_price, rating 
    FROM shoes;
```

Look at specific product record
```sql
SELECT * 
 FROM shoes_keyed  
 WHERE product_id = '0fd15be0-8b95-4f19-b90b-53aabf4c49df';
```


## Time Semantics

Look at rowtime
```sql
SELECT id, ts
FROM shoe_customers  
WHERE id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';
```

A single customer may have many orders
```sql
SELECT order_id, customer_id, ts
FROM shoe_orders
WHERE customer_id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';
```

Regular Join (join all orders against all customers): many duplicates
```sql
SELECT 
    order_id,
    shoe_orders.ts,
    first_name,
    last_name
FROM shoe_orders
    INNER JOIN shoe_customers 
ON shoe_orders.customer_id = shoe_customers.id
WHERE customer_id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';
```

Join based on 'order around shoe timestamp': some duplicates
```sql
SELECT 
    order_id,
    shoe_orders.ts AS order_time,
    shoe_customers.ts AS customer_record_time,
    email
FROM shoe_orders
    INNER JOIN shoe_customers
ON shoe_orders.customer_id = shoe_customers.id
WHERE customer_id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a' 
AND
  shoe_orders.ts BETWEEN shoe_customers.ts - INTERVAL '10' MINUTES AND shoe_customers.ts;
```

Slightly better join (with keyed table): gets most recent customer record for each joined record, but based on current value of customer record (vs. customer record value at time of order)
```sql
SELECT 
    order_id,
    shoe_orders.ts,
    first_name,
    last_name
FROM shoe_orders
    INNER JOIN shoe_customers_keyed 
ON shoe_orders.customer_id = shoe_customers_keyed.id
WHERE shoe_customers_keyed.id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';
```

Temporal Join: Best join (probably): get customer record at time of order

```sql
SELECT 
    order_id,
    shoe_orders.ts,
    first_name,
    last_name
FROM shoe_orders
    INNER JOIN shoe_customers_keyed 
    FOR SYSTEM_TIME AS OF shoe_orders.ts
ON shoe_orders.customer_id = shoe_customers_keyed.id
WHERE shoe_customers_keyed.id = 'b523f7f3-0338-4f1f-a951-a387beeb8b6a';
```

## Data Enrichment

ACTION: Create topic `shoe_order_customer_product`

```sql
CREATE TABLE shoe_order_customer_product(
    `order_id` BIGINT,
    `first_name` STRING,
    `last_name` STRING,
    `email` STRING,
    `brand` STRING,
    `model` STRING,
    `sale_price` BIGINT,
    `rating` FLOAT,
    `ts` TIMESTAMP(3) METADATA FROM 'timestamp',
      PRIMARY KEY (`order_id`) NOT ENFORCED
) WITH (
    'connector' = 'upsert-kafka',
    'topic' = 'shoe_order_customer_product',
    'properties.bootstrap.servers' = 'kafka:9071',
    'key.format' = 'raw',
    'value.format' = 'json',
    'value.fields-include' = 'ALL'
);
```

```sql
INSERT INTO shoe_order_customer_product (
    `order_id`,
    `first_name`,
    `last_name`,
    `email`,
    `brand`,
    `model`,
    `sale_price`,
    `rating`
)
SELECT
    so.order_id,
    sc.first_name,
    sc.last_name,
    sc.email,
    sp.brand,
    sp.`model`,
    sp.sale_price,
    sp.rating
FROM 
  shoe_orders so
  INNER JOIN shoe_customers_keyed sc 
    ON so.customer_id = sc.id
  INNER JOIN shoes_keyed sp
    ON so.product_id = sp.product_id;
```

Show output
```sql
SELECT * FROM shoe_order_customer_product;
```

### Fancy Stuff
Case statement

```sql
SELECT
  email,
  SUM(sale_price) AS total,
  CASE
    WHEN SUM(sale_price) > 800000 THEN 'GOLD'
    WHEN SUM(sale_price) > 70000 THEN 'SILVER'
    WHEN SUM(sale_price) > 6000 THEN 'BRONZE'
    ELSE 'CLIMBING'
  END AS rewards_level
FROM shoe_order_customer_product
GROUP BY email;
```

ACTION: Create topic `shoe_loyalty_levels`

Populate it
```sql
CREATE TABLE shoe_loyalty_levels (
  email STRING,
  total BIGINT,
  rewards_level STRING,
  PRIMARY KEY (email) NOT ENFORCED
) WITH (
    'connector' = 'upsert-kafka',
    'topic' = 'shoe_loyalty_levels',
    'properties.bootstrap.servers' = 'kafka:9071',
    'key.format' = 'raw',
    'value.format' = 'json',
    'value.fields-include' = 'ALL'
);
```

Promotions

10th order
```sql
SELECT
   email,
   COUNT(*) AS total,
   (COUNT(*) % 10) AS sequence,
   (COUNT(*) % 10) = 0 AS next_one_free
 FROM shoe_order_customer_product
 WHERE brand = 'Jones-Stokes'
 GROUP BY email;
```

Large volumes
```sql
SELECT
     email,
     COLLECT(brand) AS products,
     'bundle_offer' AS promotion_name
  FROM shoe_order_customer_product
  WHERE brand IN ('Braun-Bruen', 'Will Inc')
  GROUP BY email
  HAVING COUNT(DISTINCT brand) = 2 AND COUNT(brand) > 10;
```

ACTION ITEM: Create topic: `shoe_promotions`

Shoe promotion table
```sql
CREATE TABLE shoe_promotions (
  email STRING,
  promotion_name STRING,
  PRIMARY KEY (email) NOT ENFORCED
) WITH (
    'connector' = 'upsert-kafka',
    'topic' = 'shoe_promotions',
    'properties.bootstrap.servers' = 'kafka:9071',
    'key.format' = 'raw',
    'value.format' = 'json',
    'value.fields-include' = 'ALL'
);
```

Promotions in table
```sql
EXECUTE STATEMENT SET 
BEGIN

INSERT INTO shoe_promotions
SELECT
   email,
   'next_free' AS promotion_name
FROM shoe_order_customer_product
WHERE brand = 'Jones-Stokes'
GROUP BY email
HAVING COUNT(*) % 10 = 0;

INSERT INTO shoe_promotions
SELECT
     email,
     'bundle_offer' AS promotion_name
  FROM shoe_order_customer_product
  WHERE brand IN ('Braun-Bruen', 'Will Inc')
  GROUP BY email
  HAVING COUNT(DISTINCT brand) = 2 AND COUNT(brand) > 10;

END;
```
