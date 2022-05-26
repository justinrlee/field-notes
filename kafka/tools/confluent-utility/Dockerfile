FROM openjdk:11-buster

RUN apt-get update \
  && apt-get install -y \
    kafkacat \
    vim \
    curl \
    telnet \
    netcat \
    less \
    ldap-utils \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

# curl -O http://packages.confluent.io/archive/7.1/confluent-community-7.1.1.tar.gz
ADD confluent-community-7.1.1.tar.gz /opt

# curl -O https://s3-us-west-2.amazonaws.com/confluent.cloud/confluent-cli/archives/latest/confluent_latest_linux_amd64.tar.gz
ADD confluent_latest_linux_amd64.tar.gz /opt

# curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
ADD awscliv2.zip /opt

RUN unzip /opt/awscliv2.zip && /aws/install && rm -r /aws

RUN ln -s /usr/bin/kafkacat /usr/bin/kcat

ENV PATH="${PATH}:/opt/confluent-7.1.1/bin:/opt/confluent"

CMD ["tail", "-f", "/dev/null"]