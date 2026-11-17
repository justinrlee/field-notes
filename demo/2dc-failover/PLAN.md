# Kafka gateway switchover demo: implementation plan

This plan is written for Claude Code. Work through it phase by phase. At the end of each phase, stop, summarize what you changed, show how you verified it, and list anything you could not verify. Do not start the next phase until the current one meets its acceptance criteria.

## What the demo shows

Clients connect only to Confluent Gateway. Behind it are two Confluent Platform clusters joined by cluster links in both directions. An operator swaps the backing cluster:

1. Stop the gateway. Clients lose their connection and start retrying.
2. Reverse the cluster link, so the topic on the second cluster becomes the writable source.
3. Restart the gateway with its route pointing at the second cluster.

The point to make visible: during step 1 to 3 the client apps stay healthy. They keep running, keep accepting work, show that they are waiting, and resume on their own when the gateway returns. Afterwards, the consumers prove what was or wasn't lost or duplicated.

Confluent documents this flow as Client Switchover: https://docs.confluent.io/private-cloud-gateway/current/gateway-migrate.html. A working example lives in https://github.com/confluentinc/gateway-images/tree/master/examples/client-switchover. Start Phase 1 from that example rather than writing gateway config from memory.

## What already exists

The `client/` directory is a skeleton that has been syntax-checked and had its state logic unit-tested against a stubbed Kafka client, but it has never run against a real broker. Treat it as a starting point and fix whatever reality disagrees with.

| File | Purpose |
|---|---|
| `client/app.py` | FastAPI app. Serves the UI, `/health`, `/api/state`, `/api/events` (SSE), and producer controls `/api/send`, `/api/rate`. |
| `client/state.py` | In-process state and the event fan-out to browsers. No Kafka dependency. |
| `client/producer.py` | Sequence-numbered producer with delivery, error and stats callbacks. |
| `client/consumer.py` | Consumer with per-producer sequence checking (gap and duplicate detection). |
| `client/probe.py` | AdminClient metadata probe once per second: connectivity truth plus cluster ID. |
| `client/profiles.py` | `tuned` and `fragile` librdkafka configs, plus `KAFKA_CFG_*` env overrides. |
| `client/static/index.html` | The whole UI: one file, vanilla JS, no build step. |
| `docker-compose.yml` | Four client services: two producers (tuned, fragile) and two consumers. |

## Ground rules

- Python 3.12. No frontend build step, no bundler, no frontend framework. Each UI is a single HTML file.
- The browser talks only to its own client process. The UI must never depend on Kafka being reachable. Do not route UI state through a Kafka topic.
- `state.py` stays free of `confluent_kafka` imports so it remains unit-testable.
- The event contract below is the interface between backends and UIs. If you change it, update this file in the same change.
- Confluent-specific configuration (Gateway, Cluster Linking, Confluent Server) must come from the official docs or the gateway-images examples for the version you install. Do not invent property names. When the docs and this plan disagree, the docs win; note the discrepancy in your phase summary.
- Prefer running things over reasoning about them. Each phase has a check you can actually execute.
- The demo must work offline once images are pulled: no CDN fonts or scripts in the UIs.

## Architecture

```
 browser tabs                       client containers                 Kafka side
 ────────────                       ─────────────────                 ──────────
 producer-tuned UI  ── SSE/HTTP ──▶ producer-tuned   ─┐
 producer-fragile UI ── SSE/HTTP ─▶ producer-fragile ─┤
 consumer-1 UI      ── SSE/HTTP ──▶ consumer-1       ─┼─ Kafka protocol ─▶ Confluent Gateway ─▶ cluster A
 consumer-2 UI      ── SSE/HTTP ──▶ consumer-2       ─┤                     (switchover route)    ⇅ cluster links
 (Phase 5) auditor UI ─ SSE/HTTP ─▶ auditor          ─┘                                        cluster B
 (Phase 4) operator console ── reads every client's SSE, runs runbook steps (Docker + CLI) ──┘
```

Inside each client process:

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
- `connection`: sent immediately on a state change or cluster ID change. `data` = `{state, since, outage_started, last_outage_ms, attempts, last_error, probe_latency_ms, cluster_id}`; `state` is `connecting`, `connected` or `retrying`. The UI derives a fourth display state, "recovered", for 10 s after an outage ends.
- `metrics`: every 200 ms. `data` = `{counters, buffer, brokers, group, rate, connection}`. Counters: `queued, acked, failed, buffer_full, pending` (producer) and `consumed, gaps, missing, duplicates, rebalances` (consumer).
- `messages`: batched tile updates. `data.updates` = list of `{id, seq, state, ...}`. Producer states: `queued, acked, failed`. Consumer states: `first, ok, gap, duplicate`.
- `timeline`: one human-readable entry `{ts, kind, text}`. Kinds in use: `info, connected, outage, recovered, cluster, backpressure, failed, fatal, rate, gap, duplicate, rebalance, resume`.

Message payload produced to Kafka (JSON value, key = `producer_id`):

```json
{"producer_id": "producer-tuned", "run_id": "a1b2c3d4", "seq": 42, "msg_id": "producer-tuned-a1b2c3d4-42", "produced_at": 1760342400.123}
```

## Phase 0: make the skeleton run against one local broker

Goal: prove the client app and UI against the simplest possible Kafka, before any gateway or cluster linking.

Tasks:

1. Pin exact versions in `client/requirements.txt` to current stable releases, and confirm `pip install` uses wheels (no compiler) on the `python:3.12-slim` image.
2. Create `docker-compose.dev.yml` with a single-node KRaft broker reachable from the client containers as `broker:9092`, and a one-shot service that creates topic `orders` with 6 partitions.
3. Run the four clients from `docker-compose.yml` with `KAFKA_BOOTSTRAP=broker:9092`. Open the UIs on ports 8081 to 8084.
4. Log one real stats payload per client at startup behind a `DEBUG_STATS=1` env var and confirm the field names that `state.on_stats` reads: `brokers.*.state`, `brokers.*.connects`, `msg_cnt`, `msg_max`, `cgrp.state`, `cgrp.join_state`. Fix the code if any differ.
5. Simulate an outage with `docker compose stop broker`, wait, then start it again. Try about 20 s and about 60 s outages.
6. Fix whatever breaks. Likely candidates: SSE disconnect handling under uvicorn, consumer `close()` blocking on shutdown, the attempts counter if `connects` behaves differently than expected.
7. Add a small `tests/` directory with pytest tests for `state.py` and `consumer.SequenceTracker` (no Kafka needed). Cover the outage state machine, the delivery-before-queued race, tile eviction, and subscriber overflow resync.

Acceptance:

- Every UI shows Connected, then Waiting for Kafka with a running timer and a climbing attempt count, then Back online with the outage duration.
- `/health` returns 200 throughout, and `docker ps` shows the clients healthy during the outage.
- After a 60 s outage: `producer-tuned` shows 0 failed; `producer-fragile` shows failures (its 30 s message timeout expired) and possibly refusals; the consumers show missing messages from the fragile producer only, and none from the tuned one.
- Refreshing a browser tab mid-outage restores the full picture from the snapshot.

## Phase 1: infrastructure (two clusters, cluster links, gateway)

Goal: the real topology in `docker-compose.infra.yml`, with the Phase 0 clients working through it unchanged.

Tasks:

1. Two single-broker KRaft clusters, `cluster-a` and `cluster-b`. Cluster Linking is a Confluent Server feature, so use the Confluent Server image, not the community Kafka image. Check the licensing requirement for running enterprise features in a demo (trial period or license key) and document it in the README.
2. Cluster links in both directions, following the Confluent Platform docs for the installed version: https://docs.confluent.io/platform/current/multi-dc-deployments/cluster-linking/mirror-topics-cp.html. The docs describe reversing a mirror with the reverse-and-start and reverse-and-pause commands; confirm which link setup those commands require for the same topic name on both sides, and the exact CLI syntax (`kafka-mirrors` or the `confluent` CLI).
3. Topic `orders` (6 partitions) is the source on cluster A and a mirror topic on cluster B.
4. Enable consumer group offset sync for group `demo-consumers` on the link, using the property names from the docs.
5. Confluent Gateway with two streaming domains (one per cluster) and one switchover route, taken from the client-switchover example and https://docs.confluent.io/private-cloud-gateway/current/gateway-deploy.html. Keep two route configs side by side (for example `gateway/route-a.yaml` and `gateway/route-b.yaml`) so the switch is a file swap plus restart.
6. Broker addressing through the gateway is the most likely failure point. The docs show both a route endpoint and a per-broker address pattern. Choose the broker identification approach that works in plain Docker Compose with the least setup (start without TLS and without identity passthrough), and make sure every address the gateway advertises resolves from inside the client containers.
7. A one-shot `init` service (or `scripts/setup.sh`) that creates the topic, the links, the mirror and the offset sync, and is safe to run twice.

Acceptance:

- With `KAFKA_BOOTSTRAP=gateway:<route port>`, the four clients connect and run exactly as in Phase 0.
- Messages produced through the gateway land on cluster A and appear on cluster B's mirror topic. Show the commands you used to check.
- The cluster ID shown in the UIs matches cluster A. If the gateway reports its own ID instead of the backing cluster's, record that; Phase 3 handles it.

## Phase 2: runbook scripts

Goal: the operator procedure as repeatable scripts.

Tasks:

1. `scripts/switchover.sh <a-to-b|b-to-a>` performs, with a timestamped log line per step:
   1. Stop the gateway container.
   2. Wait until mirror lag on the destination is zero for every partition, with a timeout and a clear failure message. This is the step that prevents data loss; do not skip it.
   3. Reverse the mirror relationship so the destination becomes the source.
   4. Swap in the route config for the destination cluster.
   5. Optionally hold for `HOLD_SECONDS` (default 0) to lengthen the outage on purpose. A hold longer than 30 s makes the fragile producer's failures visible.
   6. Start the gateway.
2. `scripts/status.sh` prints which cluster is active, the link and mirror states, mirror lag, and the gateway route currently in use.
3. `scripts/reset.sh` returns everything to a clean "cluster A active" state, deleting and recreating the topic and consumer group, so rehearsals start fresh.
4. Mirror topics are read-only until reversed. Make the script refuse to start the gateway against a cluster whose `orders` topic is still a mirror.

Acceptance:

- With all clients running at 5 messages per second, `switchover.sh a-to-b` followed later by `switchover.sh b-to-a` completes cleanly.
- The UIs show one outage per switchover, Back online afterwards, and a cluster ID change (or the Phase 3 fallback).
- The tuned producer reports 0 failed across both switchovers. Record the consumers' missing and duplicate counts; they are an input to Phase 3.

## Phase 3: client hardening, driven by what Phase 2 revealed

Do the items that Phase 2 showed are needed, and explain each one in the phase summary.

1. **Cluster identity.** If the gateway does not pass the backing cluster ID through, add a fallback that still reflects the client's own view, for example a small non-mirrored topic `demo-cluster-name` on each cluster holding one record (`A` or `B`) that the probe reads. Show the chosen approach in the UI as "Cluster A" or "Cluster B" rather than a raw ID.
2. **Idempotent producer across the switch.** The new cluster has never seen the tuned producer's producer ID. Check whether the client recovers silently or raises errors (watch for fatal errors in `error_cb`). If it raises fatal errors, recreate the producer automatically, keep the same `run_id` and sequence counter, and show the recreation on the timeline.
3. **Consumer resume position.** Confirm that consumers resume on cluster B at the offsets committed on cluster A, given offset sync. Offset sync is periodic, so a small replay (shown as duplicates) is expected; measure it and explain it in the UI copy. Consider committing synchronously in `on_revoke`. If offsets are not synced at all, consumers fall back to `auto.offset.reset=latest` and the auditor will show missing messages; make sure that failure mode is visible and understood.
4. **Gateway restart effects.** The switchover docs note that consumer groups rebalance if the gateway is down longer than `session.timeout.ms`, and that producers can see duplicates when an acknowledgment is lost during the restart. Make sure both show up clearly in the UI rather than looking like bugs.
5. **Flapping.** If idle connection closes produce false `_ALL_BROKERS_DOWN` outages lasting under a second, debounce: require the probe to agree before declaring an outage.
6. **Ordering.** The switchover docs state that switching clusters does not guarantee ordering or end-to-end consistency. Do not claim strict ordering in UI copy; let the auditor report what actually happened.

## Phase 4: operator console

Goal: the presenter runs the whole demo from one page.

Tasks:

1. New service `console/`, same stack as the clients (FastAPI plus one HTML file), on host port 8080.
2. Panels for every client, built by subscribing to each client's `/api/events` from the browser (CORS is already enabled on the clients). Each panel shows: client name, display state, outage timer, cluster, and two or three key counters. Each links to the client's full UI.
3. Buttons for each runbook step and a "Run full switchover" button, which call the Phase 2 scripts from the console backend. Stream script output to the page. The console container needs the Docker socket and the Confluent CLI tools; that is acceptable for a laptop demo and must be called out in the README as unsafe anywhere else.
4. A unified timeline that merges operator steps with every client's timeline events, ordered by server timestamp.
5. A live mirror lag readout per partition, using the Kafka REST API or CLI as documented for the installed version.

Acceptance: from a fresh `reset.sh`, the presenter can run a switchover to B and back to A using only the console, and the console timeline tells the story in order.

## Phase 5: auditor, rehearsal and automated check

1. **Auditor role.** Add `ROLE=auditor`: a consumer with its own group that is the only member, reading every partition. It is the authority on missing and duplicate counts, because per-instance tracking in the regular consumers resets when a partition moves between group members. Give it its own UI variant that summarizes per producer: received, missing, duplicates, and longest gap.
2. **End-to-end check.** `scripts/e2e.sh` (or pytest with Docker) that resets, runs traffic for 60 s, performs `a-to-b` with `HOLD_SECONDS=45`, runs 60 s, performs `b-to-a`, runs 30 s, then asserts through the auditor's `/api/state`: zero missing from `producer-tuned`, and nonzero failed on `producer-fragile`. Print duplicates as information, not as a failure.
3. **Rehearsal checklist** in the README: pre-pull images, test offline, browser zoom level for projection, which tabs to have open and in what order, how to reset between runs.

## Known risks and things to verify, not assume

- The gateway image name, tag and license terms: take them from the gateway-images example.
- Whether the gateway passes the backing cluster ID through.
- The exact reverse command, its preconditions, and the link configuration it requires for the same topic name on both clusters.
- Consumer offset sync property names and sync interval.
- Behaviour of identity passthrough authentication across a switchover (the gateway docs have a troubleshooting entry for it). Start without authentication and add it only if the demo needs it.
- librdkafka statistics field names: https://github.com/confluentinc/librdkafka/blob/master/STATISTICS.md
- librdkafka configuration semantics, especially `message.timeout.ms`, `queue.buffering.max.messages` and the reconnect backoff settings: https://github.com/confluentinc/librdkafka/blob/master/CONFIGURATION.md

## Out of scope

Kafka Streams, transactions, Schema Registry switchover, TLS and authentication (unless a later phase needs them), Kubernetes deployment, and clients in other languages. The event contract is designed so a Java client could be added later by implementing only the emitter.

## Definition of done

From a clean checkout, `docker compose -f docker-compose.infra.yml -f docker-compose.yml up --build` followed by `scripts/setup.sh` brings up the full demo. The presenter can run a switchover from the console. Every client UI tells the "healthy but waiting, then back online" story without explanation. The auditor confirms the tuned producer lost nothing, and `scripts/e2e.sh` passes.
