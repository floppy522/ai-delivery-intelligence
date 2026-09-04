from datetime import UTC, datetime
from pathlib import Path

import pytest

from adi.adapters.demo import DemoAdapter, DemoPhaseStore
from adi.assessment.models import AssessmentValidationError, DeliveryHealth
from adi.assessment.replay import build_replay_assessment
from adi.assessment.validation import validate_assessment
from adi.domain.models import ContextRef, SourceType
from adi.engine.diff import compare_snapshots
from adi.engine.signals import analyze_delivery
from adi.policies.retrieval import PolicyIndex

ROOT = Path(__file__).parents[4]


@pytest.mark.asyncio
async def test_replay_assessment_is_grounded_and_at_risk() -> None:
    store = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", store)
    context = ContextRef(source=SourceType.DEMO, external_id="northstar")
    t1 = await adapter.collect(context, datetime(2026, 9, 3, 9, tzinfo=UTC))
    store.advance()
    t2 = await adapter.collect(context, datetime(2026, 9, 7, 9, tzinfo=UTC))
    changes = compare_snapshots(t1, t2)
    analysis = analyze_delivery(t2, changes)
    policies = PolicyIndex.from_directory(ROOT / "policies")

    assessment = build_replay_assessment(t2, changes, analysis, policies)

    validate_assessment(assessment, t2, changes, policies)
    assert assessment.overall_delivery_status is DeliveryHealth.AT_RISK
    assert assessment.mode == "replay"
    assert any(risk.title == "Blocker SLA exceeded" for risk in assessment.risks)
    assert all(risk.evidence for risk in assessment.risks)
    assert all(risk.policy_sources for risk in assessment.risks)


@pytest.mark.asyncio
async def test_validation_rejects_unknown_evidence() -> None:
    store = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", store)
    snapshot = await adapter.collect(
        ContextRef(source=SourceType.DEMO, external_id="northstar"),
        datetime(2026, 9, 3, 9, tzinfo=UTC),
    )
    store.advance()
    snapshot = await adapter.collect(
        ContextRef(source=SourceType.DEMO, external_id="northstar"),
        datetime(2026, 9, 7, 9, tzinfo=UTC),
    )
    changes = compare_snapshots(None, snapshot)
    analysis = analyze_delivery(snapshot, changes)
    policies = PolicyIndex.from_directory(ROOT / "policies")
    assessment = build_replay_assessment(snapshot, changes, analysis, policies)
    broken = assessment.model_copy(
        update={"risks": (assessment.risks[0].model_copy(update={"evidence": ("item:UNKNOWN",)}),)}
    )

    with pytest.raises(AssessmentValidationError, match="unknown evidence"):
        validate_assessment(broken, snapshot, changes, policies)


@pytest.mark.asyncio
async def test_first_run_does_not_fabricate_changes() -> None:
    adapter = DemoAdapter(ROOT / "demo", DemoPhaseStore())
    snapshot = await adapter.collect(
        ContextRef(source=SourceType.DEMO, external_id="northstar"),
        datetime(2026, 9, 3, 9, tzinfo=UTC),
    )
    changes = compare_snapshots(None, snapshot)
    analysis = analyze_delivery(snapshot, changes)
    policies = PolicyIndex.from_directory(ROOT / "policies")

    assessment = build_replay_assessment(snapshot, changes, analysis, policies)

    assert assessment.current_state_only is True
    assert assessment.changes == ()
    assert assessment.uncertainties == (
        "No previous snapshot available. Current-state analysis only.",
    )


@pytest.mark.asyncio
async def test_validation_rejects_context_release_language_and_status_conflict() -> None:
    store = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", store)
    context = ContextRef(source=SourceType.DEMO, external_id="northstar")
    first = await adapter.collect(context, datetime(2026, 9, 3, 9, tzinfo=UTC))
    store.advance()
    snapshot = await adapter.collect(context, datetime(2026, 9, 7, 9, tzinfo=UTC))
    policies = PolicyIndex.from_directory(ROOT / "policies")
    changes = compare_snapshots(first, snapshot, policies.rules)
    analysis = analyze_delivery(snapshot, changes, policies.rules)
    assessment = build_replay_assessment(snapshot, changes, analysis, policies)

    for broken, message in (
        (assessment.model_copy(update={"project": "Wrong project"}), "project mismatch"),
        (assessment.model_copy(update={"source": "jira"}), "source mismatch"),
        (
            assessment.model_copy(
                update={
                    "risks": (
                        assessment.risks[0].model_copy(
                            update={"reason": "Release candidate is NOT_READY; issue a Go/No-Go"}
                        ),
                    )
                }
            ),
            "prohibited release language",
        ),
        (
            assessment.model_copy(update={"overall_delivery_status": DeliveryHealth.ON_TRACK}),
            "status conflicts",
        ),
    ):
        with pytest.raises(AssessmentValidationError, match=message):
            validate_assessment(broken, snapshot, changes, policies, analysis)

    with pytest.raises(AssessmentValidationError, match="unknown policy"):
        validate_assessment(
            assessment,
            snapshot,
            changes,
            policies,
            analysis,
            retrieved_policy_ids=set(),
        )


@pytest.mark.asyncio
async def test_validation_rejects_unsafe_action_and_missing_critical_escalation() -> None:
    store = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", store)
    context = ContextRef(source=SourceType.DEMO, external_id="northstar")
    first = await adapter.collect(context, datetime(2026, 9, 3, 9, tzinfo=UTC))
    store.advance()
    snapshot = await adapter.collect(context, datetime(2026, 9, 7, 9, tzinfo=UTC))
    policies = PolicyIndex.from_directory(ROOT / "policies")
    changes = compare_snapshots(first, snapshot, policies.rules)
    analysis = analyze_delivery(snapshot, changes, policies.rules)
    assessment = build_replay_assessment(snapshot, changes, analysis, policies)

    unsafe_action = assessment.recommended_actions[0].model_copy(
        update={"action": "Delete production records immediately."}
    )
    unsafe = assessment.model_copy(
        update={
            "recommended_actions": (
                unsafe_action,
                *assessment.recommended_actions[1:],
            )
        }
    )
    with pytest.raises(AssessmentValidationError, match="safe recommendation catalog"):
        validate_assessment(unsafe, snapshot, changes, policies, analysis)

    missing_escalation = assessment.model_copy(update={"escalations": ()})
    with pytest.raises(AssessmentValidationError, match="escalation coverage"):
        validate_assessment(missing_escalation, snapshot, changes, policies, analysis)


@pytest.mark.asyncio
async def test_blocked_health_requires_structured_no_viable_path_evidence() -> None:
    store = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", store)
    context = ContextRef(source=SourceType.DEMO, external_id="northstar")
    first = await adapter.collect(context, datetime(2026, 9, 3, 9, tzinfo=UTC))
    store.advance()
    snapshot = await adapter.collect(context, datetime(2026, 9, 7, 9, tzinfo=UTC))
    blocked_relation = next(
        relation for relation in snapshot.relations if relation.source_item_id == "demo:NS-17"
    ).model_copy(update={"metadata": {"delivery_flow_blocked": True}})
    blocked_snapshot = snapshot.model_copy(
        update={
            "relations": tuple(
                blocked_relation if relation.source_item_id == "demo:NS-17" else relation
                for relation in snapshot.relations
            )
        }
    )
    policies = PolicyIndex.from_directory(ROOT / "policies")
    changes = compare_snapshots(first, blocked_snapshot, policies.rules)
    analysis = analyze_delivery(blocked_snapshot, changes, policies.rules)
    assessment = build_replay_assessment(blocked_snapshot, changes, analysis, policies)

    validate_assessment(assessment, blocked_snapshot, changes, policies, analysis)
    assert assessment.overall_delivery_status is DeliveryHealth.BLOCKED
