# Part 4: Run the JAR via CMF

Install CMF

```bash
helm upgrade --install cmf \
    confluentinc/confluent-manager-for-apache-flink \
    --namespace default
```

Install CFK

```bash
helm upgrade --install confluent-operator \
  confluentinc/confluent-for-kubernetes \
  --namespace default \
  --set enableCMFDay2Ops=true
```

Create a CMF Rest Class (describes how CFK talks to CMF)

```yaml
apiVersion: platform.confluent.io/v1beta1
kind: CMFRestClass
metadata:
  name: default
  namespace: default
spec:
  cmfRest:
    endpoint: http://cmf-service.default.svc.cluster.local
```

## Create actual apps

```yaml
apiVersion: platform.confluent.io/v1beta1
kind: FlinkEnvironment
metadata:
  name: default
  namespace: default
spec:
  kubernetesNamespace: default
  flinkApplicationDefaults:
    metadata:
      labels:
        "justinrlee.io/owner-email": "jlee@confluent.io"
    spec:
      flinkConfiguration:
        taskmanager.numberOfTaskSlots: "2"
        rest.profiling.enabled": "true"
  cmfRestClassRef:
    name: default
    namespace: default
```

FlinkApplication

```yaml
apiVersion: platform.confluent.io/v1beta1
kind: FlinkApplication
metadata:
  name: rekey-products
  namespace: default
spec:
  cmfRestClassRef:
     name: default
     namespace: default
  image: "justinrlee/cp-flink:1.19.2-cp2-java17-s3-10"
  flinkEnvironment: default
  flinkVersion: v1_19
  flinkConfiguration:
    taskmanager.numberOfTaskSlots: "2"
    user.artifacts.raw-http-enabled: "true"
  serviceAccount: flink
  jobManager:
    resource:
      cpu: "1"
      memory: 1024m
  taskManager:
    resource:
      cpu: "1"
      memory: 1024m
  mode: native                       # -- default
  job:
    jarURI: s3://justin-confluent-apse1/flink-sql-cloud-1.19.jar
    entryClass: io.justinrlee.kafka.flink.RekeyProducts
      # jarURI: s3://justin-confluent-apse1/flink-sql-cloud-1.19.jar
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
