# Hello
This is a very MVP multi-threaded synchronous producer using librdkafka in C

It has hardcoded settings.  And no parameters.  And no error handling.  And is generally very poorly written.

## Setup


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

## Build

```bash
gcc rdkafka_sync.c -lpthread -lrdkafka -o rdkafka_sync
```

## Run

Options:

* `-a`: "acks" setting
* `-l`: "linger.ms" setting
* `-b`: bootstrap server
* `-t`: topic to produce to
* `-M`: number of messages to produce
* `-T`: number of threads to use
* `-S`: size of each message (in bytes)
* `-v`: verbosity level (0, 1, 2 or 3)


Example:
```
./rdkafka_sync -M 64000 -T 4 -l 0.1 -S 4096 -a 1
Writing 64000 4096-byte messages using 4 threads (16000 per thread)
Topic test for bootstrap server localhost:9092
linger.ms = 0.1
acks = 1
All threads started
All threads completed
```

Examples, with bash `time` wrapper (note that time includes thread startup time and malloc time):
```
time ./rdkafka_sync -M 64000 -T 4 -l 0.1 -S 4096 -a 1
Writing 64000 4096-byte messages using 4 threads (16000 per thread)
Topic test for bootstrap server localhost:9092
linger.ms = 0.1
acks = 1
All threads started
All threads completed

real	0m18.944s
user	0m36.317s
sys	0m24.578s
```

```
time ./rdkafka_sync -M 64000 -T 16 -l 0.1 -S 4096 -a 1
Writing 64000 4096-byte messages using 16 threads (4000 per thread)
Topic test for bootstrap server localhost:9092
linger.ms = 0.1
acks = 1
All threads started
All threads completed

real	0m5.159s
user	0m9.586s
sys	0m6.413s
```

Verbose output:
```
$ time ./rdkafka_sync -M 16 -T 4 -l 0.1 -S 4096 -a 1 -v1
Writing 16 4096-byte messages using 4 threads (4 per thread)
Topic test for bootstrap server localhost:9092
linger.ms = 0.1
acks = 1
Initiating thread 0
Thread 0 initiated successfully: 139648992917248
Initiating thread 1
Starting thread 139648992917248
Thread 1 initiated successfully: 139648915470080
Initiating thread 2
Thread 2 initiated successfully: 139648781252352
Initiating thread 3
Starting thread 139648781252352
Starting thread 139648915470080
Thread 3 initiated successfully: 139648907077376
All threads initiated
Starting thread 139648907077376
Thread 139648781252352 finished
Thread 139648907077376 finished
Thread 139648915470080 finished
Thread 139648992917248 finished
Thread 139648992917248 joined
Thread 139648915470080 joined
Thread 139648781252352 joined
Thread 139648907077376 joined
All threads completed

real	0m0.012s
user	0m0.023s
sys	0m0.003s
```