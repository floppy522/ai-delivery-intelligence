# AI Delivery Intelligence v0.1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publicly release a source-agnostic, evidence-grounded delivery-health product that compares Kanban snapshots from Demo, Kaiten, or Jira and recommends bounded management actions.

**Architecture:** A FastAPI/React modular monolith maps three sources into one normalized domain, persists snapshots in PostgreSQL, computes temporal and flow findings deterministically, retrieves Markdown policy chunks with BM25, and optionally uses a bounded OpenAI Responses API tool loop. All generated assessments pass application-level evidence and policy-reference validation.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL 16, httpx, OpenAI Python SDK, React 19, TypeScript, Vite, Vitest, Playwright, pytest, Ruff, mypy, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-03-ai-delivery-intelligence-design.md`

## Global Constraints

- Delivery-health states are exactly `ON_TRACK`, `ATTENTION`, `AT_RISK`, and `BLOCKED`.
- Never implement Go/No-Go, release-readiness, CI, pull-request, migration, back-merge, deployment-evidence, release-scope, or release-candidate logic.
- Demo, Kaiten, and Jira must enter the same `DeliverySnapshot -> diff -> signals -> retrieval -> synthesis -> validation` pipeline.
- Provider payload types and field names are confined to `adi.adapters`.
- All provider access is manually triggered, read-only, and limited to one board or project context.
- Tracker content is untrusted data; agent tools are read-only and have no arbitrary network, shell, write-back, messaging, or policy-editing capability.
- Credentials are accepted only through environment variables and are never logged or persisted.
- Public fixtures, screenshots, policies, and docs contain fictional Northstar Platform data only.
- Evaluation results must be produced by the committed runner; no result is written by hand.

## Planned file map

```text
apps/api/
  pyproject.toml                         Python package and tool configuration
  src/adi/config.py                     Environment and YAML mapping settings
  src/adi/domain/models.py              Canonical immutable domain contracts
  src/adi/adapters/base.py              DeliverySourceAdapter protocol and errors
  src/adi/adapters/demo.py              T1/T2 fixture adapter
  src/adi/adapters/kaiten.py            Kaiten HTTP collection and normalization
  src/adi/adapters/jira.py              Jira Cloud collection and normalization
  src/adi/engine/diff.py                Snapshot comparison
  src/adi/engine/signals.py             Deterministic delivery findings
  src/adi/policies/retrieval.py          Markdown chunking and BM25 retrieval
  src/adi/agent/tools.py                 Read-only tool registry
  src/adi/agent/live.py                  Bounded Responses API loop
  src/adi/agent/replay.py                Credential-free validated demo synthesis
  src/adi/assessment/models.py           Strict output contract
  src/adi/assessment/validation.py       Evidence/policy/entity validation
  src/adi/persistence/models.py          SQLAlchemy tables
  src/adi/persistence/repository.py      Snapshot/run storage
  src/adi/service.py                     End-to-end analysis orchestration
  src/adi/main.py                        FastAPI endpoints
  tests/                                 Unit, contract, API, security tests
apps/web/
  src/api.ts                             Typed API client
  src/types.ts                           UI contracts
  src/App.tsx                            Source selection and assessment screen
  src/components/                       Decision-first sections
  src/styles.css                         Portfolio-consistent visual system
  src/**/*.test.tsx                      Focused UI tests
demo/northstar-t1.json                   Stable current-state fixture
demo/northstar-t2.json                   Risk transition fixture
demo/replay-assessment.json              Validated no-key synthesis contract
config/delivery.example.yaml            Jira/Kaiten stage and relation mappings
policies/*.md                            Replaceable fictional policies
evals/catalog.yaml                       Twenty-four versioned cases
evals/runner.py                          Reproducible evaluation output
tests/e2e/delivery-review.spec.ts        T1 -> T2 browser path
docs/{product-case,architecture,evaluation,threat-model}.md
docs/assets/                             Actual UI captures and social preview
compose.yaml                             Credential-free and live-agent stack
.github/workflows/ci.yml                 Quality gates
README.md                                Portfolio-first product entry point
```

---

### Task 1: Package skeleton and canonical domain

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/adi/__init__.py`
- Create: `apps/api/src/adi/domain/models.py`
- Create: `apps/api/src/adi/adapters/base.py`
- Test: `apps/api/tests/domain/test_models.py`

**Interfaces:**
- Produces: `SourceType`, `CapabilityLevel`, `SourceCapabilities`, `DeliveryStage`, `RelationType`, `DeliveryContext`, `EvidenceRef`, `WorkItem`, `WorkRelation`, `DeliverySnapshot`, `ContextRef`, `DeliverySourceAdapter`.
- `DeliverySourceAdapter.collect(context: ContextRef, observed_at: datetime) -> DeliverySnapshot` is the only provider-to-core boundary.

- [ ] **Step 1: Write failing model and protocol tests**

```python
def test_snapshot_rejects_duplicate_item_ids() -> None:
    with pytest.raises(ValidationError):
        DeliverySnapshot(context=context, observed_at=NOW, items=[item, item])

def test_unknown_stage_is_explicit() -> None:
    assert DeliveryStage.UNKNOWN.value == "UNKNOWN"
```

- [ ] **Step 2: Run the focused tests and confirm import failure**

Run: `uv run --project apps/api pytest apps/api/tests/domain/test_models.py -q`
Expected: FAIL because `adi.domain.models` does not exist.

- [ ] **Step 3: Implement frozen Pydantic models and adapter protocol**

Implement stable IDs as `{source}:{external_id}`, validate UTC timestamps, unique item/evidence IDs, relation endpoints, safe `https` source URLs, and capabilities with `SUPPORTED | PARTIAL | UNAVAILABLE`.

- [ ] **Step 4: Run domain tests, Ruff, and mypy**

Run: `uv run --project apps/api pytest apps/api/tests/domain/test_models.py -q && uv run --project apps/api ruff check apps/api/src apps/api/tests && uv run --project apps/api mypy apps/api/src`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat: define normalized delivery domain"
```

### Task 2: Northstar demo snapshots and adapter

**Files:**
- Create: `demo/northstar-t1.json`
- Create: `demo/northstar-t2.json`
- Create: `apps/api/src/adi/adapters/demo.py`
- Test: `apps/api/tests/adapters/test_demo.py`

**Interfaces:**
- Consumes: `DeliverySnapshot`, `ContextRef`, `DeliverySourceAdapter`.
- Produces: `DemoAdapter(phase_store: DemoPhaseStore)` and `DemoPhaseStore.current()/advance()/reset()`.

- [ ] **Step 1: Write tests for T1/T2 invariants**

```python
def test_demo_t2_contains_expected_temporal_story(adapter: DemoAdapter) -> None:
    t1 = adapter.collect(ContextRef(external_id="northstar"), T1_NOW)
    adapter.phase_store.advance()
    t2 = adapter.collect(ContextRef(external_id="northstar"), T2_NOW)
    assert len(t2.items) >= 25
    assert sum(i.stage is DeliveryStage.DONE for i in t2.items) > sum(i.stage is DeliveryStage.DONE for i in t1.items)
    assert any(r.relation_type is RelationType.BLOCKED_BY for r in t2.relations)
```

- [ ] **Step 2: Confirm failure, then add 30 fictional items and both snapshots**

Run before implementation: `uv run --project apps/api pytest apps/api/tests/adapters/test_demo.py -q`
Expected: FAIL because fixtures and adapter are absent.

T1 must keep active WIP at or below seven. T2 must include a WIP crossing, `NS-17` blocker over the two-business-day policy, aging Verify items, threatening `NS-31 -> NS-19`, harmless `NS-22 -> NS-08`, resolved blocker `NS-14`, and completed `NS-12`.

- [ ] **Step 3: Implement fixture loading through canonical validation**

`DemoAdapter.collect` reads the selected fixture, replaces relative timestamps from a fixed fixture clock, validates it as `DeliverySnapshot`, and never returns a precomputed domain object.

- [ ] **Step 4: Run tests and commit**

Run: `uv run --project apps/api pytest apps/api/tests/adapters/test_demo.py -q`
Expected: PASS.

```bash
git add demo apps/api/src/adi/adapters/demo.py apps/api/tests/adapters/test_demo.py
git commit -m "feat: add Northstar temporal demo adapter"
```

### Task 3: Deterministic diff and flow signals

**Files:**
- Create: `apps/api/src/adi/engine/diff.py`
- Create: `apps/api/src/adi/engine/signals.py`
- Test: `apps/api/tests/engine/test_diff.py`
- Test: `apps/api/tests/engine/test_signals.py`

**Interfaces:**
- Produces: `ChangeType`, `DeliveryChange`, `ChangeSet`, `SignalType`, `DeliverySignal`, `FlowMetrics`, `compare_snapshots(previous, current, policy)`, `analyze_delivery(snapshot, changes, policy)`.

- [ ] **Step 1: Add parameterized failing tests for every deterministic change type**

Cover item creation/completion, stage/owner/due-date changes, blocker/dependency appearance/resolution, overdue transition, WIP movement/limit crossing, and aging threshold crossing.

- [ ] **Step 2: Run focused tests and confirm missing-module failures**

Run: `uv run --project apps/api pytest apps/api/tests/engine -q`
Expected: FAIL because engine modules are absent.

- [ ] **Step 3: Implement pure comparison and signal functions**

Use stable dictionary joins, UTC duration arithmetic, explicit capability checks, and stable evidence IDs such as `change:NS-17:blocker_appeared`. First-run comparison returns `current_state_only=True` and no fabricated changes.

- [ ] **Step 4: Verify the Northstar expected story**

```python
assert result.metrics.wip == 10
assert result.metrics.wip_limit == 7
assert {s.signal_type for s in result.signals} >= {
    SignalType.WIP_LIMIT_EXCEEDED,
    SignalType.BLOCKER_SLA_EXCEEDED,
    SignalType.VERIFY_QUEUE_AGING,
    SignalType.DEPENDENCY_THREATENS_TARGET,
}
```

- [ ] **Step 5: Run engine tests and commit**

Run: `uv run --project apps/api pytest apps/api/tests/engine -q`
Expected: PASS.

```bash
git add apps/api/src/adi/engine apps/api/tests/engine
git commit -m "feat: detect temporal delivery changes"
```

### Task 4: Replaceable policies and inspectable BM25 retrieval

**Files:**
- Create: `policies/kanban-policy.md`
- Create: `policies/blocker-policy.md`
- Create: `policies/dependency-policy.md`
- Create: `policies/delivery-risk-policy.md`
- Create: `policies/escalation-matrix.md`
- Create: `policies/status-reporting.md`
- Create: `apps/api/src/adi/policies/retrieval.py`
- Test: `apps/api/tests/policies/test_retrieval.py`

**Interfaces:**
- Produces: `PolicyChunk`, `RetrievedPolicy`, `PolicyIndex.from_directory(path)`, `PolicyIndex.search(query, top_k=4, min_score=0.1)`.

- [ ] **Step 1: Write failing chunk-ID, retrieval, no-match, and conflict tests**

```python
def test_blocker_query_cites_sla_section(index: PolicyIndex) -> None:
    result = index.search("critical blocker age owner ETA")
    assert result[0].chunk_id == "blocker-policy.md#critical-blocker-sla"
```

- [ ] **Step 2: Confirm failure and author fictional policies with stable headings**

Set WIP limit seven, blocker SLA two business days, owner and ETA requirements, Verify aging threshold four days, dependency escalation within five days of target, and explicit conflict precedence.

- [ ] **Step 3: Implement heading-aware chunking and BM25**

Implement BM25 directly with `math.log` and token frequencies to keep retrieval local and inspectable. Preserve filename, heading path, line range, and content hash in metadata.

- [ ] **Step 4: Run retrieval tests and commit**

Run: `uv run --project apps/api pytest apps/api/tests/policies/test_retrieval.py -q`
Expected: PASS.

```bash
git add policies apps/api/src/adi/policies apps/api/tests/policies
git commit -m "feat: retrieve cited delivery policies"
```

### Task 5: PostgreSQL persistence and analysis orchestration

**Files:**
- Create: `apps/api/src/adi/persistence/models.py`
- Create: `apps/api/src/adi/persistence/repository.py`
- Create: `apps/api/src/adi/service.py`
- Test: `apps/api/tests/persistence/test_repository.py`
- Test: `apps/api/tests/test_service.py`

**Interfaces:**
- Produces: `RunRecord`, `SnapshotRepository.save_snapshot/get_previous/save_run/list_runs/get_run`, `AnalysisService.analyze(source, context, observed_at)`.

- [ ] **Step 1: Write failing persistence round-trip and two-run service tests**

The second Northstar run must load T1 as previous, persist T2, persist the exact `ChangeSet`, and return a run linked to both snapshot IDs.

- [ ] **Step 2: Confirm failure and implement JSONB-backed tables**

Tables: `source_configs`, `snapshots`, and `analysis_runs`. Add unique `(source, context_external_id, observed_at)` and foreign keys for current/previous snapshot. Persist only redacted configuration fingerprints and normalized JSON.

- [ ] **Step 3: Implement the orchestration transaction**

Collection and deterministic computation occur before one persistence transaction. Failed synthesis stores `status="FAILED_SAFE"` and a sanitized error code; it does not persist provider secrets or raw payloads.

- [ ] **Step 4: Run repository and service tests against PostgreSQL**

Run: `docker compose up -d db && uv run --project apps/api pytest apps/api/tests/persistence apps/api/tests/test_service.py -q`
Expected: PASS when Docker is available; otherwise run the same tests with the CI service container and document the local Docker limitation.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/adi/persistence apps/api/src/adi/service.py apps/api/tests
git commit -m "feat: persist delivery snapshots and runs"
```

### Task 6: Kaiten read-only adapter and contract suite

**Files:**
- Create: `apps/api/src/adi/adapters/kaiten.py`
- Create: `apps/api/tests/fixtures/kaiten/*.json`
- Create: `apps/api/tests/adapters/test_kaiten.py`
- Create: `apps/api/tests/adapters/test_contract.py`

**Interfaces:**
- Produces: `KaitenAdapter(client: httpx.AsyncClient, config: KaitenConfig)` using `/api/latest/spaces`, `/spaces/{id}/boards`, `/cards`, `/cards/{id}/blockers`, and optional `/cards/{id}/location-history`.

- [ ] **Step 1: Write failing HTTP request, pagination, normalization, and redaction tests**

Assert `limit=100` and increasing `offset`, no card collection from nested board responses, no non-GET provider call, bearer-token redaction, `UNKNOWN` fallback, and card blocker direction.

- [ ] **Step 2: Confirm failure and implement discovery/collection**

Only request blocker details for cards whose structured flags indicate blocked/blocking. Map board columns by type plus configured aliases. Mark priorities partial because standard Kaiten data supplies `asap`, not a universal multi-level priority.

- [ ] **Step 3: Add contract fixtures**

Normalize normal, blocked/missing-owner, overdue, stage-transition, completion, and due-date-change situations into the same canonical facts as demo fixtures. Do not assert generic Kaiten dependency capability.

- [ ] **Step 4: Run adapter tests and commit**

Run: `uv run --project apps/api pytest apps/api/tests/adapters/test_kaiten.py apps/api/tests/adapters/test_contract.py -q`
Expected: PASS.

```bash
git add apps/api/src/adi/adapters/kaiten.py apps/api/tests/adapters apps/api/tests/fixtures/kaiten
git commit -m "feat: add read-only Kaiten adapter"
```

### Task 7: Jira Cloud read-only adapter and cross-adapter contracts

**Files:**
- Create: `config/delivery.example.yaml`
- Create: `apps/api/src/adi/config.py`
- Create: `apps/api/src/adi/adapters/jira.py`
- Create: `apps/api/tests/fixtures/jira/*.json`
- Create: `apps/api/tests/adapters/test_jira.py`
- Modify: `apps/api/tests/adapters/test_contract.py`

**Interfaces:**
- Produces: `JiraAdapter(client: httpx.AsyncClient, config: JiraConfig)` using paginated project/board APIs, enhanced issue search, issue links, and paginated changelog.

- [ ] **Step 1: Write failing enhanced-search, next-page, workflow, relation-direction, and changelog tests**

Reject the deprecated `/rest/api/3/search` path. Verify configured status aliases, inward/outward link text, unknown mapping capability limitations, browse URLs, and Basic auth header redaction.

- [ ] **Step 2: Confirm failure and implement discovery/collection**

Request only required fields. Use `nextPageToken` where the enhanced endpoint returns it and `startAt/maxResults` where the selected Jira Software operation uses offset pagination. Fetch changelog only when configured and record capability degradation on permission failure.

- [ ] **Step 3: Complete equivalent contract cases**

Jira-shaped fixtures must match demo/Kaiten canonical findings for normal, blocked, overdue, missing-owner, stage-transition, completion, and due-date-change cases; Jira/demo also match dependency cases.

- [ ] **Step 4: Run adapter and type tests and commit**

Run: `uv run --project apps/api pytest apps/api/tests/adapters -q && uv run --project apps/api mypy apps/api/src`
Expected: PASS.

```bash
git add config apps/api/src/adi/config.py apps/api/src/adi/adapters/jira.py apps/api/tests
git commit -m "feat: add configurable Jira Cloud adapter"
```

### Task 8: Strict assessment schema, replay mode, and grounding validation

**Files:**
- Create: `apps/api/src/adi/assessment/models.py`
- Create: `apps/api/src/adi/assessment/validation.py`
- Create: `apps/api/src/adi/agent/replay.py`
- Create: `demo/replay-assessment.json`
- Test: `apps/api/tests/assessment/test_validation.py`
- Test: `apps/api/tests/agent/test_replay.py`

**Interfaces:**
- Produces: `DeliveryAssessment`, `DeliveryRisk`, `RecommendedAction`, `Uncertainty`, `validate_assessment(assessment, snapshot, changes, signals, retrieved)`, `ReplaySynthesizer.synthesize(context)`.

- [ ] **Step 1: Write failing schema and invalid-reference tests**

Reject unknown item/evidence/policy IDs, prohibited release vocabulary, a status unsupported by deterministic signals, malformed output, and recommendations without evidence or policy when policy-based.

- [ ] **Step 2: Implement strict Pydantic contracts**

Use `extra="forbid"`, required arrays, explicit uncertainty objects, and stable typed reference strings. `BLOCKED` requires a project-level delivery obstruction; one blocked item alone may produce `AT_RISK`.

- [ ] **Step 3: Build and validate the Northstar replay assessment**

The replay file contains narrative/prioritization only. At runtime it is parsed and every reference is revalidated against live T1/T2 deterministic output and current policy chunks before saving.

- [ ] **Step 4: Run assessment tests and commit**

Run: `uv run --project apps/api pytest apps/api/tests/assessment apps/api/tests/agent/test_replay.py -q`
Expected: PASS.

```bash
git add apps/api/src/adi/assessment apps/api/src/adi/agent/replay.py apps/api/tests demo/replay-assessment.json
git commit -m "feat: validate grounded delivery assessments"
```

### Task 9: Bounded live agent and prompt-injection safeguards

**Files:**
- Create: `apps/api/src/adi/agent/tools.py`
- Create: `apps/api/src/adi/agent/live.py`
- Test: `apps/api/tests/agent/test_tools.py`
- Test: `apps/api/tests/agent/test_live.py`
- Test: `apps/api/tests/security/test_prompt_injection.py`
- Modify: `apps/api/src/adi/service.py`

**Interfaces:**
- Produces: `AnalysisToolRegistry.call(name, arguments)`, `LiveAgent.run(context) -> DeliveryAssessment`, eight allowlisted read-only tools, maximum six tool rounds and twelve total calls.

- [ ] **Step 1: Write failing tool-selection, budget, malformed-output, and injection tests**

Simulate Responses API items for multiple tool calls and final structured output. Ensure unknown tools, item IDs, arbitrary arguments, excessive rounds, and mutation-shaped calls fail closed.

- [ ] **Step 2: Implement read-only tool registry**

Tools return bounded JSON from normalized facts and retrieval only. `get_work_item_evidence` requires an exact canonical item ID; `search_delivery_policies` caps query length and top-k.

- [ ] **Step 3: Implement Responses API loop**

Send function schemas with `strict: true`, pair every function output with its `call_id`, delimit tracker text as untrusted data, and request final strict structured output. Refusals, incomplete responses, timeouts, SDK errors, or validation failures return a typed safe failure.

- [ ] **Step 4: Run agent/security tests and commit**

Run: `uv run --project apps/api pytest apps/api/tests/agent apps/api/tests/security -q`
Expected: PASS without a real API key by using a fake client.

```bash
git add apps/api/src/adi/agent apps/api/src/adi/service.py apps/api/tests
git commit -m "feat: add bounded delivery analysis agent"
```

### Task 10: FastAPI surface and decision-first React UI

**Files:**
- Create: `apps/api/src/adi/main.py`
- Create: `apps/api/tests/api/test_runs.py`
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/index.html`
- Create: `apps/web/src/{main.tsx,App.tsx,api.ts,types.ts,styles.css}`
- Create: `apps/web/src/components/{HealthHero,ChangesPanel,AttentionPanel,FlowStrip,EvidenceDrawer,RunHistory}.tsx`
- Create: `apps/web/src/App.test.tsx`

**Interfaces:**
- API: `GET /api/sources`, `GET /api/sources/{source}/contexts`, `POST /api/runs`, `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/snapshot`, `GET /api/runs/{id}/changes`, `POST /api/demo/advance`, `POST /api/demo/reset`, `GET /health`.

- [ ] **Step 1: Write failing API tests for first run, T2 run, history, and secret exclusion**

Assert first-run copy exactly contains “No previous snapshot available. Current-state analysis only.” and no API response contains configured token values.

- [ ] **Step 2: Implement API models and dependency wiring**

Use typed response models, 404 for unknown run/context, 409 for incompatible demo phase, 422 for invalid mapping, and 503 with sanitized source codes for provider failures.

- [ ] **Step 3: Write failing UI tests**

Test source/context controls, disabled analyze state, `AT_RISK` hero, change list, attention ordering, evidence/policy drawer, and previous-run navigation using mocked fetch responses.

- [ ] **Step 4: Implement the UI**

Use a restrained dark navy/ivory/amber visual system distinct from ARI's release decision screen. Put temporal changes before metrics. Do not add charts unless a relationship cannot be read from the compact flow strip.

- [ ] **Step 5: Run API and frontend gates and commit**

Run: `uv run --project apps/api pytest apps/api/tests/api -q && npm --prefix apps/web ci && npm --prefix apps/web test -- --run && npm --prefix apps/web run typecheck && npm --prefix apps/web run build`
Expected: PASS.

```bash
git add apps/api/src/adi/main.py apps/api/tests/api apps/web
git commit -m "feat: add delivery review web experience"
```

### Task 11: Versioned 24-case evaluation

**Files:**
- Create: `evals/catalog.yaml`
- Create: `evals/runner.py`
- Create: `apps/api/tests/evals/test_catalog.py`
- Create: `docs/evaluation.md`

**Interfaces:**
- Produces: `python evals/runner.py --catalog evals/catalog.yaml --output evaluation-results.json` and machine-readable metric output.

- [ ] **Step 1: Write failing catalog-validation and metric tests**

Require exactly 24 unique scenario IDs and categories covering flow, blockers, dependencies, temporal changes, policy retrieval, insufficient evidence, unknown references, injection, and malformed model output.

- [ ] **Step 2: Author scenarios with expected facts**

Each case declares input fixture/source shape, previous/current state, policy set, expected changes/signals/status, and allowed uncertainty. Cross-adapter cases include demo/Kaiten/Jira blocker parity and demo/Jira dependency parity.

- [ ] **Step 3: Implement deterministic runner and actual metric calculation**

Calculate change accuracy, blocker/risk recall, escalation accuracy, citation accuracy, evidence coverage, unsupported-claim rate, and invalid-reference rate from expected versus actual sets. Exit nonzero on catalog invalidity or safety-reference failures.

- [ ] **Step 4: Run evaluation and generate documentation from output**

Run: `uv run --project apps/api python evals/runner.py --catalog evals/catalog.yaml --output evaluation-results.json`
Expected: runner completes and writes real counts/rates; failing cases are fixed or listed as limitations in `docs/evaluation.md`.

- [ ] **Step 5: Commit**

```bash
git add evals evaluation-results.json apps/api/tests/evals docs/evaluation.md
git commit -m "test: add versioned delivery evaluation"
```

### Task 12: Docker, CI, E2E, and security documentation

**Files:**
- Create: `apps/api/Dockerfile`
- Create: `apps/web/Dockerfile`
- Create: `compose.yaml`
- Create: `tests/e2e/{package.json,playwright.config.ts,delivery-review.spec.ts}`
- Create: `.github/workflows/ci.yml`
- Create: `.env.example`
- Create: `docs/threat-model.md`
- Create: `SECURITY.md`

**Interfaces:**
- Produces: `docker compose up --build -d --wait` with web on `http://localhost:8080` and no required secret in demo mode.

- [ ] **Step 1: Write the E2E test before final Docker wiring**

The test resets Demo, analyzes T1, advances to T2, analyzes again, expects `AT_RISK`, opens `NS-17`, verifies blocker evidence and `blocker-policy.md#critical-blocker-sla`, then opens the prior run.

- [ ] **Step 2: Add multi-stage images, health checks, and Compose services**

Services: `db`, `api`, `web`. Use non-root runtime users, read-only policy/demo mounts, named PostgreSQL volume, health-gated startup, and no baked secrets.

- [ ] **Step 3: Add CI jobs**

Jobs: `backend`, `frontend`, `evaluation`, `e2e`, and `compose-smoke`. Upload evaluation output and Playwright trace only on failure; never echo environment secrets.

- [ ] **Step 4: Document the threat model and reporting policy**

Cover tokens, read-only scopes, SSRF/base URLs, prompt injection, LLM exposure, evidence URLs, policy trust, output validation, redaction, and no arbitrary tools. `SECURITY.md` supports v0.1.x and links privately to GitHub Security Advisories.

- [ ] **Step 5: Run local gates available in the environment and commit**

Run: `uv run --project apps/api pytest apps/api/tests -q && npm --prefix apps/web test -- --run && npm --prefix apps/web run build && uv run --project apps/api python evals/runner.py --catalog evals/catalog.yaml --output evaluation-results.json`
Expected: PASS. If Docker is unavailable locally, validate `docker compose config` in CI and do not claim local Compose verification.

```bash
git add apps/api/Dockerfile apps/web/Dockerfile compose.yaml tests/e2e .github .env.example docs/threat-model.md SECURITY.md
git commit -m "ci: verify the credential-free delivery demo"
```

### Task 13: Portfolio documentation and actual visuals

**Files:**
- Create: `README.md`
- Create: `docs/product-case.md`
- Create: `docs/architecture.md`
- Create: `docs/assets/adi-main.png`
- Create: `docs/assets/adi-changes.png`
- Create: `docs/assets/social-preview.png`

**Interfaces:**
- Produces: truthful public review surface with actual application screenshots at 1440x900 and social preview at 1280x640.

- [ ] **Step 1: Write concise product and architecture documents**

Lead README with user/problem/product/sources/role/evidence, an actual screenshot, and the temporal hero story. Put installation later. Explicitly compare ADI continuous delivery health with ARI release readiness.

- [ ] **Step 2: Run the real Northstar T1/T2 demo and capture UI assets**

Capture the current product UI only; do not construct mock screenshots or use AI art. Ensure no localhost browser chrome, tokens, personal data, or employer references are visible.

- [ ] **Step 3: Create the social preview from the actual screenshot**

Crop and compose the product name, “What changed since the previous review?”, and the actual `AT_RISK` view. Keep the UI legible and portfolio styling consistent.

- [ ] **Step 4: Verify links, dimensions, and prohibited vocabulary**

Run: `python -m compileall apps/api/src && rg -n "YADRO|READY|NOT_READY|NEEDS_DECISION|Go/No-Go" README.md docs policies demo apps --glob '!docs/superpowers/**'`
Expected: only explicit ARI-boundary explanations may match; no ADI output, enum, fixture, or screenshot copy matches.

- [ ] **Step 5: Commit**

```bash
git add README.md docs
git commit -m "docs: present AI Delivery Intelligence v0.1.0"
```

### Task 14: Public repository, review gates, release, and portfolio re-audit

**Files:**
- Create: `LICENSE`
- Modify after verification only: GitHub repository metadata, release, profile README, and resume recommendation.

**Interfaces:**
- Produces: public `floppy522/ai-delivery-intelligence`, focused pull requests, passing main CI, and tag/release `v0.1.0`.

- [ ] **Step 1: Add MIT license and run verification-before-completion**

Run all backend, frontend, evaluation, E2E, and Compose gates that the environment supports. Inspect `git diff --check`, repository secrets scan, screenshot dimensions, and evaluation output before any completion claim.

- [ ] **Step 2: Create the public repository and push reviewable branches**

Use description “Evidence-grounded AI agent for Kanban delivery flow, blockers, dependencies, risks, and management actions.” Enable Issues and Actions. Add only topics implemented by the code.

- [ ] **Step 3: Open focused pull requests and wait for CI**

Group commits into deterministic core, source adapters, agent/RAG, and experience/release review surfaces. Each PR description lists scope, tests, trade-offs, and the ARI non-overlap check. Merge only after green required checks.

- [ ] **Step 4: Tag and publish v0.1.0**

Release notes describe delivery intelligence, three adapters, temporal diff, retrieval, bounded agent, grounding, demo, actual evaluation, and limitations. Do not claim production adoption or business impact.

- [ ] **Step 5: Re-audit portfolio and resume**

Only after v0.1.0, decide whether ADI replaces MoneyFlow as second flagship. If yes, update profile hierarchy to ARI, ADI, then MoneyFlow and propose one minimal resume sentence supported by repository evidence.

- [ ] **Step 6: Final report**

Report repository URL, product, implemented source capabilities, architecture, signals, agent/RAG, actual evaluation, verification, ARI boundary, PRs/release, portfolio decision, exact resume wording, and only high-value deferred items.
