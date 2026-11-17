# Player Struggle → Offer: a Confluent Cloud Streaming Agent demo

A player keeps dying to the same boss and is about to quit. **Confluent Cloud** spots the struggle within seconds, enriches it with who the player is, and a **Streaming Agent** (Claude on Amazon Bedrock) picks the best intervention. Usually that's a relevant product offer. **Sometimes it decides not to sell** (a minor, a spend cap) and gives a free hint or gift instead.

It is built for a multi-tenant game-infrastructure audience: one pipeline serves several (fictional) games, each with its own zones, bosses and catalog. The pitch leads with player experience, retention and **responsible monetization**; the moment the agent *declines* to upsell a minor is the one that lands.

Everything except the three small local apps (producer, trigger UI, dashboard) runs in Confluent Cloud. There is no local Kafka or Flink.

## How it works

```
producer / trigger UI (local, Avro + SASL)
  → player_combat_events · player_activity · player_profiles          (input topics; profiles = compacted upsert)
  → [player_encounters]            SESSION window per player (12 s gap) + stats
                                   + temporal join to player_profiles (enrich in-stream)
  → [player_struggle_moments]      rule-based filter: only real struggles reach the LLM
  → [player_struggle_enriched]     formats the struggle + player context as the agent's prompt
  → [player_offer_recommendations] AI_RUN_AGENT(offer_agent, ...) → parsed JSON decision
        offer_agent = Claude (Bedrock) + 3 tools:
          get_offer_catalog · check_offer_eligibility (the guardrail) · create_offer
  → dashboard (local): popup cards, decisions, latency
```

The pipeline stages are Flink **materialized tables**, so each one is a topic and a node in Stream Lineage. The three tools are mock Java UDFs (the catalog is built into a committed JAR).

## Prerequisites

- A **Confluent Cloud** account and a *Cloud resource management* API key and secret.
- An **AWS IAM user** access key with Amazon Bedrock invoke permission (`bedrock:InvokeModel`), with **model access granted** in the Bedrock console for the Claude model in your region. Use a long-lived key, not an STS key.
- **Terraform** 1.0 or later.
- **Python 3** for the local apps.
- Java and Maven are **not** needed to run the demo (`tools-udf/target/gaming-tools.jar` is committed). You only need them if you change the tool sources (JDK 17 or 21 plus Maven, then `tools-udf/build.sh`).

## Deploy

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars   # then edit: 4 credentials, identifier, region, bedrock_model_id
cd terraform && terraform init && terraform apply
```

`apply` creates the environment, Kafka cluster, Schema Registry, Flink compute pool, source tables, the pipeline, the model, tools and agent, and writes a `.env` at the repo root for the local apps. Give it a few minutes.

Use a `bedrock_model_id` that is valid for your region (the default is a `global.` inference profile; `terraform.tfvars.example` shows how to override it).

## Run the local apps

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
printf '[general]\nemail = ""\n' > ~/.streamlit/credentials.toml    # one-time, so Streamlit starts headless
./start-all.sh       # producer + trigger UI (:8080) + dashboard (:8501)
./status.sh
```

Wait until the three `create-table-*` Flink statements have completed before starting the producer (it does not register schemas). Give it a couple of minutes so the topics have data, and **open the dashboard before pressing any button** (it reads from `latest`).

| App | URL | What it is |
|---|---|---|
| Trigger UI | http://localhost:8080 | Buttons that send a scripted struggle burst for a demo player (boss wall, gear gap, rage-quit risk, two profiles, guardrail minor / capped, control) |
| Dashboard | http://localhost:8501 | Live pipeline: popup cards, agent decisions, struggle moments, encounters, latency |

Then follow [`demo.md`](demo.md) for a ~20-minute presenter walkthrough. To understand the data behind it, read [`summary.md`](summary.md).

## Tear down

```bash
./stop-all.sh
cd terraform && terraform destroy
```

## Repository map

| Path | What |
|---|---|
| `terraform/` | `main.tf` platform (environment, cluster, Flink pool, keys, ACLs); `flink.tf` source tables, model and the first two pipeline stages; `agent.tf` tools, agent and the last two stages; `modules/flink-statement/` wrapper; `connect.tf` writes `.env` |
| `producer/` | Synthetic event generator (`generate_events.py`), game and persona definitions (`gamedata.py`), Kafka/Avro plumbing (`kafka_io.py`) |
| `game-trigger/` | FastAPI trigger UI |
| `dashboard/` | Streamlit dashboard |
| `tools-udf/` | Java source and committed JAR for the three agent tools |
| `scripts/verify_topics.py` | Consume Avro topics and print counts/samples |
| `sql/prototypes/` | Throwaway Flink SQL used to settle the enrichment design |
| `.claude/skills/` | Confluent Cloud Flink SQL skill (dialect traps) used when writing the SQL |
| `demo.md` | Presenter walkthrough |
| `summary.md` | Data walkthrough: each topic, how it's generated, and what each pipeline stage does and why |
| `DESIGN.md` · `AGENTS.md` · `TODO.md` | Design notes, working conventions and gotchas, and the checklist of things to run and verify |

Notes: the producer's profile re-send interval, the session gap and the watermark delays are the main latency knobs. See `AGENTS.md` for the gotchas (agent hardening, idle-timeout, read-uncommitted consumers).
