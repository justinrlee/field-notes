package io.justinrlee.kafka.flink;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.table.api.TableResult;
import io.justinrlee.kafka.flink.config.ConfigurationManager;
import java.util.Properties;
/**
 * Hello world!
 */
public class App {
    public static void main(String[] args) throws Exception {
        // Load configuration
        ConfigurationManager config = new ConfigurationManager(args);

        Properties properties = config.getProperties();
        
        // Create a TableEnvironment for streaming processing
        EnvironmentSettings settings = EnvironmentSettings.newInstance()
            .inStreamingMode()
            .build();
        
        TableEnvironment tableEnv = TableEnvironment.create(settings);

        // Example of accessing properties
        String appName = properties.getProperty("app.name", "default-app-name");
        System.out.println("Running application: " + appName);

        // Create source table
        // I don't know of a better way to generate this. The parameters look _close_ to Kafka Java properties, but they're not (especially the schema registry properties).)
        String createSourceTable = String.format("""
        CREATE TABLE shoe_customers (
            `order_id` BIGINT,
            `product_id` VARCHAR(2147483647),
            `customer_id` VARCHAR(2147483647),
            `ts` TIMESTAMP(3) METADATA FROM 'timestamp'
        ) WITH (
            'connector' = 'kafka',
            'topic' = '%s',
            'scan.startup.mode' = 'earliest-offset',
            'properties.bootstrap.servers' = '%s',
            'properties.security.protocol' = 'SASL_SSL',
            'properties.sasl.mechanism' = 'PLAIN',
            'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="%s" password="%s";',
            'properties.group.id' = '%s',
            'value.avro-confluent.url' = '%s',
            'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
            'value.avro-confluent.basic-auth.user-info' = '%s:%s',
            'value.format' = 'avro-confluent'
        );
        """,
            properties.getProperty("kafka.topic"),
            properties.getProperty("kafka.bootstrap.servers"),
            properties.getProperty("kafka.api.key"),
            properties.getProperty("kafka.api.secret"),
            properties.getProperty("kafka.group.id"),
            properties.getProperty("schema.registry.url"),
            properties.getProperty("schema.registry.api.key"),
            properties.getProperty("schema.registry.api.secret")
        );

        String selectQuery = "SELECT * FROM shoe_customers LIMIT 10;";

        System.out.println("Executing CREATE TABLE statement:");
        System.out.println(createSourceTable);

        // Execute DDL statements (these don't return results)
        tableEnv.executeSql(createSourceTable);

        // Execute SELECT query
        TableResult sampleResult = tableEnv.executeSql(selectQuery);
        System.out.println("Sample of current results:");
        sampleResult.print();

        // The insert operation runs continuously in streaming mode
        // Wait for the insert operation to complete (or ctrl-c to stop)
        // insertResult.await();
    }
}
