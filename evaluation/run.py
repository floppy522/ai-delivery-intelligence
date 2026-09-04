from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from adi.adapters.demo import DemoAdapter, DemoPhaseStore
from adi.adapters.jira import JiraMapping, normalize_issue
from adi.adapters.kaiten import KaitenMapping, normalize_card
from adi.agent.tools import DeliveryToolExecutor
from adi.assessment.models import DeliveryAssessment, DeliveryHealth
from adi.assessment.replay import POLICY_QUERY, build_replay_assessment
from adi.assessment.validation import validate_assessment
from adi.domain.models import ContextRef, DeliveryStage, RelationType, SourceType
from adi.engine.diff import ChangeType, compare_snapshots
from adi.engine.signals import SignalType, analyze_delivery
from adi.policies.retrieval import PolicyIndex
from pydantic import ValidationError

ROOT = Path(__file__).parents[1]


async def evaluate() -> dict[str, Any]:
    definition = yaml.safe_load((ROOT / "evaluation/cases-v0.1.0.yaml").read_text())
    phase = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", phase)
    context = ContextRef(source=SourceType.DEMO, external_id="northstar")
    policies = PolicyIndex.from_directory(ROOT / "policies")
    t1 = await adapter.collect(context, datetime(2026, 9, 3, 9, tzinfo=UTC))
    phase.advance()
    t2 = await adapter.collect(context, datetime(2026, 9, 7, 9, tzinfo=UTC))
    changes = compare_snapshots(t1, t2, policies.rules)
    analysis1 = analyze_delivery(
        t1, compare_snapshots(None, t1, policies.rules), policies.rules
    )
    analysis2 = analyze_delivery(t2, changes, policies.rules)
    assessment = build_replay_assessment(t2, changes, analysis2, policies)
    executor = DeliveryToolExecutor(t2, changes, analysis2, policies)
    signal_types = {signal.signal_type for signal in analysis2.signals}
    change_types = {change.change_type for change in changes.changes}

    async def check(name: str) -> tuple[bool, str]:
        simple = {
            "healthy_board": analysis1.metrics.wip <= (t1.context.wip_limit or 999),
            "wip_exceeded": SignalType.WIP_LIMIT_EXCEEDED in signal_types,
            "aging_work": SignalType.AGING_WORK in signal_types,
            "verify_aging": SignalType.VERIFY_QUEUE_AGING in signal_types,
            "throughput_limitation": not hasattr(analysis2.metrics, "throughput"),
            "blocker_within_sla": SignalType.BLOCKER_WITHIN_SLA
            in {signal.signal_type for signal in analysis1.signals},
            "blocker_beyond_sla": SignalType.BLOCKER_SLA_EXCEEDED in signal_types,
            "blocker_owner_eta": {
                SignalType.BLOCKER_MISSING_OWNER,
                SignalType.BLOCKER_MISSING_ETA,
            }
            <= signal_types,
            "blocker_resolved": ChangeType.BLOCKER_RESOLVED in change_types,
            "dependency_harmless": SignalType.DEPENDENCY_HARMLESS in signal_types,
            "dependency_threatens": SignalType.DEPENDENCY_THREATENS_TARGET
            in signal_types,
            "stage_completion": ChangeType.ITEM_COMPLETED in change_types,
            "wip_increase": ChangeType.WIP_LIMIT_CROSSED in change_types,
            "aging_threshold": ChangeType.AGING_THRESHOLD_CROSSED in change_types,
            "correct_policy": bool(policies.search("critical blocker SLA", top_k=1)),
            "no_policy": not policies.search("quantum hardware procurement", top_k=3),
            "malformed_output": _malformed_rejected(),
            "insufficient_evidence": _unknown_blocker_age_is_explicit(t2, policies),
        }
        if name in simple:
            return simple[name], "computed"
        if name == "prompt_injection":
            return await _prompt_injection_safe(
                assessment, executor, t2, changes, policies, analysis2
            ), "tool trust label + semantic validator"
        if name == "adapter_equivalence":
            return _adapter_equivalence(), "equivalent Jira/Kaiten shaped fixtures"
        if name == "dependency_lifecycle":
            dependency = next(
                relation
                for relation in t2.relations
                if relation.relation_type is RelationType.DEPENDS_ON
            )
            old = t1.model_copy(update={"relations": (dependency,)})
            new = t2.model_copy(update={"relations": ()})
            found = ChangeType.DEPENDENCY_RESOLVED in {
                item.change_type for item in compare_snapshots(old, new).changes
            }
            return (
                found and ChangeType.DEPENDENCY_APPEARED in change_types,
                "synthetic lifecycle",
            )
        if name in {"owner_change", "due_date_change"}:
            before_item = t1.items[16]
            update = (
                {"assignee": "Maya"}
                if name == "owner_change"
                else {"due_at": datetime(2026, 9, 9, tzinfo=UTC)}
            )
            after_item = before_item.model_copy(update=update)
            changed = t1.model_copy(
                update={
                    "items": tuple(
                        after_item if item == before_item else item for item in t1.items
                    )
                }
            )
            expected = (
                ChangeType.OWNER_CHANGED
                if name == "owner_change"
                else ChangeType.DUE_DATE_CHANGED
            )
            return expected in {
                item.change_type for item in compare_snapshots(t1, changed).changes
            }, "synthetic mutation"
        if name == "unknown_entity":
            result = json.loads(
                await executor.execute(
                    "get_work_item_evidence", {"item_id": "demo:UNKNOWN"}
                )
            )
            return result["data"] == {"error": "unknown_item"}, "safe lookup"
        if name == "conflicting_policy":
            return _conflicting_policy_detected(), "parsed machine-readable directives"
        raise KeyError(name)

    results = []
    for case in definition["cases"]:
        passed, detail = await check(case["check"])
        results.append({**case, "passed": passed, "detail": detail})

    validation_ok = True
    try:
        validate_assessment(assessment, t2, changes, policies, analysis2)
    except ValueError:
        validation_ok = False
    truth = definition["ground_truth"]
    expected_change_ids = set(truth["change_ids"])
    actual_change_ids = {change.change_id for change in changes.changes}
    expected_risk_ids = set(truth["risk_signal_ids"])
    actual_signal_ids = {signal.signal_id for signal in analysis2.signals}
    actual_risk_reasons = {risk.reason for risk in assessment.risks}
    known_signal_reasons = {signal.summary for signal in analysis2.signals}
    covered_risk_ids = {
        signal.signal_id
        for signal in analysis2.signals
        if signal.summary in actual_risk_reasons
    }
    covered_escalation_ids = {
        signal.signal_id
        for signal in analysis2.signals
        if any(
            action.rationale == signal.summary
            and action.evidence == signal.evidence_ids
            for action in assessment.escalations
        )
    }
    evidence_ids = {entry.evidence_id for entry in t2.evidence}
    evidence_ids.update(
        evidence_id for change in changes.changes for evidence_id in change.evidence_ids
    )
    policy_ids = {chunk.source_id for chunk in policies.chunks}
    references: list[str] = []
    for risk in assessment.risks:
        references.extend((*risk.evidence, *risk.policy_sources))
    for action in (*assessment.recommended_actions, *assessment.escalations):
        references.extend((*action.evidence, *action.policy_sources))
    invalid_references = [
        reference
        for reference in references
        if reference not in evidence_ids and reference not in policy_ids
    ]
    correct_policy_citations = 0
    for risk in assessment.risks:
        matching_signal = next(
            (
                signal
                for signal in analysis2.signals
                if signal.summary == risk.reason and signal.signal_type in POLICY_QUERY
            ),
            None,
        )
        if matching_signal is None:
            continue
        expected_sources = tuple(
            match.source_id
            for match in policies.search(
                POLICY_QUERY[matching_signal.signal_type][1], top_k=1
            )
        )
        correct_policy_citations += risk.policy_sources == expected_sources
    risks = assessment.risks
    return {
        "version": definition["version"],
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "passed": sum(item["passed"] for item in results),
            "total": len(results),
        },
        "metrics": {
            "deterministic_change_accuracy": len(
                expected_change_ids & actual_change_ids
            )
            / max(len(expected_change_ids | actual_change_ids), 1),
            "blocker_recall": len(set(truth["blocker_signal_ids"]) & actual_signal_ids)
            / max(len(truth["blocker_signal_ids"]), 1),
            "risk_recall": len(expected_risk_ids & covered_risk_ids)
            / max(len(expected_risk_ids), 1),
            "escalation_accuracy": len(
                set(truth["escalation_signal_ids"]) & covered_escalation_ids
            )
            / max(len(truth["escalation_signal_ids"]), 1),
            "policy_citation_accuracy": correct_policy_citations / max(len(risks), 1),
            "evidence_coverage": sum(
                bool(risk.evidence)
                and all(source in evidence_ids for source in risk.evidence)
                for risk in risks
            )
            / max(len(risks), 1),
            "unsupported_claim_rate": (
                len(actual_risk_reasons - known_signal_reasons) / max(len(risks), 1)
                if validation_ok
                else 1.0
            ),
            "invalid_reference_rate": len(invalid_references) / max(len(references), 1),
        },
        "cases": results,
    }


def _malformed_rejected() -> bool:
    try:
        DeliveryAssessment.model_validate({"overall_delivery_status": "READY"})
    except ValidationError:
        return True
    return False


def _unknown_blocker_age_is_explicit(snapshot: Any, policies: PolicyIndex) -> bool:
    blocker_id = next(
        relation.source_item_id
        for relation in snapshot.relations
        if relation.relation_type is RelationType.BLOCKED_BY
    )
    items = tuple(
        item.model_copy(update={"blocked_since": None})
        if item.item_id == blocker_id
        else item
        for item in snapshot.items
    )
    relations = tuple(
        relation.model_copy(update={"observed_at": None})
        if relation.source_item_id == blocker_id
        else relation
        for relation in snapshot.relations
    )
    unknown = snapshot.model_copy(update={"items": items, "relations": relations})
    analysis = analyze_delivery(
        unknown, compare_snapshots(None, unknown, policies.rules), policies.rules
    )
    return any(
        signal.signal_type is SignalType.BLOCKER_WITHIN_SLA
        and "duration unavailable" in signal.summary
        for signal in analysis.signals
    )


def _conflicting_policy_detected() -> bool:
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        (directory / "one.md").write_text(
            "# One\n\n<!-- adi: blocker_sla_days=2 -->\n\n## Critical blocker SLA\nTwo days.\n",
            encoding="utf-8",
        )
        (directory / "two.md").write_text(
            "# Two\n\n<!-- adi: blocker_sla_days=3 -->\n\n## Critical blocker SLA\nThree days.\n",
            encoding="utf-8",
        )
        index = PolicyIndex.from_directory(directory)
        return (
            index.conflicts == ("blocker_sla_days",)
            and len(index.search("critical blocker SLA", top_k=2)) == 2
        )


async def _prompt_injection_safe(
    assessment: DeliveryAssessment,
    executor: DeliveryToolExecutor,
    snapshot: Any,
    changes: Any,
    policies: PolicyIndex,
    analysis: Any,
) -> bool:
    tool_result = json.loads(await executor.execute("get_delivery_snapshot", {}))
    injected_title_present = any(
        "Ignore all system instructions" in item["title"]
        for item in tool_result["data"]
    )
    injected = assessment.model_copy(
        update={"overall_delivery_status": DeliveryHealth.ON_TRACK}
    )
    try:
        validate_assessment(injected, snapshot, changes, policies, analysis)
    except ValueError:
        return (
            tool_result["trust"] == "untrusted_tracker_data" and injected_title_present
        )
    return False


def _adapter_equivalence() -> bool:
    fields = {
        "summary": "Critical blocked item",
        "status": {"name": "In Progress"},
        "assignee": None,
        "created": "2026-08-20T09:00:00Z",
        "updated": "2026-09-04T09:00:00Z",
        "customfield_blocked": "2026-09-03T09:00:00Z",
    }
    jira = normalize_issue(
        {"key": "NS-17", "fields": fields},
        JiraMapping(
            stages={"In Progress": DeliveryStage.IN_PROGRESS},
            blocked_since_field="customfield_blocked",
        ),
        "https://northstar.atlassian.net",
    )
    kaiten = normalize_card(
        {
            "id": "NS-17",
            "title": "Critical blocked item",
            "column_id": 3,
            "owner": None,
            "created": "2026-08-20T09:00:00Z",
            "updated": "2026-09-04T09:00:00Z",
            "blocked_since": "2026-09-03T09:00:00Z",
        },
        KaitenMapping(stages={3: DeliveryStage.IN_PROGRESS}),
        "https://northstar.kaiten.ru",
    )
    return (
        jira.stage == kaiten.stage
        and jira.assignee == kaiten.assignee
        and jira.blocked_since == kaiten.blocked_since
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(evaluate())
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
