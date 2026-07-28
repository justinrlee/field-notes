# Step 3: Start Flink Session Cluster

This guide covers starting and verifying your local Flink session mode cluster.

## What is Session Mode?

In session mode, Flink runs a long-lived cluster that can execute multiple jobs. This is ideal for:
- Local development and testing
- Running multiple jobs on shared resources
- Interactive job submission and management

## Start the Cluster

Start your local Flink cluster:

```bash
start-cluster.sh
```

You should see output similar to:

```
Starting cluster.
Starting standalonesession daemon on host <hostname>.
Starting taskexecutor daemon on host <hostname>.
```

## Verify the Cluster

### Check Process Status

Verify that Flink processes are running:

```bash
jps
```

You should see:
- `StandaloneSessionClusterEntrypoint` (JobManager)
- `TaskManagerRunner` (TaskManager)

### Access the Web UI

Open your browser and navigate to:

```
http://localhost:8081
```

The Flink Web UI should display:
- **Overview**: Cluster status and resource availability
- **Jobs**: Currently running and completed jobs (should be empty initially)
- **Task Managers**: Available task managers and their slots

### Check via Command Line

List running jobs (should be empty):

```bash
flink list
```

Expected output:
```
No running jobs.
```

## Understanding the Cluster Components

### JobManager
- Coordinates job execution
- Manages checkpoints and savepoints
- Handles job scheduling
- Default port: 8081 (Web UI and REST API)

### TaskManager
- Executes the actual data processing tasks
- Manages task slots (parallel execution units)
- Reports metrics to JobManager
- Default configuration: 1 TaskManager with 8 slots

## Cluster Configuration

Your cluster configuration is located at:
```
~/flink/conf/config.yaml
```

Key settings:

```yaml
# JobManager settings
jobmanager.rpc.address: localhost
jobmanager.rpc.port: 6123
jobmanager.memory.process.size: 2048m

# TaskManager settings
taskmanager.memory.process.size: 2048m
taskmanager.numberOfTaskSlots: 8

# Web UI settings
rest.port: 8081
rest.bind-address: 0.0.0.0
```

## Troubleshooting

### Port Already in Use

If port 8081 is already in use:

1. Find the process using the port:
   ```bash
   lsof -i :8081
   ```

2. Either kill that process or change Flink's port in `config.yaml`:
   ```yaml
   rest.port: 8082
   ```

### Insufficient Memory

If you see out-of-memory errors:

1. Reduce memory allocation in `config.yaml`:
   ```yaml
   jobmanager.memory.process.size: 1024m
   taskmanager.memory.process.size: 1024m
   ```

2. Or increase your system's available memory

### Cluster Won't Start

Check the logs for errors:

```bash
# JobManager logs
tail -f ~/flink/log/flink-*-standalonesession-*.log

# TaskManager logs
tail -f ~/flink/log/flink-*-taskexecutor-*.log
```

Common issues:
- Java version mismatch (ensure Java 17)
- Insufficient permissions
- Network port conflicts

## Stop the Cluster

When you're done, stop the cluster:

```bash
stop-cluster.sh
```

You should see:

```
Stopping taskexecutor daemon (pid: xxxxx) on host <hostname>.
Stopping standalonesession daemon (pid: xxxxx) on host <hostname>.
```

## Cluster Management Commands

```bash
# Start cluster
start-cluster.sh

# Stop cluster
stop-cluster.sh

# Restart cluster
stop-cluster.sh && start-cluster.sh

# Check cluster status
flink list

# View cluster configuration
cat ~/flink/conf/config.yaml
```

## Next Steps

Proceed to [04_build_application.md](04_build_application.md) to build the Flink application.
