package io.justinrlee.kafka.flink.udf;

import org.apache.flink.table.functions.ScalarFunction;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import org.apache.avro.Schema;
import org.apache.avro.io.Decoder;
import org.apache.avro.io.DecoderFactory;
import org.apache.avro.generic.GenericRecord;
import org.apache.avro.io.DatumReader;
import org.apache.avro.generic.GenericDatumReader;

import java.util.Base64;
import java.io.IOException;

/** Schema validation function using Apache Avro. */
public class SchemaValidator extends ScalarFunction {
   public static final String NAME = "SCHEMA_VALIDATOR";

   private static final Logger logger = LogManager.getLogger();

   public boolean eval(String inputRecord) {
      try {
         String avroSchemaB64= "ewogICJuYW1lc3BhY2UiOiAiY29tLmRlbW8uYXZybyIsCiAgInR5cGUiOiAicmVjb3JkIiwKICAibmFtZSI6ICJDdXN0b21lciIsCiAgImZpZWxkcyI6IFsKICAgIHsKICAgICAgIm5hbWUiOiAiaWQiLAogICAgICAidHlwZSI6ICJpbnQiCiAgICB9LAogICAgewogICAgICAibmFtZSI6ICJuYW1lIiwKICAgICAgInR5cGUiOiAic3RyaW5nIgogICAgfSwKICAgIHsKICAgICAgIm5hbWUiOiAicGhvbmVOdW1iZXIiLAogICAgICAidHlwZSI6IFsKICAgICAgICAibnVsbCIsCiAgICAgICAgInN0cmluZyIKICAgICAgXSwKICAgICAgImRlZmF1bHQiOiBudWxsCiAgICB9CiAgXQp9";

         logger.info("Input record: {}", inputRecord);
         logger.info("Avro schema base64: {}", avroSchemaB64);

         String avroSchemaJson = new String(Base64.getDecoder().decode(avroSchemaB64));
         logger.info("Avro schema json: {}", avroSchemaJson);

         Schema schema = new Schema.Parser().parse(avroSchemaJson);
         
         logger.info("Schema: {}", schema);

         DatumReader<GenericRecord> datumReader = new GenericDatumReader<>(schema);
         Decoder decoder = DecoderFactory.get().jsonDecoder(schema, inputRecord);
         
         // Attempt to read and validate the record against the schema
         GenericRecord record = datumReader.read(null, decoder);

         logger.info("Record: {}", record);
         
         // If we get here without exception, the JSON conforms to the schema
         logger.info("Record is valid");
         return record != null;
         
      } catch (IOException | RuntimeException e) {
         // Any parsing or validation error means the JSON doesn't conform to schema
         logger.error("Error: {}", e);
         // e.printStackTrace();
         return false;
      }
   }
}