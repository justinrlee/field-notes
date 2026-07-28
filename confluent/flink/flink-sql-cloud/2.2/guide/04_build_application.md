# Step 4: Build the Flink Application

This guide covers building the Flink Table API application using Maven.

## Prerequisites

- Maven installed and configured
- Project files in place (`pom.xml`, `HelloWorldJob.java`)
- Internet connection (for downloading dependencies)

## Understanding the Project Structure

```
flink-sql-cloud/2.2/
├── pom.xml                          # Maven build configuration
├── client.properties                # Confluent Cloud credentials (not in git)
├── sample.client.properties         # Template for credentials
└── src/
    └── main/
        └── java/
            └── io/
                └── justinrlee/
                    └── kafka/
                        └── flink/
                            └── HelloWorldJob.java  # Main application
```

## Review the pom.xml

The `pom.xml` includes:

- **Flink 2.2.0 dependencies**: Core Flink libraries
- **Kafka Connector**: For reading/writing Kafka topics
- **Avro Support**: For Avro serialization/deserialization
- **Schema Registry Client**: For Confluent Schema Registry integration
- **Maven Shade Plugin**: Creates a fat JAR with all dependencies

Key dependencies:
```xml
<flink.version>2.2.0</flink.version>
<confluent.platform.version>8.3.0-ce</confluent.platform.version>
<confluent.version>8.3.0</confluent.version>
```

## Build the Application

Navigate to the project directory and build:

```bash
cd ~/flink-sql-cloud/2.2
mvn clean package
```

### Build Process

The build will:
1. Download all dependencies (first time only)
2. Compile Java source files
3. Run tests (if any)
4. Create a shaded JAR with all dependencies

Expected output:
```
[INFO] ------------------------------------------------------------------------
[INFO] BUILD SUCCESS
[INFO] ------------------------------------------------------------------------
[INFO] Total time:  XX.XXX s
[INFO] Finished at: YYYY-MM-DDTHH:MM:SS
[INFO] ------------------------------------------------------------------------
```

### Output Artifact

The build creates:
```
target/flink-sql-cloud-2.2.jar
```

This is a "fat JAR" (uber JAR) containing:
- Your application code
- All runtime dependencies
- Kafka connector
- Avro libraries
- Schema Registry client

## Verify the Build

Check that the JAR was created:

```bash
ls -lh target/flink-sql-cloud-2.2.jar
```

You should see a file around 50-100 MB in size.

Verify the main class is set correctly:

```bash
jar -xf target/flink-sql-cloud-2.2.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF | grep Main-Class
```

Expected output:
```
Main-Class: io.justinrlee.kafka.flink.HelloWorldJob
```

## Understanding the Application Code

The `HelloWorldJob.java` application:

### 1. Configuration Loading
```java
Properties properties = loadProperties(configFile);
```
Loads Kafka and Schema Registry credentials from `client.properties`.

### 2. Table Environment Setup
```java
EnvironmentSettings settings = EnvironmentSettings.newInstance()
    .inStreamingMode()
    .build();
TableEnvironment tableEnv = TableEnvironment.create(settings);
```
Creates a Flink Table API environment for streaming.

### 3. Source Table Definition
```java
CREATE TABLE kafka_source (
    `id` STRING,
    `message` STRING,
    `timestamp` BIGINT,
    `event_time` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
    WATERMARK FOR `event_time` AS `event_time` - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'input-topic',
    ...
)
```
Defines how to read from the source Kafka topic with Avro format.

### 4. Sink Table Definition
```java
CREATE TABLE kafka_sink (
    `id` STRING,
    `message` STRING,
    `timestamp` BIGINT
) WITH (
    'connector' = 'kafka',
    'topic' = 'output-topic',
    ...
)
```
Defines how to write to the sink Kafka topic with Avro format.

### 5. Data Processing
```java
INSERT INTO kafka_sink SELECT * FROM kafka_source
```
Simple pass-through query (can be modified for transformations).

### 6. Graceful Shutdown
```java
Runtime.getRuntime().addShutdownHook(...)
```
Handles Ctrl+C to gracefully cancel the job.

## Troubleshooting Build Issues

### Dependency Download Failures

If Maven can't download dependencies:

```bash
# Clear local Maven cache
rm -rf ~/.m2/repository

# Retry build
mvn clean package
```

### Compilation Errors

Check Java version:
```bash
java -version
# Should be Java 17
```

### Out of Memory During Build

Increase Maven memory:
```bash
export MAVEN_OPTS="-Xmx2g"
mvn clean package
```

### Proxy Issues

If behind a corporate proxy, configure Maven:

```bash
nano ~/.m2/settings.xml
```

Add proxy configuration:
```xml
<settings>
  <proxies>
    <proxy>
      <id>corporate-proxy</id>
      <active>true</active>
      <protocol>http</protocol>
      <host>proxy.company.com</host>
      <port>8080</port>
    </proxy>
  </proxies>
</settings>
```

## Rebuild After Code Changes

After modifying the Java code:

```bash
# Quick rebuild (skips tests)
mvn clean package -DskipTests

# Full rebuild
mvn clean package
```

## Next Steps

Proceed to [05_run_application.md](05_run_application.md) to run the application on your Flink cluster.
