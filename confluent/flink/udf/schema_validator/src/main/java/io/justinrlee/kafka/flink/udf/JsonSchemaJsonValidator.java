package io.justinrlee.kafka.flink.udf;

import org.apache.flink.table.functions.ScalarFunction;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import com.github.erosb.jsonsKema.FormatValidationPolicy;
import com.github.erosb.jsonsKema.JsonParser;
import com.github.erosb.jsonsKema.JsonValue;
import com.github.erosb.jsonsKema.Schema;
import com.github.erosb.jsonsKema.SchemaLoader;
import com.github.erosb.jsonsKema.ValidationFailure;
import com.github.erosb.jsonsKema.Validator;
import com.github.erosb.jsonsKema.ValidatorConfig;

import java.util.Base64;
import java.io.IOException;

/** Schema validation function using Apache Avro. */
public class JsonSchemaJsonValidator extends ScalarFunction {
   public static final String NAME = "JSON_SCHEMA_JSON_VALIDATOR";

   private static final Logger logger = LogManager.getLogger();

   public boolean eval(String jsonString, String jsonSchemaB64) {
      logger.info("Input record: {}", jsonString);
      logger.info("JSON schema base64: {}", jsonSchemaB64);

      String jsonSchemaJson = new String(Base64.getDecoder().decode(jsonSchemaB64));
      logger.info("JSON schema json: {}", jsonSchemaJson);

      JsonValue schemaJson = new JsonParser(jsonSchemaJson).parse();

      Schema schema = new SchemaLoader(schemaJson).load();

      Validator validator = Validator.create(schema, new ValidatorConfig(FormatValidationPolicy.ALWAYS));
      JsonValue inputJson = new JsonParser(jsonString).parse();


      ValidationFailure failure = validator.validate(inputJson);
      logger.info("Validation failure: {}", failure);

      return failure == null;
   }
}