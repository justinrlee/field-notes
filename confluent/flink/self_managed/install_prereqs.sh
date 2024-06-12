#!/bin/bash
# Shell script to install CP + OS Flink, on K3s, on an Ubuntu instance

JRE_VERSION=openjdk-17-jre-headless
SCALA_VERSION=2.12
CP_VERSION=7.6.1
FLINK_VERSION=1.19.0
FLINK_OPERATOR_VERSION=1.8.0
CERT_MANAGER_VERSION=v1.8.2

CP_MINOR=${CP_VERSION%%.[0-9]}

# Install Docker
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

# Install K3s + Helm
curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE=644 sh - \
  && mkdir -p ~/.kube \
  && cp /etc/rancher/k3s/k3s.yaml ~/.kube/config \
  && chmod 400 ~/.kube/config \
  && echo "alias k=kubectl" >> .bashrc \
  && echo "alias kc='kubectl -n confluent'" >> .bashrc \
  && alias k=kubectl \
  && alias kc='kubectl -n confluent' \
&& curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \
  && chmod 700 get_helm.sh \
  && ./get_helm.sh \

# Install Cert Manager
kubectl create -f https://github.com/jetstack/cert-manager/releases/download/${CERT_MANAGER_VERSION}/cert-manager.yaml


# Install Java
sudo apt-get update && \
  sudo apt-get install ${JRE_VERSION} -y

# Download Confluent Tarball
curl -O http://packages.confluent.io/archive/${CP_MINOR}/confluent-${CP_VERSION}.tar.gz && \
  tar -xzvf confluent-${CP_VERSION}.tar.gz && \
  ln -s confluent-${CP_VERSION} confluent && \
  echo 'export PATH=${PATH}:/home/ubuntu/confluent/bin' >> ~/.bashrc && \
  export PATH=${PATH}:/home/ubuntu/confluent/bin

# Download Flink Tarball
curl -LO https://dlcdn.apache.org/flink/flink-${FLINK_VERSION}/flink-${FLINK_VERSION}-bin-scala_${SCALA_VERSION}.tgz && \
  tar -xzvf flink-${FLINK_VERSION}-bin-scala_${SCALA_VERSION}.tgz && \
  ln -s flink-${FLINK_VERSION} flink && \
  echo 'export PATH=${PATH}:/home/ubuntu/flink/bin' >> ~/.bashrc && \
  export PATH=${PATH}:/home/ubuntu/flink/bin

echo "Waiting for Cert Manager Installation"
# Wait for Cert Manager
while [[ $(kubectl -n cert-manager get pod | grep webhook | grep '1/1' | grep 'Running' | wc -l) -ne 1 ]]; \
    do echo 'Waiting for Cert Manager Installation'; sleep 5; done

# Install Confluent Operator
helm repo add confluentinc https://packages.confluent.io/helm \
  && helm repo update \
  && helm search repo confluentinc -l \
  && kubectl create ns confluent \
  && helm upgrade --install confluent-for-kubernetes confluentinc/confluent-for-kubernetes --namespace confluent

# Install Flink Operator
helm repo add flink-operator-repo https://downloads.apache.org/flink/flink-kubernetes-operator-${FLINK_OPERATOR_VERSION}/ \
  && helm install flink-kubernetes-operator flink-operator-repo/flink-kubernetes-operator -namespace confluent