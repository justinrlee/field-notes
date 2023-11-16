#!/bin/bash

# Simple shell script that installs most of CP (zookeeper, kafka, sr, c3) on a single (Ubuntu) VM, using cp-ansible

# Designed for AWS

sudo apt-get update \
  && sudo apt-get install openssl python3-pip -y \
  && sudo python3 -m pip install ansible

git clone https://github.com/confluentinc/cp-ansible.git \
  && cd cp-ansible \
  && ansible-galaxy collection build \
  && ansible-galaxy collection install confluent-platform-*.tar.gz

cd ~

# Change this for clouds other than AWS
export DNS_NAME=$(curl http://169.254.169.254/latest/meta-data/public-hostname)

tee ~/hosts.yml <<-EOF
all:
  vars:
    ansible_become: true
    ansible_connection: ssh
    ansible_user: ubuntu

    jmxexporter_enabled: true

    control_center_custom_properties:
      confluent.controlcenter.mode.enable: management


# zookeeper:
#   hosts:
#     ${DNS_NAME}: null

kafka_controller:
  hosts:
    ${DNS_NAME}: null
kafka_broker:
  hosts:
    ${DNS_NAME}: null
schema_registry:
  hosts:
    ${DNS_NAME}: null
control_center:
  hosts:
    ${DNS_NAME}: null
EOF

ssh-keygen -t rsa -f ~/.ssh/id_rsa -N ''
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys

tee ~/.ansible.cfg <<-'EOF'
[defaults]
hash_behaviour=merge
callbacks_enabled = timer, profile_tasks, profile_roles
forks=20
host_key_checking = False

[ssh_connection]
ssh_args = -o StrictHostKeyChecking=accept-new
# ssh_args = -o StrictHostKeyChecking=no -o ControlMaster=auto -o ControlPersist=120s
EOF

ansible-playbook -i hosts.yml confluent.platform.all