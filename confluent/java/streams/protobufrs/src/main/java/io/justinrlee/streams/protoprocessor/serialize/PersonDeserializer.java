package io.justinrlee.streams.protoprocessor.serialize;

import io.justinrlee.mqtt.protobuf.Person;
import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.errors.SerializationException;

// import java.io.UnsupportedEncodingException;
import java.io.IOException;
import java.lang.RuntimeException;
import java.util.Map;

public class PersonDeserializer implements Deserializer<Person> 
{

    @Override
    public void configure(Map<String, ?> configs, boolean isKey) {}

    @Override
    public Person deserialize(String topic, byte[] data) {
        try {
            if (data == null)
            {
                // System.out.println("Null received at deserializing");
                return null;
            }
            // System.out.println("Deserializing...");
            return Person.parseFrom(data);
        } catch (Exception e) {
            throw new SerializationException("Error when deserializing byte[] to MessageDto");
        }
    }

    @Override
    public void close() {}
}