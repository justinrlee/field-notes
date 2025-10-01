```bash
docker compose up


docker exec postgres bash -c "psql -U myuser -d postgres -c 'SELECT * FROM CUSTOMERS'"


log "Adding an element to the table"

docker exec postgres psql -U myuser -d postgres -c "insert into customers (id, first_name, last_name, email, gender, comments) values (21, 'Bernardo', 'Dudman', 'bdudmanb@lulu.com', 'Male', 'Robust bandwidth-monitored budgetary management');"

log "Show content of CUSTOMERS table:"
docker exec postgres bash -c "psql -U myuser -d postgres -c 'SELECT * FROM CUSTOMERS'"
```


```bash
tee kafka.txt <<-EOF
username=D623ZASJYJC6MRSP
password=W78x3Urx64Iol16hBJLxaDq/cU77dk49ozD1Dp5mm8rUDaFHCBSlryJPxY6+6ZSe
EOF

tee sr.txt <<-EOF
username=KSFKMPFKGKO7XBZ6
password=46Gdhp6nXQTSxhGCfvXssg3HNt2AbeKJAimLJ5HSgXt8EDQQL5tVwsRAZOYVYpus
EOF

kubectl -n confluent create secret generic ccloud-credentials --from-file=plain.txt=kafka.txt

kubectl -n confluent create secret generic ccloud-sr-credentials --from-file=basic.txt=sr.txt
```

```bash
psql -h 10.0.1.37 -p 5432 -U myuser postgres
```

```json
{
  "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
  "tasks.max": "1",
  "database.hostname": "10.0.1.37",
  "database.port": "5432",
  "database.user": "myuser",
  "database.password": "mypassword",
  "database.dbname" : "postgres",
  "database.server.name": "asgard",
  "transforms": "addTopicSuffix",
  "transforms.addTopicSuffix.type":"org.apache.kafka.connect.transforms.RegexRouter",
  "transforms.addTopicSuffix.regex":"(.*)",
  "transforms.addTopicSuffix.replacement":"$1-raw"
}
```

```bash



curl \
  -X PUT \
  -H 'content-type:application/json' \
  -d @test.json \
  http://connect:8083/connectors/pg/config
```


```bash
v=0
tee ${v}.json <<-EOF
{
  "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
  "tasks.max": "1",
  "database.hostname": "10.0.1.37",
  "database.port": "5432",
  "database.user": "myuser",
  "database.password": "mypassword",
  "database.dbname" : "postgres",
  "database.server.name": "asgard",
  "transforms": "addTopicSuffix",
  "transforms.addTopicSuffix.type":"org.apache.kafka.connect.transforms.RegexRouter",
  "transforms.addTopicSuffix.regex":"(.*)",
  "transforms.addTopicSuffix.replacement":"\$1-${v}-raw"
}
EOF

curl \
  -X PUT \
  -H 'content-type:application/json' \
  -d @${v}.json \
  http://connect:8083/connectors/pg-${v}/config
```


```bash
v=3
tee ${v}.json <<-EOF
{
  "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
  "tasks.max": "1",
  "database.hostname": "10.0.1.37",
  "database.port": "5432",
  "database.user": "myuser",
  "database.password": "mypassword",
  "database.dbname" : "postgres",
  "database.server.name": "asgard",
  "transforms": "addTopicSuffix",
  "transforms.addTopicSuffix.type":"org.apache.kafka.connect.transforms.RegexRouter",
  "transforms.addTopicSuffix.regex":"(.*)",
  "transforms.addTopicSuffix.replacement":"\$1-${v}-raw"
}
EOF

curl \
  -X PUT \
  -H 'content-type:application/json' \
  -d @${v}.json \
  http://connect:8083/connectors/pg-${v}/config
```

Generated connect config:
```conf
admin.bootstrap.servers=pkc-lzvrd.us-west4.gcp.confluent.cloud:9092
admin.sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="${file:/mnt/secrets/ccloud-credentials/plain.txt:username}" password="${file:/mnt/secrets/ccloud-credentials/plain.txt:password}";
admin.sasl.mechanism=PLAIN
admin.security.protocol=SASL_SSL
bootstrap.servers=pkc-lzvrd.us-west4.gcp.confluent.cloud:9092
config.providers=file
config.providers.file.class=org.apache.kafka.common.config.provider.FileConfigProvider
config.storage.replication.factor=3
config.storage.topic=confluent.connect-configs
confluent.topic.replication.factor=3
consumer.bootstrap.servers=pkc-lzvrd.us-west4.gcp.confluent.cloud:9092
consumer.sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="${file:/mnt/secrets/ccloud-credentials/plain.txt:username}" password="${file:/mnt/secrets/ccloud-credentials/plain.txt:password}";
consumer.sasl.mechanism=PLAIN
consumer.security.protocol=SASL_SSL
group.id=confluent.connect
key.converter=io.confluent.connect.avro.AvroConverter
key.converter.schema.registry.basic.auth.credentials.source=USER_INFO
key.converter.schema.registry.basic.auth.user.info=${file:/mnt/secrets/ccloud-sr-credentials/basic.txt:username}:${file:/mnt/secrets/ccloud-sr-credentials/basic.txt:password}
key.converter.schema.registry.url=https://psrc-gk071.us-east-2.aws.confluent.cloud
key.converter.schemas.enable=false
listeners=http://0.0.0.0:8083
offset.flush.interval.ms=10000
offset.storage.replication.factor=3
offset.storage.topic=confluent.connect-offsets
plugin.path=/usr/share/java,/usr/share/confluent-hub-components,/mnt/plugins
producer.bootstrap.servers=pkc-lzvrd.us-west4.gcp.confluent.cloud:9092
producer.sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="${file:/mnt/secrets/ccloud-credentials/plain.txt:username}" password="${file:/mnt/secrets/ccloud-credentials/plain.txt:password}";
producer.sasl.mechanism=PLAIN
producer.security.protocol=SASL_SSL
request.timeout.ms=20000
rest.advertised.listener=http
retry.backoff.ms=500
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="${file:/mnt/secrets/ccloud-credentials/plain.txt:username}" password="${file:/mnt/secrets/ccloud-credentials/plain.txt:password}";
sasl.mechanism=PLAIN
security.protocol=SASL_SSL
status.storage.replication.factor=3
status.storage.topic=confluent.connect-status
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.basic.auth.credentials.source=USER_INFO
value.converter.schema.registry.basic.auth.user.info=${file:/mnt/secrets/ccloud-sr-credentials/basic.txt:username}:${file:/mnt/secrets/ccloud-sr-credentials/basic.txt:password}
value.converter.schema.registry.url=https://psrc-gk071.us-east-2.aws.confluent.cloud
value.converter.schemas.enable=false
rest.advertised.host.name=connect-0.connect.confluent.svc.cluster.local
rest.advertised.host.port=8083
```

Note: all converter stuff is used in connect