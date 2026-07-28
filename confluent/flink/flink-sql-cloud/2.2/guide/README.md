# Flink 2.2 with Confluent Platform 8.3.0 - Step-by-Step Guide

This directory contains a comprehensive step-by-step guide for setting up and running Apache Flink 2.2 with Confluent Platform 8.3.0.

## Guide Overview

Follow these guides in order to build and run a complete Flink streaming application:

1. **[01_setup.md](01_setup.md)** - Environment Setup
   - Install Java 17
   - Install Maven
   - Download and install Confluent Platform 8.3.0
   - Download and install Apache Flink 2.2.0
   - Configure Flink for local development

2. **[02_configure_confluent_cloud.md](02_configure_confluent_cloud.md)** - Confluent Cloud Configuration
   - Create Kafka API keys
   - Create Schema Registry API keys
   - Create topics
   - Configure client.properties
   - Security best practices

3. **[03_start_flink_cluster.md](03_start_flink_cluster.md)** - Start Flink Cluster
   - Start local session mode cluster
   - Verify cluster status
   - Access Flink Web UI
   - Understand cluster components
   - Troubleshooting

4. **[04_build_application.md](04_build_application.md)** - Build the Application
   - Understand project structure
   - Review Maven configuration
   - Build the application JAR
   - Verify the build
   - Understand the application code

5. **[05_run_application.md](05_run_application.md)** - Run the Application
   - Submit job to Flink cluster
   - Monitor job execution
   - Produce test data
   - Verify output
   - Stop the job
   - Troubleshooting

6. **[06_advanced_topics.md](06_advanced_topics.md)** - Advanced Topics (Coming Soon)
   - Query transformations
   - Aggregations and windowing
   - State management
   - Performance tuning

## Quick Start

If you're already familiar with Flink and just want to get started quickly:

```bash
# 1. Install prerequisites
sudo apt-get install -y openjdk-17-jdk-headless maven

# 2. Download and extract Confluent Platform and Flink
# (See 01_setup.md for detailed commands)

# 3. Configure client.properties with your Confluent Cloud credentials
cp sample.client.properties client.properties
nano client.properties

# 4. Start Flink cluster
start-cluster.sh

# 5. Build application
mvn clean package

# 6. Run application
flink run target/flink-sql-cloud-2.2.jar --config-file client.properties
```

## What You'll Learn

By following this guide, you will:

- Set up a complete local Flink development environment
- Connect Flink to Confluent Cloud
- Build a Flink Table API application
- Process streaming data with Avro serialization
- Monitor and manage Flink jobs
- Troubleshoot common issues

## Prerequisites

- Linux or macOS environment
- Basic knowledge of:
  - Command line operations
  - Java programming
  - Apache Kafka concepts
  - SQL (for Table API queries)
- Access to Confluent Cloud (free trial available)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Confluent Cloud                       │
│  ┌──────────────┐         ┌─────────────────────┐      │
│  │ Kafka Cluster│         │  Schema Registry    │      │
│  │              │         │                     │      │
│  │ input-topic  │         │  Avro Schemas       │      │
│  │ output-topic │         │                     │      │
│  └──────────────┘         └─────────────────────┘      │
└─────────────────────────────────────────────────────────┘
                           ▲
                           │ SASL_SSL + Avro
                           │
┌──────────────────────────┼──────────────────────────────┐
│                Local Flink Cluster                       │
│  ┌────────────────────────────────────────────────┐    │
│  │           Flink Session Cluster                 │    │
│  │  ┌──────────────┐      ┌──────────────────┐   │    │
│  │  │ JobManager   │      │  TaskManager(s)  │   │    │
│  │  │              │      │                  │   │    │
│  │  │ - Scheduling │      │ - Task Execution │   │    │
│  │  │ - Checkpoints│      │ - State Mgmt     │   │    │
│  │  └──────────────┘      └──────────────────┘   │    │
│  │                                                 │    │
│  │  ┌──────────────────────────────────────────┐ │    │
│  │  │     HelloWorldJob (Table API)            │ │    │
│  │  │  - Read from input-topic                 │ │    │
│  │  │  - Process with SQL                      │ │    │
│  │  │  - Write to output-topic                 │ │    │
│  │  └──────────────────────────────────────────┘ │    │
│  └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## Support

For issues or questions:
- Check the troubleshooting sections in each guide
- Review [Apache Flink Documentation](https://flink.apache.org/docs/stable/)
- Visit [Confluent Documentation](https://docs.confluent.io/)

## Next Steps

Start with [01_setup.md](01_setup.md) to begin your journey with Flink and Confluent Platform!
