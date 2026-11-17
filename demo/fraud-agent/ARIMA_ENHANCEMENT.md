# ARIMA Enhancement: Parallel Pipeline Architecture

**Date:** 2026-07-02  
**Status:** Implemented

## Overview

This document describes the integration of ARIMA-based statistical anomaly detection with session-based activity profiling in the fraud detection pipeline. The enhancement combines two independent windowing strategies through a parallel pipeline architecture.

## Problem Statement

The original fraud detection system used session-based activity profiling:
- **Input:** Raw event streams (transactions, logins, account changes)
- **Processing:** 3-second SESSION windows to capture burst activity
- **Output:** Activity profiles sent to fraud detection agent

**Limitation:** No statistical baseline for "normal" vs "anomalous" spending patterns. The agent analyzed all profiles equally, making it harder to distinguish legitimate high-value purchases from actual fraud.

**Goal:** Add ARIMA time-series anomaly detection to pre-filter activity profiles, sending only statistically anomalous patterns to the agent.

## Initial Approach (Failed)

**Attempted flow:**
```
transactions → TUMBLE(15s) → ARIMA → anomalous_windows
                                          ↓
                                   JOIN transactions
                                          ↓
                                 anomalous_transactions
                                          ↓
                       UNION(user_logins, account_changes)
                                          ↓
                                   SESSION(3s)
                                          ↓
                                   activity_profiles
```

**Critical error:** Time attribute preservation failure
```
The window function requires the timecol is a time attribute type, 
but is TIMESTAMP_WITH_LOCAL_TIME_ZONE(3).
```

**Root cause:** Flink SQL time attributes are **lost** when materializing through CTAS:
1. `transactions.event_time` is a **time attribute** (computed column with watermark)
2. After `CREATE TABLE anomalous_transactions AS SELECT t.event_time FROM transactions t JOIN ...`, `anomalous_transactions.event_time` becomes a **regular TIMESTAMP_LTZ(3)** (time attribute property is stripped)
3. UNION of time attribute (from base table) + regular timestamp (from CTAS) → result is regular timestamp
4. SESSION window requires time attribute → fails

**Key insight from CC Flink Reference (Trap #8):**
> `$rowtime AS alias` in CTE silently strips time-attribute property; watermarks break downstream

**Extrapolated rule:**
- Time attributes exist **only** in base table computed columns with watermarks
- CTAS results lose time attribute properties → become regular timestamps
- **Never** try to window on CTAS-derived timestamp columns
- **Do** windowing on base tables, **then** materialize, **then** join

## Solution: Parallel Pipeline Architecture

Instead of trying to preserve time attributes through joins and re-windowing, we split the processing into two **independent** parallel pipelines that each do their own windowing, then join the **materialized results**.

### Architecture Diagram

```
┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐
│   Path 1: Activity Profiling        │    │   Path 2: Anomaly Detection         │
│                                      │    │                                     │
│  transactions (base table)           │    │  transactions (base table)          │
│  user_logins (base table)            │    │         ↓                           │
│  account_changes (base table)        │    │  TUMBLE(15s windows)                │
│         ↓                            │    │         ↓                           │
│  UNION ALL (preserves time attrs)    │    │  GROUP BY user_id, window           │
│         ↓                            │    │         ↓                           │
│  SESSION(3s inactivity gap)          │    │  ML_DETECT_ANOMALIES (ARIMA)        │
│         ↓                            │    │    - minTrainingSize: 8             │
│  GROUP BY + LISTAGG                  │    │    - maxTrainingSize: 100           │
│         ↓                            │    │    - confidencePercentage: 95%      │
│  CTAS → activity_profiles            │    │         ↓                           │
│    (materialized, regular timestamps)│    │  Filter: is_anomaly=TRUE            │
│                                      │    │          total > upper_bound        │
│                                      │    │         ↓                           │
│                                      │    │  CTAS → anomalous_windows           │
│                                      │    │    (materialized, regular timestamps)│
└──────────────┬───────────────────────┘    └────────────┬────────────────────────┘
               │                                         │
               └────────────── JOIN ─────────────────────┘
                     ON user_id AND window overlap
                              ↓
                      anomalous_profiles
                              ↓
                   enrich with ARIMA context
                              ↓
                anomalous_profiles_enriched
                              ↓
                        AI_RUN_AGENT
                              ↓
                        fraud_alerts
```

### Why This Works

**Path 1 (Activity Profiling):**
- UNION ALL on **base tables** → all have time attributes → preserves time attribute property
- SESSION window operates on proper time attribute
- CTAS materializes result → `window_start`/`window_end` become regular timestamps (windowing complete)

**Path 2 (Anomaly Detection):**
- TUMBLE window on **base table** → has time attribute
- ARIMA detection on aggregates
- CTAS materializes result → `window_start`/`window_end` become regular timestamps (windowing complete)

**Join:**
- Both sides are **regular tables** with **regular timestamp columns**
- No time attributes needed → simple temporal overlap join
- Overlap condition: `p.window_start < w.window_end AND p.window_end > w.window_start`

## Pipeline Stages

### Stage 1: ARIMA Scoring (All Windows)

**Table:** `arima_scored_windows`

```sql
CREATE TABLE arima_scored_windows (
  user_id STRING NOT NULL,
  window_start TIMESTAMP_LTZ(3) NOT NULL,
  window_end TIMESTAMP_LTZ(3),
  txn_count BIGINT,
  total_amount DOUBLE,
  expected_amount DOUBLE,  -- ARIMA forecast
  upper_bound DOUBLE,
  lower_bound DOUBLE,
  is_anomaly BOOLEAN,
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH ('changelog.mode' = 'append');
```

**Purpose:** Score **all** 15-second spending windows with ARIMA, providing observability into normal vs anomalous patterns.

### Stage 2: Filter to Anomalous Windows

**Table:** `anomalous_windows`

```sql
SELECT * FROM arima_scored_windows
WHERE is_anomaly = TRUE 
  AND total_amount > upper_bound;
```

**Purpose:** Narrow to windows that are both statistically anomalous **and** exceed the upper confidence bound.

### Stage 3: Build Activity Profiles (All Users)

**Table:** `activity_profiles`

```sql
WITH unified AS (
  SELECT user_id, event_type, event_time, line
  FROM transactions
  UNION ALL
  SELECT user_id, event_type, event_time, line
  FROM user_logins
  UNION ALL
  SELECT user_id, event_type, event_time, line
  FROM account_changes
)
SELECT
  user_id,
  window_start,
  window_end,
  CONCAT(
    'User: ', user_id, '\n\n',
    'Transactions:\n', LISTAGG(...), '\n\n',
    'Logins:\n', LISTAGG(...), '\n\n',
    'Account changes:\n', LISTAGG(...)
  ) AS profile_text
FROM TABLE(
  SESSION(TABLE unified, DESCRIPTOR(event_time), INTERVAL '3' SECONDS)
)
GROUP BY user_id, window_start, window_end;
```

**Purpose:** Capture **burst activity** patterns. 3-second inactivity gap means rapid sequences of events (e.g., login → email change → multiple transactions) are grouped together, forming a narrative of suspicious behavior.

**Key characteristic:** Processes **all** users, not just anomalous ones. Profiling and anomaly detection are independent.

### Stage 4: Filter Profiles to Anomalous Windows

**Table:** `anomalous_profiles`

```sql
SELECT 
  p.user_id,
  p.window_start AS profile_start,
  p.window_end AS profile_end,
  p.profile_text,
  w.window_start AS arima_window_start,
  w.window_end AS arima_window_end,
  w.total_amount AS window_total,
  w.expected_amount,
  w.upper_bound,
  w.lower_bound
FROM activity_profiles p
INNER JOIN anomalous_windows w
  ON p.user_id = w.user_id
  AND p.window_start < w.window_end
  AND p.window_end > w.window_start;
```

**Purpose:** Combine session-based burst detection with statistical anomaly detection. Only profiles that **temporally overlap** with ARIMA-flagged windows proceed to the agent.

**Overlap semantics:** A session window that touches an anomalous ARIMA window gets flagged, even if the session includes some events outside the ARIMA window. This preserves full context (e.g., a login at t=13s followed by anomalous spending at t=16s).

### Stage 5: Enrich with ARIMA Context

**Table:** `anomalous_profiles_enriched`

**Purpose:** Prepend ARIMA anomaly context to the activity profile text. The agent sees both the statistical signal (spending is 3x higher than expected) and the detailed activity narrative.

### Stage 6: Agent Analysis

**Table:** `fraud_alerts`

**Purpose:** Run the fraud detection agent only on profiles that were pre-filtered by ARIMA. The agent performs contextual analysis on top of the statistical signal.

**Agent's updated role:** No longer analyzing raw volume/velocity (ARIMA already flagged that). Instead, looks for supporting fraud signals:
- Geographic impossibility (transaction in NYC, login in Tokyo minutes apart)
- Account takeover (email change + password change + rapid purchases)
- Device/IP anomalies combined with ARIMA anomaly
- Contextual mismatch (ARIMA flagged it but context suggests legitimate holiday shopping)

## Key Implementation Details

### PRIMARY KEYs and Kafka Message Keys

All intermediate tables use `PRIMARY KEY (user_id) NOT ENFORCED` with `'changelog.mode' = 'append'`:

**Effect:**
- Kafka message key = `user_id` only (not compound key with window timestamps)
- All events for the same user go to the same partition
- Multiple windows for the same user are separate append-only messages
- Window columns remain in the message value/payload

**Rationale:** Partitioning by user ensures co-location of related events, enabling downstream consumers to maintain per-user state efficiently.

### CREATE TABLE + INSERT INTO Pattern

Each intermediate table is defined using two modules:
1. **CREATE TABLE module** - defines schema with PRIMARY KEY
2. **INSERT INTO module** - contains the query logic

**Rationale:** CTAS (CREATE TABLE AS SELECT) in Confluent Cloud Flink doesn't support PRIMARY KEY definitions. The two-module pattern enables both message keys and append-only semantics.

### Watermark Idle-Timeout Pinning

The `insert_activity_profiles` module uses `extra_properties = { "sql.tables.scan.idle-timeout" = "5 s" }`.

**Problem:** Confluent Cloud's default "progressive idleness" grows the idle-partition timeout with statement age (10s → up to 5 min). With 6-partition topics and a producer that only touches some users per cycle, the session-window watermark stalls as the statement ages → alerts dry up.

**Solution:** Pin idle-timeout to 5s. The watermark advances even when some partitions are idle, so session windows close and profiles flow continuously.

## Window Semantics: Both SESSION

**ARIMA windows (SESSION):**
- Variable-length windows with 3-second inactivity gap
- Per-user partitioning (`PARTITION BY user_id`) - separate session streams per user
- Event-driven: window extends until 3s of silence
- Each session produces one aggregate: `total_amount = SUM(transaction amounts in session)`
- Purpose: Analyze spending patterns at activity-burst granularity

**Activity profiles (SESSION):**
- Identical SESSION parameters to ARIMA (`PARTITION BY user_id`, 3-second gap)
- Captures full narrative of each activity burst
- Perfect 1:1 alignment with ARIMA windows (same session = same window boundaries)

**Benefits of SESSION for both:**
- **Semantic clarity**: Each analysis unit is a user activity burst, not an arbitrary time slice
- **Perfect alignment**: Same window boundaries for ARIMA and profiling → 1:1 join on `(user_id, window_start)`
- **Natural fraud capture**: Variable fraud durations (1-1.5s) fit naturally in variable-length sessions
- **Adaptive**: Long fraud bursts (e.g., 6 rapid transactions over 1.5s) captured in one window, closed after 3s idle

**ARIMA on irregular intervals:**
ARIMA analyzes the **sequence of session aggregates** across time:
```
User user-001:
  Session 1 (t=1.2-4.8s):  total=$105
  [14s gap - no activity]
  Session 2 (t=18.3-21.5s): total=$850  ← ARIMA detects anomaly
  [11s gap]
  Session 3 (t=32.1-34.9s): total=$95
```

The irregular gaps between sessions are acceptable because ARIMA forecasts **"what should the next session total be?"** based on historical session totals, not time-of-day patterns. Each session is one data point in the time series, regardless of the gap to the previous session.

## Benefits of Parallel Pipeline Architecture

1. **Separation of concerns:**
   - ARIMA handles statistical baseline (volume/velocity anomalies)
   - SESSION windows handle burst detection (rapid event sequences)
   - Agent handles contextual analysis (geo-impossible, account takeover, etc.)

2. **No time attribute issues:**
   - Each path does its own windowing on base tables
   - Join happens on materialized results with regular timestamps
   - No need to preserve time attributes through complex query chains

3. **Observability:**
   - `arima_scored_windows` topic shows all scored windows (normal + anomalous)
   - `activity_profiles` topic shows all session-windowed profiles
   - `anomalous_profiles` topic shows filtered result of join

4. **Alignment:**
   - ARIMA and activity profiling use identical SESSION parameters (3s gap, partitioned by user_id)
   - Perfect 1:1 window correspondence enables exact equality join
   - Can adjust ARIMA confidence threshold without changing profiling logic
   - Can modify profile text format without touching ARIMA logic
   - **Note**: SESSION gap must remain synchronized between both paths to maintain alignment

5. **Efficiency:**
   - Agent only analyzes pre-filtered profiles (reduces LLM invocations)
   - ARIMA pre-filtering reduces false positives reaching the agent
   - Partitioning by user_id ensures efficient state management

## Trade-offs

**Cons:**
- Two identical SESSION windowing operations (ARIMA + profiling) = duplicate state per session
- Profiles for **all** users, not just anomalous ones (could be optimized in production)
- ARIMA trained on irregular intervals (gaps between sessions vary by user activity)

**Pros from SESSION alignment:**
- Perfect 1:1 window correspondence (no many-to-many joins)
- Simpler join condition (exact equality vs temporal overlap)
- Semantically meaningful analysis units (activity bursts, not arbitrary time slices)

**Empirical validation needed:**
- Does Flink's `ML_DETECT_ANOMALIES` handle irregular session timing well?
- Does forecast accuracy degrade compared to regular TUMBLE intervals?
- How long to accumulate `minTrainingSize: 8` sessions for typical users?

**Production optimization:** For very high-volume deployments, Path 1 could be modified to only profile users with recent anomalous windows (requires tracking user state).

## Files Modified

- `terraform/flink.tf`: All ARIMA and activity profiling logic
  - Lines 182-292: ARIMA scoring + filtering (2 modules each for CREATE + INSERT)
  - Lines 603-691: Activity profiling (2 modules for CREATE + INSERT)
  - Lines 693-759: Anomalous profiles join + enrichment (4 modules)
  - Lines 836-895: Detection statement (updated to read from enriched profiles)

## References

- Original activity profiling: `.justin/old/activity_profiles.sql`
- Reference ARIMA pattern: `.justin/reference/claims_anomalies_by_city.sql`
- Confluent Cloud Flink SQL reference: `.justin/cc-flink-complete-reference.md`
- Time attribute trap #8: "Aliasing $rowtime in CTE strips time-attribute property"
