package examples;

import org.apache.avro.Schema;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericRecord;

import org.apache.kafka.clients.producer.*;

import org.apache.kafka.common.serialization.StringSerializer;
import io.confluent.kafka.serializers.KafkaAvroSerializer;
import java.util.Properties;

import java.io.*;
import java.nio.file.*;
import java.util.*;

public class AvroProducer {

    public static void main(final String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Please provide the configuration file path as a command line argument");
            System.exit(1);
        }

        // Load producer configuration settings from a local file
        final Properties props = loadConfig(args[0]);
        final String topic = "data";

        props.put(
          ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
          org.apache.kafka.common.serialization.StringSerializer.class
        );

        props.put(
          ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
          io.confluent.kafka.serializers.KafkaAvroSerializer.class
        );

        String userSchema = "{\"type\":\"record\",\"name\":\"EventDataPayload\",\"namespace\":\"justin.avro\",\"fields\":[{\"name\":\"user\",\"type\":[\"null\",{\"type\":\"string\"}],\"default\":null},{\"name\":\"item\",\"type\":[\"null\",{\"type\":\"string\"}],\"default\":null}]}";

        Schema.Parser parser = new Schema.Parser();
        Schema schema = parser.parse(userSchema);
        GenericRecord avroRecord;

        String[] users = {"justin", "eric", "kenny"};
        String[] items = {"toy", "apple", "car", "house", "ball"};
        final Random rnd = new Random();

        try (final Producer<String, Object> producer = new KafkaProducer<>(props)) {

            
            final Long numMessages = 100000000L;
            
            for (Long i = 0L; i < numMessages; i++) {
                String key = UUID.randomUUID().toString();
                avroRecord = new GenericData.Record(schema);
                avroRecord.put("user", users[rnd.nextInt(users.length)]);
                avroRecord.put("item", items[rnd.nextInt(items.length)]);

                producer.send(
                        new ProducerRecord<String, Object>(topic, key, avroRecord),
                        (event, ex) -> {
                            if (ex != null)
                                ex.printStackTrace();
                            else
                                System.out.printf("Produced event to topic %s, key %s\n", topic, key);
                        });
            }
            System.out.printf("%s events were produced to topic %s%n", numMessages, topic);
        }

    }

    // We'll reuse this function to load properties from the Consumer as well
    public static Properties loadConfig(final String configFile) throws IOException {
        if (!Files.exists(Paths.get(configFile))) {
            throw new IOException(configFile + " not found.");
        }
        final Properties cfg = new Properties();
        try (InputStream inputStream = new FileInputStream(configFile)) {
            cfg.load(inputStream);
        }
        return cfg;
    }
}