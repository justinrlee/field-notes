FROM openjdk:11-buster

RUN apt-get update \
  && apt-get install -y \
    kafkacat \
    vim \
    curl \
    telnet \
    netcat

# curl -O http://packages.confluent.io/archive/7.1/confluent-7.1.0.tar.gz
ADD confluent-7.1.0.tar.gz /opt

# curl -O https://s3-us-west-2.amazonaws.com/confluent.cloud/confluent-cli/archives/latest/confluent_latest_linux_amd64.tar.gz
RUN confluent_latest_linux_amd64.tar.gz /opt

ENV PATH="/opt/confluent-7.1.0/bin"