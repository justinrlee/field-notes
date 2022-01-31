Setting up build env (Ubuntu 20.04):

Build stuff
```bash

sudo apt-get update
sudo apt-get install -y \
  build-essential

sudo apt-get install -y librdkafka-dev

```

Local Confluent (KRaft) cluster
```bash

sudo apt-get update && \
  sudo apt-get install openjdk-11-jre-headless -y && \
  wget -qO - https://packages.confluent.io/deb/7.0/archive.key | sudo apt-key add - && \
  sudo add-apt-repository "deb [arch=amd64] https://packages.confluent.io/deb/7.0 stable main" && \
  sudo add-apt-repository "deb https://packages.confluent.io/clients/deb $(lsb_release -cs) main" && \
  sudo apt-get update && sudo apt-get install confluent-platform -y

#### kraft stuff
sudo mv /etc/kafka/server.properties /etc/kafka/server.properties.bak

sudo tee /etc/kafka/server.properties <<-'EOF'
# broker.id=0
node.id=1

process.roles=broker,controller
controller.quorum.voters=1@localhost:9093

listeners=PLAINTEXT://:9092,CONTROLLER://:9093
inter.broker.listener.name=PLAINTEXT
advertised.listeners=PLAINTEXT://localhost:9092
controller.listener.names=CONTROLLER
listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,SSL:SSL,SASL_PLAINTEXT:SASL_PLAINTEXT,SASL_SSL:SASL_SSL

log.dirs=/var/lib/kafka

num.network.threads=3
num.io.threads=8

socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400
socket.request.max.bytes=104857600

num.partitions=1
num.recovery.threads.per.data.dir=1

offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1

log.retention.hours=168
log.segment.bytes=1073741824
log.retention.check.interval.ms=300000

group.initial.rebalance.delay.ms=0

confluent.license.topic.replication.factor=1
confluent.metadata.topic.replication.factor=1
confluent.security.event.logger.exporter.kafka.topic.replicas=1
confluent.balancer.topic.replication.factor=1

confluent.balancer.enable=false
confluent.cluster.link.enable=false
EOF

sudo kafka-storage format -t $(kafka-storage random-uuid) -c /etc/kafka/server.properties

sudo systemctl start confluent-server
```