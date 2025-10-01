json-producer-perf-test

Based on kafka-producer-perf-test, but generates JSON payloads using Jackson

Build:
```
mvn package
```

Run:
```
java -cp /home/ubuntu/git/justinrlee/field-notes/kafka/java/json-producer-perf-test/target/json-producer-perf-test-1.0-SNAPSHOT.jar io.justinrlee.kafka.JsonProducerPerformance --producer.config justin.std.properties --topic p1 --throughput 100 --num-records 1000000
```