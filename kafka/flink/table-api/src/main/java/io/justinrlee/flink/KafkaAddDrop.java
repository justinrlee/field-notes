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
 * Deserializes basic JSON, drops a few fields, combines two fields into one
 * Do not use for production. Only used as a proof of concept
 * Sample Data:
 * 
    {
        "timeUnixNano": "1726116132821304903$",
        "severityNumber": 10,
        "severityText": "Info",
        "body": "de359e1fea70f1d36aa7faeee249f8fedb7a400631c0e3516dd135be1836c26a 55422ec8ad70e59d",
        "sensitive_info": "692ea1cb097ebc40e457640d5a7946886194ef2c23973e3475fe9c7889bd2e03 aee57350044c0387",
        "traceId": "71e7a034963f1d37d4589cf02b8ccb75",
        "spanId": "d54b5a8f37d93230"
    }
 *
 */
public class KafkaAddDrop {

  public static void main(String[] args) throws Exception {

    final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
    final StreamTableEnvironment tableEnv = StreamTableEnvironment.create(env);

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
            .option("properties.sasl.jaas.config", "org.apache.kafka.common.security.plain.PlainLoginModule required username='xxx' password='yyy';")
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
            .option("properties.sasl.jaas.config", "org.apache.kafka.common.security.plain.PlainLoginModule required username='xxx' password='yyy';")
            .build();

    tableEnv.createTemporaryTable("input", otel_descriptor);
    tableEnv.createTable("output", otel_output);

    tableEnv.executeSql("INSERT INTO output SELECT timeUnixNano, severityNumber, severityText, body, sensitive_info, CONCAT(body, sensitive_info) as `combined` FROM input");
  }
}
