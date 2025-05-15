# Hello world Kafka Streams app

Does this:
* Read from `input` topic (using String Serde for both key and value, although key is ignored)
* Print the value to console
* Convere the string value to upper case
* Print the updated value to console
* Write the updated message to the `output` topic

```shell
sudo apt-get update && \
sudo apt-get install -y openjdk-17-jdk-headless maven
```

```shell
mvn package
```

Copy `configuration/cloud.properties` and update it with relevant bootstrap server and credentials, e.g.

```config
# client.properties
application.id=streams-demo
bootstrap.servers=pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username='xxx' password='yyy';
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
client.dns.lookup=use_all_dns_ips
acks=all
cache.max.bytes.buffering=0
```

Run with this:

```shell
java -cp target/quickstart-1.0-SNAPSHOT.jar io.justinrlee.kafka.streams.App client.properties
```