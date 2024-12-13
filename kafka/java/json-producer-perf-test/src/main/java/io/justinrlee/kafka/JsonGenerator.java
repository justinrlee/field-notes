package io.justinrlee.kafka;

import java.io.*;

import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;
import java.time.ZonedDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

import com.fasterxml.jackson.databind.ObjectMapper;

import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Hello world!
 */
public class JsonGenerator {

    ObjectMapper objectMapper;
    Random r;
    JsonGeneratorConfig jsonConfig;

    static String CHAR_POOL = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    static int CHAR_POOL_LENGTH = CHAR_POOL.length();

    public JsonGenerator() {
        objectMapper = new ObjectMapper();
        jsonConfig = new SampleJsonGeneratorConfig();
        r = ThreadLocalRandom.current();
        // Run once to warm the generator (not sure if this does anything)
    }

    private ObjectNode generateObjectNode(
        String[] strings,
        String[] ints,
        String[] zeros,
        String[] nulls
    ) {
        ObjectNode objectNode = objectMapper.createObjectNode();
        
        for (String s: strings) {
            objectNode.put(s, randomString(16));
        }
        for (String s: ints) {
            objectNode.put(s, r.nextInt(Integer.MAX_VALUE));
        }
        for (String s: zeros) {
            objectNode.put(s, 0);
        }
        for (String s: nulls) {
            objectNode.set(s, null);
        }
        return objectNode;
    }

    public byte[] generate() throws Exception {
        String createdate = ZonedDateTime.now( ZoneOffset.UTC ).format( DateTimeFormatter.ISO_INSTANT );
        String payloadInnerType = jsonConfig.types[r.nextInt(jsonConfig.types.length)];

        // Four tiers of objects:
        // message
        // messageNested -> JSON String of payload
        // payloadOuter
        // payloadpayloadInner

        // Construct from the inside out

        ObjectNode nestedPayload = generateObjectNode(
            jsonConfig.nestedPayloadStrings,
            jsonConfig.nestedPayloadInts,
            jsonConfig.nestedPayloadZeros,
            jsonConfig.nestedPayloadNulls
        );
        
        ObjectNode payloadJSON = generateObjectNode(
            jsonConfig.payloadStrings,
            jsonConfig.payloadInts,
            jsonConfig.payloadZeros,
            jsonConfig.payloadNulls
        );
        payloadJSON.put("createdate", createdate);
        payloadJSON.put("type", payloadInnerType);
        payloadJSON.set(payloadInnerType, nestedPayload);
        
        ObjectNode nestedMessage = objectMapper.createObjectNode();
        nestedMessage.put(jsonConfig.payloadFieldName, objectMapper.writeValueAsString(payloadJSON));

        ObjectNode message = generateObjectNode(
            jsonConfig.messageStrings,
            jsonConfig.messageInts,
            jsonConfig.messageZeros,
            jsonConfig.messageNulls
        );
        message.put("timesync", false);
        message.put("createdate", createdate);
        message.put("type", jsonConfig.payloadType);
        message.set(jsonConfig.payloadType, nestedMessage);

        return objectMapper.writeValueAsBytes(message);
    }

    String randomString(int length) {
        StringBuilder sb = new StringBuilder(length);
        for (int i = 0; i < length; i++) {
            sb.append(CHAR_POOL.charAt(r.nextInt(CHAR_POOL_LENGTH)));
        }

        return sb.toString();
    }

    public static void main(String[] args) throws Exception {
        JsonGenerator jg = new JsonGenerator();
        byte[] randomPayload = jg.generate();
        String x = new String(randomPayload);
        System.out.println(x);

    }
}