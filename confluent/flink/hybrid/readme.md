## Hybrid: Confluent Cloud + Self-Managed Flink SQL

Notes:
* This has no resiliency architecture, and is not intended for production
* This uses open source Flink 1.19.0
* This currently runs on a small VM
* Confluent Cloud has a `confluent` Flink Table API connector, which is similar to, but not identical to, the open source `kafka` and `upsert-kafka` Table API connectors:
    * with the `kafka` table connector:
        * for source, we treat all topics (tables) as append-only stream
        * for destination, we always use INSERT
        * in flink, the table is basically is effectively unkeyed
    * with `upsert-kafka` table connector:
        * we require a key
        * for source, we treat all topics (tables) as changelog (update/delete messages only) streams
        * for sink, we can consume a changelog stream (INSERT/UPDATE are one message type and DELETE is tombstones)
        * in flink, the table is effectively keyed
    * with the `confluent` table connector (in confluent cloud only):
        * if we have a key and/or are compacted, it roughly acts like the upsert-kafka connector
        * otherwise it acts like the kafka connector
    * In this repo, we use both the `kafka` and `upsert-kafka` connectors

Prerequisites:
* Ubuntu 20.04 VM, running in AWS / Azure on AMD64 instance type (ARM64 should also work, but not as tested)
    * For functional testing, use an instance with 4 cores, 16 GB of memory, and 1 TB of disk (more will be needed for larger use cases)
* VM should have access to a Confluent Cloud Kafka cluster (either via Internet, or via private networking)
* VM should have access to Confluent Cloud Schema Registry (access to the Internet)
* Need to be able to SSH into the VM and get sudo acecss
* Ideally, should be able to acesss port 8081 (or some static port) on the VM from a workstation (nice-to-have, not necessary)

This will install Kubernetes + Helm:

```bash
# Install K3s, create 'confluent' namespace, install Helm
curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE=644 sh - \
  && mkdir -p ~/.kube \
  && cp /etc/rancher/k3s/k3s.yaml ~/.kube/config \
&& curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \
  && chmod 700 get_helm.sh \
  && ./get_helm.sh
```

Create a namespace:
```bash
kubectl create namespace confluent
```

Install the Cert Manager:
```bash
kubectl create -f https://github.com/jetstack/cert-manager/releases/download/v1.8.2/cert-manager.yaml
```

Wait for cert manager to be ready:
```bash
while [[ $(kubectl -n cert-manager get pod | grep webhook | grep '1/1' | grep 'Running' | wc -l) -ne 1 ]]; \
    do echo 'Waiting for Cert Manager Installation'; sleep 5; done
```

(or just run this until it's 1/1 and 'Running'):
```bash
kubectl -n cert-manager get pod -w
```

Install Flink Operator
```bash
helm repo add flink-operator-repo https://downloads.apache.org/flink/flink-kubernetes-operator-1.8.0/ \
  && helm install flink-kubernetes-operator flink-operator-repo/flink-kubernetes-operator -n confluent
```

Wait for the operator to be healthy:
```bash
kubectl -n confluent get pods -l app.kubernetes.io/name=flink-kubernetes-operator
```

Create a "Session Mode" Flink Cluster with this yaml:
```yaml
# flink.yaml
---
# FlinkDeployment
apiVersion: flink.apache.org/v1beta1
kind: FlinkDeployment
metadata:
  name: flink-session
  namespace: confluent
spec:
  image: "justinrlee/flink:1.19.0-scala_2.12-java17-cflt-0.0.3"
  flinkVersion: v1_18
  flinkConfiguration:
    taskmanager.numberOfTaskSlots: "2"
  serviceAccount: flink
  jobManager:
    resource:
      memory: "2048m"
      cpu: 2
  taskManager:
    resource:
      memory: "2048m"
      cpu: 2
---
# Expose container on 'jobmanager' endpoint:
# Internally: `http://jobmanager.confluent:8081`
# Externally (on k3s): `http://<VM-hostname>:8081`
apiVersion: v1
kind: Service
metadata:
  name: jobmanager
  namespace: confluent
spec:
  ports:
  - name: rest
    port: 8081
    protocol: TCP
    targetPort: 8081
  selector:
    app: flink-session
    component: jobmanager
    type: flink-native-kubernetes
  type: LoadBalancer
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: confluent-flink-utility
  namespace: confluent
spec:
  selector:
    matchLabels:
      app: confluent-flink-utility # has to match .spec.template.metadata.labels
  serviceName: "confluent-flink-utility"
  replicas: 1 # by default is 1
  # minReadySeconds: 10 # by default is 0
  template:
    metadata:
      labels:
        app: confluent-flink-utility # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: utility
        image: "justinrlee/flink:1.19.0-scala_2.12-java17-cflt-0.0.3"
        command: ["tail"]
        args: ["-f", "/dev/null"]
```

From there, you can exec into the utility container and use the SQL CLI:
```bash
kubectl -n confluent exec -it confluent-flink-utility-0 -- bash
```

```bash
sql-client.sh -Drest.address=jobmanager.confluent -Drest.port=8081
```

Or as a one-liner:
```bash
kubectl -n confluent exec -it confluent-flink-utility-0 -- sql-client.sh -Drest.address=jobmanager.confluent -Drest.port=8081
```

## SQL

When working with SQL with SR, you have to define tables with the `kafka` or `upsert-kafka` connectors. Few examples:

Joint data (all value fields are also in key):

```sql
CREATE TABLE test (
  `id` BIGINT,
  `first_name` VARCHAR(2147483647),
  `last_name` VARCHAR(2147483647),
  `email` VARCHAR(2147483647),
  `ts` TIMESTAMP(3) METADATA FROM 'timestamp'
) WITH (
  'connector' = 'kafka',
  'topic' = 'debezium-sql-demo-unwrap-10.demo.dbo.composite',
  'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
  'properties.security.protocol' = 'SASL_SSL',
  'properties.sasl.mechanism' = 'PLAIN',
  'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="xxx" password="yyy";',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'earliest-offset',
  'key.format' = 'json',
  'key.fields' = 'id;email',

  'value.avro-confluent.url' = 'https://psrc-7yzmzo.ap-southeast-1.aws.confluent.cloud',
  'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
  'value.avro-confluent.basic-auth.user-info' = 'xxx:yyy',
  'value.format' = 'avro-confluent'
);
```

Disjoint data:
* https://nightlies.apache.org/flink/flink-docs-master/docs/connectors/table/kafka/ ('overlapping format fields')

```sql
CREATE TABLE test (
  `k_id` BIGINT,
  `k_email` VARCHAR(2147483647),
  `id` BIGINT,
  `first_name` VARCHAR(2147483647),
  `last_name` VARCHAR(2147483647),
  `email` VARCHAR(2147483647),
  `ts` TIMESTAMP(3) METADATA FROM 'timestamp'
) WITH (
  'connector' = 'kafka',
  'topic' = 'debezium-sql-demo-unwrap-10.demo.dbo.composite',
  'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
  'properties.security.protocol' = 'SASL_SSL',
  'properties.sasl.mechanism' = 'PLAIN',
  'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="xxx" password="yyy";',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'earliest-offset',
  'key.format' = 'json',
  'key.fields-prefix' = 'k_',
  'value.fields-include' = 'EXCEPT_KEY',
  'key.fields' = 'k_id;k_email',

  'value.avro-confluent.url' = 'https://psrc-7yzmzo.ap-southeast-1.aws.confluent.cloud',
  'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
  'value.avro-confluent.basic-auth.user-info' = 'xxx:yyy',
  'value.format' = 'avro-confluent'
);
```

To be added: upsert kafka with key. Might look something like this (but haven't tested):
```sql
CREATE TABLE test (
  `k_id` BIGINT,
  `k_email` VARCHAR(2147483647),
  `id` BIGINT,
  `first_name` VARCHAR(2147483647),
  `last_name` VARCHAR(2147483647),
  `email` VARCHAR(2147483647),
  `ts` TIMESTAMP(3) METADATA FROM 'timestamp',
  PRIMARY KEY (k_id,k_email) NOT ENFORCED
) WITH (
  'connector' = 'upsert-kafka',
  'topic' = 'debezium-sql-demo-unwrap-10.demo.dbo.composite',
  'properties.bootstrap.servers' = 'pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092',
  'properties.security.protocol' = 'SASL_SSL',
  'properties.sasl.mechanism' = 'PLAIN',
  'properties.sasl.jaas.config' = 'org.apache.kafka.common.security.plain.PlainLoginModule required username="xxx" password="yyy";',
  'properties.group.id' = 'testGroup',
  'scan.startup.mode' = 'earliest-offset',
  'key.format' = 'json',
  'key.fields-prefix' = 'k_',
  'value.fields-include' = 'EXCEPT_KEY',
  'key.fields' = 'k_id;k_email',

  'value.avro-confluent.url' = 'https://psrc-7yzmzo.ap-southeast-1.aws.confluent.cloud',
  'value.avro-confluent.basic-auth.credentials-source' = 'USER_INFO',
  'value.avro-confluent.basic-auth.user-info' = 'xxx:yyy',
  'value.format' = 'avro-confluent'
);
```

## Appendix
Docker image is multiarch as of 0.0.3 built with this:

```Dockerfile
# Used to build justinrlee/flink:1.19.0-scala_2.12-java17-cflt-0.0.x
FROM flink:1.19.0-scala_2.12-java17
# TODO: Add other tools (vi, net-tools, etc.)

RUN wget -P /opt/flink/lib/ https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-kafka/3.2.0-1.19/flink-connector-kafka-3.2.0-1.19.jar; \
    wget -P /opt/flink/lib/ https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-avro-confluent-registry/1.19.0/flink-sql-avro-confluent-registry-1.19.0.jar; \
    wget -P /opt/flink/lib/ https://repo.maven.apache.org/maven2/org/apache/kafka/kafka-clients/3.4.0/kafka-clients-3.4.0.jar; \
    wget -P /opt/flink/lib/ https://repo.maven.apache.org/maven2/org/apache/flink/flink-json/1.19.0/flink-json-1.19.0.jar; \
    wget -P /opt/flink/lib/ https://repo.maven.apache.org/maven2/org/apache/flink/flink-csv/1.19.0/flink-csv-1.19.0.jar; \
    wget -P /opt/flink/lib/ https://github.com/knaufk/flink-faker/releases/download/v0.5.2/flink-faker-0.5.2.jar;

RUN chown -R flink:flink /opt/flink/lib
```