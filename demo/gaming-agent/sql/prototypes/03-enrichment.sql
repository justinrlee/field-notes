-- =============================================================================
-- Step 3: enrichment prototype (DESIGN.md §4, option 1: event-time temporal join).
--
-- RUN BY THE USER in a Flink workspace (Claude does not run anything). Run each numbered
-- block as its own statement, in order, and report the results (see TODO.md, Step 3).
-- Needs the producer running (./start-producer.sh) so events and profile heartbeats flow.
--
-- Questions this answers:
--   Q1  Does a temporal join of raw events against player_profiles work at all?
--   Q2  Can the join happen on the windowed result (window_time stays a time attribute
--       inside the same query)?                                -> "join inside player_encounters"
--   Q3  Does a downstream table (materialized output) still have a usable time attribute via
--       `$rowtime`, so enrichment can be its own stage?        -> "separate player_struggle_enriched"
--   Q4  Does the join stall if profiles go quiet (no heartbeat)?
--
-- Conventions: every identifier is backquoted (timestamp/value etc. are reserved words);
-- no backslash escapes in literals (Flink SQL doesn't process them); session gap 12 s.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 0. Sanity (run first; each as its own statement)
-- -----------------------------------------------------------------------------
SET 'sql.tables.scan.idle-timeout' = '5 s';

DESCRIBE EXTENDED `player_profiles`;
-- Expect: PRIMARY KEY (`player_id`), changelog.mode upsert, watermark on `event_time`.

SELECT COUNT(DISTINCT `player_id`) AS `profiles` FROM `player_profiles`;
-- Expect 53 (45 simulated + 8 demo-*). Stop the query once it shows 53.


-- -----------------------------------------------------------------------------
-- Q1. Temporal join: raw events -> profiles (no window)
-- -----------------------------------------------------------------------------
SELECT
  e.`player_id`, e.`event_type`, e.`zone_id`, e.`source_id`,
  p.`tier`, p.`level`, p.`is_minor`, p.`monthly_cap`, p.`spend_30d`,
  e.`event_time`,
  TIMESTAMPDIFF(SECOND, e.`event_time`, CURRENT_TIMESTAMP) AS `lag_s`
FROM `player_combat_events` e
JOIN `player_profiles` FOR SYSTEM_TIME AS OF e.`event_time` AS p
  ON e.`player_id` = p.`player_id`
WHERE e.`event_type` = 'DEATH';
-- Expect: DEATH rows (a few per minute) with profile columns filled in.
-- Report: does it return rows? typical `lag_s`? (join waits for the profile watermark, so
-- lag_s ~ up to the profile heartbeat interval is plausible; large/growing lag_s = stall.)


-- -----------------------------------------------------------------------------
-- Q2-pre. Plan check (EXPLAIN only; costs nothing). The first Q2 attempt failed because the
-- session window was planned as a regular `GroupAggregate` (emits updates: [I,UB,UA]) instead of a
-- window aggregate (append-only). The group keys must be exactly the PARTITION BY key plus the
-- window columns (no extra keys such as game_id; carry it with MAX()).
-- Look at the plan: you want a window aggregate node and changelogMode=[I] all the way up;
-- `GroupAggregate ... changelogMode=[I,UB,UA]` means it is still wrong.
-- -----------------------------------------------------------------------------
EXPLAIN
WITH `unified` AS (
  SELECT `player_id`, `game_id`, `event_time`, `event_type` AS `kind`, `damage_amount`
  FROM `player_combat_events`
  UNION ALL
  SELECT `player_id`, `game_id`, `event_time`, `activity_type` AS `kind`, 0 AS `damage_amount`
  FROM `player_activity`
)
SELECT `player_id`, MAX(`game_id`) AS `game_id`, `window_start`, `window_end`, `window_time`,
       COUNT(*) AS `events`
FROM TABLE(
  SESSION(TABLE `unified` PARTITION BY `player_id`, DESCRIPTOR(`event_time`), INTERVAL '12' SECONDS)
)
GROUP BY `player_id`, `window_start`, `window_end`, `window_time`;


-- -----------------------------------------------------------------------------
-- Q2. Join INSIDE the windowing query (join on window_time)
--     This is the likely shape of player_encounters if the enrichment lives there.
-- -----------------------------------------------------------------------------
WITH `unified` AS (
  SELECT `player_id`, `game_id`, `event_time`, `event_type` AS `kind`,
         `damage_amount`,
         CONCAT(`event_type`, ' ', `source_id`, ' (', CAST(`damage_amount` AS STRING), ') in ', `zone_id`) AS `line`
  FROM `player_combat_events`
  UNION ALL
  SELECT `player_id`, `game_id`, `event_time`, `activity_type` AS `kind`,
         0 AS `damage_amount`,
         CONCAT(`activity_type`, COALESCE(CONCAT(' ', `item_id`), '')) AS `line`
  FROM `player_activity`
),
`windowed` AS (
  SELECT
    `player_id`, MAX(`game_id`) AS `game_id`, `window_start`, `window_end`, `window_time`,
    COUNT(CASE WHEN `kind` = 'DEATH' THEN 1 END) AS `deaths`,
    SUM(`damage_amount`) AS `damage_taken`,
    COUNT(CASE WHEN `kind` = 'QUEST_FAIL' THEN 1 END) AS `quest_fails`,
    COUNT(*) AS `events`,
    LISTAGG(`line`, ' | ') AS `activity`
  FROM TABLE(
    SESSION(TABLE `unified` PARTITION BY `player_id`, DESCRIPTOR(`event_time`), INTERVAL '12' SECONDS)
  )
  GROUP BY `player_id`, `window_start`, `window_end`, `window_time`
)
SELECT
  w.`player_id`, w.`game_id`, w.`window_end`,
  w.`deaths`, w.`damage_taken`, w.`quest_fails`, w.`events`,
  p.`tier`, p.`level`, p.`is_minor`, p.`monthly_cap`, p.`spend_30d`, p.`owned_skus`,
  TIMESTAMPDIFF(SECOND, w.`window_time`, CURRENT_TIMESTAMP) AS `lag_s`
FROM `windowed` w
JOIN `player_profiles` FOR SYSTEM_TIME AS OF w.`window_time` AS p
  ON w.`player_id` = p.`player_id`;
-- Expect: one row per player session window (roughly one per player scene), profile columns
-- filled. `lag_s` = delay after the window closes; want single digits.
-- Report: works? any error text (verbatim)? typical `lag_s`?


-- -----------------------------------------------------------------------------
-- Q3. Separate stage: does `$rowtime` work downstream of a materialized output?
--     (The fraud repo's notes say time attributes are lost after CTAS; the Bob skill's traps
--     file says `$rowtime` survives. This block settles it for the *output* table.)
--
--     3a. Materialize the windowed result into a scratch table (continuous statement!).
--         NOTE: the first run omitted 'kafka.consumer.isolation-level' = 'read-uncommitted'. Flink sinks
--         write transactionally and commit on checkpoint, so read-committed readers (3b/3c) see rows only
--         after the commit -> inflated lag. Re-run 3a/3b/3c (drop the old scratch table first) with it set.
-- -----------------------------------------------------------------------------
CREATE TABLE `scratch_windowed`
WITH (
  'changelog.mode' = 'append',
  'kafka.consumer.isolation-level' = 'read-uncommitted'
)
AS
WITH `unified` AS (
  SELECT `player_id`, `game_id`, `event_time`, `event_type` AS `kind`,
         `damage_amount`,
         CONCAT(`event_type`, ' ', `source_id`, ' (', CAST(`damage_amount` AS STRING), ') in ', `zone_id`) AS `line`
  FROM `player_combat_events`
  UNION ALL
  SELECT `player_id`, `game_id`, `event_time`, `activity_type` AS `kind`,
         0 AS `damage_amount`,
         CONCAT(`activity_type`, COALESCE(CONCAT(' ', `item_id`), '')) AS `line`
  FROM `player_activity`
)
SELECT
  `player_id`, MAX(`game_id`) AS `game_id`, `window_start`, `window_end`, `window_time`,
  COUNT(CASE WHEN `kind` = 'DEATH' THEN 1 END) AS `deaths`,
  SUM(`damage_amount`) AS `damage_taken`,
  COUNT(CASE WHEN `kind` = 'QUEST_FAIL' THEN 1 END) AS `quest_fails`,
  COUNT(*) AS `events`,
  LISTAGG(`line`, ' | ') AS `activity`
FROM TABLE(
  SESSION(TABLE `unified` PARTITION BY `player_id`, DESCRIPTOR(`event_time`), INTERVAL '12' SECONDS)
)
GROUP BY `player_id`, `window_start`, `window_end`, `window_time`;

-- 3b. Inspect the scratch table's time semantics (wait ~1 min for rows):
DESCRIBE EXTENDED `scratch_windowed`;
SELECT `player_id`, `window_time`, `$rowtime` AS `kafka_ts` FROM `scratch_windowed`;
-- Report: is `window_time` still a time attribute (DESCRIBE shows rowtime/watermark?), and is
-- `$rowtime` ~= `window_time` (event time) or ~= wall-clock at write?

-- 3c. Temporal join downstream, on `$rowtime`:
SELECT
  s.`player_id`, s.`game_id`, s.`deaths`, s.`events`,
  p.`tier`, p.`level`, p.`is_minor`, p.`monthly_cap`,
  TIMESTAMPDIFF(SECOND, s.`$rowtime`, CURRENT_TIMESTAMP) AS `lag_s`
FROM `scratch_windowed` s
JOIN `player_profiles` FOR SYSTEM_TIME AS OF s.`$rowtime` AS p
  ON s.`player_id` = p.`player_id`;
-- Report: works? error text? typical `lag_s`?

-- 3d. CLEANUP: stop the CTAS statement first (Flink UI / `confluent flink statement stop`), then:
--     DROP TABLE `scratch_windowed`;     -- deletes the scratch topic + its schema subjects. Ours; safe.


-- -----------------------------------------------------------------------------
-- Q4. Stall test (profiles go quiet)
--     Restart the producer with a very long heartbeat so profiles are seeded once and then
--     change only on purchases/level-ups:
--         ./stop-all.sh   (or kill the producer)
--         ./venv/bin/python producer/generate_events.py --heartbeat-secs 100000
--     then re-run Q1 (or Q2) in a NEW statement and watch for ~5 minutes.
-- Report: does output keep flowing at a steady rate, or dry up after the initial burst?
--   Keeps flowing -> the 5 s idle-timeout lets the join advance; heartbeat is just insurance.
--   Dries up      -> keep the 5 s heartbeat (default) and tell Claude.
-- -----------------------------------------------------------------------------


-- -----------------------------------------------------------------------------
-- Q5. Latency isolation: windowed result ONLY (no profile join)
--     Q2 showed lag_s ~15-25 s and the scratch CTAS wrote rows ~40 s after window_time, so most
--     of the delay may be the window/watermark itself, not the join. This tells us.
--
--     Before running: STOP every other prototype statement (Q1, Q2, Q3 SELECTs and the
--     scratch_windowed CTAS). They share a 10-CFU pool and compete with each other, which can
--     inflate lag. Run this alone for ~3 minutes after it has caught up (ignore the first rows:
--     catch-up of the backlog from earliest offsets shows up as huge lag_s).
--
--     Also confirm the idle-timeout is really applied to THIS statement: run the SET and then
--     `SET;` (lists active config) in the same workspace tab right before the query.
-- -----------------------------------------------------------------------------
SET 'sql.tables.scan.idle-timeout' = '5 s';
SET;

WITH `unified` AS (
  SELECT `player_id`, `game_id`, `event_time`, `event_type` AS `kind`, `damage_amount`
  FROM `player_combat_events`
  UNION ALL
  SELECT `player_id`, `game_id`, `event_time`, `activity_type` AS `kind`, 0 AS `damage_amount`
  FROM `player_activity`
)
SELECT
  `player_id`, `window_end`, `window_time`,
  COUNT(CASE WHEN `kind` = 'DEATH' THEN 1 END) AS `deaths`,
  COUNT(*) AS `events`,
  TIMESTAMPDIFF(SECOND, `window_time`, CURRENT_TIMESTAMP) AS `lag_s`
FROM TABLE(
  SESSION(TABLE `unified` PARTITION BY `player_id`, DESCRIPTOR(`event_time`), INTERVAL '12' SECONDS)
)
GROUP BY `player_id`, `window_start`, `window_end`, `window_time`;
-- Report: steady-state lag_s (after catch-up), and whether `SET;` showed the 5 s idle-timeout.
--   lag_s here ~ same as Q2 -> the window/watermark dominates; the join adds little.
--   lag_s here much lower   -> the profile join is the bottleneck.
