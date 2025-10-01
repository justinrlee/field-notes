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
import org.apache.flink.table.api.TableSchema;
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
 * This is incomplete; it deserializes and prints to stdout (on the client), rather than doing anything
 * 
 */
public class KafkaAddDropOTLP {

  public static void main(String[] args) throws Exception {

    final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
    final StreamTableEnvironment tableEnv = StreamTableEnvironment.create(env);

    Schema schema = Schema.newBuilder()
                    .column("resourceLogs", DataTypes.ARRAY(
                        DataTypes.ROW(
                            DataTypes.FIELD("resource", DataTypes.ROW(
                                DataTypes.FIELD("attributes", DataTypes.ARRAY(
                                    DataTypes.ROW(
                                        DataTypes.FIELD("key", DataTypes.STRING()),
                                        DataTypes.FIELD("value", DataTypes.ROW(
                                            DataTypes.FIELD("stringValue", DataTypes.STRING())
                                        ))
                                    )
                                ))
                            )),
                            DataTypes.FIELD("scopeLogs", DataTypes.ARRAY(
                                DataTypes.ROW(
                                    DataTypes.FIELD("logRecords", DataTypes.ARRAY(
                                        DataTypes.ROW(
                                            DataTypes.FIELD("timeUnixNano", DataTypes.STRING()),
                                            DataTypes.FIELD("severityNumber", DataTypes.BIGINT()),
                                            DataTypes.FIELD("severityText", DataTypes.STRING()),
                                            DataTypes.FIELD("traceId", DataTypes.STRING()),
                                            DataTypes.FIELD("spanId", DataTypes.STRING()),
                                            DataTypes.FIELD("body", DataTypes.ROW(
                                                DataTypes.FIELD("stringValue", DataTypes.STRING())
                                            )),
                                            DataTypes.FIELD("attributes", DataTypes.ARRAY(
                                                DataTypes.ROW(
                                                    DataTypes.FIELD("key", DataTypes.STRING()),
                                                    DataTypes.FIELD("value", DataTypes.ROW(
                                                        DataTypes.FIELD("stringValue", DataTypes.STRING())
                                                    ))
                                                )
                                            ))
                                        )
                                    ))
                                )
                            ))
                        )
                    ))
                    .build();

    TableDescriptor otlp_json = TableDescriptor.forConnector("kafka")
            .schema(schema)
            .option("format", "json")
            .option("topic", "otlp_metrics_json")
            .option("scan.startup.mode", "earliest-offset")
            .option("properties.bootstrap.servers", "pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092")
            .option("properties.security.protocol", "SASL_SSL")
            .option("properties.sasl.mechanism", "PLAIN")
            .option("properties.sasl.jaas.config", "org.apache.kafka.common.security.plain.PlainLoginModule required username='x' password='yyy';")
            .build();

    tableEnv.createTemporaryTable("input", otlp_json);

    tableEnv.sqlQuery("SELECT * FROM input limit 20")
      .execute()
      .print();
  }
}
