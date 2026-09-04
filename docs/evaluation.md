# Evaluation

The versioned suite is defined in `evaluation/cases-v0.1.0.yaml`, executed by `evaluation/run.py`, and recorded in `evaluation/results-v0.1.0.json`. It uses the same T1/T2 normalization, diff, flow, retrieval, tool, and validation code as the product. Targeted synthetic mutations isolate owner, due-date, and dependency lifecycle cases.

## v0.1.0 result

**25 / 25 scenarios passed.**

| Metric | Result |
|---|---:|
| Deterministic change accuracy | 1.00 |
| Blocker recall | 1.00 |
| Risk recall | 1.00 |
| Escalation accuracy | 1.00 |
| Policy citation accuracy | 1.00 |
| Evidence coverage | 1.00 |
| Unsupported-claim rate | 0.00 |
| Invalid-reference rate | 0.00 |

These are fixture-suite results, not production performance or business impact. The versioned catalog holds explicit expected change and signal IDs; the runner compares those with runtime output and measures exact signal-to-policy citation matches, evidence references, validator outcomes, and cross-adapter equivalence. It does not embed result metrics.

The runner detects both retrieved conflicting policy chunks and conflicting machine-readable thresholds but deliberately does not choose between them; policy owners must resolve the conflict before relying on the affected threshold.

Cross-adapter contract tests verify equivalent blocked-item facts from Jira-shaped and Kaiten-shaped data. HTTP mock tests exercise current read-only endpoints, pagination boundaries, configurable workflows, issue-link mapping, structured Kaiten blocker selection, and the rule that unknown blocker targets are not invented.
