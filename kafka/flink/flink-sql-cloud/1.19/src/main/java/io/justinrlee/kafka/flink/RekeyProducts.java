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
public class RekeyProducts {
    private static volatile boolean isRunning = true;
    private static TableResult productsInsertResult;

    public static void main(String[] args) throws Exception {
        // Create a latch for coordinating shutdown
        CountDownLatch shutdownLatch = new CountDownLatch(1);

        // Add shutdown hook
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("Shutdown hook triggered. Cancelling jobs...");
            isRunning = false;

            if (productsInsertResult != null) {
                try {
                    productsInsertResult.getJobClient().ifPresent(client -> {
                        try {
                            client.cancel().get();
                        } catch (Exception e) {
                            System.err.println("Error cancelling products job: " + e.getMessage());
                        }
                    });
                } catch (Exception e) {
                    System.err.println("Error during products job cancellation: " + e.getMessage());
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
        String appName = properties.getProperty("app.name", "rekey-shoe-products");
        System.out.println("Running application: " + appName);

        ConnectorConfigGenerator configGenerator = new ConnectorConfigGenerator(properties);

        String createShoeProductsTable = String.format("""
        CREATE TABLE `shoe_products` (
            `key` VARCHAR(2147483647), -- or VARBINARY
            `id` VARCHAR(2147483647),
            `brand` VARCHAR(2147483647),
            `name` VARCHAR(2147483647),
            `sale_price` INT,
            `rating` DOUBLE,
            `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
            WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
        ) %s
        """,
            configGenerator.generateKafkaAvroValueConfig(
                "flink-shoe_products"
            )
        );

        String createShoeProductsKeyedTable = String.format("""
        CREATE TABLE `shoe_products_keyed` (
            `product_id` STRING NOT NULL,
            `brand` STRING,
            `model` STRING,
            `sale_price` INT,
            `rating` DOUBLE,
            `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
            WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
        ) %s
        """,
            configGenerator.generateKafkaAvroKeyAndValueConfig(
                "cp-shoe_products_keyed",
                "product_id"
            )
        );

        String populateShoeProductsKeyedTable = String.format("""
        INSERT INTO `shoe_products_keyed`
        SELECT `id`, `brand`, `name`, `sale_price`, `rating`, `$rowtime`
        FROM `shoe_products`;
        """);

        System.out.println("Executing CREATE TABLE statements:\n");
        System.out.println(createShoeProductsTable);
        System.out.println(createShoeProductsKeyedTable);

        // Execute DDL statements (these don't return results)
        tableEnv.executeSql(createShoeProductsTable);
        tableEnv.executeSql(createShoeProductsKeyedTable);

        // Execute the continuous INSERT statements
        System.out.println("Starting continuous INSERT statements:\n");
        System.out.println(populateShoeProductsKeyedTable);

        productsInsertResult = tableEnv.executeSql(populateShoeProductsKeyedTable);

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
