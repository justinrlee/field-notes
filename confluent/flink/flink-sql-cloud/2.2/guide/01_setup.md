# Step 1: Environment Setup

This guide covers installing all prerequisites for running Flink 2.2 with Confluent Platform 8.3.0.

## Prerequisites

- Linux or macOS environment
- Internet connection
- Sudo access (for package installation)

## Install Java 17

### Ubuntu/Debian

```bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jdk-headless
```

### macOS

```bash
brew install openjdk@17
```

### Verify Installation

```bash
java -version
# Should show: openjdk version "17.x.x"
```

## Install Maven

### Ubuntu/Debian

```bash
sudo apt-get install -y maven
```

### macOS

```bash
brew install maven
```

### Verify Installation

```bash
mvn -version
# Should show: Apache Maven 3.x.x
```

## Download Confluent Platform 8.3.0

```bash
# Navigate to home directory
cd ~

# Download Confluent Platform
curl -O https://packages.confluent.io/archive/8.3/confluent-8.3.0.tar.gz

# Extract
tar -xzvf confluent-8.3.0.tar.gz

# Create symbolic link
ln -s confluent-8.3.0 confluent

# Add to PATH
echo 'export PATH=${PATH}:${HOME}/confluent/bin' >> ~/.bashrc
source ~/.bashrc
```

### Verify Installation

```bash
kafka-topics --version
# Should show Confluent Platform version
```

## Download Apache Flink 2.2.0

```bash
# Navigate to home directory
cd ~

# Download Flink (check https://flink.apache.org/downloads/ for latest mirror)
curl -LO https://dlcdn.apache.org/flink/flink-2.2.0/flink-2.2.0-bin-scala_2.12.tgz

# Extract
tar -xzvf flink-2.2.0-bin-scala_2.12.tgz

# Create symbolic link
ln -s flink-2.2.0 flink

# Add to PATH
echo 'export PATH=${PATH}:${HOME}/flink/bin' >> ~/.bashrc
source ~/.bashrc
```

### Verify Installation

```bash
flink --version
# Should show: Version: 2.2.0
```

## Configure Flink (Optional)

Edit Flink configuration for local development:

```bash
nano ~/flink/conf/config.yaml
```

Recommended settings:

```yaml
# Allow access to Web UI from other machines
rest.bind-address: 0.0.0.0
rest.port: 8081

# Increase task slots for better parallelism
taskmanager.numberOfTaskSlots: 8

# Memory settings (adjust based on your system)
jobmanager.memory.process.size: 2048m
taskmanager.memory.process.size: 2048m
```

## Next Steps

Proceed to [02_configure_confluent_cloud.md](02_configure_confluent_cloud.md) to set up your Confluent Cloud connection.
