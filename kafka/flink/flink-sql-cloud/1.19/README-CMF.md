
## Prerequisites

If you don't already have a Kubernetes cluster, but do have acesss to cloud VM instance (i.e. EC2) with at least 4 cores / 16 GB, on Ubuntu (22.04)


TODO:
* Document how to build JAR and upload to S3
* Docuemnt how to attach credentials to job(s)
* Turn this into an actual document rather than a list of manifests
* Document how to create the custom image (adds S3 Presto)
* Document environment setup

Install K3s + Helm

```bash
curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE=644 sh -s - --disable=traefik \
  && mkdir -p ~/.kube \
  && cp /etc/rancher/k3s/k3s.yaml ~/.kube/config \
  && echo "alias k=kubectl" >> .bashrc \
  && echo "alias kc='kubectl -n confluent'" >> .bashrc \
  && alias k=kubectl \
  && alias kc='kubectl -n confluent' \
&& curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \
  && chmod 700 get_helm.sh \
  && ./get_helm.sh \
```

(Optional) Install several useful utilities

```bash
sudo add-apt-repository -y ppa:rmescandon/yq \
    && sudo apt-get update \
    && sudo apt-get install -y \
      golang-cfssl \
      yq \
      jq
```

(Optional) Make CP packages available locally

```bash
# Also from home directory
curl -O http://packages.confluent.io/archive/7.9/confluent-7.9.1.tar.gz && \
    tar -xzvf confluent-7.9.1.tar.gz && \
    ln -s confluent-7.9.1 confluent && \
    echo 'export PATH=${PATH}:/home/ubuntu/confluent/bin' >> ~/.bashrc && \
    export PATH=${PATH}:/home/ubuntu/confluent/bin
```

## Install Flink Kubernetes Operator (FKO), Confluent Manager for Flink (CMF), Confluent for Kubernetes (CFK)

Set up Helm repo (requires Helm + K8s)

```bash
helm repo add confluentinc https://packages.confluent.io/helm
helm repo update
```

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
            secretName: flink-properties
```


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
      # cpu: "0.5"
      memory: 1024m
  taskManager:
    resource:
      cpu: "1"
      # cpu: "0.5"
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
            secretName: flink-properties
```

`Dockerfile` for `justinrlee/cp-flink:1.19.2-cp2-java17-s3-10`
```Dockerfile
FROM confluentinc/cp-flink:1.19.2-cp2-java17

# https://repo1.maven.org/maven2/org/apache/flink/flink-s3-fs-presto/1.19.2/flink-s3-fs-presto-1.19.2.jar/
COPY --chown=flink:root flink-s3-fs-presto-1.19.2.jar /opt/flink/plugins/s3-fs-presto/
```