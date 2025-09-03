#!/bin/bash

sqlplus sys/confluent123@//${ORACLE_HOSTNAME}:1521/ORCLCDB as sysdba @scripts/basic.sql

sqlplus sys/confluent123@//${ORACLE_HOSTNAME}:1521/ORCLCDB as sysdba @scripts/schema_create.sql

sqlplus ordermgmt/kafka@//${ORACLE_HOSTNAME}:1521/ORCLPDB1 @scripts/schema_ddl.sql
sqlplus ordermgmt/kafka@//${ORACLE_HOSTNAME}:1521/ORCLPDB1 @scripts/schema_load.sql

sqlplus c##cflt_xstream_capture/confluent123@//${ORACLE_HOSTNAME}:1521/ORCLCDB @scripts/start_capture.sql

sqlplus sys/confluent123@//${ORACLE_HOSTNAME}:1521/ORCLCDB as sysdba @scripts/orclcdc_readiness.sql c##cflt_xstream_capture c##cflt_xstream_client xout ORCLPDB1