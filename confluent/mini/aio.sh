#!/bin/bash

# Simple shell script that installs all of CP on a single (Ubuntu) VM, using apt and systemd
if [[ $# -gt 0 ]]; then
	VERSION=$1
else
	VERSION=7.5
fi

sudo apt-get update && \
  sudo apt-get install openjdk-17-jre-headless -y && \
  wget -qO - https://packages.confluent.io/deb/${VERSION}/archive.key | sudo apt-key add - && \
  sudo add-apt-repository "deb [arch=amd64] https://packages.confluent.io/deb/${VERSION} stable main" && \
  sudo add-apt-repository "deb https://packages.confluent.io/clients/deb $(lsb_release -cs) main" && \
  sudo apt-get update && sudo apt-get install confluent-platform -y

### Enable and set up

CUSTOM=/etc/confluent
sudo mkdir -p ${CUSTOM}

sudo tee ${CUSTOM}/confluent-zookeeper.replacement <<-'EOF'
EOF

sudo tee ${CUSTOM}/confluent-server.replacement <<-'EOF'
EOF

sudo tee ${CUSTOM}/confluent-schema-registry.replacement <<-'EOF'
EOF

sudo tee ${CUSTOM}/confluent-kafka-connect.replacement <<-'EOF'
key.converter.schema.registry.url=http://localhost:8081
key.converter=io.confluent.connect.avro.AvroConverter

value.converter.schema.registry.url=http://localhost:8081
value.converter=io.confluent.connect.avro.AvroConverter
EOF

sudo tee ${CUSTOM}/confluent-ksqldb.replacement <<-'EOF'
ksql.schema.registry.url=http://localhost:8081
EOF

sudo tee ${CUSTOM}/confluent-control-center.replacement <<-'EOF'
bootstrap.servers=localhost:9092
confluent.controlcenter.mode.enable=management
confluent.controlcenter.command.topic.replication=1
confluent.controlcenter.id=1
confluent.controlcenter.internal.topics.partitions=2
confluent.controlcenter.internal.topics.replication=1
confluent.controlcenter.schema.registry.url=http://localhost:8081
confluent.controlcenter.connect.connect-default.cluster=http://localhost:8083
confluent.controlcenter.ksql.ksqlDB.url=http://localhost:8088
confluent.controlcenter.streams.cprest.url=http://localhost:8090
confluent.controlcenter.ui.autoupdate.enable=false
confluent.metrics.topic.replication=1
confluent.monitoring.interceptor.topic.partitions=2
confluent.monitoring.interceptor.topic.replication=1
EOF

for SERVICE in \
  confluent-zookeeper \
  confluent-server \
  confluent-schema-registry \
  confluent-kafka-connect \
  confluent-ksqldb \
  confluent-control-center;
  do
    echo ${SERVICE};
    sudo mkdir -p /etc/systemd/system/${SERVICE}.service.d
    COMMAND=$(systemctl cat ${SERVICE} | awk -F'[= ]' '/ExecStart/ {print $2; exit;}')
    PROPERTY_FILE=$(systemctl cat ${SERVICE} | awk '/ExecStart/ {print $NF; exit;}')
    NEW_PROPERTY_FILE=${CUSTOM}/${SERVICE}.properties
    sudo cp -npv ${PROPERTY_FILE} ${NEW_PROPERTY_FILE}

sudo tee /etc/systemd/system/${SERVICE}.service.d/override.conf <<-EOF
[Service]
ExecStart=
ExecStart=${COMMAND} ${NEW_PROPERTY_FILE}
EOF

  for REPLACEMENT in $(cat ${CUSTOM}/${SERVICE}.replacement)
  do
    KEY=${REPLACEMENT%%=*}
    VALUE=${REPLACEMENT#*=}
    sudo sed -i -n -e '/^'"${KEY}"'=/!p' -e '$a'"${KEY}=${VALUE}" /etc/confluent/${SERVICE}.properties
  done

done

sudo systemctl daemon-reload

for SERVICE in \
  confluent-zookeeper \
  confluent-server \
  confluent-schema-registry \
  confluent-kafka-connect \
  confluent-ksqldb \
  confluent-control-center;
  do
    echo ${SERVICE};
    sudo systemctl enable ${SERVICE};
    sudo systemctl start ${SERVICE};
done