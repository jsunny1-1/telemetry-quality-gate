# Five-minute demonstration

## 0:00 to 0:45: Establish the decision

"Two fictional brands want one operational dashboard. Before automating action from that dashboard, can we tell the difference between a broken device, missing data and delayed data?"

Show the six-device inventory. Ask who owns device identity, freshness expectations and operational escalation. A monitoring platform cannot infer devices that never report unless a separate source defines what should exist.

## 0:45 to 2:00: Reproduce the evidence

Run the command in the README. Point to these three rows:

1. `cedar-01-router`: its event arrived one second before evaluation, but the observation is ten minutes old. Treating receipt time as freshness would produce false confidence.
2. `cedar-02-terminal`: a fresh explicit error, so the device is degraded.
3. `harbor-01-terminal`: no valid observation, so state is unknown. An investigation belongs with telemetry owners before claiming a device outage.

Then show the record accounting: 11 records become four accepted observations, one exact replay, two conflicting records and four invalid records. Explain why dropping duplicates differs from discarding conflicting evidence.

## 2:00 to 3:00: Explain a subtle tradeoff

`cedar-02-router` has a fresh `ok` observation but a 150-second delivery delay. Its device state is healthy while the rollout quality gate fails its delivery budget. Device health and telemetry delivery are different decisions.

Conflicting event IDs are quarantined, which can reduce apparent coverage. That is intentional here: silently choosing a winner could conceal a producer or replay bug. A real implementation needs accountable triage and access to original records.

## 3:00 to 4:00: Show tests and make one change

Run `python3 -m unittest -v`. The tests exercise recent receipt of old data, out-of-order arrival, conflicting IDs, timezone equivalence, attribution failure and exit codes.

Optionally rerun with `--delivery-budget 180`. The late-but-fresh router now meets the delivery budget, but the stale router and other faults keep the gate failed. Changing an acceptance threshold cannot repair missing telemetry.

## 4:00 to 5:00: Close on adoption and limitations

Explain how you would establish a baseline, run the evaluator in shadow mode, review false classifications with operators, then canary a bounded device cohort. Do not automatically page on every unknown device or enable remediation directly from this snapshot.

Be ready to answer:

- What makes inventory trustworthy, and how are replacements or site moves handled?
- What if the collector cannot supply reliable source event time?
- When should a conflicting ID reject the entire batch versus just affected records?
- How would durable deduplication, retention windows and backpressure change the design?
- What additional signal proves an actual customer transaction can complete?

This is a prepared, synthetic demonstration. Describe any modifications or experiments you personally performed, and keep them distinct from the AI-assisted starting implementation.
