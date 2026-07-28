# Flink 2.2 with Confluent Platform 8.3.0 - Hello World Demo

This guide walks you through setting up a local Apache Flink 2.2 session cluster and running a simple Table API job that reads from one Confluent Cloud Kafka topic and writes to another.

## Overview

This demo includes two applications:

1. **HelloWorldJob**: Simple pass-through job that reads from one topic and writes to another
2. **HelloWorldAggregate**: Continuous aggregation job that computes running sum and count by key

Both demonstrate:
- Installing Confluent Platform 8.3.0 and Apache Flink 2.2
- Starting a local Flink session mode cluster
- Building a Flink Table API application with Maven
- Running the application on the local Flink cluster
- Reading from and writing to Confluent Cloud Kafka topics with Avro format

## Prerequisites

- Linux or macOS environment (tested on Ubuntu 22.04)
- Java 17 JDK installed
- Maven 3.6+ installed
- Access to a Confluent Cloud cluster with:
  - Kafka cluster with API credentials
  - Schema Registry with API credentials
  - Two topics created (source and sink)
- Internet connection for downloading packages

## Step 1: Install Prerequisites

### Install Java 17 and Maven

On Ubuntu/Debian:
```bash
sudo apt-get update && \
sudo apt-get install -y \
    openjdk-17-jdk-headless \
    maven
```

On macOS (using Homebrew):
```bash
brew install openjdk@17 maven
```

Verify installations:
```bash
java -version
mvn -version
```

## Step 2: Download and Install Confluent Platform 8.3.0

Download and extract Confluent Platform:

```bash
# From your home directory
cd ~

# Download Confluent Platform 8.3.0
curl -O https://packages.confluent.io/archive/8.3/confluent-8.3.0.tar.gz

# Extract the archive
tar -xzvf confluent-8.3.0.tar.gz

# Create a symbolic link for easier access
ln -s confluent-8.3.0 confluent

# Add to PATH
echo 'export PATH=${PATH}:${HOME}/confluent/bin' >> ~/.bashrc
export PATH=${PATH}:${HOME}/confluent/bin
```

Verify installation:
```bash
kafka-topics --version
```

## Step 3: Download and Install Apache Flink 2.2.0

Download and extract Apache Flink:

```bash
# From your home directory
cd ~

# Download Flink 2.2.0 (check https://flink.apache.org/downloads/ for the latest mirror)
curl -LO https://dlcdn.apache.org/flink/flink-2.2.1/flink-2.2.1-bin-scala_2.12.tgz

# Extract the archive
tar -xzvf flink-2.2.1-bin-scala_2.12.tgz

# Create a symbolic link
ln -s flink-2.2.1 flink

# Add to PATH
echo 'export PATH=${PATH}:${HOME}/flink/bin' >> ~/.bashrc
export PATH=${PATH}:${HOME}/flink/bin
```

Verify installation:
```bash
flink --version
```

## Step 4: Configure Flink (Optional)

You can optionally tune the Flink configuration for better local development:

```bash
# Edit the Flink configuration
nano ~/flink/conf/config.yaml
```

Recommended changes:
- Set `rest.bind-address: 0.0.0.0` (to access Web UI from other machines)
- Set `taskmanager.numberOfTaskSlots: 8` (increase parallelism)

Example configuration snippet:
```yaml
rest.bind-address: 0.0.0.0
rest.port: 8081
taskmanager.numberOfTaskSlots: 8
```

## Step 5: Start Flink Session Cluster

Start the local Flink cluster in session mode:

```bash
start-cluster.sh
```

Verify the cluster is running:
- Check the Web UI at http://localhost:8081
- Or use the command line:
  ```bash
  flink list
  ```

To stop the cluster later:
```bash
stop-cluster.sh
```

## Step 6: Configure Confluent Cloud Connection



# Table API Jobs

In addition to the SQL-based jobs, this project includes **Table API** versions that use programmatic method chaining instead of SQL strings.

## Available Table API Jobs

1. **HelloWorldTableJob**: Pass-through job using Table API
2. **HelloWorldTableAggregate**: Continuous aggregation using Table API

## SQL vs Table API Comparison

| Aspect | SQL-based Jobs | Table API Jobs |
|--------|----------------|----------------|
| **Table Creation** | SQL DDL strings (`CREATE TABLE ...`) | TableDescriptor API (`.forConnector()`, `.schema()`) |
| **Query Style** | SQL strings (`INSERT INTO ... SELECT ...`) | Method chaining (`.select()`, `.groupBy()`) |
| **Type Safety** | String-based (runtime errors) | Expression-based (some compile-time checking) |
| **IDE Support** | Limited (SQL in strings) | Better (autocomplete, refactoring) |
| **Readability** | Familiar SQL syntax | Java/functional style |
| **Use Case** | Quick prototyping, SQL experts | Complex transformations, Java developers |

**Key Difference**: Table API jobs use **TableDescriptor** for fully programmatic table creation, eliminating SQL DDL strings entirely.

## HelloWorldTableJob - Table API Version

### What's Different

**Table Creation** - Uses TableDescriptor instead of SQL DDL:
```java
TableDescriptor sourceDescriptor = TableDescriptor.forConnector("kafka")
    .schema(Schema.newBuilder()
        .column("id", DataTypes.STRING())
        .column("message", DataTypes.STRING())
        .column("timestamp", DataTypes.BIGINT())
        .build())
    .option("topic", sourceTopic)
    .option("properties.bootstrap.servers", bootstrapServers)
    // ... more options
    .build();
tableEnv.createTemporaryTable("kafka_source", sourceDescriptor);
```

**Query Execution** - Uses Table API instead of SQL:
```java
Table sourceTable = tableEnv.from("kafka_source");
Table resultTable = sourceTable.select($("id"), $("message"), $("timestamp"));
resultTable.executeInsert("kafka_sink");
```

### Running HelloWorldTableJob

```bash
flink run \
  -c io.justinrlee.kafka.flink.HelloWorldTableJob \
  target/flink-sql-cloud-2.2.jar \
  --config-file client.properties
```

Uses the same configuration as HelloWorldJob (same topics).

## HelloWorldTableAggregate - Table API Version

### What's Different

**Table Creation** - Uses TableDescriptor with upsert-kafka:
```java
TableDescriptor sinkDescriptor = TableDescriptor.forConnector("upsert-kafka")
    .schema(Schema.newBuilder()
        .column("key", DataTypes.STRING())
        .column("id", DataTypes.STRING())
        .column("sum", DataTypes.DOUBLE())
        .column("count", DataTypes.BIGINT())
        .column("last_update", DataTypes.BIGINT())
        .primaryKey("key")
        .build())
    .option("topic", sinkTopic)
    // ... more options
    .build();
tableEnv.createTemporaryTable("kafka_sink_aggregate", sinkDescriptor);
```

**Aggregation Query** - Uses Table API instead of SQL:
```java
Table aggregatedTable = sourceTable
    .groupBy($("key"))
    .select(
        $("key"),
        $("key").as("id"),
        $("number").sum().as("sum"),
        $("key").count().as("count"),
        $("timestamp").max().as("last_update")
    );
```

### Running HelloWorldTableAggregate

```bash
flink run \
  -c io.justinrlee.kafka.flink.HelloWorldTableAggregate \
  target/flink-sql-cloud-2.2.jar \
  --config-file client.properties
```

Uses the same configuration as HelloWorldAggregate (same topics).

## When to Use Table API vs SQL

**Use SQL-based jobs when:**
- You're more comfortable with SQL syntax
- Quick prototyping and ad-hoc queries
- Working with data analysts who know SQL
- Simple transformations and filters

**Use Table API jobs when:**
- Building complex data pipelines with many transformations
- Need better IDE support (autocomplete, refactoring)
- Prefer functional/method-chaining style
- Want more type safety in your code
- Building reusable transformation logic

## Summary of All Jobs

| Job Name | API Style | Purpose | Input | Output |
|----------|-----------|---------|-------|--------|
| HelloWorldJob | SQL | Pass-through | Avro value | Avro value |
| HelloWorldTableJob | Table API | Pass-through | Avro value | Avro value |
| HelloWorldAggregate | SQL | Aggregation | String key + Avro value | String key + Avro value (upsert) |
| HelloWorldTableAggregate | Table API | Aggregation | String key + Avro value | String key + Avro value (upsert) |

---


Create a `client.properties` file with your Confluent Cloud credentials:

```bash
cd ~/flink-sql-cloud/2.2
cp sample.client.properties client.properties
nano client.properties
```

Update the file with your actual credentials:

```properties
# Kafka Configuration
kafka.bootstrap.servers=pkc-xxxxx.region.provider.confluent.cloud:9092
kafka.api.key=YOUR_KAFKA_API_KEY
kafka.api.secret=YOUR_KAFKA_API_SECRET
kafka.group.id=flink-hello-world

# Schema Registry Configuration
schema.registry.url=https://psrc-xxxxx.region.provider.confluent.cloud
schema.registry.api.key=YOUR_SR_API_KEY
schema.registry.api.secret=YOUR_SR_API_SECRET

# Application Configuration
app.source.topic=input-topic
app.sink.topic=output-topic
```

**Important:** Never commit `client.properties` to version control. It's already in `.gitignore`.

## Step 7: Create Test Topics in Confluent Cloud

Create the source and sink topics in your Confluent Cloud cluster:

```bash
# Using Confluent CLI (if installed)
confluent kafka topic create input-topic --partitions 3
confluent kafka topic create output-topic --partitions 3

# Or use the Confluent Cloud UI
```

## Step 8: Build the Application

Build the Flink application using Maven:

```bash
cd ~/flink-sql-cloud/2.2
mvn clean package
```

This will create a fat JAR at:
```
target/flink-sql-cloud-2.2.jar
```

## Step 9: Run the Application

Submit the job to your local Flink cluster:

```bash
flink run \
  target/flink-sql-cloud-2.2.jar \
  --config-file client.properties
```

The application will:
1. Connect to your Confluent Cloud Kafka cluster
2. Create source and sink table definitions
3. Start streaming data from the source topic to the sink topic
4. Continue running until you stop it

## Step 10: Monitor the Job

### Using Flink Web UI

Open http://localhost:8081 in your browser to:
- View running jobs
- Check job metrics
- Monitor task managers
- View job execution plan

### Using Command Line

List running jobs:
```bash
flink list
```

Get job details:
```bash
flink info <job-id>
```

## Step 11: Produce Test Data

In a separate terminal, produce some test data to the source topic:

```bash
# Using kafka-avro-console-producer (requires Confluent Platform)
kafka-avro-console-producer \
  --bootstrap-server ${CONFLUENT_CLOUD_KAFKA_BOOTSTRAP_SERVER} \
  --topic input-topic \
  --property schema.registry.url=${CONFLUENT_CLOUD_SCHEMA_REGISTRY_ENDPOINT} \
  --property basic.auth.credentials.source=USER_INFO \
  --property basic.auth.user.info=${CONFLUENT_CLOUD_SCHEMA_REGISTRY_API_KEY}:${CONFLUENT_CLOUD_SCHEMA_REGISTRY_API_SECRET} \
  --producer.config <(cat <<EOF
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username='KAFKA_API_KEY' password='KAFKA_API_SECRET';
EOF
) \
  --property value.schema='{"type":"record","name":"TestMessage","fields":[{"name":"id","type":"string"},{"name":"message","type":"string"},{"name":"timestamp","type":"long"}]}'
```

Then enter messages in JSON format:
```json
{"id":"1","message":"Hello Flink","timestamp":1234567890}
{"id":"2","message":"Hello World","timestamp":1234567891}
```

## Step 12: Verify Output

Consume from the sink topic to verify data is flowing:

```bash
kafka-avro-console-consumer \
  --bootstrap-server ${CONFLUENT_CLOUD_KAFKA_BOOTSTRAP_SERVER} \
  --topic output-topic \
  --from-beginning \
  --property schema.registry.url=${CONFLUENT_CLOUD_SCHEMA_REGISTRY_ENDPOINT} \
  --property basic.auth.credentials.source=USER_INFO \
  --property basic.auth.user.info=${CONFLUENT_CLOUD_SCHEMA_REGISTRY_API_KEY}:${CONFLUENT_CLOUD_SCHEMA_REGISTRY_API_SECRET} \
  --consumer.config <(cat <<EOF
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username='KAFKA_API_KEY' password='KAFKA_API_SECRET';
group.id=test-consumer
EOF
)
```

## Step 13: Stop the Job

To stop the running job:

1. Get the job ID:
   ```bash
   flink list
   ```

2. Cancel the job:
   ```bash
   flink cancel <job-id>
   ```

Or simply press `Ctrl+C` in the terminal where you ran `flink run` (note: this may not gracefully stop the job).

## Troubleshooting

### Job Fails to Start

- Verify Confluent Cloud credentials are correct
- Check that topics exist in Confluent Cloud
- Ensure Schema Registry is accessible
- Check Flink logs: `~/flink/log/`

### Connection Timeout

- Verify network connectivity to Confluent Cloud
- Check firewall rules
- Ensure bootstrap servers URL is correct

### Schema Registry Errors

- Verify Schema Registry credentials
- Check that Schema Registry URL is correct
- Ensure topics have schemas registered (will be auto-registered on first write)

### Out of Memory Errors

- Increase JVM heap size in `~/flink/conf/config.yaml`:
  ```yaml
  jobmanager.memory.process.size: 2048m
  taskmanager.memory.process.size: 2048m
  ```

## Understanding the Code

The `HelloWorldJob.java` application:

1. **Loads Configuration**: Reads connection details from `client.properties`
2. **Creates Table Environment**: Sets up Flink Table API in streaming mode
3. **Defines Source Table**: Creates a Kafka source table with Avro deserialization
4. **Defines Sink Table**: Creates a Kafka sink table with Avro serialization
5. **Executes Query**: Runs a simple `INSERT INTO ... SELECT * FROM ...` query
6. **Handles Shutdown**: Gracefully cancels the job on Ctrl+C

Key features:
- Uses Flink Table API (SQL-like interface)
- Supports Avro format with Confluent Schema Registry
- Includes watermark strategy for event time processing
- Handles SASL_SSL authentication for Confluent Cloud

## Next Steps

- Modify the query to add transformations (filtering, aggregations, joins)
- Add more complex event time processing
- Experiment with different Flink connectors
- Deploy to a production Flink cluster (Kubernetes, YARN, etc.)
- Explore Flink's state management and checkpointing

## Additional Resources

- [Apache Flink Documentation](https://flink.apache.org/docs/stable/)
- [Flink Table API & SQL](https://flink.apache.org/docs/stable/dev/table/)
- [Confluent Platform Documentation](https://docs.confluent.io/)
- [Flink Kafka Connector](https://nightlies.apache.org/flink/flink-docs-stable/docs/connectors/table/kafka/)

## Clean Up

To clean up your environment:

```bash
# Stop Flink cluster
stop-cluster.sh

# Remove downloaded archives (optional)
rm ~/confluent-8.3.0.tar.gz
rm ~/flink-2.2.0-bin-scala_2.12.tgz

# Delete topics in Confluent Cloud (if no longer needed)
confluent kafka topic delete input-topic
confluent kafka topic delete output-topic
```


# HelloWorldAggregate - Continuous Aggregation Job

In addition to the basic HelloWorldJob, this project includes **HelloWorldAggregate**, which demonstrates continuous stateful aggregation.

## What It Does

HelloWorldAggregate:
- Reads Kafka messages with **string keys** and **Avro values**
- Performs **continuous aggregation** by key (running sum and count)
- Uses **event time processing** with watermarks
- Writes aggregated results back to Kafka

### Input Schema
- **Key**: String ID (used for Kafka partitioning and aggregation grouping)
- **Value**: Avro with fields:
  - `number` (DOUBLE): Numeric value to aggregate
  - `timestamp` (BIGINT): Event timestamp

### Output Schema
- **Key**: String ID (same as input)
- **Value**: Avro with fields:
  - `id` (STRING): The aggregation key
  - `sum` (DOUBLE): Running total of all `number` values for this key
  - `count` (BIGINT): Total count of messages for this key
  - `last_update` (BIGINT): Timestamp of the most recent message

**Note**: The output uses the `upsert-kafka` connector, which means each key will have only one record in the topic (the latest aggregate). Updates overwrite previous values for the same key.

## Configuration

Add these properties to your `client.properties`:

```properties
# Aggregate Job Topics
app.aggregate.source.topic=aggregate-input
app.aggregate.sink.topic=aggregate-output
```

## Running HelloWorldAggregate

### 1. Create Topics

```bash
# Create topics with appropriate partitions
confluent kafka topic create aggregate-input --partitions 3
confluent kafka topic create aggregate-output --partitions 3
```

### 2. Build the Application

```bash
mvn clean package
```

### 3. Submit the Job

```bash
flink run \
  -c io.justinrlee.kafka.flink.HelloWorldAggregate \
  target/flink-sql-cloud-2.2.jar \
  --config-file client.properties
```

Note the `-c` flag to specify the main class.

## Testing with Sample Data

### Produce Test Messages

Create a file `aggregate-test-data.json` with sample messages:

```json
{"key":"user1","number":10.5,"timestamp":1234567890}
{"key":"user2","number":20.0,"timestamp":1234567891}
{"key":"user1","number":5.5,"timestamp":1234567892}
{"key":"user3","number":15.0,"timestamp":1234567893}
{"key":"user1","number":8.0,"timestamp":1234567894}
{"key":"user2","number":12.5,"timestamp":1234567895}
```

### Using kafka-avro-console-producer with String Key and Avro Value

Since we need string keys and Avro values, use kafka-avro-console-producer:

```bash
# Produce messages with string keys and Avro values
kafka-avro-console-producer \
  --bootstrap-server ${CONFLUENT_CLOUD_KAFKA_BOOTSTRAP_SERVER} \
  --property schema.registry.url=${CONFLUENT_CLOUD_SCHEMA_REGISTRY_ENDPOINT} \
  --property basic.auth.credentials.source=USER_INFO \
  --property basic.auth.user.info=${CONFLUENT_CLOUD_SCHEMA_REGISTRY_API_KEY}:${CONFLUENT_CLOUD_SCHEMA_REGISTRY_API_SECRET} \
  --property value.schema='{"name":"AggregateInput","type":"record","fields":[{"name":"number","type":"double"},{"name":"timestamp","type":"long"}]}' \
  --property key.serializer=org.apache.kafka.common.serialization.StringSerializer \
  --property parse.key=true \
  --property key.separator="|" \
  --topic aggregate-input \
  --producer.config client.properties
```

Then enter messages in `key|value` format (note the pipe separator):
```
user1|{"number":10.5,"timestamp":1234567890}
user2|{"number":20.0,"timestamp":1234567891}
user1|{"number":5.5,"timestamp":1234567892}
user3|{"number":15.0,"timestamp":1234567893}
user1|{"number":8.0,"timestamp":1234567894}
user2|{"number":12.5,"timestamp":1234567895}
```

### Expected Output

After processing, the aggregate-output topic should contain:

```json
{"key":"user1","id":"user1","sum":24.0,"count":3,"last_update":1234567894}
{"key":"user2","id":"user2","sum":32.5,"count":2,"last_update":1234567895}
{"key":"user3","id":"user3","sum":15.0,"count":1,"last_update":1234567893}
```

Note: Since this is continuous aggregation, each new message for a key will produce an updated aggregate result.

### Consume Aggregated Results

```bash
kafka-avro-console-consumer \
  --bootstrap-server ${CONFLUENT_CLOUD_KAFKA_BOOTSTRAP_SERVER} \
  --topic aggregate-output \
  --from-beginning \
  --property print.key=true \
  --property key.separator=" => " \
  --property schema.registry.url=${CONFLUENT_CLOUD_SCHEMA_REGISTRY_ENDPOINT} \
  --property basic.auth.credentials.source=USER_INFO \
  --property basic.auth.user.info=${CONFLUENT_CLOUD_SCHEMA_REGISTRY_API_KEY}:${CONFLUENT_CLOUD_SCHEMA_REGISTRY_API_SECRET} \
  --consumer.config <(cat <<EOF
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username='${KAFKA_API_KEY}' password='${KAFKA_API_SECRET}';
group.id=aggregate-test-consumer
EOF
)
```

## How It Works

1. **Stateful Aggregation**: Flink maintains state for each key, updating the sum and count as new messages arrive
2. **Event Time Processing**: Uses watermarks to handle out-of-order events (5-second tolerance)
3. **Continuous Updates**: Each new message triggers an update to the aggregate, which is written to the output topic
4. **Exactly-Once Semantics**: With proper checkpointing, Flink guarantees each message is processed exactly once

## Comparison: HelloWorldJob vs HelloWorldAggregate

| Feature | HelloWorldJob | HelloWorldAggregate |
|---------|---------------|---------------------|
| **Purpose** | Pass-through (copy data) | Continuous aggregation |
| **State** | Stateless | Stateful (maintains running totals) |
| **Key Handling** | No key required | Requires string key for grouping |
| **Output** | One output per input | One output per key (updated continuously) |
| **Use Case** | Data transformation, filtering | Real-time analytics, metrics |

---

