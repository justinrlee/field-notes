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
        String createSourceTable = """
        CREATE TABLE shoe_customers (
            `kafka_key` VARCHAR(2147483647),
            `order_id` BIGINT,
            `product_id` VARCHAR(2147483647),
            `customer_id` VARCHAR(2147483647),
            `ts` TIMESTAMP(3) METADATA FROM 'timestamp'
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'flink-shoe_orders',
            'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
            'properties.security.protocol' = 'SASL_SSL',
            'properties.sasl.mechanism' = 'PLAIN',
            'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="xxx" password="yyy";',
            'properties.auto.offset.reset' = 'latest',

            'properties.group.id' = 'flink-shoe-customers-2',

            'key.format' = 'raw',
            'key.fields' = 'kafka_key',

            'value.avro-confluent.url' = 'https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud',
            'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
            'value.avro-confluent.basic-auth.user-info' = 'aaa:bbb',
            'value.format' = 'avro-confluent'
        );
        """;

        // // 2. Create a view for customer statistics
        // String createCustomerStatsView = """
        // CREATE VIEW customer_stats AS
        // SELECT 
        //     customer_id,
        //     COUNT(*) as order_count,
        //     COUNT(DISTINCT product_id) as unique_products
        // FROM shoe_customers
        // GROUP BY customer_id
        // """;

        // // 3. Create a table to store results (example with print connector)
        // String createResultsTable = """
        // CREATE TABLE high_value_customers (
        //     customer_id VARCHAR(2147483647),
        //     order_count BIGINT,
        //     unique_products BIGINT
        // ) WITH (
        //     'connector' = 'print'
        // )
        // """;

        // // 4. Insert query to populate results
        // String insertQuery = """
        // INSERT INTO high_value_customers
        // SELECT * FROM customer_stats 
        // WHERE order_count >= 2
        // """;

        // Execute DDL statements (these don't return results)
        tableEnv.executeSql(createSourceTable);
        // tableEnv.executeSql(createCustomerStatsView);
        // tableEnv.executeSql(createResultsTable);

        // Execute INSERT query - this will start the actual processing
        // TableResult insertResult = tableEnv.executeSql(insertQuery);

        // If you want to see some immediate results, you can run a SELECT query
        // Note: In streaming mode, this will show continuous results
        System.out.println("Sample of current results:");
        TableResult sampleResult = tableEnv.executeSql("SELECT * FROM shoe_customers LIMIT 10");
        sampleResult.print();

        // The insert operation runs continuously in streaming mode
        // Wait for the insert operation to complete (or ctrl-c to stop)
        // insertResult.await();
    }
}
