# Step 5: Run the Application

This guide covers running your Flink application on the local session cluster.

## Prerequisites

- Flink cluster is running (`start-cluster.sh`)
- Application JAR is built (`target/flink-sql-cloud-2.2.jar`)
- `client.properties` is configured with valid credentials
- Topics exist in Confluent Cloud

## Submit the Job

Submit your application to the Flink cluster:

```bash
cd ~/flink-sql-cloud/2.2

flink run \
  target/flink-sql-cloud-2.2.jar \
  --config-file client.properties
```

### Expected Output

You should see output similar to:

```
Starting Flink Hello World Job
Source topic: input-topic
Sink topic: output-topic

Creating source table:
CREATE TABLE kafka_source (
    `id` STRING,
    `message` STRING,
    ...
) WITH (...)

Creating sink table:
CREATE TABLE kafka_sink (
    `id` STRING,
    `message` STRING,
    ...
) WITH (...)

Executing query:
INSERT INTO kafka_sink SELECT * FROM kafka_source

Job has been submitted with JobID: a1b2c3d4e5f6g7h8i9j0
Job is running. Press Ctrl+C to stop...
```

## Monitor the Job

### Using Flink Web UI

1. Open http://localhost:8081
2. Navigate to **Running Jobs**
3. Click on your job to see:
   - Job graph (visual representation)
   - Metrics (records processed, throughput)
   - Task status
   - Checkpoints
   - Exceptions (if any)

### Using Command Line

List running jobs:
```bash
flink list
```

Output:
```
------------------------- Running/Restarting Jobs -------------------------
27.07.2026 14:02:43 : a1b2c3d4e5f6g7h8i9j0 : Flink Streaming Job (RUNNING)
---------------------------------------------------------------------------
```

Get detailed job information:
```bash
flink info a1b2c3d4e5f6g7h8i9j0
```

## Produce Test Data

In a **separate terminal**, produce test messages to the source topic.

### Option 1: Using kafka-avro-console-producer

```bash
kafka-avro-console-producer \
  --broker-list pkc-xxxxx.region.provider.confluent.cloud:9092 \
  --topic input-topic \
  --property schema.registry.url=https://psrc-xxxxx.region.provider.confluent.cloud \
  --property basic.auth.credentials.source=USER_INFO \
  --property basic.auth.user.info=SR_API_KEY:SR_API_SECRET \
  --producer.config <(cat <<EOF
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username='KAFKA_API_KEY' password='KAFKA_API_SECRET';
EOF
) \
  --property value.schema='{"type":"record","name":"TestMessage","fields":[{"name":"id","type":"string"},{"name":"message","type":"string"},{"name":"timestamp","type":"long"}]}'
```

Then enter messages (one per line):
```json
{"id":"1","message":"Hello Flink","timestamp":1234567890}
{"id":"2","message":"Hello World","timestamp":1234567891}
{"id":"3","message":"Testing streaming","timestamp":1234567892}
```

Press `Ctrl+C` when done.

### Option 2: Using Confluent Cloud UI

1. Navigate to your Kafka cluster in Confluent Cloud
2. Go to **Topics** → **input-topic**
3. Click **Produce a new message**
4. Select **Avro** format
5. Enter message in JSON format
6. Click **Produce**

## Verify Output

Consume from the sink topic to verify data is flowing:

```bash
kafka-avro-console-consumer \
  --bootstrap-server pkc-xxxxx.region.provider.confluent.cloud:9092 \
  --topic output-topic \
  --from-beginning \
  --property schema.registry.url=https://psrc-xxxxx.region.provider.confluent.cloud \
  --property basic.auth.credentials.source=USER_INFO \
  --property basic.auth.user.info=SR_API_KEY:SR_API_SECRET \
  --consumer.config <(cat <<EOF
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username='KAFKA_API_KEY' password='KAFKA_API_SECRET';
group.id=test-consumer
EOF
)
```

You should see the messages you produced:
```json
{"id":"1","message":"Hello Flink","timestamp":1234567890}
{"id":"2","message":"Hello World","timestamp":1234567891}
{"id":"3","message":"Testing streaming","timestamp":1234567892}
```

Press `Ctrl+C` to stop consuming.

## Understanding Job Behavior

### Continuous Processing

The job runs continuously:
- Reads from `input-topic` in real-time
- Processes each message
- Writes to `output-topic`
- Maintains state and checkpoints

### Parallelism

By default, the job uses available task slots:
- Check parallelism in Web UI
- Adjust in code or via CLI parameter

### Checkpointing

Flink periodically saves state:
- Enables fault tolerance
- Allows job recovery
- View checkpoints in Web UI

## Stop the Job

### Method 1: Cancel via Command Line

1. Get the job ID:
   ```bash
   flink list
   ```

2. Cancel the job:
   ```bash
   flink cancel a1b2c3d4e5f6g7h8i9j0
   ```

Expected output:
```
Cancelling job a1b2c3d4e5f6g7h8i9j0.
Cancelled job a1b2c3d4e5f6g7h8i9j0.
```

### Method 2: Cancel via Web UI

1. Open http://localhost:8081
2. Navigate to **Running Jobs**
3. Click on your job
4. Click **Cancel Job** button

### Method 3: Ctrl+C (Not Recommended)

Pressing `Ctrl+C` in the terminal where you ran `flink run`:
- Terminates the client
- **Does NOT stop the job** (it continues running)
- You must cancel the job separately

## Troubleshooting

### Job Fails to Start

Check the logs:
```bash
# JobManager logs
tail -f ~/flink/log/flink-*-standalonesession-*.log

# TaskManager logs
tail -f ~/flink/log/flink-*-taskexecutor-*.log
```

Common issues:
- Invalid Confluent Cloud credentials
- Topics don't exist
- Network connectivity issues
- Schema Registry errors

### Connection Timeout

```
Caused by: org.apache.kafka.common.errors.TimeoutException
```

Solutions:
- Verify bootstrap servers URL
- Check network connectivity
- Verify API credentials
- Check firewall rules

### Schema Registry Errors

```
Caused by: io.confluent.kafka.schemaregistry.client.rest.exceptions.RestClientException
```

Solutions:
- Verify Schema Registry URL
- Check Schema Registry credentials
- Ensure Schema Registry is accessible

### No Data Flowing

If messages aren't appearing in the sink topic:

1. Check job is running:
   ```bash
   flink list
   ```

2. Verify source topic has data:
   ```bash
   kafka-console-consumer \
     --bootstrap-server <bootstrap-server> \
     --topic input-topic \
     --consumer.config <config-file> \
     --from-beginning \
     --max-messages 1
   ```

3. Check job metrics in Web UI:
   - Records received
   - Records sent
   - Exceptions

4. Review job logs for errors

## Job Management Commands

```bash
# List all jobs
flink list

# Get job details
flink info <job-id>

# Cancel a job
flink cancel <job-id>

# Cancel with savepoint
flink cancel -s <savepoint-path> <job-id>

# Stop a job (graceful shutdown)
flink stop <job-id>
```

## Next Steps

Proceed to [06_advanced_topics.md](06_advanced_topics.md) to learn about:
- Modifying the query for transformations
- Adding aggregations and windowing
- State management and checkpointing
- Performance tuning
