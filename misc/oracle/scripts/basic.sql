------ Verify Archive Log is turned on
ALTER SESSION SET CONTAINER=cdb$root;
ARCHIVE LOG LIST

------ Enable Goldengate (?)
ALTER SESSION SET CONTAINER=cdb$root;
ALTER SYSTEM SET ENABLE_GOLDENGATE_REPLICATION=TRUE SCOPE=BOTH;
SHOW PARAMETER ENABLE_GOLDENGATE_REPLICATION;

------ Enable logging for both CDB$ROOT and ORCLPDB1
ALTER SESSION SET CONTAINER=cdb$root;
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
SELECT SUPPLEMENTAL_LOG_DATA_MIN, SUPPLEMENTAL_LOG_DATA_ALL FROM V$DATABASE;

ALTER SESSION SET CONTAINER=ORCLPDB1;
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
SELECT SUPPLEMENTAL_LOG_DATA_MIN, SUPPLEMENTAL_LOG_DATA_ALL FROM V$DATABASE;

------ Create XStream capture user (runs the xstream captures)
-- Create CDB tablespace
ALTER SESSION SET CONTAINER=cdb$root;
CREATE TABLESPACE cflt_xstream_capture DATAFILE '/opt/oracle/oradata/ORCLCDB/cflt_xstream_capture.dbf'
  SIZE 25M REUSE AUTOEXTEND ON MAXSIZE UNLIMITED;

-- Create PDB tablespace
ALTER SESSION SET CONTAINER=ORCLPDB1;
CREATE TABLESPACE cflt_xstream_capture DATAFILE '/opt/oracle/oradata/ORCLCDB/ORCLPDB1/cflt_xstream_capture.dbf'
  SIZE 25M REUSE AUTOEXTEND ON MAXSIZE UNLIMITED;

-- Create XStream Capture User
ALTER SESSION SET CONTAINER=cdb$root;
CREATE USER c##cflt_xstream_capture IDENTIFIED BY confluent123
  DEFAULT TABLESPACE cflt_xstream_capture
  QUOTA UNLIMITED ON cflt_xstream_capture
  CONTAINER=ALL;

-- Grant permissions
GRANT CREATE SESSION, SET CONTAINER TO c##cflt_xstream_capture CONTAINER=ALL;

-- Grant capture permission
BEGIN
  DBMS_XSTREAM_AUTH.GRANT_ADMIN_PRIVILEGE(
    grantee                 => 'c##cflt_xstream_capture',
    privilege_type          => 'CAPTURE',
    grant_select_privileges => TRUE,
    container               => 'ALL');
END;
/

------ Create XStream client user (used by XStream client)
-- Create CDB tablespace
ALTER SESSION SET CONTAINER=cdb$root;
CREATE TABLESPACE cflt_xstream_client DATAFILE '/opt/oracle/oradata/ORCLCDB/cflt_xstream_client.dbf'
  SIZE 25M REUSE AUTOEXTEND ON MAXSIZE UNLIMITED;

-- Create PDB tablespace
ALTER SESSION SET CONTAINER=ORCLPDB1;
CREATE TABLESPACE cflt_xstream_client DATAFILE '/opt/oracle/oradata/ORCLCDB/ORCLPDB1/cflt_xstream_client.dbf'
  SIZE 25M REUSE AUTOEXTEND ON MAXSIZE UNLIMITED;

-- Create XStream capture client user
ALTER SESSION SET CONTAINER=cdb$root;
CREATE USER c##cflt_xstream_client IDENTIFIED BY confluent123
  DEFAULT TABLESPACE cflt_xstream_client
  QUOTA UNLIMITED ON cflt_xstream_client
  CONTAINER=ALL;

-- Grant permissions
GRANT CREATE SESSION, SET CONTAINER TO c##cflt_xstream_client CONTAINER=ALL;
GRANT SELECT_CATALOG_ROLE TO c##cflt_xstream_client CONTAINER=ALL;

-- Grant table permissions
GRANT SELECT ANY TABLE TO c##cflt_xstream_client CONTAINER=ALL;
GRANT LOCK ANY TABLE TO c##cflt_xstream_client CONTAINER=ALL;
GRANT FLASHBACK ANY TABLE TO c##cflt_xstream_client CONTAINER=ALL;

exit;