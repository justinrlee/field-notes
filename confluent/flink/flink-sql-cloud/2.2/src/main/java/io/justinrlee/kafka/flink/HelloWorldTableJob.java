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
 * Flink Table API job (using programmatic Table API instead of SQL queries).
 * 
 * This job demonstrates:
 * - Using Table API methods instead of SQL strings for data processing
 * - Reading from Kafka using table descriptors
 * - Transforming data using .select() method
 * - Writing to Kafka using .executeInsert()
 * 
 * Compared to HelloWorldJob (SQL-based), this uses:
 * - Table API: table.select(...) instead of SQL: SELECT ... FROM ...
 * - Method chaining for transformations
 * - Type-safe column references using $("column_name")
 */
public class HelloWorldTableJob {
    private static volatile boolean isRunning = true;
    private static TableResult insertResult;

    public static void main(String[] args) throws Exception {
        // Parse command line arguments
        if (args.length < 2) {
            System.err.println("Usage: HelloWorldTableJob --config-file <path-to-properties>");
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

        System.out.println("Starting Flink Table API Job");
        System.out.println("Source topic: " + properties.getProperty("app.source.topic"));
        System.out.println("Sink topic: " + properties.getProperty("app.sink.topic"));

        // Create source table using TableDescriptor (fully programmatic)
        System.out.println("\nCreating source table using TableDescriptor API");
        TableDescriptor sourceDescriptor = createKafkaSourceDescriptor(properties);
        tableEnv.createTemporaryTable("kafka_source", sourceDescriptor);

        // Create sink table using TableDescriptor
        System.out.println("Creating sink table using TableDescriptor API");
        TableDescriptor sinkDescriptor = createKafkaSinkDescriptor(properties);
        tableEnv.createTemporaryTable("kafka_sink", sinkDescriptor);

        // Use Table API to read, transform, and write data
        System.out.println("\nUsing Table API for data processing:");
        
        // Get source table
        Table sourceTable = tableEnv.from("kafka_source");
        
        // Select columns using Table API (equivalent to SELECT id, message, timestamp FROM kafka_source)
        Table resultTable = sourceTable.select(
            $("id"),
            $("message"),
            $("timestamp")
        );
        
        System.out.println("Table API query: sourceTable.select($('id'), $('message'), $('timestamp'))");
        
        // Execute insert using Table API
        insertResult = resultTable.executeInsert("kafka_sink");

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
     * Create Kafka source table using TableDescriptor API
     */
    private static TableDescriptor createKafkaSourceDescriptor(Properties props) {
        String bootstrapServers = props.getProperty("kafka.bootstrap.servers");
        String apiKey = props.getProperty("kafka.api.key");
        String apiSecret = props.getProperty("kafka.api.secret");
        String groupId = props.getProperty("kafka.group.id", "flink-table-api");
        String sourceTopic = props.getProperty("app.source.topic");
        String schemaRegistryUrl = props.getProperty("schema.registry.url");
        String srApiKey = props.getProperty("schema.registry.api.key");
        String srApiSecret = props.getProperty("schema.registry.api.secret");
        
        String jaasConfig = String.format(
            "org.apache.kafka.common.security.plain.PlainLoginModule required username=\"%s\" password=\"%s\";",
            apiKey, apiSecret
        );

        return TableDescriptor.forConnector("kafka")
            .schema(Schema.newBuilder()
                .column("id", DataTypes.STRING())
                .column("message", DataTypes.STRING())
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
            .option("value.format", "avro-confluent")
            .option("value.avro-confluent.url", schemaRegistryUrl)
            .option("value.avro-confluent.basic-auth.credentials-source", "USER_INFO")
            .option("value.avro-confluent.basic-auth.user-info", srApiKey + ":" + srApiSecret)
            .build();
    }

    /**
     * Create Kafka sink table using TableDescriptor API
     */
    private static TableDescriptor createKafkaSinkDescriptor(Properties props) {
        String bootstrapServers = props.getProperty("kafka.bootstrap.servers");
        String apiKey = props.getProperty("kafka.api.key");
        String apiSecret = props.getProperty("kafka.api.secret");
        String sinkTopic = props.getProperty("app.sink.topic");
        String schemaRegistryUrl = props.getProperty("schema.registry.url");
        String srApiKey = props.getProperty("schema.registry.api.key");
        String srApiSecret = props.getProperty("schema.registry.api.secret");
        
        String jaasConfig = String.format(
            "org.apache.kafka.common.security.plain.PlainLoginModule required username=\"%s\" password=\"%s\";",
            apiKey, apiSecret
        );

        return TableDescriptor.forConnector("kafka")
            .schema(Schema.newBuilder()
                .column("id", DataTypes.STRING())
                .column("message", DataTypes.STRING())
                .column("timestamp", DataTypes.BIGINT())
                .build())
            .option("topic", sinkTopic)
            .option("properties.bootstrap.servers", bootstrapServers)
            .option("properties.security.protocol", "SASL_SSL")
            .option("properties.sasl.mechanism", "PLAIN")
            .option("properties.sasl.jaas.config", jaasConfig)
            .option("value.format", "avro-confluent")
            .option("value.avro-confluent.url", schemaRegistryUrl)
            .option("value.avro-confluent.basic-auth.credentials-source", "USER_INFO")
            .option("value.avro-confluent.basic-auth.user-info", srApiKey + ":" + srApiSecret)
            .build();
    }
}
