package io.justinrlee.streams.protoprocessor.serialize;

import io.justinrlee.mqtt.protobuf.Person;
import org.apache.kafka.common.serialization.Serializer;
import org.apache.kafka.common.errors.SerializationException;

import java.io.IOException;
import java.lang.RuntimeException;

import java.util.Map;

public class PersonSerializer implements Serializer<Person>
{
    // private boolean isKey;

    @Override
    public void configure(Map<String, ?> configs, boolean isKey) {}

    @Override
    public byte[] serialize(String topic, Person person)
    {
        if (person == null) 
        {
            return null;
        }

        try {
            return person.toByteArray();
        } catch (RuntimeException e) {
            throw new SerializationException("Error serializing value", e);
        }
    }

    @Override
    public void close() {}
}