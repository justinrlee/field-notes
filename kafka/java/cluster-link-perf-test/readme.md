json-producer-perf-test

Based on kafka-producer-perf-test, but generates JSON payloads using Jackson

Build:
```
mvn package
```

Run:
```
java -cp target/cluster-link-producer-perf-test-1.0-SNAPSHOT.jar io.justinrlee.kafka.CLConsumerPerformance --consumer.config ~/justin.std.properties --topic p2 --bootstrap-server pkc-rgm37.us-west-2.aws.confluent.cloud:9092 --messages 10000 --from-latest
```