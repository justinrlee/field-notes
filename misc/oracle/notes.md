Heavily inspired by https://github.com/ora0600/confluent-new-cdc-connector

Before running, export the environment variable ORACLE_HOSTNAME with a the hostname for Oracle, and verify that this gets you into the Oracle database:

```bash
export ORACLE_HOSTNAME=10.10.10.10
sqlplus sys/confluent123@//${ORACLE_HOSTNAME}:1521/ORCLCDB
```