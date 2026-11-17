# Test instructions

One section per phase of `PLAN.md`. Every step lists what to expect and what
counts as a failure. When something fails, send back what the phase's
"Collect results" steps produce.

## Conventions

- Shell commands run on the EC2 instance, from the repo directory (the one
  holding `run.sh`).
- Each client runs in the foreground in its own terminal. "Client terminals"
  below means those; "command terminal" is one more shell for everything else.
- `UI_HOST` in a browser URL means `localhost` if you reach the UIs through an
  SSH tunnel, or the EC2 instance's address if you reach them directly.
- Steps on the Kafka side (stop the gateway, reverse the mirror) say what to do
  and when; you use your own procedure for them.

In the command terminal, set this. Commands on the instance reach the UIs on
`localhost`, whichever way your browser reaches them:

```sh
export DEMO_HOST=localhost
```

Prints one summary line per client. Several steps use it:

```sh
summary() {
  for port in 8081 8082 8083 8084; do
    curl -s "http://$DEMO_HOST:$port/api/state" | jq -c '{
      client: .client.client_id,
      kafka: .connection.state,
      attempts: .connection.attempts,
      last_outage_s: ((.connection.last_outage_ms // 0) / 1000),
      cluster: .connection.cluster_id,
      topic_problem: .connection.topic_problem,
      counters: .metrics.counters
    }'
  done
}
```

---

## Phases 0 and 1: the clients against the gateway

### Prerequisites

On the EC2 instance (Ubuntu 24.04):

- `sudo apt install -y python3-venv curl jq`
- Five terminals: four client terminals and one command terminal.

On the Kafka side (yours):

- The gateway is up, with its route pointing at cluster A.
- Topic `orders` with 6 partitions, writable on cluster A.
- Offset sync for group `demo-consumers` on the link. Nothing here fails over,
  but Phase 2 relies on it.
- Cluster A's cluster ID, from your own tooling. Step 6 compares it with what
  the clients see through the gateway.

From your workstation: SSH access to the instance, or a security group rule you
can add (step 5).

### 1. Install and unit tests

```sh
python3 -m venv .venv
.venv/bin/pip install --only-binary=:all: -r requirements-dev.txt
.venv/bin/pytest -q | tee pytest.txt
```

Expect:

- pip installs only wheels. Because of `--only-binary=:all:`, a package with no
  wheel fails with "No matching distribution found" rather than compiling. If
  that happens, send the pip output and `uname -m`.
- Every test passes. A failure here is a code bug; send `pytest.txt`.

### 2. Configure

```sh
cp .env.example .env
rm -rf logs
```

Check `KAFKA_BOOTSTRAP` (already set to
`ip-10-32-1-10.ap-southeast-1.compute.internal:19092`), and choose `UI_BIND`
for step 5: `127.0.0.1` for an SSH tunnel, `0.0.0.0` for direct access.

### 3. Preflight

```sh
./run.sh preflight | tee preflight.txt
```

Expect only `INFO` and `PASS` lines, roughly:

```
INFO  bootstrap.servers: ip-10-32-1-10.ap-southeast-1.compute.internal:19092
INFO  security.protocol: plaintext (default)
INFO  KAFKA_CFG_* overrides: none
PASS  bootstrap ip-10-32-1-10.ap-southeast-1.compute.internal:19092 reachable: resolves to 10.32.1.10, connected in 1 ms
PASS  metadata request: cluster ID <id>, controller <id>, 3 broker(s)
PASS  metadata lists at least one broker
PASS  broker <id> ip-10-32-1-10.ap-southeast-1.compute.internal:19093 reachable: ...
PASS  broker <id> ip-10-32-1-10.ap-southeast-1.compute.internal:19094 reachable: ...
PASS  broker <id> ip-10-32-1-10.ap-southeast-1.compute.internal:19095 reachable: ...
PASS  topic orders has at least 6 partitions: found 6
PASS  every partition of orders has a leader
```

The exit code is 0 when nothing failed. If a broker resolves but doesn't accept
connections, the gateway advertises an address or port the instance can't
reach (security group, or gateway configuration).

### 4. Start the clients

One per client terminal:

```sh
DEBUG_STATS=1 ./run.sh producer-tuned
DEBUG_STATS=1 ./run.sh producer-fragile
DEBUG_STATS=1 ./run.sh consumer-1
DEBUG_STATS=1 ./run.sh consumer-2
```

Expect each to print `Uvicorn running on http://<UI_BIND>:<port>` and
`Application startup complete`, and keep running. Then, in the command
terminal:

```sh
for port in 8081 8082 8083 8084; do curl -s -o /dev/null -w "$port %{http_code}\n" "http://$DEMO_HOST:$port/health"; done
grep demo.stats logs/*.log
```

Expect `200` from all four. For the stats check, expect for each client:

- One or two `stats payload:` lines: the first payload, and the first one with
  a broker UP. A client that was already connected when its first payload
  arrived logs only one.
- An INFO line after each payload: `stats payload has every field on_stats reads`.

Fail: any `WARNING ... stats payload lacks fields on_stats reads: ...` line.
Send the warning together with the payload line logged just before it. The
broker names in the payloads are gateway addresses (ports 19092 to 19095).

### 5. Reach the UIs from your workstation

Choose one:

- **SSH tunnel** (`UI_BIND=127.0.0.1`). On the workstation:

  ```sh
  ssh -N -L 8080:localhost:8080 -L 8081:localhost:8081 -L 8082:localhost:8082 \
         -L 8083:localhost:8083 -L 8084:localhost:8084 -L 8085:localhost:8085 \
         -L 8089:localhost:8089 <user>@<ec2-address>
  ```

  Then `UI_HOST` is `localhost`. Ports 8080 and 8085 are for the console and
  auditor in later phases, and 8089 is for step 7. Forwarding them now does no
  harm.
- **Direct** (`UI_BIND=0.0.0.0`). Add a security group rule allowing TCP 8080
  to 8089 from your workstation's IP only (`/32`). The UIs have no
  authentication. Then `UI_HOST` is the instance's address as your workstation
  reaches it.

If you change `UI_BIND`, stop the clients (Ctrl-C) and start them again.

### 6. Steady state

Open these in a browser:

| UI | URL |
|---|---|
| producer-tuned | `http://<UI_HOST>:8081` |
| producer-fragile | `http://<UI_HOST>:8082` |
| consumer-1 | `http://<UI_HOST>:8083` |
| consumer-2 | `http://<UI_HOST>:8084` |

Expect on every page:

- A green band reading **Connected to Kafka**.
- "App reachable, live updates on" in the top right.
- The cluster under the band matches the cluster ID from preflight. Compare it
  with cluster A's real ID and record whether they match. A match means the
  gateway passes the backing cluster ID through. A mismatch means the UIs show
  the gateway's own ID; that's not a failure here, but Phase 3 depends on it.
- "Broker connections" lists gateway addresses. Brokers the client is using
  show **connected**; the rest show grey "idle" or "not used yet". None should
  be amber.
- No red "Connected, but the topic isn't usable" band.

Producers show "Delivered" climbing by about 5 per second, with "Failed" at 0.
The 6 partitions are split between the two consumers (see "Partitions
assigned" in each timeline), and each consumer's "Received" climbs by about 5
per second: half of the two producers' combined 10. Neither consumer sits at 0.
"Missing" stays at 0. Hovering over a tile shows its partition.

Check that each producer spreads its messages evenly over all 6 partitions:

```sh
for port in 8081 8082; do curl -s "http://$DEMO_HOST:$port/api/state" | jq -c '[.messages[].partition] | group_by(.) | map({partition: .[0], tiles: length})'; done
```

Expect partitions 0 to 5 on each line, with about the same count each.

Run `summary` and keep the output.

### 7. Missing-topic display

In the command terminal, start one extra consumer, outside the demo's consumer
group, pointed at a topic that doesn't exist:

```sh
TOPIC=demo-no-such-topic GROUP_ID=demo-topic-check CLIENT_ID=topic-check PORT=8089 ./run.sh consumer-1
```

From another shell on the instance (or a browser at `http://<UI_HOST>:8089`):

```sh
curl -s http://localhost:8089/api/state | jq '{state: .connection.state, topic_problem: .connection.topic_problem}'
```

Expect `"state": "connected"` and
`"topic_problem": "Topic demo-no-such-topic doesn't exist, or this client isn't allowed to see it"`.
The page shows a red band reading "Connected, but the topic isn't usable". The
extra consumer doesn't create the topic: librdkafka consumers don't
auto-create topics unless `allow.auto.create.topics` is set.

Stop it with Ctrl-C.

### 8. About 20 s gateway outage

The gateway's route stays on cluster A throughout this phase. On the
producer-fragile page, set the rate slider to 50 per second, so that refused
sends become possible in step 9. Then stop the gateway, wait about 20 s, and
start it again. Note the stop and start times.

While the gateway is down, check each page for:

- An amber band reading **Waiting for Kafka**, a timer counting up, and "N
  connection attempts so far", with N climbing every few seconds.
- "Waiting to send" climbing on both producer pages.

And in the command terminal:

```sh
for port in 8081 8082 8083 8084; do curl -s -o /dev/null -w "$port %{http_code}\n" "http://$DEMO_HOST:$port/health"; done
```

Expect `200` from all four: the apps are healthy while Kafka is unreachable.
The client terminals show librdkafka connection errors; that's expected.

Mid-outage, refresh one page (say consumer-1). Expect the same picture straight
back: the timer continues from where it was, and the "What happened" timeline
shows no duplicated entries.

Within a few seconds of the gateway accepting connections again, expect:

- A green-tinted **Back online** band on every page, showing the outage
  duration: the time from stop to start, plus however long the gateway takes
  to accept connections.
- Pending drains to 0, and "Delivered" on the producers jumps by the backlog.
- After 10 s, the band returns to **Connected to Kafka**.
- The cluster ID doesn't change, and no timeline shows "Cluster changed".

producer-tuned should show 0 failed. producer-fragile may show a few failed if
the outage came close to its 30 s message timeout. Record the number either way.

Run `summary` and keep the output.

### 9. About 60 s gateway outage

Stop the gateway, wait about 60 s, and start it again. Note the times.

During the outage, expect the same as step 8. In addition:

- producer-fragile starts showing **Failed** about 30 s in. At 50 messages per
  second its 2,000-message buffer fills after about 40 s. From then on
  "Refused, buffer full" climbs, and its timeline shows "Send buffer is full".
- producer-tuned keeps "Failed" at 0 and its buffer gauge low.

After recovery (acceptance criteria):

- Every page shows **Back online**, with an outage duration of about 60 s plus
  the gateway's startup time.
- producer-tuned: **0 failed**.
- producer-fragile: failed > 0, and refused > 0 is likely.
- Consumers: "Missing" > 0, caused by producer-fragile only. Check which
  producers the gaps came from:

  ```sh
  for port in 8083 8084; do curl -s "http://$DEMO_HOST:$port/api/state" | jq -r '.timeline[] | select(.kind=="gap") | .text'; done
  ```

  Every line should name `producer-fragile`. Any line naming `producer-tuned`
  is a failure.
- Consumers may show a rebalance. The outage is longer than their 45 s
  `session.timeout.ms`. Record it; it isn't a failure.
- Duplicates on the consumers are information, not failure. Record the count.

If you plan to fence the gateway rather than stop it, also fence and unfence
it once for about 60 s, and note how each UI behaves: band, errors shown, and
whether an outage was declared at all. Phase 2 covers this in detail; an early
look helps.

Set producer-fragile back to 5 per second. Run `summary` and keep the output.

### 10. Save state

Before step 11 restarts some clients and resets their counters:

```sh
mkdir -p phase1-results
for port in 8081 8082 8083 8084; do curl -s "http://$DEMO_HOST:$port/api/state" > "phase1-results/state-$port.json"; done
```

### 11. Stop and start while Kafka is down

1. Stop the gateway, and wait about 10 s.
2. Press Ctrl-C in the producer-tuned and consumer-1 terminals. Expect each to
   return to the prompt within about 5 s, after printing
   `Finished server process`. If one hangs, note which, then press Ctrl-C again
   to force it.
3. Start both again (`./run.sh producer-tuned`, `./run.sh consumer-1`), with the
   gateway still down. Expect each UI to load and show **Waiting for Kafka**
   with "Can't reach Kafka yet" on its timeline.
4. Start the gateway. Expect both to show **Back online**, and consumer-1 to
   get partitions again.

Messages that producer-tuned still had queued when you stopped it are lost:
they lived only in that process. That's expected; the demo's no-loss promise
covers outages, not killing the client.

### 12. Collect results

```sh
cp preflight.txt pytest.txt phase1-results/
cp -r logs phase1-results/
tar czf phase1-results.tgz phase1-results
```

Send back `phase1-results.tgz`, plus:

- cluster A's real cluster ID;
- the `summary` outputs from steps 6, 8 and 9;
- the step 7 output;
- the approximate stop and start times of each gateway outage;
- what happened in step 11;
- anything a UI showed that didn't match the descriptions here. Screenshots
  are welcome, especially mid-outage and just after recovery.
