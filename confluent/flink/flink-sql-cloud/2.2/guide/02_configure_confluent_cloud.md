# Step 2: Configure Confluent Cloud Connection

This guide covers setting up your connection to Confluent Cloud.

## Prerequisites

- Confluent Cloud account with an active cluster
- Kafka cluster with API credentials
- Schema Registry with API credentials

## Create Kafka API Key

1. Log in to [Confluent Cloud](https://confluent.cloud)
2. Navigate to your Kafka cluster
3. Go to **API Keys** section
4. Click **Add Key**
5. Select appropriate scope (cluster-level recommended)
6. Save the API Key and Secret securely

## Create Schema Registry API Key

1. In Confluent Cloud, navigate to **Schema Registry**
2. Go to **API Keys** section
3. Click **Add Key**
4. Save the API Key and Secret securely

## Create Topics

Create the source and sink topics for the demo:

### Using Confluent Cloud UI

1. Navigate to your Kafka cluster
2. Go to **Topics** section
3. Click **Add Topic**
4. Create `input-topic` with 3 partitions
5. Create `output-topic` with 3 partitions

### Using Confluent CLI

```bash
# Login to Confluent Cloud
confluent login

# Set your environment and cluster
confluent environment use <env-id>
confluent kafka cluster use <cluster-id>

# Create topics
confluent kafka topic create input-topic --partitions 3
confluent kafka topic create output-topic --partitions 3
```

## Configure client.properties

Navigate to your project directory and create the configuration file:

```bash
cd ~/flink-sql-cloud/2.2
cp sample.client.properties client.properties
```

Edit `client.properties` with your actual credentials:

```bash
nano client.properties
```

Update with your values:

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

### Finding Your Connection Details

**Bootstrap Servers:**
- Confluent Cloud UI → Cluster → Cluster Settings → Bootstrap server

**Schema Registry URL:**
- Confluent Cloud UI → Schema Registry → API endpoint

## Security Best Practices

⚠️ **Important Security Notes:**

1. **Never commit credentials to version control**
   - `client.properties` is already in `.gitignore`
   - Double-check before committing

2. **Use environment-specific files**
   - Keep separate configs for dev/staging/prod
   - Example: `client.dev.properties`, `client.prod.properties`

3. **Rotate credentials regularly**
   - Set up a schedule for API key rotation
   - Update all applications when rotating

4. **Use least-privilege access**
   - Create separate API keys for different applications
   - Limit permissions to only what's needed

## Verify Configuration

Test your connection using Confluent CLI tools:

```bash
# Test Kafka connection
kafka-console-consumer \
  --bootstrap-server <your-bootstrap-server> \
  --topic input-topic \
  --consumer.config <(cat <<EOF
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username='<KAFKA_API_KEY>' password='<KAFKA_API_SECRET>';
group.id=test-consumer
EOF
) \
  --from-beginning \
  --max-messages 1
```

If the connection is successful, you'll see either:
- Messages (if topic has data)
- A waiting cursor (if topic is empty)

Press `Ctrl+C` to exit.

## Next Steps

Proceed to [03_start_flink_cluster.md](03_start_flink_cluster.md) to start your local Flink cluster.
