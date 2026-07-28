package io.justinrlee.kafka.flink;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.table.api.TableResult;

import java.io.FileInputStream;
import java.io.IOException;
import java.util.Properties;

/**
 * Flink Table API job that performs continuous aggregation on Kafka messages.
 * 
 * This job demonstrates:
 * - Reading Kafka messages with string keys and Avro values
 * - Continuous stateful aggregation (running sum and count) by key
 * - Event time processing with watermarks
 * - Writing aggregated results back to Kafka
 * 
 * Input Schema:
 * - Key: String ID (used for Kafka partitioning and aggregation)
 * - Value: Avro with fields: number (numeric value to aggregate), timestamp
 * 
 * Output Schema:
 * - Key: String ID
 * - Value: Avro with fields: id, sum (running total), count (message count), last_update (timestamp)
 */
public class HelloWorldAggregate {
    private static volatile boolean isRunning = true;
    private static TableResult insertResult;

    public static void main(String[] args) throws Exception {
        // Parse command line arguments
        if (args.length < 2) {
            System.err.println("Usage: HelloWorldAggregate --config-file <path-to-properties>");
            System.exit(1);
        }

        String configFile = null;
        for (int i = 0; i < args.length; i++) {
            if ("--config-file".equals(args[i]) && i + 1 < args.length) {
                configFile = args[i + 1];
                break;
            }
        }

        if (configFile == null) {
            System.err.println("Error: --config-file parameter is required");
            System.exit(1);
        }

        // Load properties from file
        Properties properties = loadProperties(configFile);
        
        // Add shutdown hook for graceful termination
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("Shutdown hook triggered. Cancelling job...");
            isRunning = false;

            if (insertResult != null) {
                try {
                    insertResult.getJobClient().ifPresent(client -> {
                        try {
                            client.cancel().get();
                            System.out.println("Job cancelled successfully.");
                        } catch (Exception e) {
                            System.err.println("Error cancelling job: " + e.getMessage());
                        }
                    });
                } catch (Exception e) {
                    System.err.println("Error during job cancellation: " + e.getMessage());
                }
            }
        }));

        // Create TableEnvironment for streaming
        EnvironmentSettings settings = EnvironmentSettings.newInstance()
            .inStreamingMode()
            .build();
        
        TableEnvironment tableEnv = TableEnvironment.create(settings);

        System.out.println("Starting Flink Aggregate Job");
        System.out.println("Source topic: " + properties.getProperty("app.aggregate.source.topic"));
        System.out.println("Sink topic: " + properties.getProperty("app.aggregate.sink.topic"));

        // Create source table with key
        String createSourceTable = createKafkaSourceTable(properties);
        System.out.println("\nCreating source table:");
        System.out.println(createSourceTable);
        tableEnv.executeSql(createSourceTable);

        // Create sink table with key
        String createSinkTable = createKafkaSinkTable(properties);
        System.out.println("\nCreating sink table:");
        System.out.println(createSinkTable);
        tableEnv.executeSql(createSinkTable);

        // Perform continuous aggregation
        String aggregateQuery = """
            INSERT INTO kafka_sink_aggregate
            SELECT 
                `key`,
                `key` as `id`,
                SUM(`number`) as `sum`,
                COUNT(*) as `count`,
                MAX(`timestamp`) as `last_update`
            FROM kafka_source_aggregate
            GROUP BY `key`
            """;
        
        System.out.println("\nExecuting aggregation query:");
        System.out.println(aggregateQuery);
        
        insertResult = tableEnv.executeSql(aggregateQuery);

        System.out.println("\nJob is running. Press Ctrl+C to stop...");
        
        // Keep the application running
        while (isRunning) {
            try {
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                break;
            }
        }

        System.out.println("Application shutdown complete.");
    }

    /**
     * Load properties from a file
     */
    private static Properties loadProperties(String configFile) throws IOException {
        Properties properties = new Properties();
        try (FileInputStream fis = new FileInputStream(configFile)) {
            properties.load(fis);
        }
        return properties;
    }

    /**
     * Create Kafka source table DDL with string key and Avro value format
     */
    private static String createKafkaSourceTable(Properties props) {
        String bootstrapServers = props.getProperty("kafka.bootstrap.servers");
        String apiKey = props.getProperty("kafka.api.key");
        String apiSecret = props.getProperty("kafka.api.secret");
        String groupId = props.getProperty("kafka.group.id", "flink-aggregate");
        String sourceTopic = props.getProperty("app.aggregate.source.topic");
        String schemaRegistryUrl = props.getProperty("schema.registry.url");
        String srApiKey = props.getProperty("schema.registry.api.key");
        String srApiSecret = props.getProperty("schema.registry.api.secret");

        return String.format("""
            CREATE TABLE kafka_source_aggregate (
                `key` STRING,
                `number` DOUBLE,
                `timestamp` BIGINT,
                `event_time` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
                WATERMARK FOR `event_time` AS `event_time` - INTERVAL '5' SECOND
            ) WITH (
                'connector' = 'kafka',
                'topic' = '%s',
                'properties.bootstrap.servers' = '%s',
                'properties.security.protocol' = 'SASL_SSL',
                'properties.sasl.mechanism' = 'PLAIN',
                'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="%s" password="%s";',
                'properties.group.id' = '%s',
                'scan.startup.mode' = 'earliest-offset',
                'key.format' = 'raw',
                'key.fields' = 'key',
                'value.format' = 'avro-confluent',
                'value.avro-confluent.url' = '%s',
                'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
                'value.avro-confluent.basic-auth.user-info' = '%s:%s',
                'value.fields-include' = 'EXCEPT_KEY'
            )
            """,
            sourceTopic,
            bootstrapServers,
            apiKey,
            apiSecret,
            groupId,
            schemaRegistryUrl,
            srApiKey,
            srApiSecret
        );
    }

    /**
     * Create Kafka sink table DDL with string key and Avro value format
     */
    private static String createKafkaSinkTable(Properties props) {
        String bootstrapServers = props.getProperty("kafka.bootstrap.servers");
        String apiKey = props.getProperty("kafka.api.key");
        String apiSecret = props.getProperty("kafka.api.secret");
        String sinkTopic = props.getProperty("app.aggregate.sink.topic");
        String schemaRegistryUrl = props.getProperty("schema.registry.url");
        String srApiKey = props.getProperty("schema.registry.api.key");
        String srApiSecret = props.getProperty("schema.registry.api.secret");

        return String.format("""
            CREATE TABLE kafka_sink_aggregate (
                `key` STRING,
                `id` STRING,
                `sum` DOUBLE,
                `count` BIGINT,
                `last_update` BIGINT,
                PRIMARY KEY (`key`) NOT ENFORCED
            ) WITH (
                'connector' = 'upsert-kafka',
                'topic' = '%s',
                'properties.bootstrap.servers' = '%s',
                'properties.security.protocol' = 'SASL_SSL',
                'properties.sasl.mechanism' = 'PLAIN',
                'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="%s" password="%s";',
                'key.format' = 'raw',
                'value.format' = 'avro-confluent',
                'value.avro-confluent.url' = '%s',
                'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
                'value.avro-confluent.basic-auth.user-info' = '%s:%s'
            )
            """,
            sinkTopic,
            bootstrapServers,
            apiKey,
            apiSecret,
            schemaRegistryUrl,
            srApiKey,
            srApiSecret
        );
    }
}
