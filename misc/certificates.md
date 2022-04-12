## Create CA Key and self-signed CA certificate:
```bash
export CERT_DIR=${PWD}

export CA_KEY_PASSWORD=confluent

export CA_CN="Justin Internal CA"

openssl req \
  -x509 \
  -sha256 \
  -newkey \
  rsa:4096 \
  -keyout ${CERT_DIR}/ca.key \
  -out ${CERT_DIR}/ca.crt \
  -days 356 \
  -passout pass:${CA_KEY_PASSWORD} \
  -subj "/CN=${CA_CN}"
```

(add `-nodes` and remove `-passout` to do unencrypted)

## Create Server Key and Cert (with CN and multiple SANs):
```bash
export CERT_DIR=${PWD}
export FILENAME=server

export CA_KEY_PASSWORD=confluent
export KEY_PASSWORD=confluent

export CN="test.server.internal"
export PUBLIC_DNS=test.server.external
export PRIVATE_DNS=test.server.internal
export PUBLIC_IP=1.2.3.4
export PRIVATE_IP=10.0.0.10

openssl req \
  -new \
  -newkey \
  rsa:4096 \
  -keyout ${CERT_DIR}/${FILENAME}.key \
  -out ${CERT_DIR}/${FILENAME}.csr \
  -passout pass:${KEY_PASSWORD} \
  -subj "/CN=${CN}"


tee ${CERT_DIR}/${FILENAME}.ext <<EOF
subjectAltName = @alt_names
[alt_names]
DNS.1=${PUBLIC_DNS}
DNS.2=${PRIVATE_DNS}
DNS.3=localhost
IP.1=${PUBLIC_IP}
IP.2=${PRIVATE_IP}
IP.3=127.0.0.1
EOF

openssl x509 \
  -req \
  -sha256 \
  -days 365 \
  -in ${CERT_DIR}/${FILENAME}.csr \
  -CA ${CERT_DIR}/ca.crt \
  -CAkey ${CERT_DIR}/ca.key \
  -extfile ${CERT_DIR}/${FILENAME}.ext \
  -passin pass:${CA_KEY_PASSWORD} \
  -CAcreateserial \
  -out ${CERT_DIR}/${FILENAME}.crt
```

Add/update/modify SAN file as applicable for various SAN entries

## Create Client Key and Cert (with CN, no SAN):
```bash
export CERT_DIR=${PWD}
export FILENAME=client

export CA_KEY_PASSWORD=confluent
export KEY_PASSWORD=confluent

export CN="client"

openssl req \
  -new \
  -newkey \
  rsa:4096 \
  -keyout ${CERT_DIR}/${FILENAME}.key \
  -out ${CERT_DIR}/${FILENAME}.csr \
  -passout pass:${KEY_PASSWORD} \
  -subj "/CN=${CN}"


openssl x509 \
  -req \
  -sha256 \
  -days 365 \
  -in ${CERT_DIR}/${FILENAME}.csr \
  -CA ${CERT_DIR}/ca.crt \
  -CAkey ${CERT_DIR}/ca.key \
  -passin pass:${CA_KEY_PASSWORD} \
  -CAcreateserial \
  -out ${CERT_DIR}/${FILENAME}.crt
```

## Create JKS truststore (CA only) from CA certificate
```bash
export CERT_DIR=${PWD}
export FILENAME=client

export KEY_PASSWORD=confluent

keytool -importcert \
    -keystore ${CERT_DIR}/${FILENAME}.truststore.jks \
    -alias CARoot \
    -file ${CERT_DIR}/ca.crt \
    -storepass ${KEY_PASSWORD} \
    -noprompt
```

## Create JKS keystore (Certificate, Key, and CA)
```bash
export CERT_DIR=${PWD}
export FILENAME=client

export KEY_PASSWORD=confluent

openssl pkcs12 -export \
    -in ${CERT_DIR}/${FILENAME}.crt \
    -inkey ${CERT_DIR}/${FILENAME}.key \
    -out ${CERT_DIR}/${FILENAME}.keystore.jks \
    -name ${FILENAME} \
    -CAfile ${CERT_DIR}/ca.crt \
    -caname CARoot \
    -passin pass:${KEY_PASSWORD} \
    -password pass:${KEY_PASSWORD}

keytool -importcert \
    -keystore ${CERT_DIR}/${FILENAME}.keystore.jks \
    -alias CARoot \
    -file ${CERT_DIR}/ca.crt \
    -storepass ${KEY_PASSWORD} \
    -noprompt
```