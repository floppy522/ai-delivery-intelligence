# Product case

## Problem

Delivery reviews often mix current board state, remembered history, policy interpretation, and subjective narration. The manager still has to reconstruct the useful question: **what changed, what requires attention now, and why?**

## User / JTBD

The primary user is a Technical Project Manager or Delivery Manager. Engineering Managers, Technical Program Managers, and software Project Managers are secondary users. The job is management intervention in delivery flow—not analytics consumption and not release approval.

## Why temporal analysis

A static red card is ambiguous. A newly blocked critical item, a blocker that crossed SLA, or WIP that moved from 7 to 10 is actionable. Persisted normalized snapshots make those changes explicit and reviewable. On a first run the product states that only current-state analysis is available; it never invents a past.

## Why deterministic flow analysis

Stages, owners, due dates, relations, WIP, aging, and threshold crossings are structured facts. Code computes them consistently. The model cannot rewrite them. This lowers unsupported-claim risk and makes cross-adapter behavior testable.

## Why an agent

Not every review needs the same evidence. A bounded agent can choose among snapshot, diff, metrics, aging, blocker, dependency, due-date, item-evidence, and policy-search tools. Its work stops at prioritization, explanation, uncertainty, and recommended management action.

## Why RAG

Recommendations depend on local delivery policy: a two-day blocker SLA or a WIP limit of seven is not universal knowledge. Heading-aware Markdown chunks and an inspectable BM25 index provide stable sources such as `blocker-policy.md#critical-blocker-sla` without a decorative vector database.

## Why source adapters

Jira and Kaiten expose different schemas and evidence. Adapters own pagination, authentication, workflow mappings, link mappings, capabilities, and provider URLs. The diff, flow, RAG, agent, assessment, persistence, UI, and evaluation layers only consume the normalized model.

## MVP scope

v0.1.0 is a read-only modular monolith: Demo/Kaiten/Jira adapters, one board per run, persisted snapshots and assessments, temporal diff, targeted flow signals, Markdown retrieval, replay/live agent modes, validated references, web UI, run history, Docker Compose, CI, E2E, and 25 evaluation cases.

## Key product decisions

- Target dates are urgency context, never release-readiness inputs.
- PostgreSQL is the deployed default; SQLite keeps direct local backend development simple.
- Replay mode makes the complete synthetic product inspectable without credentials or cost.
- Missing provider evidence becomes a capability limitation, not an LLM inference.
- The UI leads with delivery health, changes, attention, actions, evidence, and history—not charts.

## Agent boundaries

The agent may inspect, retrieve, analyze, prioritize, explain, and recommend. It cannot mutate trackers, message people, execute escalation, run arbitrary commands, accept risk, or alter policy. Only allowlisted read tools are compiled into the agent request.

## Evaluation and safeguards

The versioned suite covers flow, blockers, dependencies, temporal change, retrieval, malformed output, invalid references, insufficient evidence, and prompt injection. Output is parsed through a strict Pydantic schema and then cross-checked against the run’s evidence, items, and indexed policy IDs.

## Trade-offs and limitations

The implementation favors small, inspectable mechanisms. It does not compute throughput when reliable history is absent, automatically resolve conflicting policies, aggregate projects, synchronize Jira and Kaiten, or claim production adoption. Conflicting machine-readable thresholds are detected and left for policy-owner resolution. Kaiten dependency evidence is unavailable in the implemented official surface and is not guessed.

## Relationship to AI Release Intelligence

AI Delivery Intelligence supports continuous flow intervention from work-management evidence. AI Release Intelligence supports a specific release Go/No-Go decision from engineering/release evidence. “Dependency threatens the target date” belongs here; `NOT_READY` does not.

## My role

Problem framing, product scope, delivery-domain modeling, source-adapter boundaries, agent/tool contracts, RAG architecture decisions, evaluation criteria, acceptance criteria, verification, and release management. Implementation was supported by AI coding agents through specification-driven, test-driven, and review-gated workflows; accountability for decisions and release quality remains mine.
