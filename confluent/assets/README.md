NOTHING IN HERE IS SENSITIVE

This is primarily a reorganized set of files from https://github.com/confluentinc/confluent-kubernetes-examples, useful for scripting

Consists of:
* certs:
    * Static Test CA private key + public certificate (can be used to generate certificates for MRC so clusters share a CA)
    * Static MDS private/public key
* cfssl: various CFSSL JSON templates to generate certificates
* creds: sample cred files
* openldap: OpenLDAP helm chart