from __future__ import annotations

from adi.assessment.models import (
    ActionType,
    AssessmentChange,
    AssessmentMode,
    AssessmentSignal,
    DeliveryAssessment,
    DeliveryHealth,
    DeliveryRisk,
    Period,
    RecommendedAction,
    Severity,
)
from adi.domain.models import DeliverySnapshot
from adi.engine.diff import ChangeSet
from adi.engine.signals import DeliveryAnalysis, DeliverySignal, SignalType
from adi.policies.retrieval import PolicyIndex

POLICY_QUERY = {
    SignalType.WIP_LIMIT_EXCEEDED: ("WIP limit exceeded", "WIP limit exceeded"),
    SignalType.AGING_WORK: ("Aging work", "aging work stage review"),
    SignalType.VERIFY_QUEUE_AGING: ("Verify queue is aging", "aging Verify queue"),
    SignalType.BLOCKER_SLA_EXCEEDED: (
        "Blocker SLA exceeded",
        "critical blocker SLA owner ETA",
    ),
    SignalType.BLOCKER_MISSING_OWNER: (
        "Blocked work has no owner",
        "critical blocker owner requirement",
    ),
    SignalType.BLOCKER_MISSING_ETA: (
        "Blocked work has no ETA",
        "critical blocker ETA requirement",
    ),
    SignalType.DEPENDENCY_THREATENS_TARGET: (
        "Dependency threatens target date",
        "unresolved dependency target date commitment",
    ),
    SignalType.OVERDUE_WORK: ("Work is overdue", "delivery target date risk"),
    SignalType.DELIVERY_FLOW_BLOCKED: (
        "Delivery flow has no viable path",
        "delivery flow cannot continue no viable path",
    ),
}

ACTION_TEXT = {
    ActionType.ESCALATE_BLOCKER: "Escalate blocker ownership and agree a recovery ETA.",
    ActionType.ASSIGN_OWNER: "Assign an accountable owner for the blocker.",
    ActionType.OBTAIN_ETA: "Obtain and record a blocker resolution ETA.",
    ActionType.REBALANCE_WIP: "Stop starting work and rebalance active WIP.",
    ActionType.REVIEW_AGING_QUEUE: "Review queue capacity and unblock the oldest item.",
    ActionType.COORDINATE_DEPENDENCY: "Convene dependency owners and agree mitigation.",
    ActionType.REVIEW_OVERDUE_WORK: "Review overdue work and agree a recovery plan.",
    ActionType.RESTORE_FLOW_PATH: "Restore a viable delivery path with accountable owners.",
    ActionType.REVIEW_EVIDENCE: "Review the evidence and agree a management response.",
}

ACTION_TYPE_BY_RISK_TITLE = {
    "Blocker SLA exceeded": ActionType.ESCALATE_BLOCKER,
    "Blocked work has no owner": ActionType.ASSIGN_OWNER,
    "Blocked work has no ETA": ActionType.OBTAIN_ETA,
    "WIP limit exceeded": ActionType.REBALANCE_WIP,
    "Verify queue is aging": ActionType.REVIEW_AGING_QUEUE,
    "Aging work": ActionType.REVIEW_AGING_QUEUE,
    "Dependency threatens target date": ActionType.COORDINATE_DEPENDENCY,
    "Work is overdue": ActionType.REVIEW_OVERDUE_WORK,
    "Delivery flow has no viable path": ActionType.RESTORE_FLOW_PATH,
}


def build_replay_assessment(
    snapshot: DeliverySnapshot,
    changes: ChangeSet,
    analysis: DeliveryAnalysis,
    policies: PolicyIndex,
) -> DeliveryAssessment:
    material = [signal for signal in analysis.signals if signal.signal_type in POLICY_QUERY]
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    risks = tuple(
        sorted(
            (_risk(signal, policies) for signal in material),
            key=lambda risk: severity_rank.get(risk.severity, 4),
        )
    )
    high = sum(risk.severity in {"high", "critical"} for risk in risks)
    status = (
        DeliveryHealth.BLOCKED
        if any(signal.signal_type is SignalType.DELIVERY_FLOW_BLOCKED for signal in material)
        else DeliveryHealth.AT_RISK
        if high >= 2
        else DeliveryHealth.ATTENTION
        if risks
        else DeliveryHealth.ON_TRACK
    )
    critical_risks = [risk for risk in risks if risk.severity == "critical"]
    other_risks = [risk for risk in risks if risk.severity != "critical"]
    selected_risks = (*critical_risks, *other_risks[: max(0, 4 - len(critical_risks))])
    actions = tuple(_action(risk) for risk in selected_risks)
    escalations = tuple(
        action
        for action, risk in zip(actions, selected_risks, strict=True)
        if risk.severity == "critical"
    )
    uncertainty = (
        ("No previous snapshot available. Current-state analysis only.",)
        if changes.current_state_only
        else ()
    )
    return DeliveryAssessment(
        project=snapshot.context.name,
        source=snapshot.context.source,
        period=Period(from_timestamp=changes.from_timestamp, to_timestamp=snapshot.observed_at),
        overall_delivery_status=status,
        mode=AssessmentMode.REPLAY,
        current_state_only=changes.current_state_only,
        changes=tuple(
            AssessmentChange(
                change_type=change.change_type,
                summary=change.summary,
                item_id=change.item_id,
                evidence=change.evidence_ids,
            )
            for change in changes.changes
        ),
        flow_signals=tuple(
            AssessmentSignal(
                signal_type=signal.signal_type,
                severity=Severity(signal.severity),
                summary=signal.summary,
                item_ids=signal.item_ids,
                evidence=signal.evidence_ids,
            )
            for signal in analysis.signals
        ),
        risks=risks,
        recommended_actions=actions,
        escalations=escalations,
        uncertainties=uncertainty,
    )


def _risk(signal: DeliverySignal, policies: PolicyIndex) -> DeliveryRisk:
    title, query = POLICY_QUERY[signal.signal_type]
    matches = policies.search(query, top_k=1)
    return DeliveryRisk(
        title=title,
        severity=Severity(signal.severity),
        reason=signal.summary,
        evidence=signal.evidence_ids,
        policy_sources=tuple(match.source_id for match in matches),
    )


def _action(risk: DeliveryRisk) -> RecommendedAction:
    action_type = ACTION_TYPE_BY_RISK_TITLE.get(risk.title, ActionType.REVIEW_EVIDENCE)
    return RecommendedAction(
        action_type=action_type,
        action=ACTION_TEXT[action_type],
        rationale=risk.reason,
        evidence=risk.evidence,
        policy_sources=risk.policy_sources,
    )
