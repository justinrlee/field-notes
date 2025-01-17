json-producer-perf-test

Based on kafka-producer-perf-test, but generates JSON payloads using Jackson

Build:
```
mvn package

cp target/cluster-link-producer-perf-test-1.0-SNAPSHOT.jar ~
```

Create topic on source cluster
```bash
# Verify connectivity
kafka-broker-api-versions --bootstrap-server ${SOURCE_BOOTSTRAP} --command-config source.properties
# Create topic
kafka-topics --bootstrap-server ${SOURCE_BOOTSTRAP} --command-config source.properties --create --topic cluster-link-latency --partitions 12 --config message.timestamp.type=LogAppendTime

```

Create cluster link (exercise left to reader)

Produce on source cluster (takes same flags as kafka-producer-perf-test, although some don't do anything)
```bash
# 25 MB/s, for 120 seconds (two minutes)
java -cp cluster-link-producer-perf-test-1.0-SNAPSHOT.jar io.justinrlee.kafka.CLProducerPerformance \
    --record-size 2048 \
    --throughput 12500 \
    --num-records 1500000 \
    --topic cluster-link-latency \
    --producer.config source.properties
```

Consume on destination cluster (takes same flags as kafka-consumer-perf-test, although some don't do anything)
```bash
java -cp cluster-link-producer-perf-test-1.0-SNAPSHOT.jar io.justinrlee.kafka.CLConsumerPerformance \
    --bootstrap-server ${DEST_BOOTSTRAP} \
    --topic cluster-link-latency \
    --consumer.config dest.properties \
    --messages 10000 \
    --from-latest
```