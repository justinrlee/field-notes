# Part 3: Run the JAR on Kubernetes

We have to make the JAR accessible to Flink, both the client and the jobmanager/taskmanager.

Three ways to do this:
* Bake it into an image
* Host it on an HTTP endpoint
* Host it on S3 (requires modifying Confluent-provided Docker image to support S3)

## Install FKO

Install Certificate Manager (used by FKO)

```bash
kubectl create -f https://github.com/jetstack/cert-manager/releases/download/v1.8.2/cert-manager.yaml
```

Wait for cert manager to be fully installed (TODO: Document)

Install Confluent's distribution of FKO

```bash
helm upgrade --install cp-flink-kubernetes-operator \
    confluentinc/flink-kubernetes-operator
    --namespace default
```

## Create credential file

```conf
# client.properties
kafka.group.id=test-app
kafka.bootstrap.servers=pkc-312o0.ap-southeast-1.aws.confluent.cloud:9092
kafka.api.key=xxx
kafka.api.secret=yyy

schema.registry.url=https://psrc-1dx3ljw.ap-southeast-1.aws.confluent.cloud
schema.registry.api.key=xxx
schema.registry.api.secret=yyy
```

Create Kubernetes secret with the credential file in it

```bash
kubectl --namespace default create secret generic flink-client-properties --from-file=client.properties=client.properties
```

## Create manifest

Sample FKO FlinkDeployment manifest

```yaml
apiVersion: flink.apache.org/v1beta1
kind: FlinkDeployment
metadata:
  name: enrich-orders
spec:
  image: "justinrlee/cp-flink:1.19.2-cp2-java17-s3-10"
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
      memory: "4096m"
      cpu: 2
  job:
    jarURI: local:///opt/flink-sql-cloud-1.19.jar
    # jarURI: http://10.10.10.10:9000/flink-sql-cloud-1.19.jar
    # jarURI: s3://justin-confluent-apse1/flink-sql-cloud-1.19.jar
    entryClass: io.justinrlee.kafka.flink.EnrichOrders
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
            secretName: flink-client-properties
```

TODO: expand docs