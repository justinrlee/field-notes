# FROM openjdk:11-buster
FROM eclipse-temurin:17-jdk-focal

RUN apt-get update \
  && apt-get install -y \
    software-properties-common \
    kafkacat \
    vim \
    curl \
    telnet \
    netcat \
    less \
    ldap-utils \
    dnsutils \
    jq \
    unzip \
  && rm -rf /var/lib/apt/lists/*

# Separate command cause of the apt repo stuff
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys CC86BB64 \
    && add-apt-repository -y ppa:rmescandon/yq \
    && apt-get update \
    && apt install yq -y \
  && rm -rf /var/lib/apt/lists/*

# curl -O https://packages.confluent.io/archive/7.7/confluent-community-7.7.1.tar.gz
ADD confluent-community-7.7.1.tar.gz /opt

# curl -O https://s3-us-west-2.amazonaws.com/confluent.cloud/confluent-cli/archives/latest/confluent_latest_linux_amd64.tar.gz
ADD confluent_latest_linux_amd64.tar.gz /opt

# curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
ADD awscliv2.zip /opt

RUN unzip /opt/awscliv2.zip && /aws/install && rm -r /aws

RUN ln -s /usr/bin/kafkacat /usr/bin/kcat

ENV PATH="${PATH}:/opt/confluent-7.7.1/bin:/opt/confluent"

CMD ["tail", "-f", "/dev/null"]