# Gaming Offer Agent Tools (Flink UDFs)

Three Java `ScalarFunction` UDFs exposed to the Streaming Agent as function-based tools. All return
JSON strings.

| Function | Signature (all but `level`/`discount_pct`/`ttl_seconds` are STRING) | What it does |
|----------|------|------|
| `get_offer_catalog` | `(game_id, player_class, level INT, zone_id, source_id)` | Candidate SKUs for this game, ranked by relevance to the boss/zone, plus free options. The catalog is built into the JAR. |
| `check_offer_eligibility` | `(player_id, is_minor, spend_30d, monthly_cap, last_purchase_ts)` | The guardrail: is a paid offer allowed (minor / monthly cap / cooldown)? |
| `create_offer` | `(player_id, sku, discount_pct INT, ttl_seconds INT, channel)` | The action. Mock: returns a confirmation, no side effect. |

`check_offer_eligibility` takes the profile values as arguments (copied from the prompt by the agent)
because a UDF has no state. The "cooldown" is a proxy: a purchase in the last 15 minutes.

The SKU/zone/boss ids must match `producer/gamedata.py`.

## Build (once, then commit the JAR)

JDK 17 or 21 plus Maven; the pom compiles for Java 11, which is what Confluent Cloud supports.

```bash
./build.sh        # produces target/gaming-tools.jar
```

`target/gaming-tools.jar` is committed (the `.gitignore` un-ignores it) and Terraform uploads it.
Demo users do not need Java or Maven; only rebuild when the sources change.
