package io.justinrlee.kafka;

public class SampleJsonGeneratorConfig extends JsonGeneratorConfig{

    public SampleJsonGeneratorConfig() {
        payloadType = "payload_type";
        payloadFieldName = "payload_field";
        
        types = new String[] {
            "type_anteater",
            "type_bighorn",
            "type_chinchilla",
            "type_chipmunk",
            "type_cow",
            "type_crocodile",
            "type_dromedary",
            "type_duckbill platypus",
            "type_dugong",
            "type_elk",
            "type_fawn",
            "type_hare",
            "type_hare",
            "type_koala",
            "type_lamb",
            "type_lizard",
            "type_mole",
            "type_musk deer",
            "type_muskrat",
            "type_parrot",
            "type_porpoise",
            "type_puppy",
            "type_rabbit",
            "type_skunk",
            "type_steer",
            "type_tapir",
            "type_vicuna",
            "type_whale",
            "type_wolf",
            "type_wolverine"
        };

        nestedPayloadZeros = new String[] {
            "inner_payload_field_zero"
        };

        nestedPayloadNulls = new String[] {
            "inner_payload_field_null_0",
            "inner_payload_field_null_1",
            "inner_payload_field_null_2"
        };

        nestedPayloadInts = new String[] {
            "inner_payload_field_int_0",
            "inner_payload_field_int_1",
            "inner_payload_field_int_2",
            "inner_payload_field_int_3"
        };

        nestedPayloadStrings = new String[] {
            "inner_payload_field_string_0",
            "inner_payload_field_string_1",
            "inner_payload_field_string_2",
            "inner_payload_field_string_3"
        };

        payloadZeros = new String[] {
            "payload_field_zero"
        };

        payloadNulls = new String[] {
            "payload_field_null_0",
            "payload_field_null_1",
            "payload_field_null_2"
        };

        payloadInts = new String[] {
            "payload_field_int_0",
            "payload_field_int_1",
            "payload_field_int_2",
            "payload_field_int_3"
        };

        payloadStrings = new String[] {
            "payload_field_string_0",
            "payload_field_string_1",
            "payload_field_string_2",
            "payload_field_string_3"
        };

        messageZeros = new String[] {
            "message_field_zero"
        };
        messageNulls = new String[] {
            "message_field_null_0",
            "message_field_null_1",
            "message_field_null_2"
        };

        messageInts = new String[] {
            "message_field_int_0",
            "message_field_int_1",
            "message_field_int_2",
            "message_field_int_3"
        };

        messageStrings = new String[] {
            "message_field_string_0",
            "message_field_string_1",
            "message_field_string_2",
            "message_field_string_3"
        };
    }
}