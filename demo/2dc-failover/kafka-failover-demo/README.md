# Kafka gateway switchover demo

Client apps that stay healthy while Confluent Gateway is down and the backing
cluster is swapped underneath them. Each client serves its own web UI showing
connection state, an outage timer, pending messages, and loss or duplicate
detection.

The Kafka side (clusters, Confluent Gateway, cluster links, mirroring, and the
failover itself) is run separately and isn't part of this repo. See `PLAN.md`
for the build plan and `TESTING.md` for test instructions.

## Set up

On the EC2 instance (Ubuntu 24.04, which ships Python 3.12):

```sh
sudo apt install -y python3-venv
python3 -m venv .venv
.venv/bin/pip install --only-binary=:all: -r client/requirements.txt
cp .env.example .env            # check KAFKA_BOOTSTRAP, choose UI_BIND
./run.sh preflight
```

Preflight checks that the bootstrap address and every broker address the
gateway advertises resolve and accept connections, and that topic `orders`
exists with 6 partitions. It prints the cluster ID the gateway reports.

## Run

One client per terminal, each in the foreground. Ctrl-C stops it.

```sh
./run.sh producer-tuned
./run.sh producer-fragile
./run.sh consumer-1
./run.sh consumer-2
```

| Client | UI |
|---|---|
| producer-tuned | http://UI_HOST:8081 |
| producer-fragile | http://UI_HOST:8082 |
| consumer-1 | http://UI_HOST:8083 |
| consumer-2 | http://UI_HOST:8084 |

Settings come from `.env`. A variable set on the command line wins, for example
`DEBUG_STATS=1 ./run.sh producer-tuned`. Each client's output also goes to
`logs/<client>.log`.

## Reaching the UIs from your workstation

The UIs have no authentication, so don't expose them beyond your workstation.
Choose one:

- **SSH tunnel.** Set `UI_BIND=127.0.0.1` in `.env`, so the UIs listen on the
  instance only. Then, on the workstation:

  ```sh
  ssh -N -L 8080:localhost:8080 -L 8081:localhost:8081 -L 8082:localhost:8082 \
         -L 8083:localhost:8083 -L 8084:localhost:8084 -L 8085:localhost:8085 \
         <user>@<ec2-address>
  ```

  `UI_HOST` is then `localhost`.
- **Direct.** Keep `UI_BIND=0.0.0.0`, and allow TCP 8080 to 8085 in the
  instance's security group from your workstation's IP only (`/32`). `UI_HOST`
  is then the instance's address.

Ports 8080 (console) and 8085 (auditor) arrive in later phases.

## What the Kafka side must provide

- A gateway route address reachable from the EC2 instance, with every broker
  address the gateway advertises reachable too.
- Topic `orders` with 6 partitions, writable on the active cluster.
- Consumer offset sync for group `demo-consumers` on the cluster link.

## Unit tests

`tests/` covers `client/state.py` and `consumer.SequenceTracker`. No Kafka needed.

```sh
.venv/bin/pip install --only-binary=:all: -r requirements-dev.txt
.venv/bin/pytest
```
