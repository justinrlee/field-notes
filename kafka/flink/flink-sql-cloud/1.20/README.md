

2025-05-16
This is still a WIP - Can't get the SQL query to work (works in sql-client, doesn't work in app)

General ad-hoc testing:
* Set up local Flink cluster (session mode)
* Compile JAR
* Submit JAR to Flink cluster

General prereqs
```bash
# From home directory
sudo apt-get update && \
    sudo apt-get install -y \
        openjdk-17-jdk-headless \
        maven
```

Install CP packages
```bash
curl -O http://packages.confluent.io/archive/7.9/confluent-7.9.1.tar.gz && \
    tar -xzvf confluent-7.9.1.tar.gz && \
    ln -s confluent-7.9.1 confluent && \
    echo 'export PATH=${PATH}:/home/ubuntu/confluent/bin' >> ~/.bashrc && \
    export PATH=${PATH}:/home/ubuntu/confluent/bin
```

Install Flink packages
```bash
# Link from https://www.apache.org/dyn/closer.lua/flink/flink-1.20.1/flink-1.20.1-bin-scala_2.12.tgz
curl -LO https://dlcdn.apache.org/flink/flink-1.20.1/flink-1.20.1-bin-scala_2.12.tgz && \
    tar -xzvf flink-1.20.1-bin-scala_2.12.tgz && \
    ln -s flink-1.20.1 flink && \
    echo 'export PATH=${PATH}:/home/ubuntu/flink/bin' >> ~/.bashrc && \
    export PATH=${PATH}:/home/ubuntu/flink/bin
```

Do a maven build, use it to bulk add libraries to flink:

```bash
mvn clean package
cp target/flink-sql-cloud-1.0-SNAPSHOT.jar /home/ubuntu/flink/lib/
```

```bash
# should already be populated by .bashrc
# export PATH=${PATH}:/home/ubuntu/flink/bin
start-cluster.sh

sql-client.sh

stop-cluster.sh
```


Done so far:
* Launch local flink cluster
* Do a create table and select via flink CLI

TODO:
* Build into jar
* Do more complex query (create second table, insert into)
* Launch JAR on local cluster
* Launch K8s session cluster
* Run JAR on session cluster
* Run JAR on application cluster (FKO)


Add Plugins (don't do this, just do a maven build and use that)
```bash
curl -LO https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-kafka/3.3.0-1.20/flink-connector-kafka-3.3.0-1.20.jar
curl -LO https://repo.maven.apache.org/maven2/org/apache/flink/flink-avro-confluent-registry/1.20.1/flink-avro-confluent-registry-1.20.1.jar
curl -LO https://repo1.maven.org/maven2/org/apache/avro/avro/1.12.0/avro-1.12.0.jar
curl -LO https://repo.maven.apache.org/maven2/org/apache/flink/flink-avro/1.20.1/flink-avro-1.20.1.jar
curl -LO https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-core/2.19.0/jackson-core-2.19.0.jar
curl -LO https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-annotations/2.19.0/jackson-annotations-2.19.0.jar
curl -LO https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-databind/2.19.0/jackson-databind-2.19.0.jar
curl -LO https://packages.confluent.io/maven/io/confluent/kafka-schema-registry-client/7.9.0/kafka-schema-registry-client-7.9.0.jar
curl -LO https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.9.0/kafka-clients-3.9.0.jar
curl -LO https://repo1.maven.org/maven2/com/google/guava/guava/33.4.8-jre/guava-33.4.8-jre.jar

# For ease of use, putting these directly into the lib directory, but ideally would use plugin configuration
```
