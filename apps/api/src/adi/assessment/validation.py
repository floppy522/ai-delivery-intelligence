import json
import re

from adi.assessment.models import (
    AssessmentValidationError,
    DeliveryAssessment,
    DeliveryRisk,
    RecommendedAction,
)
from adi.assessment.replay import ACTION_TEXT, ACTION_TYPE_BY_RISK_TITLE, POLICY_QUERY
from adi.domain.models import DeliverySnapshot
from adi.engine.diff import ChangeSet
from adi.engine.signals import DeliveryAnalysis, SignalType
from adi.policies.retrieval import PolicyIndex


def validate_assessment(
    assessment: DeliveryAssessment,
    snapshot: DeliverySnapshot,
    changes: ChangeSet,
    policies: PolicyIndex,
    analysis: DeliveryAnalysis | None = None,
    retrieved_policy_ids: set[str] | None = None,
) -> None:
    evidence_ids = {item.evidence_id for item in snapshot.evidence}
    evidence_ids.update(
        evidence_id for change in changes.changes for evidence_id in change.evidence_ids
    )
    item_ids = {item.item_id for item in snapshot.items}
    policy_ids = (
        retrieved_policy_ids
        if retrieved_policy_ids is not None
        else {chunk.source_id for chunk in policies.chunks}
    )
    if assessment.project != snapshot.context.name:
        raise AssessmentValidationError("project mismatch")
    if assessment.source != snapshot.context.source:
        raise AssessmentValidationError("source mismatch")
    if assessment.period.to_timestamp != snapshot.observed_at:
        raise AssessmentValidationError("period end mismatch")
    if assessment.current_state_only != changes.current_state_only:
        raise AssessmentValidationError("temporal mode mismatch")
    if assessment.period.from_timestamp != changes.from_timestamp:
        raise AssessmentValidationError("period start mismatch")
    rendered = json.dumps(assessment.model_dump(mode="json"), ensure_ascii=False)
    prohibited = re.compile(
        r"\b(?:NOT_READY|READY|NEEDS_DECISION|Go/No-Go|Go or No-Go|release[- ]readiness)\b",
        re.IGNORECASE,
    )
    if prohibited.search(rendered):
        raise AssessmentValidationError("prohibited release language")
    claims: tuple[DeliveryRisk | RecommendedAction, ...] = (
        *assessment.risks,
        *assessment.recommended_actions,
        *assessment.escalations,
    )
    for claim in claims:
        if not claim.evidence:
            raise AssessmentValidationError("claim is missing evidence")
        if not claim.policy_sources:
            raise AssessmentValidationError("claim is missing policy source")
        unknown_evidence = set(claim.evidence) - evidence_ids
        if unknown_evidence:
            raise AssessmentValidationError(f"unknown evidence: {sorted(unknown_evidence)}")
        unknown_policies = set(claim.policy_sources) - policy_ids
        if unknown_policies:
            raise AssessmentValidationError(f"unknown policy: {sorted(unknown_policies)}")
    for change in assessment.changes:
        if change.item_id and change.item_id not in item_ids:
            raise AssessmentValidationError(f"unknown item: {change.item_id}")
        unknown_evidence = set(change.evidence) - evidence_ids
        if unknown_evidence:
            raise AssessmentValidationError(f"unknown change evidence: {sorted(unknown_evidence)}")
        if not any(
            expected.change_type == change.change_type and expected.item_id == change.item_id
            for expected in changes.changes
        ):
            raise AssessmentValidationError("unsupported temporal change")
    expected_changes = {
        (change.change_type, change.item_id, change.evidence_ids) for change in changes.changes
    }
    reported_changes = {
        (change.change_type, change.item_id, change.evidence) for change in assessment.changes
    }
    if reported_changes != expected_changes:
        raise AssessmentValidationError("temporal change coverage mismatch")
    for signal in assessment.flow_signals:
        unknown_items = set(signal.item_ids) - item_ids
        if unknown_items:
            raise AssessmentValidationError(f"unknown signal item: {sorted(unknown_items)}")
        unknown_evidence = set(signal.evidence) - evidence_ids
        if unknown_evidence:
            raise AssessmentValidationError(f"unknown signal evidence: {sorted(unknown_evidence)}")
        if analysis is not None and not any(
            expected.signal_type == signal.signal_type
            and expected.item_ids == signal.item_ids
            and expected.evidence_ids == signal.evidence
            for expected in analysis.signals
        ):
            raise AssessmentValidationError("unsupported flow signal")
    if analysis is not None:
        expected_signals = {
            (signal.signal_type, signal.item_ids, signal.evidence_ids)
            for signal in analysis.signals
        }
        reported_signals = {
            (signal.signal_type, signal.item_ids, signal.evidence)
            for signal in assessment.flow_signals
        }
        if reported_signals != expected_signals:
            raise AssessmentValidationError("flow signal coverage mismatch")
        material = [signal for signal in analysis.signals if signal.signal_type in POLICY_QUERY]
        matched_risks = [
            risk
            for risk in assessment.risks
            if any(
                risk.reason == signal.summary
                and risk.title == POLICY_QUERY[signal.signal_type][0]
                and risk.severity.value == signal.severity
                and risk.evidence == signal.evidence_ids
                and risk.policy_sources
                == tuple(
                    match.source_id
                    for match in policies.search(POLICY_QUERY[signal.signal_type][1], top_k=1)
                )
                for signal in material
            )
        ]
        if len(matched_risks) != len(material) or len(assessment.risks) != len(material):
            raise AssessmentValidationError("risk coverage mismatch")
    for action in (*assessment.recommended_actions, *assessment.escalations):
        if action.action != ACTION_TEXT[action.action_type]:
            raise AssessmentValidationError("action is outside the safe recommendation catalog")
        matching_risk = next(
            (
                risk
                for risk in assessment.risks
                if action.rationale == risk.reason
                and action.evidence == risk.evidence
                and action.policy_sources == risk.policy_sources
            ),
            None,
        )
        if matching_risk is None:
            raise AssessmentValidationError("action is not grounded in a reported risk")
        if action.action_type is not ACTION_TYPE_BY_RISK_TITLE.get(
            matching_risk.title, action.action_type
        ):
            raise AssessmentValidationError("action type conflicts with the grounded risk")
    critical_reasons = {
        risk.reason for risk in assessment.risks if risk.severity.value == "critical"
    }
    action_reasons = {action.rationale for action in assessment.recommended_actions}
    if not critical_reasons <= action_reasons:
        raise AssessmentValidationError("critical risk is missing a recommended action")
    expected_escalations = {
        (action.action_type, action.rationale, action.evidence, action.policy_sources)
        for action in assessment.recommended_actions
        if action.rationale in critical_reasons
    }
    reported_escalations = {
        (action.action_type, action.rationale, action.evidence, action.policy_sources)
        for action in assessment.escalations
    }
    if reported_escalations != expected_escalations:
        raise AssessmentValidationError("critical escalation coverage mismatch")
    if assessment.current_state_only and assessment.changes:
        raise AssessmentValidationError("first run cannot contain temporal changes")
    high = sum(risk.severity.value in {"high", "critical"} for risk in assessment.risks)
    flow_blocked = analysis is not None and any(
        signal.signal_type is SignalType.DELIVERY_FLOW_BLOCKED for signal in analysis.signals
    )
    expected_status = (
        "BLOCKED"
        if flow_blocked
        else "AT_RISK"
        if high >= 2
        else "ATTENTION"
        if assessment.risks
        else "ON_TRACK"
    )
    if assessment.overall_delivery_status.value != expected_status:
        raise AssessmentValidationError("status conflicts with deterministic analysis")
