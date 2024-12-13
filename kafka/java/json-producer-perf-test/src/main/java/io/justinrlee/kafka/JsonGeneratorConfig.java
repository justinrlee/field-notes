package io.justinrlee.kafka;

public abstract class JsonGeneratorConfig {
    public String[] types;
    public String[] nestedPayloadZeros;
    public String[] nestedPayloadNulls;
    public String[] nestedPayloadInts;
    public String[] nestedPayloadStrings;
    public String[] payloadZeros;
    public String[] payloadNulls;
    public String[] payloadStrings;
    public String[] payloadInts;
    public String[] messageZeros;
    public String[] messageNulls;
    public String[] messageStrings;
    public String[] messageInts;

    public String payloadType;
    public String payloadFieldName;
}