package io.justinrlee.kafka.flink;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.Schema;
import org.apache.flink.table.api.Table;
import org.apache.flink.table.api.TableDescriptor;
import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.table.api.TableResult;
import org.apache.flink.table.api.DataTypes;

import java.io.FileInputStream;
import java.io.IOException;
import java.util.Properties;

import static org.apache.flink.table.api.Expressions.$;

/**
 * Flink Table API job for continuous aggregation (using programmatic Table API instead of SQL).
 * 
 * This job demonstrates:
 * - Using Table API .groupBy() and aggregate functions instead of SQL GROUP BY
 * - Continuous stateful aggregation by key using method chaining
 * - Event time processing with watermarks
 * - Writing to upsert-kafka for maintaining latest aggregates
 * 
 * Compared to HelloWorldAggregate (SQL-based), this uses:
 * - Table API: table.groupBy($("key")).select(...) instead of SQL: GROUP BY key
 * - Aggregate expressions: $("number").sum(), $("number").count()
 * - Type-safe column references
 * 
 * Input Schema:
 * - Key: String ID (used for Kafka partitioning and aggregation)
 * - Value: Avro with fields: number (DOUBLE), timestamp (BIGINT)
 * 
 * Output Schema:
 * - Key: String ID
 * - Value: Avro with fields: id, sum, count, last_update
 */
public class HelloWorldTableAggregate {
    private static volatile boolean isRunning = true;
    private static TableResult insertResult;

    public static void main(String[] args) throws Exception {
        // Parse command line arguments
        if (args.length < 2) {
            System.err.println("Usage: HelloWorldTableAggregate --config-file <path-to-properties>");
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

        System.out.println("Starting Flink Table API Aggregate Job");
        System.out.println("Source topic: " + properties.getProperty("app.aggregate.source.topic"));
        System.out.println("Sink topic: " + properties.getProperty("app.aggregate.sink.topic"));

        // Create source table using TableDescriptor (fully programmatic)
        System.out.println("\nCreating source table using TableDescriptor API");
        TableDescriptor sourceDescriptor = createKafkaSourceDescriptor(properties);
        tableEnv.createTemporaryTable("kafka_source_aggregate", sourceDescriptor);

        // Create sink table using TableDescriptor (upsert-kafka)
        System.out.println("Creating sink table using TableDescriptor API (upsert-kafka)");
        TableDescriptor sinkDescriptor = createKafkaSinkDescriptor(properties);
        tableEnv.createTemporaryTable("kafka_sink_aggregate", sinkDescriptor);

        // Use Table API for aggregation
        System.out.println("\nUsing Table API for aggregation:");
        
        // Get source table
        Table sourceTable = tableEnv.from("kafka_source_aggregate");
        
        // Perform aggregation using Table API
        // Equivalent to: SELECT key, key as id, SUM(number) as sum, COUNT(*) as count, MAX(timestamp) as last_update FROM ... GROUP BY key
        Table aggregatedTable = sourceTable
            .groupBy($("key"))
            .select(
                $("key"),
                $("key").as("id"),
                $("number").sum().as("sum"),
                $("key").count().as("count"),
                $("timestamp").max().as("last_update")
            );
        
        System.out.println("Table API query:");
        System.out.println("  sourceTable");
        System.out.println("    .groupBy($('key'))");
        System.out.println("    .select($('key'), $('key').as('id'), $('number').sum().as('sum'),");
        System.out.println("            $('key').count().as('count'), $('timestamp').max().as('last_update'))");
        
        // Execute insert using Table API
        insertResult = aggregatedTable.executeInsert("kafka_sink_aggregate");

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
     * Create Kafka source table using TableDescriptor API with string key and Avro value
     */
    private static TableDescriptor createKafkaSourceDescriptor(Properties props) {
        String bootstrapServers = props.getProperty("kafka.bootstrap.servers");
        String apiKey = props.getProperty("kafka.api.key");
        String apiSecret = props.getProperty("kafka.api.secret");
        String groupId = props.getProperty("kafka.group.id", "flink-table-api-aggregate");
        String sourceTopic = props.getProperty("app.aggregate.source.topic");
        String schemaRegistryUrl = props.getProperty("schema.registry.url");
        String srApiKey = props.getProperty("schema.registry.api.key");
        String srApiSecret = props.getProperty("schema.registry.api.secret");
        
        String jaasConfig = String.format(
            "org.apache.kafka.common.security.plain.PlainLoginModule required username=\"%s\" password=\"%s\";",
            apiKey, apiSecret
        );

        return TableDescriptor.forConnector("kafka")
            .schema(Schema.newBuilder()
                .column("key", DataTypes.STRING())
                .column("number", DataTypes.DOUBLE())
                .column("timestamp", DataTypes.BIGINT())
                .columnByMetadata("event_time", DataTypes.TIMESTAMP_LTZ(3), "timestamp", false)
                .watermark("event_time", "event_time - INTERVAL '5' SECOND")
                .build())
            .option("topic", sourceTopic)
            .option("properties.bootstrap.servers", bootstrapServers)
            .option("properties.security.protocol", "SASL_SSL")
            .option("properties.sasl.mechanism", "PLAIN")
            .option("properties.sasl.jaas.config", jaasConfig)
            .option("properties.group.id", groupId)
            .option("scan.startup.mode", "earliest-offset")
            .option("key.format", "raw")
            .option("key.fields", "key")
            .option("value.format", "avro-confluent")
            .option("value.avro-confluent.url", schemaRegistryUrl)
            .option("value.avro-confluent.basic-auth.credentials-source", "USER_INFO")
            .option("value.avro-confluent.basic-auth.user-info", srApiKey + ":" + srApiSecret)
            .option("value.fields-include", "EXCEPT_KEY")
            .build();
    }

    /**
     * Create Kafka sink table using TableDescriptor API (upsert-kafka)
     */
    private static TableDescriptor createKafkaSinkDescriptor(Properties props) {
        String bootstrapServers = props.getProperty("kafka.bootstrap.servers");
        String apiKey = props.getProperty("kafka.api.key");
        String apiSecret = props.getProperty("kafka.api.secret");
        String sinkTopic = props.getProperty("app.aggregate.sink.topic");
        String schemaRegistryUrl = props.getProperty("schema.registry.url");
        String srApiKey = props.getProperty("schema.registry.api.key");
        String srApiSecret = props.getProperty("schema.registry.api.secret");
        
        String jaasConfig = String.format(
            "org.apache.kafka.common.security.plain.PlainLoginModule required username=\"%s\" password=\"%s\";",
            apiKey, apiSecret
        );

        return TableDescriptor.forConnector("upsert-kafka")
            .schema(Schema.newBuilder()
                .column("key", DataTypes.STRING().notNull())
                .column("id", DataTypes.STRING())
                .column("sum", DataTypes.DOUBLE())
                .column("count", DataTypes.BIGINT())
                .column("last_update", DataTypes.BIGINT())
                .primaryKey("key")
                .build())
            .option("topic", sinkTopic)
            .option("properties.bootstrap.servers", bootstrapServers)
            .option("properties.security.protocol", "SASL_SSL")
            .option("properties.sasl.mechanism", "PLAIN")
            .option("properties.sasl.jaas.config", jaasConfig)
            .option("key.format", "raw")
            .option("value.format", "avro-confluent")
            .option("value.avro-confluent.url", schemaRegistryUrl)
            .option("value.avro-confluent.basic-auth.credentials-source", "USER_INFO")
            .option("value.avro-confluent.basic-auth.user-info", srApiKey + ":" + srApiSecret)
            .build();
    }
}
