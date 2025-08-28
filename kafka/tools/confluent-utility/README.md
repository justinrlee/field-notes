
# **This has been moved to [justinrlee/confluent-utility](https://github.com/justinrlee/confluent-utility)**

# confluent-utility

justinrlee/confluent-utility is a 'kitchen sink' Docker image that has a bunch of tools for interacting with Kafka and Confluent.

No guarantees or warranties provided.

Provides the following:
* Clients:
  * kafka-X CLI tools (from Confluent package)
  * confluent CLI
  * kcat (formerly kafkacat)
  * vault
  * kubectl
  * aws
* Network tools:
  * ping
  * dig
  * curl
  * telnet
  * nslookup
* Misc:
  * jq
  * yq
  * unzip
  * vim
  * less

## Use (kubernetes)

Sample Kubernetes manifest to run the utility in a Kubernetes cluster:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: confluent-utility
  namespace: confluent
spec:
  selector:
    matchLabels:
      app: confluent-utility
  serviceName: "confluent-utility"
  replicas: 1 # by default is 1
  template:
    metadata:
      labels:
        app: confluent-utility
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: utility
        image: justinrlee/confluent-utility:latest
```

Once running, you can exec in with:

```bash
kubectl -n confluent exec -it confluent-utility -- bash
```

## Build
Build system for confluent-utility

Usually run on an x86-64 Ubuntu EC2 instance. Does a multi-arch (amd64 and arm64) build, but you need to set up multiarch:

```bash
sudo apt-get update -y && \
  sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
  && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
  && echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null \
  && sudo apt-get update -y \
  && sudo apt-get install -y docker-ce docker-ce-cli docker-compose containerd.io \
  && sudo usermod -aG docker ubuntu

sudo apt-get install -y \
  qemu-user-static \
  binfmt-support
```

Once Docker is installed, log out and log back in (to inherit new permissions). Then do:

```bash
# Replace with your username
docker login -u justinrlee
```

Local build only (will create different tag for each architecture)

```bash
bash build.sh
```

Create and push multi-arch image

```bash
bash push.sh
```