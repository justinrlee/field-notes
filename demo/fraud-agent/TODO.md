# TODO

## Update demo screenshots

The screenshots in `images/demo/` (used by `demo.md`) and `images/fraud-detection-dashboard.png`
(used by the README) were captured on the earlier pipeline (`activity_profiles` → `fraud_alerts`).
Recapture them against a live deployment of the current pipeline
(`user_activity_scored` → `user_activity_anomalous` → `user_activity_anomalous_enriched` →
`fraud_analysis_results`). Run the producer with `--both` first so ARIMA has a baseline.

Must update (content changed):

- [x] `01-stream-lineage-overview.png` — split into `01a-lineage-ingest-scoring.png` and `01b-lineage-agent-verdicts.png` (shared node: `user_activity_anomalous`); old file removed
- [ ] `06-flink-job-node.png` — now the materialized-table nodes, not two statements (Stream Lineage currently shows them as generic `sys-lkc-…` Flink Statement nodes; `demo.md` step 6 notes this known issue — remove the note when fixed)
- [x] `07-flink-union.png` — SQL now lives in the `user_activity_scored` query
- [x] `08-session-window-a.png` — query/result is now `user_activity_scored`
- [x] `08-session-window-b.png` — `SELECT * FROM user_activity_scored` (adds ARIMA columns)
- [x] `12-ai-run-agent.png` — now in the `fraud_analysis_results` query, reading `enriched_profile_text` (optional: crop the red lint marker in the line-1 gutter)
- [x] `13-fraud_analysis_results-topic.png` — renamed from `13-fraud-alerts-topic.png`
- [ ] `14-select-fraud_analysis_results.png` — renamed from `14-select-fraud-alerts.png`, but it shows a plain `SELECT *` (mostly low scores) while `demo.md` step 14 says `WHERE risk_score >= 70`; either recapture with the filter or change the step 14 query text
- [ ] `15-dashboard-overview.png` — recaptured, but ARIMA ANOMALIES / ANOMALY RATE / FRAUD ALERTS tiles read 0 while the charts show alerts, and the user filter box contains "49"; recapture
- [ ] `16-dashboard-critical-alert.png` — recaptured, but `$` in reasoning text renders as LaTeX/code ("783.64vsexpected"); fix in `dashboard/app.py` (escape `$`) then recapture
- [ ] `17-recap-lineage.png` — also used in the README intro (the lineage graph is wide; consider using one of the 01a/01b halves or stacking both)
- [x] `../fraud-detection-dashboard.png` — README header image (dashboard v2)

Check, may still be accurate:

- [x] `03-transactions-topic.png`, `04-user-logins-topic.png`, `05-account-changes-topic.png` — recaptured
- [ ] `02-producer-node.png` — source side is unchanged, but the producer node name may differ
- [ ] `09-create-model.png` — model unchanged; confirm it still matches the deployed `CREATE MODEL`
- [x] `10-create-tools.png` — tools unchanged (verified)
- [ ] `11-create-agent.png` — recaptured, but it shows the OLD prompt ("3-second window" total, `[WINDOW ANOMALY: total=$X, expected=$Y]`); recapture after the agent prompt fix below

New screenshots to consider adding:

- [ ] `SELECT * FROM user_activity_anomalous` result, for demo step 8b

When done (all boxes above checked, or the remaining ones consciously accepted):

- [ ] Remove the "screenshots in this walkthrough were captured on an earlier version" note after step 1 in `demo.md`
- [ ] Remove the "screenshots predate it" remark from the `demo.md` row of the repository map in `AGENTS.md`
- [ ] Remove the Stream Lineage known-issue note in `demo.md` step 6 once materialized tables render properly in Stream Lineage (external bug), and recapture `06`/`01a`/`01b` if node names change
- [ ] Remove this section of `TODO.md`

## Dashboard fixes (`dashboard/app.py`)

- [ ] Escape `$` in the agent reasoning text (`st.markdown(f"{reasoning}")` around line 551) so dollar amounts don't render as LaTeX / inline code in Recent Fraud Analysis (seen in `16`)
- [ ] Reasoning is truncated at 150 chars (`[:150]`, around line 537), cutting mid-word ("Amazo", "legitimate ele"); truncate on a word boundary with an ellipsis, or widen
- [ ] Investigate the metric tiles in `15`: ARIMA ANOMALIES / ANOMALY RATE / FRAUD ALERTS read 0 while HIGH RISK is 4 and the charts show alerts (dashboard bug, or only an artifact of consuming from `latest`?)
- [ ] Investigate the user filter box showing "49" in `15` while the charts show other users
- [ ] Recapture `15`, `16` (and the README header image if it shows the same issues) afterwards

## Add comments around ARIMA scoring

- [ ] Document the `ML_DETECT_ANOMALIES` call in `terraform/flink.tf` (`user_activity_scored` query): why `avg_amount` per session rather than totals, why `window_time` is the ordering column, and what each option does (`minTrainingSize` 50, `maxTrainingSize` 128, `confidencePercentage` 99.95, `enableStl` false) and why those values were chosen
- [ ] Explain in `flink.tf` why `user_activity_anomalous` filters on `avg_amount > upper_bound` (only spend spikes, not dips)
- [ ] Explain in `flink.tf` why windowing and ARIMA live in the same query (time attributes are lost through CTAS / materialized tables; see `ARIMA_ENHANCEMENT.md`)
- [ ] Comment the producer's spending profiles in `producer/generate_events.py` (`USER_PROFILES`): how each profile feeds the ARIMA baseline, and why `fraud_target` users have low baselines
- [ ] Comment where `arima_scoring_active` is set in `dashboard/app.py` and how the "ARIMA scoring pending" indicator is derived
- [ ] Reconcile `ARIMA_ENHANCEMENT.md` with the code: it still describes 15s tumbling windows, `minTrainingSize` 8 / `maxTrainingSize` 100 / 95% confidence, and a separate profiles/join pipeline
- [ ] Update the agent prompt in `flink.tf`: it still refers to "15-second window" and "[WINDOW ANOMALY: total=$X, expected=$Y]" per transaction, but the pipeline now scores 3s session averages and prepends a "STATISTICAL ANOMALY DETECTED" header. Deployed prompt (visible in `11`) also says "total spending in a 3-second window". Needs `terraform apply -replace="module.agent.confluent_flink_statement.this"`, then recapture `11`
