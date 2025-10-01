package io.justinrlee.kafka.flink.config;

import java.util.Properties;
import java.util.Map;
import java.lang.StringBuilder;


// Generates Flink Connector configuration strings from a Properties object
public class ConnectorConfigGenerator {
    private final Properties properties;

    public ConnectorConfigGenerator(Properties properties) {
        this.properties = properties;
    }

    // Generates a Kafka connector config for a table with:
    // raw key
    // avro-confluent value
    // (excludes key from value)
    public String generateKafkaAvroValueConfig(String topic) {
        return generate(
            "kafka",
            topic,
            "raw",
            "key",
            "avro-confluent",
            "EXCEPT_KEY",
            "group-offsets"
        );
    }

    // Generates a Kafka connector config for a table with:
    // avro-confluent key
    // avro-confluent value
    // (excludes key from value)
    public String generateKafkaAvroKeyAndValueConfig(
        String topic,
        String key
    ) {
        return generate(
            "kafka",
            topic,
            "avro-confluent",
            key,
            "avro-confluent",
            "EXCEPT_KEY",
            "group-offsets"
        );
    }

    public String generateKafkaUpsertConfig(String topic) {
        return generate(
            "upsert-kafka",
            topic,
            "avro-confluent",   // key format
            null,               // key fields - don't want to put `key.fields` when using upsert-kafka to read a keyed table
            "avro-confluent",   // value format
            "EXCEPT_KEY",       // value fields include
            null                // scan startup mode
        );
    }

    // Defaults to kafka, with raw key and avro-confluent value format
    public String generate(
        String connectorType,
        String topic,
        String keyFormat,
        String keyFields,
        String valueFormat,
        String valueFieldsInclude,
        String scanStartupMode
    ) {
        StringBuilder sb = new StringBuilder("WITH (");
        
        // Boilerplate
        sb.append(String.format("'connector' = '%s',", connectorType));
        sb.append(String.format("'topic' = '%s',", topic));
        if (scanStartupMode != null) {
            sb.append(String.format("'scan.startup.mode' = '%s',", scanStartupMode));
        }

        // Application ID
        sb.append(String.format("'properties.group.id' = '%s',", properties.getProperty("kafka.group.id")));
        
        // Kafka connection details
        sb.append(String.format("'properties.auto.offset.reset' = 'latest',"));
        sb.append(String.format("'properties.bootstrap.servers' = '%s',", properties.getProperty("kafka.bootstrap.servers")));
        sb.append(String.format("'properties.security.protocol' = 'SASL_SSL',"));
        sb.append(String.format("'properties.sasl.mechanism' = 'PLAIN',"));
        sb.append(String.format("'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username=\"%s\" password=\"%s\";',", properties.getProperty("kafka.api.key"), properties.getProperty("kafka.api.secret")));
        
        // Key format
        sb.append(String.format("'key.format' = '%s',", keyFormat));
        if (keyFormat == "avro-confluent") {
            sb.append(String.format("'key.avro-confluent.url' = '%s',", properties.getProperty("schema.registry.url")));
            sb.append(String.format("'key.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',"));
            sb.append(String.format("'key.avro-confluent.basic-auth.user-info' = '%s:%s',", properties.getProperty("schema.registry.api.key"), properties.getProperty("schema.registry.api.secret")));
        }

        // Value format
        sb.append(String.format("'value.format' = '%s',", valueFormat));
        if (valueFormat == "avro-confluent") {
            sb.append(String.format("'value.avro-confluent.url' = '%s',", properties.getProperty("schema.registry.url")));
            sb.append(String.format("'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',"));
            sb.append(String.format("'value.avro-confluent.basic-auth.user-info' = '%s:%s',", properties.getProperty("schema.registry.api.key"), properties.getProperty("schema.registry.api.secret")));
        }

        // Key fields
        if (keyFields != null) {
            sb.append(String.format("'key.fields' = '%s',", keyFields));
        }

        // Value fields include
        if (valueFieldsInclude != null) {
            sb.append(String.format("'value.fields-include' = '%s',", valueFieldsInclude));
        }

        // Remove trailing comma
        sb.setLength(sb.length() - 1);

        sb.append(");");

        return sb.toString();
    }
}