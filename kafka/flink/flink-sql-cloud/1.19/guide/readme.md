# Introduction to Flink SQL with Confluent Platform for Apache Flink

This guide will walk you building a simple Flink job that does the following:

* Is based on Apache Flink's SQL API (on top of the Table API)
* Interacts with topics in Confluent Cloud, using Avro messages and Confluent Cloud Schema Registry
* Uses Apache Flink 1.19
* Uses the Flink Table Connectors `kafka` and `upsert-kafka`
* Uses the Table API Format `avro-confluent` ([docs](https://nightlies.apache.org/flink/flink-docs-release-1.19/docs/connectors/table/formats/avro-confluent/))

We'll run the application logic several ways:

* Through the interactive Flink sql-client, against a local Flink cluster
* Through `flink run`, against a local Flink cluster
* Through Flink Kubernetes Operator (FKO), against a small local Kubernetes cluster
* Through Confluent for Kubernetes (CFK) and Confluent Manager for Flink (CMF), against a small local Kubernetes cluster.

# Prerequisites

To run this lab, you'll need the following:

* Access to a Confluent Cloud environment, with:
    * Kafka cluster (basic or standard is fine)
        * Kafka cluster bootstrap server
        * API Key and Secret
    * Schema registry
        * Schema Registry endpoint
        * API Key and Secret
    * Three Kafka topics for 'source' data:
        * `shoe-customers` (6 partitions)
        * `shoe-products` (6 partitions)
        * `shoe-orders` (6 partitions)
    * Two Kafka topics for 'interim' (rekeyed) data (Flink will not automatically create topics for you, but it will register schemas)
        * `shoe-customers-keyed`
        * `shoe-products-keyed`
    * One Kafka topic for enriched data (again, Flink will not create the underlying topic for you)
        * `shoe-orders-enriched`
    * Three fully-managed connectors, one for each source data topic (all configured with the "Avro" output record value format)
        * `shoe-customers`: "Shoe customers" quick start
        * `shoe-products`: "Shoes" quick start
        * `shoe-orders`: "Shoe orders" quick start

_TODO: document setting up Confluent Cloud environment._

* A cloud VM (preferably AWS EC2) with at least 4 cores and 16 GB of memory, with Ubuntu, with the ability to SSH in and some familiarity with the terminal (including a text editor)

_TODO: build a version of this that can be run from MacOS; for now this needs EC2._

# Overview

The high-level logic for this app is pretty simple (this lab is intended to teach tooling, not a deep dive on application logic).

See also: https://github.com/griga23/shoe-store (thanks Jan!)

We have three input topics:
* `shoe-customers` - list of customers of our shoe store. each has a customer id, and other information about the customer (name, email, etc.). customers may change their information.
    * think of this as a table with rows that may change
* `show-products` - list of products of our shoe store. each has a product id, and other information about the product (name, price, etc.)
    * think of this as a table with rows that may change
* `shoe-orders` - orders that are coming in. each has a timestamp, the customer id that made the order, and the product that they purchased
    * think of this as a stream of events

We will do three things with this data:
* Rekey the shoe-customers topic into another topic that is keyed by customer ID
* Rekey the shoe-products topic into another topic that is keyed by product ID'
* Do a three-way temporal join, so that each order is enriched by information about both the customer and the product, at the time of the order

# Part 0: Install tooling

On your EC2 instance, install the following:

Install K3s + Helm (and set up kubeconfig)

```bash
cd ~ && \
  curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE=644 sh -s - --disable=traefik && \
  mkdir -p ~/.kube && \
  cp /etc/rancher/k3s/k3s.yaml ~/.kube/config && \
  echo "alias k=kubectl" >> .bashrc && \
  echo "alias kc='kubectl -n confluent'" >> .bashrc && \
  alias k=kubectl && \
  alias kc='kubectl -n confluent' && \
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 && \
  chmod 700 get_helm.sh && \
  ./get_helm.sh
```

Install Java (JDK 17) and Maven

```bash
sudo apt-get update && \
sudo apt-get install -y \
    openjdk-17-jdk-headless \
    maven
```

Download and install Flink package, including CLI clients (and add to path)

```bash
# Link from https://www.apache.org/dyn/closer.lua/flink/flink-1.19.2/flink-1.19.2-bin-scala_2.12.tgz
curl -LO https://dlcdn.apache.org/flink/flink-1.19.2/flink-1.19.2-bin-scala_2.12.tgz && \
    tar -xzvf flink-1.19.2-bin-scala_2.12.tgz && \
    ln -s flink-1.19.2 flink && \
    echo 'export PATH=${PATH}:/home/ubuntu/flink/bin' >> ~/.bashrc && \
    export PATH=${PATH}:/home/ubuntu/flink/bin
```

(Optional) Install several useful utilities:
* cfssl (cloudfront SSL tool
* yq
* jq

```bash
sudo add-apt-repository -y ppa:rmescandon/yq \
    && sudo apt-get update \
    && sudo apt-get install -y \
      golang-cfssl \
      yq \
      jq
```

(Optional) Download and install Confluent Platform package, including CLI clients (and add to path)

```bash
# Also from home directory
cd ~ && \
curl -O http://packages.confluent.io/archive/7.9/confluent-7.9.1.tar.gz && \
    tar -xzvf confluent-7.9.1.tar.gz && \
    ln -s confluent-7.9.1 confluent && \
    echo 'export PATH=${PATH}:/home/ubuntu/confluent/bin' >> ~/.bashrc && \
    export PATH=${PATH}:/home/ubuntu/confluent/bin
```

Download Flink SQL JARs

```bash
cd ~
# Run from home directory
curl -LO https://packages.confluent.io/maven/io/confluent/flink/flink-sql-connector-kafka/3.3.0-1.19-cp1/flink-sql-connector-kafka-3.3.0-1.19-cp1.jar
curl -LO https://packages.confluent.io/maven/io/confluent/flink/flink-sql-avro-confluent-registry/1.19.2-cp2/flink-sql-avro-confluent-registry-1.19.2-cp2.jar
curl -LO https://packages.confluent.io/maven/org/apache/kafka/kafka-clients/7.9.1-ce/kafka-clients-7.9.1-ce.jar
```