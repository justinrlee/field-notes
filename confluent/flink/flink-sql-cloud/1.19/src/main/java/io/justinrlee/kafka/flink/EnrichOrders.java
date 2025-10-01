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
public class EnrichOrders {
    private static volatile boolean isRunning = true;
    private static TableResult ordersEnrichedInsertResult;

    public static void main(String[] args) throws Exception {
        // Create a latch for coordinating shutdown
        CountDownLatch shutdownLatch = new CountDownLatch(1);

        // Add shutdown hook
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("Shutdown hook triggered. Cancelling jobs...");
            isRunning = false;

            if (ordersEnrichedInsertResult != null) {
                try {
                    ordersEnrichedInsertResult.getJobClient().ifPresent(client -> {
                        try {
                            client.cancel().get();
                        } catch (Exception e) {
                            System.err.println("Error cancelling orders enriched job: " + e.getMessage());
                        }
                    });
                } catch (Exception e) {
                    System.err.println("Error during orders enriched job cancellation: " + e.getMessage());
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
        String appName = properties.getProperty("app.name", "enrich-shoe-orders");
        System.out.println("Running application: " + appName);

        ConnectorConfigGenerator configGenerator = new ConnectorConfigGenerator(properties);

        String createShoeOrdersTable = String.format("""
        CREATE TABLE `shoe_orders` (
            `key` VARCHAR(2147483647), -- or VARBINARY
            `order_id` BIGINT,
            `product_id` VARCHAR(2147483647),
            `customer_id` VARCHAR(2147483647),
            `ts` TIMESTAMP(3),
            `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
            WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
        ) %s
        """,
            configGenerator.generateKafkaAvroValueConfig(
                "flink-shoe_orders"
            )
        );
        
        String createShoeProductsKeyedSourceTable = String.format("""
        CREATE TABLE `shoe_products_keyed-source` (
            `product_id` STRING NOT NULL,
            `brand` STRING,
            `model` STRING,
            `sale_price` INT,
            `rating` DOUBLE,
            `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
            PRIMARY KEY (`product_id`) NOT ENFORCED,
            WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
        ) %s
        """,
            configGenerator.generateKafkaUpsertConfig(
                "cp-shoe_products_keyed"
            )
        );

        String createShoeCustomersKeyedSourceTable = String.format("""
        CREATE TABLE `shoe_customers_keyed-source` (
            `customer_id` VARCHAR(2147483647) NOT NULL,
            `first_name` VARCHAR(2147483647),
            `last_name` VARCHAR(2147483647),
            `email` VARCHAR(2147483647),
            `$rowtime` TIMESTAMP_LTZ(3) METADATA FROM 'timestamp',
            PRIMARY KEY (`customer_id`) NOT ENFORCED,
            WATERMARK FOR `$rowtime` AS `$rowtime` - INTERVAL '5' SECOND
        ) %s
        """,
            configGenerator.generateKafkaUpsertConfig(
                "cp-shoe_customers_keyed"
            )
        );

        String createShoeOrdersEnrichedTable = String.format("""
        CREATE TABLE `shoe_orders_enriched` (
            `order_id` BIGINT,
            `first_name` VARCHAR(2147483647),
            `last_name` VARCHAR(2147483647),
            `email` VARCHAR(2147483647),
            `sale_price` INT,
            `brand` VARCHAR(2147483647),
            `model` VARCHAR(2147483647),
            `ordertime` TIMESTAMP(3)
        ) %s
        """,
            configGenerator.generateKafkaAvroKeyAndValueConfig(
                "cp-shoe_orders_enriched",
                "order_id"
            )
        );

        String populateShoeOrdersEnrichedTable = String.format("""
        INSERT INTO 
            `shoe_orders_enriched`
        SELECT 
            `order_id`,
            `first_name`,
            `last_name`,
            `email`,
            `sale_price`,
            `brand`,
            `model`,
            `shoe_orders`.`$rowtime`
        FROM `shoe_orders`
        INNER JOIN 
            `shoe_customers_keyed-source` FOR SYSTEM_TIME AS OF `shoe_orders`.`$rowtime`
        ON 
            `shoe_orders`.`customer_id` = `shoe_customers_keyed-source`.`customer_id`
        INNER JOIN
            `shoe_products_keyed-source` FOR SYSTEM_TIME AS OF `shoe_orders`.`$rowtime`
        ON
            `shoe_orders`.`product_id` = `shoe_products_keyed-source`.`product_id`;
        """);

        System.out.println("Executing CREATE TABLE statements:\n");
        System.out.println(createShoeOrdersTable);
        System.out.println(createShoeProductsKeyedSourceTable);
        System.out.println(createShoeCustomersKeyedSourceTable);
        System.out.println(createShoeOrdersEnrichedTable);

        // Execute DDL statements (these don't return results)
        tableEnv.executeSql(createShoeOrdersTable);
        tableEnv.executeSql(createShoeProductsKeyedSourceTable);
        tableEnv.executeSql(createShoeCustomersKeyedSourceTable);
        tableEnv.executeSql(createShoeOrdersEnrichedTable);

        System.out.println("Starting enrichment statement:\n");
        System.out.println(populateShoeOrdersEnrichedTable);

        ordersEnrichedInsertResult = tableEnv.executeSql(populateShoeOrdersEnrichedTable);

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
