
curl -O https://packages.confluent.io/archive/7.7/confluent-community-7.7.1.tar.gz

curl -O https://packages.confluent.io/confluent-cli/archives/latest/confluent_linux_amd64.tar.gz
curl -O https://packages.confluent.io/confluent-cli/archives/latest/confluent_linux_arm64.tar.gz

curl -O "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip"
curl -O "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip"

curl -L "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/arm64/kubectl" -o kubectl-arm64
curl -L "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" -o kubectl-amd64
