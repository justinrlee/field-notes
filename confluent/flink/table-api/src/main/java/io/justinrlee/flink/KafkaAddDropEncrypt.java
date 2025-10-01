/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package io.justinrlee.flink;

import java.util.Properties;
import java.util.UUID;
import java.time.LocalDate;

import java.nio.charset.StandardCharsets;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.KeyGenerator;
import javax.crypto.spec.IvParameterSpec;
import java.security.SecureRandom;
import java.security.Security;
import java.security.Provider;
import java.util.Base64;
import java.util.Base64.Encoder;


import org.apache.flink.table.functions.ScalarFunction;
import org.apache.flink.table.functions.FunctionContext;

import org.apache.flink.table.api.DataTypes;
import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.Schema;
import org.apache.flink.table.api.Table;
import org.apache.flink.table.api.TableDescriptor;
import org.apache.flink.table.api.TableEnvironment;

import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.table.api.bridge.java.StreamTableEnvironment;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.streaming.api.datastream.DataStream;

import static org.apache.flink.table.api.Expressions.*;


import org.apache.flink.table.api.TableDescriptor;

/**
 *
 * Hello world; deserializes JSON, drops a few fields, and encrypts one.
 * Do not use for production. Only used as a proof of concept. Encryption algo may be insecure.
 * 
 */
public class KafkaAddDropEncrypt {

    public static class EncryptFunction extends ScalarFunction {
        
        private Cipher cipher;
        private Encoder b64Encoder;

        @Override
        public void open(FunctionContext context) throws Exception{
            KeyGenerator keygenerator = KeyGenerator.getInstance("AES");
            keygenerator.init(256);
            SecretKey symmetricKey = keygenerator.generateKey();

            byte[] ivb = new byte[16];
            SecureRandom secureRandom = new SecureRandom();
            secureRandom.nextBytes(ivb);

            IvParameterSpec iv = new IvParameterSpec(ivb);

            cipher = Cipher.getInstance("AES_256/CFB/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, symmetricKey, iv);

            b64Encoder = Base64.getEncoder();
        }

        public String eval(String s) throws Exception{
            byte[] cipherText = cipher.doFinal(s.getBytes(StandardCharsets.UTF_8));
            return b64Encoder.encodeToString(cipherText);
        }
    }

    public static void main(String[] args) throws Exception {

        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        final StreamTableEnvironment tableEnv = StreamTableEnvironment.create(env);

        tableEnv.createTemporarySystemFunction("Encrypt", EncryptFunction.class);

        TableDescriptor otel_descriptor = TableDescriptor.forConnector("kafka")
            .schema(
                Schema.newBuilder()
                    .column("timeUnixNano", DataTypes.STRING())
                    .column("severityNumber", DataTypes.BIGINT())
                    .column("severityText", DataTypes.STRING())
                    .column("body", DataTypes.STRING())
                    .column("sensitive_info", DataTypes.STRING())
                    .column("traceId", DataTypes.STRING())
                    .column("spanId", DataTypes.STRING())
                    .build())
            .option("format", "json")
            .option("topic", "dummy_otel_json")
            .option("scan.startup.mode", "earliest-offset")
            .option("properties.bootstrap.servers", "pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092")
            .option("properties.security.protocol", "SASL_SSL")
            .option("properties.sasl.mechanism", "PLAIN")
            .option("properties.sasl.jaas.config", "org.apache.kafka.common.security.plain.PlainLoginModule required username='xxx' password='ooo';")
            .build();

        TableDescriptor otel_output = TableDescriptor.forConnector("kafka")
            .schema(
                Schema.newBuilder()
                    .column("timeUnixNano", DataTypes.STRING())
                    .column("severityNumber", DataTypes.BIGINT())
                    .column("severityText", DataTypes.STRING())
                    .column("body", DataTypes.STRING())
                    .column("sensitive_info", DataTypes.STRING())
                    .column("combined", DataTypes.STRING())
                    .build())
            .option("format", "json")
            .option("topic", "dummy_output_json")
            .option("properties.bootstrap.servers", "pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092")
            .option("properties.security.protocol", "SASL_SSL")
            .option("properties.sasl.mechanism", "PLAIN")
            .option("properties.sasl.jaas.config", "org.apache.kafka.common.security.plain.PlainLoginModule required username='xxx' password='ooo';")
            .build();

        tableEnv.createTemporaryTable("input", otel_descriptor);
        tableEnv.createTable("output", otel_output);

        tableEnv.executeSql("INSERT INTO output SELECT timeUnixNano, severityNumber, severityText, body, Encrypt(sensitive_info), CONCAT(body, severityText) as `combined` FROM input");
    }
}
