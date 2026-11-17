# Kafka gateway switchover demo: implementation plan

This plan is written for Claude Code. Work through it phase by phase. At the end of each phase, stop, summarize what you changed, and add that phase's test instructions to `TESTING.md` (see "Testing" below). Do not start the next phase until the user reports that the current phase meets its acceptance criteria, unless the user says to go ahead.

## Scope

This repo contains the **client side only**: the demo client apps, their web UIs, a presenter console, an auditor, and the instructions and helper scripts for running them.

The Kafka side is **out of scope** and is run by the user by hand: the Confluent Platform clusters, Confluent Gateway, cluster links, mirror topics, consumer offset sync, and the switchover itself (stopping or fencing the gateway, reversing the mirror, starting or unfencing the gateway). Don't write gateway, cluster, link or mirror configuration, and don't script the switchover. Where the clients need something from the Kafka side, list it under "What the Kafka side must provide" and in `TESTING.md` prerequisites; the user sets it up.

## Testing

Claude Code does not run anything: no unit tests, no installs, no client processes, no scripts, no syntax checks. All testing happens remotely, on infrastructure the user manages. Claude Code's job is to build, and to write instructions precise enough for someone else to run.

For each phase, `TESTING.md` gets a section with:

- Prerequisites (tools, versions, images to pull, environment variables, anything needed from the Kafka side). Don't assume the tests run on the machine the code was written on: take hostnames from variables such as `DEMO_HOST`.
- Numbered steps with exact commands. For steps the user performs on the Kafka side (stop the gateway, reverse the mirror), say what to do and when, not how: the user owns those commands.
- What to expect at each step, tied to the phase's acceptance criteria, including the timing and counts that make a step pass or fail.
- What to capture and send back (logs, `/api/state` output, screenshots), with a command that collects it.

Fixes are driven by the results the user reports. When a result shows a problem, fix it and update `TESTING.md` if the steps change.

## What the demo shows

Clients connect only to Confluent Gateway. Behind it are two Confluent Platform clusters joined by cluster links. The presenter:

1. Starts the clients and opens their UIs.
2. Performs a failover by hand: stop or fence the gateway, reverse the mirror so the topic on the second cluster becomes the writable source, then start or unfence the gateway with its route pointing at the second cluster.
3. Shows how the clients behaved.

The point to make visible: during the failover the client apps stay healthy. They keep running, keep accepting work, show that they are waiting, and resume on their own when the gateway returns. Afterwards, the consumers and the auditor prove what was or wasn't lost or duplicated.

Confluent documents this flow as Client Switchover: https://docs.confluent.io/private-cloud-gateway/current/gateway-migrate.html. Read it for what clients should expect (rebalances, duplicates, ordering), not for gateway configuration.

## Where things run

```
 workstation                      EC2 instance (Ubuntu 24.04, venv)        user-managed
 ───────────                      ─────────────────────────────────        ────────────
 browser tabs ── HTTP/SSE ──────▶ presenter console :8080
      │                           producer-tuned     :8081 ─┐
      └──────── HTTP/SSE ───────▶ producer-fragile   :8082 ─┤
                                  consumer-1         :8083 ─┼─ Kafka protocol ─▶ Confluent Gateway ─▶ cluster A
                                  consumer-2         :8084 ─┤                                          ⇅ cluster links
                                  auditor (Phase 5)  :8085 ─┘                                        cluster B
```

- The clients run directly on one EC2 instance (Ubuntu 24.04) that can reach the gateway: Python 3.12 from the OS, packages in a venv (`.venv`, plain `venv` and `pip`). No Docker, no process manager.
- Each process runs in the foreground in its own terminal, started with `./run.sh <client>`; Ctrl-C stops it. Later services (console, auditor) get their own `run.sh` entries.
- The presenter's workstation reaches the UIs on the EC2 instance, either directly (security group open to the workstation's IP only) or through an SSH tunnel. The UIs have no authentication; never expose them to the internet.
- Every URL a browser uses must work both ways: through a tunnel (`localhost:<port>`) and directly (`<ec2-host>:<port>`). Pages use relative URLs, and the console builds client URLs from `window.location.hostname` plus each client's port. Host port numbers stay the same on both ends of a tunnel.

## What the Kafka side must provide

The user sets these up. `TESTING.md` repeats them as prerequisites.

- A gateway route address reachable from the EC2 instance. Every broker address the gateway advertises must resolve and connect from the instance too.
- Topic `orders` with 6 partitions, writable on the active cluster and mirrored on the other.
- Consumer offset sync on the link for group `demo-consumers` (and `demo-auditor` from Phase 5). Without it, consumers resume at `auto.offset.reset` on the new cluster, and the auditor shows the gap.
- Any client security settings the gateway requires (SASL, TLS). The clients take them as `KAFKA_CFG_*` environment variables; see `client/profiles.py`.
- Optional, for Phase 3: a non-mirrored topic `demo-cluster-name` on each cluster holding one record (`A` or `B`), if the gateway hides the backing cluster ID.

## The user's environment

As reported by the user. Use these in defaults, examples and test instructions.

- Gateway bootstrap: `ip-10-32-1-10.ap-southeast-1.compute.internal:19092`. The gateway advertises one port per broker: 19093 to 19095 for the three brokers.
- Plaintext, no SASL, no TLS, no authentication.
- Names resolve through DNS (not `/etc/hosts`).
- Topic `orders` exists with 6 partitions, and offset sync covers `demo-consumers`.

## What already exists

| File | Purpose |
|---|---|
| `client/app.py` | FastAPI app. Serves the UI, `/health`, `/api/state`, `/api/events` (SSE), and producer controls `/api/send`, `/api/rate`. |
| `client/state.py` | In-process state and the event fan-out to browsers. No Kafka dependency. |
| `client/producer.py` | Sequence-numbered producer with delivery, error and stats callbacks. |
| `client/consumer.py` | Consumer with per-producer sequence checking (gap and duplicate detection). |
| `client/probe.py` | AdminClient metadata probe once per second: connectivity truth plus cluster ID. |
| `client/profiles.py` | `tuned` and `fragile` librdkafka configs, plus `KAFKA_CFG_*` env overrides. |
| `client/static/index.html` | The whole UI: one file, vanilla JS, no build step. |
| `run.sh` | Runs one client in the foreground (`./run.sh producer-tuned`), or the preflight check. Reads `.env`. |
| `client/preflight.py` | Checks that the gateway, every advertised broker address and the topic are usable from the instance. |
| `.env.example` | Every setting for a run against the gateway: bootstrap address, UI bind address, `DEBUG_STATS`, `KAFKA_CFG_*`. |
| `tests/` | pytest unit tests for `state.py` and `consumer.SequenceTracker`. |
| `TESTING.md` | Test instructions, one section per phase. |

The code has not yet run against a real broker or the gateway. Treat it as a starting point and fix whatever the user's test results show to be wrong.

## Ground rules

- Python 3.12, run directly from a venv. No Docker, no process manager, no `uv`. No frontend build step, no bundler, no frontend framework. Each UI is a single HTML file.
- The browser talks only to the client processes (and, from Phase 4, the console). The UI must never depend on Kafka being reachable. Do not route UI state through a Kafka topic.
- `state.py` stays free of `confluent_kafka` imports so it remains unit-testable.
- The event contract below is the interface between backends and UIs. If you change it, update this file in the same change.
- Client behaviour that depends on Confluent Gateway or Cluster Linking (cluster ID passthrough, idempotent producer state, offset sync timing) must be checked against the official docs, not assumed. When the docs and this plan disagree, the docs win; note the discrepancy in your phase summary.
- Every phase ends with test instructions in `TESTING.md` that the user can execute. Don't run them yourself (see "Testing").
- The UIs must work without internet access from the EC2 instance or the workstation: no CDN fonts or scripts.

## Inside each client process

```
 librdkafka threads ──callbacks──▶ DemoState (lock) ──call_soon_threadsafe──▶ asyncio loop ──▶ SSE queues ──▶ browsers
 probe thread ─────────────────────────┘                         flush() every 200 ms batches message updates
```

## Event contract

Every SSE `data:` line is one JSON envelope:

```json
{"type": "snapshot | connection | metrics | messages | timeline", "client_id": "producer-tuned", "ts": 1760342400000, "data": {}}
```

- `snapshot`: sent first on every stream, and again if a subscriber falls behind. `data` = `{client, connection, metrics, messages, timeline, server_time}`.
- `connection`: sent immediately on a state change or cluster ID change. `data` = `{state, since, outage_started, last_outage_ms, attempts, last_error, probe_latency_ms, cluster_id, topic_problem}`; `state` is `connecting`, `connected` or `retrying`. `topic_problem` is null, or a sentence saying why the demo topic can't be used (missing, not visible, or a metadata error), from the last successful probe. The UI derives two more display states: "recovered" for 10 s after an outage ends, and "problem" while connected with a `topic_problem`.
- `metrics`: every 200 ms. `data` = `{counters, buffer, brokers, group, rate, connection}`. Counters: `queued, acked, failed, buffer_full, pending` (producer) and `consumed, gaps, missing, duplicates, rebalances` (consumer).
- `messages`: batched tile updates. `data.updates` = list of `{id, seq, state, ...}`. Producer states: `queued, acked, failed`. Consumer states: `first, ok, gap, duplicate`.
- `timeline`: one human-readable entry `{ts, kind, text}`. Kinds in use: `info, connected, outage, recovered, cluster, topic, backpressure, failed, fatal, rate, gap, duplicate, rebalance, resume`.

Message payload produced to Kafka (JSON value, key = `producer_id`):

```json
{"producer_id": "producer-tuned", "run_id": "a1b2c3d4", "partition": 3, "seq": 42, "msg_id": "producer-tuned-a1b2c3d4-p3-42", "produced_at": 1760342400.123}
```

Partitioning: each producer sends to partitions 0 to `PARTITIONS`-1 in turn (default 6), choosing the partition explicitly; the key is a label only. `seq` counts per (producer, run, partition), and consumers check it per partition, using the partition the message was read from. Kafka orders messages within a partition, so gap and duplicate detection stays exact while every partition, and every consumer in the group, gets traffic. Producer tiles in `messages` updates carry `partition`.

## Phase 0: make the skeleton runnable

Status: built. Tested together with Phase 1.

Goal: fix what the skeleton was likely to get wrong, before it meets the gateway.

Tasks (done):

1. Pin exact versions in `client/requirements.txt` to current stable releases. They install as wheels only (`pip install --only-binary=:all:`) on Ubuntu 24.04's Python 3.12, so a missing wheel fails the install instead of compiling.
2. Behind a `DEBUG_STATS=1` env var, log one real stats payload per client at startup, and check it for the field names that `state.on_stats` reads: `brokers.*.state`, `brokers.*.connects`, `msg_cnt`, `msg_max`, `cgrp.state`, `cgrp.join_state`. Log a warning naming any that are missing, so the user's test run reports mismatches directly.
3. Fix the likely failure points up front: SSE disconnect handling under uvicorn, consumer `close()` blocking on shutdown, the attempts counter if `connects` behaves differently than expected.
4. Add a small `tests/` directory with pytest tests for `state.py` and `consumer.SequenceTracker` (no Kafka needed). Cover the outage state machine, the delivery-before-queued race, tile eviction, and subscriber overflow resync.

An earlier version ran a throwaway local broker in Docker for outage tests. It was dropped with Docker; the outage tests now stop the user's gateway instead (Phase 1).

## Phase 1: run on EC2 against the gateway

Status: built, waiting for the user's test results.

Goal: the four clients on the EC2 instance, connected through the user's gateway, with their UIs open on the workstation, surviving gateway outages.

Tasks:

1. `run.sh <client>` runs one client in the foreground in the current terminal; Ctrl-C stops it. It reads `.env`, lets variables set in the shell override it, sets the role, profile and port per client, and appends output to `logs/<client id>.log`. `./run.sh preflight` runs the preflight check.
2. Configuration by `.env` file next to `run.sh`: `KAFKA_BOOTSTRAP` (gateway route address), `UI_BIND`, `DEBUG_STATS`, plus any `KAFKA_CFG_*` settings. Ship `.env.example` with every variable explained, and make sure secrets never reach the UI (the settings panel is already a whitelist; keep it that way). Fail at startup with a clear message if `KAFKA_BOOTSTRAP` is unset.
3. A preflight check, `client/preflight.py`. It reports, with a clear pass or fail line for each:
   - the bootstrap address answers a metadata request, and the cluster ID it returns;
   - every broker address in that metadata resolves and accepts a TCP connection from the instance;
   - topic `orders` exists, with its partition count;
   - the security settings in use (names only, never values).
4. The UI makes a missing or unreadable topic obvious, rather than leaving the producer quietly pending or the consumer quietly idle: the probe reports a `topic_problem`, shown as a red band.
5. Remote access instructions in the README: security group rule limited to the workstation's IP, or one SSH command that forwards ports 8080 to 8085.
6. `TESTING.md` "Phases 0 and 1": install and unit tests, preflight, start, the stats field check, open the UIs from the workstation, steady state, the missing-topic display, gateway outages of about 20 s and about 60 s (no failover), and stopping and starting clients while the gateway is down.

Acceptance:

- Unit tests pass, and preflight passes from the EC2 instance.
- The four UIs load on the workstation and show Connected through the gateway.
- Every UI shows Connected, then Waiting for Kafka with a running timer and a climbing attempt count, then Back online with the outage duration.
- `/health` returns 200 throughout the outage.
- After a 60 s outage: `producer-tuned` shows 0 failed; `producer-fragile` shows failures (its 30 s message timeout expired) and possibly refusals; the consumers show missing messages from the fragile producer only, and none from the tuned one.
- Refreshing a browser tab mid-outage restores the full picture from the snapshot.
- The cluster ID shown in the UIs is recorded. If it is the gateway's own ID rather than cluster A's, note it; Phase 3 handles it.

## Phase 2: first real failover, observed

Goal: learn what a full failover does to the clients. The user performs it by hand; this phase builds the tooling to observe and record it.

Tasks:

1. `scripts/capture.sh <label>`, run on the EC2 instance, saves `/api/state` from every client plus the new lines in `logs/` since the last capture into `captures/<timestamp>-<label>/`. The user runs it before, during and after each failover step.
2. `TESTING.md` Phase 2: with all clients running at 5 messages per second, the user fails over from A to B and later back to A, using their own procedure, capturing at each step. Spell out what to watch in each UI at each step, and what to record: outage duration, cluster ID before and after, tuned and fragile failed counts, consumer missing and duplicates, rebalances, and any fatal or unexpected errors.
3. Separately cover **stop** versus **fence**. A stopped gateway refuses connections; a fenced one may accept them and return errors instead. Ask the user to try both if they plan to use fencing, so Phase 3 can make the UI treat both as an outage.

Acceptance:

- The user has run A to B and B to A and sent back the captures.
- Each switchover shows as one outage per UI, followed by Back online.
- The tuned producer's failed count, and the consumers' missing and duplicate counts, are recorded. They drive Phase 3.

## Phase 3: client hardening, driven by what Phase 2 revealed

Do the items that the user's Phase 2 results showed are needed, and explain each one in the phase summary.

1. **Cluster identity.** If the gateway does not pass the backing cluster ID through, add a fallback that still reflects the client's own view: the probe reads the `demo-cluster-name` topic, which the user creates on each cluster (see "What the Kafka side must provide"). Show the result in the UI as "Cluster A" or "Cluster B" rather than a raw ID.
2. **Idempotent producer across the switch.** The new cluster has never seen the tuned producer's producer ID. Check whether the client recovers silently or raises errors (watch for fatal errors in `error_cb`). If it raises fatal errors, recreate the producer automatically, keep the same `run_id` and sequence counter, and show the recreation on the timeline.
3. **Consumer resume position.** Confirm that consumers resume on cluster B at the offsets committed on cluster A, given offset sync. Offset sync is periodic, so a small replay (shown as duplicates) is expected; measure it and explain it in the UI copy. Consider committing synchronously in `on_revoke`. If offsets are not synced at all, consumers fall back to `auto.offset.reset=latest` and the auditor will show missing messages; make sure that failure mode is visible and understood.
4. **Gateway restart effects.** The switchover docs note that consumer groups rebalance if the gateway is down longer than `session.timeout.ms`, and that producers can see duplicates when an acknowledgment is lost during the restart. Make sure both show up clearly in the UI rather than looking like bugs.
5. **Fenced gateway.** If fencing produced errors rather than connection failures, make the probe and state machine treat them as an outage, with a band message that says the gateway is refusing requests.
6. **Flapping.** If idle connection closes produce false `_ALL_BROKERS_DOWN` outages lasting under a second, debounce: require the probe to agree before declaring an outage.
7. **Ordering.** The switchover docs state that switching clusters does not guarantee ordering or end-to-end consistency. Do not claim strict ordering in UI copy; let the auditor report what actually happened.

## Phase 4: presenter console

Goal: the presenter watches every client from one page, and the timeline tells the failover story, including the steps done by hand.

Tasks:

1. New service `console/`, same stack as the clients (FastAPI plus one HTML file), on port 8080, started with `./run.sh console`. No Kafka access, no CLI tools.
2. Panels for every client, built by subscribing to each client's `/api/events` from the browser (CORS is already enabled on the clients). Client URLs come from `window.location.hostname` plus a port list in the console's config, so they work through a tunnel and directly. Each panel shows client name, display state, outage timer, cluster, and two or three key counters, and links to the client's full UI.
3. Step markers. The failover happens outside the demo, so the presenter records it: buttons for "Gateway stopped", "Mirror reversed", "Gateway started" (and "Gateway fenced" and "Gateway unfenced"), plus a free-text note. The console backend stores markers in memory with a server timestamp and serves them to every open console tab over its own SSE stream. Keyboard shortcuts for the three main steps, so the presenter doesn't hunt for buttons.
4. A unified timeline that merges the step markers with every client's timeline events, ordered by server timestamp.
5. Add the console's marker events to the event contract in this file.

Acceptance: during a failover, the presenter can follow every client from the console alone, and afterwards the console timeline tells the story in order: markers, outages, recoveries, cluster change, gaps and duplicates.

## Phase 5: auditor, report and rehearsal

1. **Auditor role.** Add `ROLE=auditor`: a consumer in its own group `demo-auditor`, the only member, reading every partition. It is the authority on missing and duplicate counts, because per-instance tracking in the regular consumers resets when a partition moves between group members. Started with `./run.sh auditor`. Give it its own UI variant on port 8085 that summarizes, per producer: received, missing, duplicates, and the longest gap. Track out-of-order arrivals so a late message fills its gap rather than counting as both missing and duplicate. Add the auditor to the console.
2. **Run report.** `scripts/report.sh`, run on the EC2 instance after a failover, reads the auditor's and producers' `/api/state` and prints a verdict: missing from `producer-tuned` (expected 0), failed on `producer-fragile` (expected above 0 for an outage longer than 30 s), and duplicates as information. It exits non-zero if the tuned producer lost anything.
3. **Reset between runs.** A way to start a rehearsal fresh from the client side: restarting each client (Ctrl-C, then `./run.sh` again) gives producers a new `run_id` and resets the auditor's and consumers' tracking; document it, and add anything that restart doesn't cover. Topic and consumer group cleanup on the Kafka side belongs to the user; list what to reset there.
4. **Rehearsal checklist** in the README: install the venv on the EC2 instance ahead of time, which terminal runs which client, check the tunnel or security group from the presentation network, browser zoom for projection, which tabs to have open and in what order, the failover steps in order with the marker to click after each, how to reset between runs.

## Known risks and things to verify, not assume

Verify these from the docs where possible. Where only a running system can answer, make the answer an explicit step in `TESTING.md`.

- Whether the gateway passes the backing cluster ID through.
- What clients see from a fenced gateway, compared with a stopped one.
- Every broker address the gateway advertises must be reachable from the EC2 instance, not only the bootstrap address.
- Idempotent producer behaviour when the backing cluster changes.
- Consumer offset sync interval, and how much replay it causes.
- Behaviour of identity passthrough authentication across a switchover, if the gateway uses it (the gateway docs have a troubleshooting entry for it).
- librdkafka statistics field names: https://github.com/confluentinc/librdkafka/blob/master/STATISTICS.md
- librdkafka configuration semantics, especially `message.timeout.ms`, `queue.buffering.max.messages` and the reconnect backoff settings: https://github.com/confluentinc/librdkafka/blob/master/CONFIGURATION.md

## Out of scope

Everything on the Kafka side: clusters, Confluent Gateway, cluster links, mirror topics, offset sync, and performing the switchover (see "Scope"). Also Kafka Streams, transactions, Schema Registry switchover, Kubernetes deployment, and clients in other languages. The event contract is designed so a Java client could be added later by implementing only the emitter.

## Definition of done

On the EC2 instance, with the venv installed and `.env` filled in, `./run.sh preflight` passes, and `./run.sh <name>` in one terminal each starts the clients, the console and the auditor. From the workstation, the presenter opens the console and the client UIs, performs a failover from A to B and back by hand, and marks each step in the console. Every client UI tells the "healthy but waiting, then back online" story without explanation, the console timeline tells it in order, and `scripts/report.sh` confirms the tuned producer lost nothing.
