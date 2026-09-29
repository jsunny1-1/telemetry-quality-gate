# Discovery and acceptance notes

## Illustrative customer problem

A fictional operator wants consistent visibility across two brands without sending support teams to investigate every data gap as a device outage. This project tests the data contract supporting that goal. It does not claim a real engagement or measured commercial outcome.

| Stakeholder | Decision they need | Discovery question |
| --- | --- | --- |
| Operations | Investigate a device or investigate visibility? | Which transaction or service failure is actionable, and who responds? |
| Device engineering | Are observations correctly identified and ordered? | Who creates immutable event IDs and maintains source clocks? |
| Platform owner | Can several consumers trust the same contract? | Where do inventory, retries and raw record retention live? |
| Brand stakeholder | Is coverage sufficient for rollout? | Which sites/devices are in scope, and what freshness is acceptable? |

## Acceptance criteria demonstrated by the code

1. Every expected device appears exactly once in the report, even if it emits no valid data.
2. An event attributed to a different brand or site cannot establish health for a registered device.
3. Old observations arriving recently remain stale. Freshness uses source observation time.
4. An exact replay does not inflate accepted counts. Conflicting valid payloads under one ID are quarantined.
5. Missing and stale data are unknown; only fresh explicit errors create a degraded state.
6. Out-of-order arrivals cannot replace newer observations. Equal-time contradictory observations are unknown.
7. Counts reconcile: records read equal invalid plus conflicting plus replayed plus accepted records.
8. The CLI returns distinct codes for passing acceptance, failing acceptance and invalid configuration.

## Proposed rollout, not work performed

- **Discovery and POC:** agree on inventory ownership and timestamp meanings; reproduce the failure cases with synthetic fixtures. Confirm device health is not equivalent to business-service availability.
- **Development testing:** add representative producer payloads and failure cases; approve attribution changes and replay semantics. Keep any real data outside this public repository.
- **Canary:** evaluate a limited cohort in shadow mode, reconcile classifications with known device state, and compare event age with operator expectations. Require named owners to resolve rejected and unknown records.
- **Production decision:** set evidence-based thresholds and rollback criteria, review ingestion cost and delivery overhead, and validate operational runbooks. Introduce automation only when its failure consequences and recovery path are understood.

## Success measures to collect in a real pilot

Measure expected-device coverage, age of the latest observation, delivery latency distributions, invalid attribution rate, conflicting ID rate and operator investigation outcomes. Define the denominator and period for each. Establish a baseline before claiming fewer escalations, faster detection or reduced cost.

The committed demonstration proves deterministic classification of its fixtures. It does not validate these pilot outcomes, production throughput or suitability for a specific monitoring vendor.
