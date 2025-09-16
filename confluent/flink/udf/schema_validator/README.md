# Confluent Cloud Flink UDF - Schema Validator

Validates the schema of a string-serialized JSON object, returns (boolean) `TRUE` or `FALSE`.

Two versions:
* [JSONSchema](https://json-schema.org/): io.justinrlee.kafka.flink.udf.AvroSchemaJsonValidator
* [Avro Schema](https://avro.apache.org/): io.justinrlee.kafka.flink.udf.JsonSchemaJsonValidator

Each UDF takes two parameters:
* String `jsonString`: Stringified JSON
* String `avroSchemaB64` or `jsonSchemaB64`: Base64-encoded schema (of the relevant schema type)

_Note: this is designed assuming a large number of schemas need to be validated. If you have a small number of schemas to validate, you could hardcode the schema into the UDF and compile UDF for each schema. See [SchemaValidator](./src/main/java/io/justinrlee/kafka/flink/udf/SchemaValidator.java) for an incomplete example of this._

## JSONSchema Examples

Using this schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "name": {
      "type": "string"
    },
    "id": {
      "type": "integer"
    },
    "phoneNumber": {
      "type": "string"
    }
  },
  "required": [
    "name",
    "id"
  ],
  "additionalProperties": false
}
```

Base64 encoded (with flag `-w0` to encode as a single line)

```
ewogICIkc2NoZW1hIjogImh0dHBzOi8vanNvbi1zY2hlbWEub3JnL2RyYWZ0LzIwMjAtMTIvc2NoZW1hIiwKICAidHlwZSI6ICJvYmplY3QiLAogICJwcm9wZXJ0aWVzIjogewogICAgIm5hbWUiOiB7CiAgICAgICJ0eXBlIjogInN0cmluZyIKICAgIH0sCiAgICAiaWQiOiB7CiAgICAgICJ0eXBlIjogImludGVnZXIiCiAgICB9LAogICAgInBob25lTnVtYmVyIjogewogICAgICAidHlwZSI6ICJzdHJpbmciCiAgICB9CiAgfSwKICAicmVxdWlyZWQiOiBbCiAgICAibmFtZSIsCiAgICAiaWQiCiAgXSwKICAiYWRkaXRpb25hbFByb3BlcnRpZXMiOiBmYWxzZQp9Cg
```

```sql
--- returns TRUE
JsonSchemaJsonValidator('{"id": 123456, "name": "Justin"}', 'ewogICIkc2NoZW1hIjogImh0dHBzOi8vanNvbi1zY2hlbWEub3JnL2RyYWZ0LzIwMjAtMTIvc2NoZW1hIiwKICAidHlwZSI6ICJvYmplY3QiLAogICJwcm9wZXJ0aWVzIjogewogICAgIm5hbWUiOiB7CiAgICAgICJ0eXBlIjogInN0cmluZyIKICAgIH0sCiAgICAiaWQiOiB7CiAgICAgICJ0eXBlIjogImludGVnZXIiCiAgICB9LAogICAgInBob25lTnVtYmVyIjogewogICAgICAidHlwZSI6ICJzdHJpbmciCiAgICB9CiAgfSwKICAicmVxdWlyZWQiOiBbCiAgICAibmFtZSIsCiAgICAiaWQiCiAgXSwKICAiYWRkaXRpb25hbFByb3BlcnRpZXMiOiBmYWxzZQp9Cg')

-- returns FALSE (`id` needs to be an integer, not a string)
JsonSchemaJsonValidator('{"id": "123456", "name": "Justin"}', 'ewogICIkc2NoZW1hIjogImh0dHBzOi8vanNvbi1zY2hlbWEub3JnL2RyYWZ0LzIwMjAtMTIvc2NoZW1hIiwKICAidHlwZSI6ICJvYmplY3QiLAogICJwcm9wZXJ0aWVzIjogewogICAgIm5hbWUiOiB7CiAgICAgICJ0eXBlIjogInN0cmluZyIKICAgIH0sCiAgICAiaWQiOiB7CiAgICAgICJ0eXBlIjogImludGVnZXIiCiAgICB9LAogICAgInBob25lTnVtYmVyIjogewogICAgICAidHlwZSI6ICJzdHJpbmciCiAgICB9CiAgfSwKICAicmVxdWlyZWQiOiBbCiAgICAibmFtZSIsCiAgICAiaWQiCiAgXSwKICAiYWRkaXRpb25hbFByb3BlcnRpZXMiOiBmYWxzZQp9Cg')
```

## Avro Examples


```json
{
  "namespace": "com.demo.avro",
  "type": "record",
  "name": "Customer",
  "fields": [
    {
      "name": "id",
      "type": "int"
    },
    {
      "name": "name",
      "type": "string"
    },
    {
      "name": "phoneNumber",
      "type": [
        "null",
        "string"
      ],
      "default": null
    }
  ]
}
```

Base64 encoded (with flag `-w0` to encode as a single line)

```
ewogICJuYW1lc3BhY2UiOiAiY29tLmRlbW8uYXZybyIsCiAgInR5cGUiOiAicmVjb3JkIiwKICAibmFtZSI6ICJDdXN0b21lciIsCiAgImZpZWxkcyI6IFsKICAgIHsKICAgICAgIm5hbWUiOiAiaWQiLAogICAgICAidHlwZSI6ICJpbnQiCiAgICB9LAogICAgewogICAgICAibmFtZSI6ICJuYW1lIiwKICAgICAgInR5cGUiOiAic3RyaW5nIgogICAgfSwKICAgIHsKICAgICAgIm5hbWUiOiAicGhvbmVOdW1iZXIiLAogICAgICAidHlwZSI6IFsKICAgICAgICAibnVsbCIsCiAgICAgICAgInN0cmluZyIKICAgICAgXSwKICAgICAgImRlZmF1bHQiOiBudWxsCiAgICB9CiAgXQp9Cg
```


```sql
--- returns TRUE
AvroSchemaJsonValidator('{"id": 123456, "name": "Justin", "phoneNumber": {"string": "12345"}}', 'ewogICJuYW1lc3BhY2UiOiAiY29tLmRlbW8uYXZybyIsCiAgInR5cGUiOiAicmVjb3JkIiwKICAibmFtZSI6ICJDdXN0b21lciIsCiAgImZpZWxkcyI6IFsKICAgIHsKICAgICAgIm5hbWUiOiAiaWQiLAogICAgICAidHlwZSI6ICJpbnQiCiAgICB9LAogICAgewogICAgICAibmFtZSI6ICJuYW1lIiwKICAgICAgInR5cGUiOiAic3RyaW5nIgogICAgfSwKICAgIHsKICAgICAgIm5hbWUiOiAicGhvbmVOdW1iZXIiLAogICAgICAidHlwZSI6IFsKICAgICAgICAibnVsbCIsCiAgICAgICAgInN0cmluZyIKICAgICAgXSwKICAgICAgImRlZmF1bHQiOiBudWxsCiAgICB9CiAgXQp9Cg')

-- returns FALSE (`id` needs to be an integer, not a string)
AvroSchemaJsonValidator('{"id": "123456", "name": "Justin", "phoneNumber": {"string": "12345"}}', 'ewogICJuYW1lc3BhY2UiOiAiY29tLmRlbW8uYXZybyIsCiAgInR5cGUiOiAicmVjb3JkIiwKICAibmFtZSI6ICJDdXN0b21lciIsCiAgImZpZWxkcyI6IFsKICAgIHsKICAgICAgIm5hbWUiOiAiaWQiLAogICAgICAidHlwZSI6ICJpbnQiCiAgICB9LAogICAgewogICAgICAibmFtZSI6ICJuYW1lIiwKICAgICAgInR5cGUiOiAic3RyaW5nIgogICAgfSwKICAgIHsKICAgICAgIm5hbWUiOiAicGhvbmVOdW1iZXIiLAogICAgICAidHlwZSI6IFsKICAgICAgICAibnVsbCIsCiAgICAgICAgInN0cmluZyIKICAgICAgXSwKICAgICAgImRlZmF1bHQiOiBudWxsCiAgICB9CiAgXQp9Cg')
```

Note: Avro schemas don't really play nicely with JSON strings, especially w.r.t. optional fields. For example, with the above optional field "phoneNumber", this is valid JSON, but doesn't meet the schema because Avro requires the type to be defined in the JSON:

Invalid (per Avro schema):

```json
{
    "id": 123456
    "name": "Justin",
    "phoneNumber": "123-456-7890"
}
```

Correct (per Avro scehma):

```json
{
    "id": 123456
    "name": "Justin",
    "phoneNumber": {"string": "123-456-7890"}
}
```

This is part of the Avro spec and is not a limitation of the UDF, but depending on the expected format of your JSON, Avro may not be a viable schema validation choice.

## Build and Installation

1. Build the UDF JAR (and, optionally rename)

```bash
mvn clean package

cp target/SchemaValidator-0.0.1.jar SchemaValidator.jar
```

2. Upload the JAR to Confluent Cloud Flink UDF portal

Using the `confluent` CLI:

```bash
confluent flink artifact create schema_validator --artifact-file SchemaValidator.jar --cloud aws --region ap-southeast-1 --environment env-1234
```

3. Register the UDF(s)

In the Confluent Cloud Flink SQL shell:

```sql
CREATE FUNCTION JsonSchemaJsonValidator AS 'io.justinrlee.kafka.flink.udf.JsonSchemaJsonValidator'
USING JAR 'confluent-artifact://cfa-abc123';

CREATE FUNCTION AvroSchemaJsonValidator AS 'io.justinrlee.kafka.flink.udf.AvroSchemaJsonValidator'
USING JAR 'confluent-artifact://cfa-abc123';
```