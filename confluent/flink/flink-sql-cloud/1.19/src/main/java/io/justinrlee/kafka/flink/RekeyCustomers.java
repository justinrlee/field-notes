package io.justinrlee.kafka.flink;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.table.api.TableResult;
import io.justinrlee.kafka.flink.config.ConfigurationManager;
import io.justinrlee.kafka.flink.config.ConnectorConfigGenerator;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
/**
 * Hello world!
 */
public class RekeyCustomers {
    private static volatile boolean isRunning = true;
    private static TableResult customersInsertResult;

    public static void main(String[] args) throws Exception {
        // Create a latch for coordinating shutdown
        CountDownLatch shutdownLatch = new CountDownLatch(1);

        // Add shutdown hook
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("Shutdown hook triggered. Cancelling jobs...");
            isRunning = false;

            if (customersInsertResult != null) {
                try {
                    customersInsertResult.getJobClient().ifPresent(client -> {
                        try {
                            client.cancel().get();
                        } catch (Exception e) {
                            System.err.println("Error cancelling customers job: " + e.getMessage());
                        }
                    });
                } catch (Exception e) {
                    System.err.println("Error during customers job cancellation: " + e.getMessage());
                }
            }

            shutdownLatch.countDown();
            System.out.println("Jobs cancelled.");
        }));

        // Load configuration
        ConfigurationManager config = new ConfigurationManager(args);

        Properties properties = config.getProperties();
        
        // Create a TableEnvironment for streaming processing
        EnvironmentSettings settings = EnvironmentSettings.newInstance()
            .inStreamingMode()
            .build();
        
        TableEnvironment tableEnv = TableEnvironment.create(settings);

        // Example of accessing properties
        String appName = properties.getProperty("app.name", "rekey-shoe-customers");
        System.out.println("Running application: " + appName);

        ConnectorConfigGenerator configGenerator = new ConnectorConfigGenerator(properties);

        String createShoeCustomersTable = String.format("""
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
        ) %s
        """,
            configGenerator.generateKafkaAvroValueConfig(
                "flink-shoe_customers"
            )
        );
        
        String createShoeCustomersKeyedTable = String.format("""
        CREATE TABLE `shoe_customers_keyed` (
            `customer_id` STRING NOT NULL,
            `first_name` STRING,
            `last_name` STRING,
            `email` STRING,
            `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
            WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
        ) %s
        """,
            configGenerator.generateKafkaAvroKeyAndValueConfig(
                "cp-shoe_customers_keyed",
                "customer_id"
            )
        );
        
        String populateShoeCustomersKeyedTable = String.format("""
        INSERT INTO `shoe_customers_keyed`
        SELECT `id`, `first_name`, `last_name`, `email`, `$rowtime`
        FROM `shoe_customers`;
        """);

        System.out.println("Executing CREATE TABLE statements:\n");
        System.out.println(createShoeCustomersTable);
        System.out.println(createShoeCustomersKeyedTable);

        // Execute DDL statements (these don't return results)
        tableEnv.executeSql(createShoeCustomersTable);
        tableEnv.executeSql(createShoeCustomersKeyedTable);

        // Execute the continuous INSERT statements
        System.out.println("Starting continuous INSERT statements:\n");
        System.out.println(populateShoeCustomersKeyedTable);

        customersInsertResult = tableEnv.executeSql(populateShoeCustomersKeyedTable);

        // Wait for shutdown signal
        System.out.println("Jobs are running. Press ctrl-c to stop...");
        try {
            shutdownLatch.await();
        } catch (InterruptedException e) {
            System.out.println("Main thread interrupted");
        }

        System.out.println("Application shutdown complete.");
    }
}
