

2025-05-19

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
# Also from home directory
curl -O http://packages.confluent.io/archive/7.9/confluent-7.9.1.tar.gz && \
    tar -xzvf confluent-7.9.1.tar.gz && \
    ln -s confluent-7.9.1 confluent && \
    echo 'export PATH=${PATH}:/home/ubuntu/confluent/bin' >> ~/.bashrc && \
    export PATH=${PATH}:/home/ubuntu/confluent/bin
```

Install Flink packages
```bash
# Link from https://www.apache.org/dyn/closer.lua/flink/flink-1.19.2/flink-1.19.2-bin-scala_2.12.tgz
curl -LO https://dlcdn.apache.org/flink/flink-1.19.2/flink-1.19.2-bin-scala_2.12.tgz && \
    tar -xzvf flink-1.19.2-bin-scala_2.12.tgz && \
    ln -s flink-1.19.2 flink && \
    echo 'export PATH=${PATH}:/home/ubuntu/flink/bin' >> ~/.bashrc && \
    export PATH=${PATH}:/home/ubuntu/flink/bin
```

(Optional): edit `~/flink/conf/config.yaml`, change rest.bind-address to 0.0.0.0

Start (local) Flink session mode cluster
```bash
start-cluster.sh

### Later on, to stop the cluster
stop-cluster.sh
```

Ad-hoc query (using local Flink cluster) via sql-client.sh:

```bash
# Run from home directory
curl -LO https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.20/flink-sql-connector-kafka-3.3.0-1.20.jar
curl -LO https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-avro-confluent-registry/1.20.1/flink-sql-avro-confluent-registry-1.20.1.jar
cp ~/confluent/share/java/kafka/kafka-clients-7.9.1-ce.jar .

sql-client.sh \
    --jar flink-sql-connector-kafka-3.3.0-1.20.jar \
    --jar flink-sql-avro-confluent-registry-1.20.1.jar \
    --jar kafka-clients-7.9.1-ce.jar
```

Run your ad-hoc query


```sql
CREATE TABLE shoe_customers (
  `order_id` BIGINT,
  `product_id` VARCHAR(2147483647),
  `customer_id` VARCHAR(2147483647),
  `ts` TIMESTAMP(3) METADATA FROM 'timestamp'
) WITH (
  'connector' = 'kafka',
  'topic' = 'flink-shoe_orders',
  'properties.bootstrap.servers' = '<BOOTSTRAP_SERVER>',
  'properties.security.protocol' = 'SASL_SSL',
  'properties.sasl.mechanism' = 'PLAIN',
  'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="<KAFKA_API_KEY>" password="<KAFKA_API_SECRET>";',
  'properties.group.id' = 'test-app',
  'scan.startup.mode' = 'earliest-offset',
  'value.avro-confluent.url' = '<SCHEMA_REGISTRY_ENDPOINT>',
  'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
  'value.avro-confluent.basic-auth.user-info' = '<SCHEMA_REGISTRY_API_KEY>:<SCHEMA_REGISTRY_API_SECRET>',
  'value.format' = 'avro-confluent'
);

SELECT * FROM shoe_customers LIMIT 10;
```

Do a maven build

```bash
mvn clean package
```

```bash

flink run /home/ubuntu/git/justinrlee/field-notes/kafka/flink/flink-sql-cloud/1.19/target/flink-sql-cloud-1.19.jar -config-file client.properties -app.name override
```

Note: the job will continue running, even after you ctrl-c out of the application. You have to kill it manually:

Get flink job ID

```bash
flink list
```

Cancel flink job

```bash
flink cancel b24f93013276f99b3a71f70850c1af28
```

# Kubernetes

TODO: Install FKO

Create secret from client.properties:
```bash
kubectl create secret generic flink-properties --from-file=client.properties=client.properties
```

Manifest, using local hosting
```yaml
apiVersion: flink.apache.org/v1beta1
kind: FlinkDeployment
metadata:
  name: basic-example
spec:
  image: "confluentinc/cp-flink:1.19.2-cp2-java17"
  flinkVersion: v1_19
  flinkConfiguration:
    taskmanager.numberOfTaskSlots: "2"
    user.artifacts.raw-http-enabled: "true"
  serviceAccount: flink
  jobManager:
    resource:
      memory: "2048m"
      cpu: 1
  taskManager:
    resource:
      memory: "2048m"
      cpu: 1
  job:
    jarURI: http://10.32.1.246:8000/flink-sql-cloud-1.19.jar
    args:
    - --config-file
    - /client/client.properties
    parallelism: 2
    upgradeMode: stateless
  podTemplate:
    spec:
      containers:
        - name: flink-main-container
          volumeMounts:
            - mountPath: /client
              name: client
      volumes:
        - name: client
          secret:
            secretName: flink-properties
```

S3 version

```yaml
apiVersion: flink.apache.org/v1beta1
kind: FlinkDeployment
metadata:
  name: basic-example
spec:
  image: "justinrlee/cp-flink:1.19.2-cp2-java17-s3-10"
  # image: "confluentinc/cp-flink:1.19.1-cp2"
  flinkVersion: v1_19
  flinkConfiguration:
    taskmanager.numberOfTaskSlots: "2"
    user.artifacts.raw-http-enabled: "true"
  serviceAccount: flink
  jobManager:
    resource:
      memory: "2048m"
      cpu: 1
  taskManager:
    resource:
      memory: "2048m"
      cpu: 1
  job:
    jarURI: s3://justin-confluent-apse1/flink-sql-cloud-1.19.jar
    args:
    - --config-file
    - /client/client.properties
    parallelism: 2
    upgradeMode: stateless
  podTemplate:
    spec:
      containers:
        - name: flink-main-container
          volumeMounts:
            - mountPath: /client
              name: client
      volumes:
        - name: client
          secret:
            secretName: flink-properties
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
