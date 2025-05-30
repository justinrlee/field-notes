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

import org.apache.flink.api.java.utils.MultipleParameterTool;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.connectors.kafka.FlinkKafkaConsumer010;
import org.apache.flink.streaming.util.serialization.SimpleStringSchema;

/**
 * Skeleton for a Flink Streaming Job.
 *
 * This uses the old (deprecated) Flink Kafka Consumer 0.10.0, and probably shouldn't be used.
 * 
 */
public class KafkaHelloWorld {

	public static void main(String[] args) throws Exception {

		// Checking input parameters
		final MultipleParameterTool params = MultipleParameterTool.fromArgs(args);

		// set up the streaming execution environment
		final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

		env.getConfig().setGlobalJobParameters(params);

    Properties properties = new Properties();
    properties.put("group.id", UUID.randomUUID().toString());
    properties.put("auto.offset.reset", "earliest");
    properties.put("bootstrap.servers", "x.y.z:9093");
    properties.put("ssl.endpoint.identification.algorithm", "https");
    properties.put("ssl.truststore.location", "ssl/truststore.jks");
    properties.put("ssl.truststore.password", "confluent");
    properties.put("security.protocol", "SASL_SSL");
    properties.put("sasl.mechanism", "PLAIN");
    properties.put("sasl.jaas.config", "org.apache.kafka.common.security.plain.PlainLoginModule required username=\"professor\" password=\"professor\";");

    FlinkKafkaConsumer010<String> kafka = new FlinkKafkaConsumer010<>("flink", new SimpleStringSchema(), properties);

		DataStream<String> events = env.addSource(kafka);
    events.print();

		// execute program
		env.execute("Flink Streaming Java API Skeleton");
	}
}
