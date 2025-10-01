
curl -O https://packages.confluent.io/archive/8.0/confluent-8.0.0.tar.gz

curl -O https://packages.confluent.io/confluent-cli/archives/latest/confluent_linux_amd64.tar.gz
curl -O https://packages.confluent.io/confluent-cli/archives/latest/confluent_linux_arm64.tar.gz

curl -O "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip"
curl -O "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip"

curl -L "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/arm64/kubectl" -o kubectl-arm64
curl -L "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" -o kubectl-amd64

curl -LO https://releases.hashicorp.com/vault/1.20.2/vault_1.20.2_linux_amd64.zip
curl -LO https://releases.hashicorp.com/vault/1.20.2/vault_1.20.2_linux_arm64.zip