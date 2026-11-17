# Bidirectional cluster link setup

Two clusters, PLAINTEXT, no auth. Run all commands from any host that can reach both clusters and has the Confluent Platform CLI tools (`kafka-cluster-links`, `kafka-mirrors`, `kafka-topics`, `kafka-configs`).

> Flags below are from the CP Cluster Linking docs (7.5+/8.x). Confirm with `<tool> --help` on your version; the docs win if they disagree.
> Docs: https://docs.confluent.io/platform/current/multi-dc-deployments/cluster-linking/

# get brokers
```bash
kafka-broker-api-versions --bootstrap-server localhost:9092 2>/dev/null | grep rack | sort | awk '{print $1 ","}' | tr -d '\n' | sed 's|,$|\n|'
```

```bash
export A=ip-10-32-1-50.ap-southeast-1.compute.internal:9092,ip-10-32-2-50.ap-southeast-1.compute.internal:9092,ip-10-32-3-50.ap-southeast-1.compute.internal:9092
export B=ip-10-32-1-51.ap-southeast-1.compute.internal:9092,ip-10-32-2-51.ap-southeast-1.compute.internal:9092,ip-10-32-3-51.ap-southeast-1.compute.internal:9092
```

## 0. Prerequisites

- Both clusters run Confluent Server (not Apache Kafka) with a valid license (or trial). Cluster Linking is an enterprise feature.
- Brokers have `confluent.cluster.link.enable=true` (default on recent versions; check `server.properties` if link creation errors).
- Every broker in each cluster can resolve and reach every broker in the other cluster on 9092. Cluster Linking traffic goes broker-to-broker, so check DNS and security groups across both sets of hosts, not just the bootstrap hosts.

## 1. Create the link on both clusters (same name, bidirectional mode)

A bidirectional link is one link name defined on **both** clusters, each pointing at the other.

`link-a-to-b.properties` (created on cluster A, points at B):

```bash
tee link-a-to-b.properties <<-EOF
bootstrap.servers=${B}
link.mode=BIDIRECTIONAL
consumer.offset.sync.enable=true
consumer.offset.sync.ms=5000
EOF

tee link-b-to-a.properties <<-EOF
bootstrap.servers=${A}
link.mode=BIDIRECTIONAL
consumer.offset.sync.enable=true
consumer.offset.sync.ms=5000
EOF

tee filter.json <<-'EOF'
{"groupFilters":[{"name":"demo-consumers","patternType":"LITERAL","filterType":"INCLUDE"}]}
EOF


kafka-cluster-links --bootstrap-server $A --create --link demo --config-file link-a-to-b.properties --consumer-group-filters-json-file filter.json
kafka-cluster-links --bootstrap-server $B --create --link demo --config-file link-b-to-a.properties --consumer-group-filters-json-file filter.json

kafka-cluster-links --bootstrap-server $A --describe --link demo

kafka-cluster-links --bootstrap-server $B --describe --link demo

kafka-topics --bootstrap-server $A --create --topic orders --partitions 6 --replication-factor 3
kafka-mirrors --bootstrap-server $B --create --source-topic orders --mirror-topic orders --link demo --replication-factor 3

kafka-topics --bootstrap-server $A --create --topic transactions --partitions 6 --replication-factor 3
kafka-mirrors --bootstrap-server $B --create --source-topic transactions --mirror-topic transactions --link demo --replication-factor 3

kafka-mirrors --bootstrap-server $A --describe --topics orders
kafka-mirrors --bootstrap-server $B --describe --topics orders

# Set B to primary
kafka-mirrors --bootstrap-server $B --reverse-and-start --topics orders

kafka-cluster cluster-id --bootstrap-server ${A}
kafka-cluster cluster-id --bootstrap-server ${B}

kafka-cluster cluster-id --bootstrap-server ${BS}

# Set A to primary
kafka-mirrors --bootstrap-server $A --reverse-and-start --topics orders
```

```properties
bootstrap.servers=ip-10-32-1-51.ap-southeast-1.compute.internal:9092,ip-10-32-2-51.ap-southeast-1.compute.internal:9092,ip-10-32-3-51.ap-southeast-1.compute.internal:9092
link.mode=BIDIRECTIONAL
consumer.offset.sync.enable=true
consumer.offset.sync.ms=5000
```


`link-b-to-a.properties` (created on cluster B, points at A): same, but `bootstrap.servers` is the cluster A list.


```properties
bootstrap.servers=ip-10-32-1-50.ap-southeast-1.compute.internal:9092,ip-10-32-2-50.ap-southeast-1.compute.internal:9092,ip-10-32-3-50.ap-southeast-1.compute.internal:9092
link.mode=BIDIRECTIONAL
consumer.offset.sync.enable=true
consumer.offset.sync.ms=5000
```

`filter.json`

```json
{"groupFilters":[{"name":"demo-consumers","patternType":"LITERAL","filterType":"INCLUDE"}]}
```

```bash
kafka-cluster-links --bootstrap-server $A --create --link demo --config-file link-a-to-b.properties --consumer-group-filters-json-file filter.json
kafka-cluster-links --bootstrap-server $B --create --link demo --config-file link-b-to-a.properties --consumer-group-filters-json-file filter.json
```

Verify (both should list `demo-link`, mode BIDIRECTIONAL):

```bash
kafka-cluster-links --bootstrap-server $A --list --link demo
kafka-cluster-links --bootstrap-server $B --list --link demo
```

## 2. Topics

| Topic | Where | Config | Purpose |
|---|---|---|---|
| `orders` | Created on A, mirrored to B | 6 partitions, RF 3 | The data topic all clients use |
| `demo-cluster-name` | One per cluster, **not** mirrored | 1 partition, RF 3 | Optional: holds `A` or `B` so the UI can show which cluster it is on (PLAN.md Phase 3, only needed if the gateway hides the cluster ID) |

Consumer group `demo-consumers` needs no pre-creation; offsets are synced by the link (filter above).

```bash
# Source topic on A
kafka-topics --bootstrap-server $A --create --topic orders --partitions 6 --replication-factor 3

# Mirror on B
kafka-mirrors --bootstrap-server $B --create --source-topic orders --mirror-topic orders --link demo
```

Optional cluster-name topics (write one record each):

```bash
kafka-topics --bootstrap-server $A --create --topic demo-cluster-name --partitions 1 --replication-factor 3
kafka-topics --bootstrap-server $B --create --topic demo-cluster-name --partitions 1 --replication-factor 3
echo A | kafka-console-producer --bootstrap-server $A --topic demo-cluster-name
echo B | kafka-console-producer --bootstrap-server $B --topic demo-cluster-name
```

If you want to avoid mirroring `demo-cluster-name`, simply never create a mirror for it; mirroring is per topic.

## 3. Verify replication

```bash
# produce a few records to A
echo test | kafka-console-producer --bootstrap-server $A --topic orders

# status and lag on B
kafka-mirrors --bootstrap-server $B --describe --topics orders
# read from B
kafka-console-consumer --bootstrap-server $B --topic orders --from-beginning --max-messages 1
```

Expect mirror state `ACTIVE` and lag 0. Writes to `orders` on B are rejected while it is a mirror.

## 4. Switchover (A to B)

With the gateway stopped and mirror lag at 0 on B:

```bash
kafka-mirrors --bootstrap-server $B --describe --topics orders      # confirm lag 0 on every partition
kafka-mirrors --bootstrap-server $B --reverse-and-start --topics orders
```

Run the reverse against the mirror (to reverse the link, promote the mirror, and start it)

Run the reverse against whichever cluster the docs/`--help` say for your version (the current source, A, in the flow I know of). After it, `orders` on B is writable and `orders` on A is a mirror of B. Check with `--describe` on both. Switch back by repeating with A and B swapped.

If `--reverse-and-start` is rejected, the link mode or topic state is wrong; `--describe` on both sides and the broker log will say which.

## Cleanup / reset

```bash
kafka-mirrors --bootstrap-server $B --promote --topics orders   # stop mirroring if B is still a mirror
kafka-topics --bootstrap-server $A --delete --topic orders
kafka-topics --bootstrap-server $B --delete --topic orders
kafka-cluster-links --bootstrap-server $A --delete --link-name demo-link
kafka-cluster-links --bootstrap-server $B --delete --link-name demo-link
```
