package io.justinrlee.kafka.streams;

import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Produced;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.FileInputStream;
import java.io.InputStream;
import java.util.Arrays;
import java.util.Optional;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;

/**
 * Hello world!
 *
 */
public class App 
{

    private static final Logger logger = LoggerFactory.getLogger(App.class);

    static void runKafkaStreams(final KafkaStreams streams) 
    {
        final CountDownLatch latch = new CountDownLatch(1);
        streams.setStateListener((newState, oldState) -> 
        {
            if (oldState == KafkaStreams.State.RUNNING && newState != KafkaStreams.State.RUNNING) 
            {
                latch.countDown();
            }
        });

        streams.start();

        try {
            latch.await();
        } catch (final InterruptedException e) {
            throw new RuntimeException(e);
        }

        logger.info("Streams Closed");
    }

    static Topology buildTopology(String inputTopic, String outputTopic) 
    {
        Serde<String> stringSerde = Serdes.String();
        StreamsBuilder builder = new StreamsBuilder();
        builder
            .stream(inputTopic, Consumed.with(stringSerde, stringSerde))
            .peek((k,v) -> logger.info("Observed event: {}", v))
            .mapValues(s -> s.toUpperCase())
            .peek((k,v) -> logger.info("Transformed event: {}", v))
            .to(outputTopic, Produced.with(stringSerde, stringSerde));

        return builder.build();
    }

    public static void main( String[] args ) {

        if (args.length < 1) {
            throw new IllegalArgumentException("This program takes one argument: the path to a configuration file.");
        }
      
        // System.out.println( "Hello World!" );
        Properties props = new Properties();

        try (InputStream inputStream = new FileInputStream(args[0])) {
            props.load(inputStream);
        } catch (Exception e) {
            logger.error("Something went wrong: ", e);
            System.exit(1);
        }

        KafkaStreams kafkaStreams = new KafkaStreams(
            buildTopology("input", "output"),
            props
        );

        Runtime.getRuntime().addShutdownHook(new Thread(kafkaStreams::close));

        logger.info("Kafka Streams 101 App Started");
        runKafkaStreams(kafkaStreams);
    }
}