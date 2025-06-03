## Background

A Kafka cluster consists of a cluster of Kafka brokers that each host some subset of the total data in the Kafka cluster. Because the data is distributed across the brokers, clients need to be able to communicate with all brokers in the cluster.

_This document is from the perspective of a single Kafka client that talks to a single set of Kafka listeners, regardless of how many listeners there may be_

The Kafka client protocol follows this high-level workflow:
* The Kafka client is configured with one or more brokers (called `bootstrap.servers`) to bootstrap the client session
* The Kafka client will connect to one of the bootstrap servers, using provided connection settings, and request information about all of the brokers in the cluster ("metadata request" and corresponding "metadata response")
* For subsequent requests to the cluster, the client will connect directly to the individual brokers as necessary
* As part of the Kafka protocol, clients will periodically receive updated metadata to account for broker changes

A Kafka client needs the following information to connect to a Kafka cluster:

* Bootstrap servers (a set of hostname/port combinations), used to bootstrap the connection.
* If the cluster listener requires encryption, encryption settings. There are three options:
    * Unencrypted (plaintext)
    * Encrypted (TLS)
    * Encrypted, with client certificate ("mutual TLS" or mTLS)†
* If the cluster listener requires authentication, credentials. There are approximately five†† options, provided via the SASL protocol
    * No authentication
    * PLAIN (username/password)
    * SCRAM (username/password with a slightly different protocol)
    * GSSAPI (Kerberos keytab)
    * OAUTHBEARER
    * IAM

† If you're using mTLS, then mTLS covers both encryption and authorization and you don't generally use SASL, unless you have a listener configured to support both mTLS and SASL (see KIP-684).
†† IAM is not technically part of the Apache Kafka protocol, but is provided as an add-on by Amazon

The above options results in approximately these valid configuration modes:
* Unencrypted and unauthenticated
* Unecrypted with PLAIN (SASL_PLAINTEXT w/ SASL mechanism PLAIN)
* Unencrypted with SCRAM (SASL_PLAINTEXT w/ SASL mechanism SCRAM-SHA-256 or SCRAM-SHA-512)
* Unencrypted with GSSAPI (SASL_PLAINTEXT w/ SASL mechanism GSSAPI)
* Unencrypted with OAUTHBEARER (SASL_PLAINTEXT w/ SASL mechanism OAUTHBEARER)
* Encrypted but unauthenticated (SSL)
* Encrypted with PLAIN (SASL_SSL w/ SASL mechanism PLAIN)
* Encrypted with SCRAM (SASL_SSL w/ SASL SCRAM)
* Encrypted with GSSAPI 
* Encrypted with OAUTHBEARER
* Encrypted with IAM
* Encrypted and authenticated with mTLS (mTLS)

The best way "native" I've found to test connectivity is with the Kafka Java libraries, which assume you have the Kafka package and a Java runtime installed. Kafka binary packages can be downloaded from the Apache Kafka website (https://kafka.apache.org/downloads); you can also use the Confluent distributions of the same (https://docs.confluent.io/platform/current/installation/installing_cp/zip-tar.html).

The Kafka package comes with the Java-based CLI tool `kafka-broker-api-versions`, which does several things:

* Initiates a connection with the provided client configuration to the provided bootstrap server
* Requests a list of supported APIs on the provided bootstrap server
* Requests a list of other brokers in the cluster
* Initiates a request to each of the brokers in the cluster

Because it connects to all the brokers in the cluster, it is very handy for troubleshooting connectivity issues (e.g. it will tell you which brokers it is able to successfully connect to).

The Kafka (Java) client configuration consists of a set of key-value pairs that encapsulate all of the above. For example, you may have a properties file that looks like this (this works with Confluent Cloud):

```conf
# client.properties
bootstrap.servers=pkc-xyc123.ap-southeast-1.aws.confluent.cloud:9092
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="abc" password="def";
```

This configuration provides:
* The bootstrap server for the initial client connection
* security.protocol of SASL_SSL (which means SASL protocol, encrypted with SSL)
* sasl.mechanism of PLAIN (username/password)
* sasl configuration using the PlainLoginModule with the provided username and password

Assuming the client properties file is `client.properties`, you could use this by running (from the kafka package directory; if you are using the Confluent package, the command does not have `.sh` at the end.)

```bash
./kafka_2.13-3.9.0/bin/kafka-broker-api-versions.sh --bootstrap-server pkc-xyc123.ap-southeast-1.aws.confluent.cloud:9092 --command-config client.properties
```

If all goes well, this will return an output with a big list of supported API versions, from each broker.

If all does not go well, try turning on DEBUG (edit `./etc/tools-log4j.properties` in the package and change WARN to INFO or DEBUG, then run again)

_Note that even though the bootstrap server is provided in the properties file, it also must be provided to the CLI client directly._

### Sample client configuration files for different security configurations

Unencrypted and unauthenticated

```conf
bootstrap.servers=localhost:9092
```

Unecrypted with PLAIN

```conf
bootstrap.servers=localhost:9092
security.protocol=SASL_PLAINTEXT
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="abc" password="def";
```

Unencrypted with SCRAM

```conf
bootstrap.servers=localhost:9092
security.protocol=SASL_PLAINTEXT
# Check with your Kafka administrator which SCRAM type you're using
# sasl.mechanism=SCRAM-SHA-256
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="abc" password="def";
```

Unencrypted with GSSAPI

```conf
bootstrap.servers=localhost:9092
security.protocol=SASL_PLAINTEXT
sasl.mechanism=GSSAPI
sasl.kerberos.service.name=principal
sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required \
  useKeyTab=true \
  storeKey=true \
  keyTab="/path/to/keytab.keytab" \
  principal="principal/sub@KERBEROS.DOMAIN";
```

Unencrypted with OAUTHBEARER

```conf
bootstrap.servers=localhost:9092
security.protocol=SASL_PLAINTEXT
sasl.mechanism=OAUTHBEARER
sasl.oauthbearer.token.endpoint.url=https://myidp.example.com/oauth2/default/v1/token
sasl.login.callback.handler.class=org.apache.kafka.common.security.oauthbearer.secured.OAuthBearerLoginCallbackHandler
# Settings here will depend on your OAuth2.0/OIDC provider and cluster configuration
sasl.jaas.config=org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required \
    clientId='<client-id>'
    scope='<requested-scope>'
    clientSecret='<client-secret>'
    extension_logicalCluster='<cluster-id>'
    extension_identityPoolId='<pool-id>';
```

Encrypted but unauthenticated

```conf
bootstrap.servers=localhost:9092
security.protocol=SSL
# Truststore only has to be provided if you Kafka cluster has certificates signed by a custom CA
ssl.truststore.location=/etc/confluent/certs/kafka.server.truststore.jks
ssl.truststore.password=confluent
```

Encrypted with PLAIN

```conf
bootstrap.servers=localhost:9092
security.protocol=SASL_SSL
# Truststore only has to be provided if you Kafka cluster has certificates signed by a custom CA
ssl.truststore.location=/etc/confluent/certs/kafka.server.truststore.jks
ssl.truststore.password=confluent
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="abc" password="def";
```

Encrypted with SCRAM

```conf
bootstrap.servers=localhost:9092
security.protocol=SASL_SSL
# Truststore only has to be provided if you Kafka cluster has certificates signed by a custom CA
ssl.truststore.location=/etc/confluent/certs/kafka.server.truststore.jks
ssl.truststore.password=confluent
# Check with your Kafka administrator which SCRAM type you're using
# sasl.mechanism=SCRAM-SHA-256
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="abc" password="def";
```

Encrypted with GSSAPI

```conf
bootstrap.servers=localhost:9092
security.protocol=SASL_SSL
# Truststore only has to be provided if you Kafka cluster has certificates signed by a custom CA
ssl.truststore.location=/etc/confluent/certs/kafka.server.truststore.jks
ssl.truststore.password=confluent
sasl.mechanism=GSSAPI
sasl.kerberos.service.name=principal
sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required \
  useKeyTab=true \
  storeKey=true \
  keyTab="/path/to/keytab.keytab" \
  principal="principal/sub@KERBEROS.DOMAIN";
```

Encrypted with OAUTHBEARER

```conf
bootstrap.servers=localhost:9092
security.protocol=SASL_SSL
# Truststore only has to be provided if you Kafka cluster has certificates signed by a custom CA
ssl.truststore.location=/etc/confluent/certs/kafka.server.truststore.jks
ssl.truststore.password=confluent
sasl.mechanism=OAUTHBEARER
sasl.oauthbearer.token.endpoint.url=https://myidp.example.com/oauth2/default/v1/token
sasl.login.callback.handler.class=org.apache.kafka.common.security.oauthbearer.secured.OAuthBearerLoginCallbackHandler
# Settings here will depend on your OAuth2.0/OIDC provider and cluster configuration
sasl.jaas.config=org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required \
    clientId='<client-id>'
    scope='<requested-scope>'
    clientSecret='<client-secret>'
    extension_logicalCluster='<cluster-id>'
    extension_identityPoolId='<pool-id>';
```

Encrypted with IAM

TBD

Encrypted and authenticated with mTLS (mTLS)

```conf
bootstrap.servers=localhost:9092
security.protocol=SSL
# truststore should include the CA for your cluster's certificate(s)
ssl.truststore.location=/etc/confluent/certs/kafka.server.truststore.jks
ssl.truststore.password=confluent
# keystore includes information about your client certificate
ssl.keystore.location=/etc/confluent/certs/kafka.server.keystore.jks
ssl.keystore.password=confluent
ssl.key.password=confluent
```
