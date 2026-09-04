from __future__ import annotations

from enum import StrEnum

from adi.domain.models import DeliverySnapshot, DeliveryStage, FrozenModel, RelationType
from adi.engine.diff import ChangeSet
from adi.policies.retrieval import DeliveryPolicyRules


class SignalType(StrEnum):
    WIP_LIMIT_EXCEEDED = "WIP_LIMIT_EXCEEDED"
    AGING_WORK = "AGING_WORK"
    VERIFY_QUEUE_AGING = "VERIFY_QUEUE_AGING"
    BLOCKER_WITHIN_SLA = "BLOCKER_WITHIN_SLA"
    BLOCKER_SLA_EXCEEDED = "BLOCKER_SLA_EXCEEDED"
    BLOCKER_MISSING_OWNER = "BLOCKER_MISSING_OWNER"
    BLOCKER_MISSING_ETA = "BLOCKER_MISSING_ETA"
    DEPENDENCY_THREATENS_TARGET = "DEPENDENCY_THREATENS_TARGET"
    DEPENDENCY_HARMLESS = "DEPENDENCY_HARMLESS"
    OVERDUE_WORK = "OVERDUE_WORK"
    DELIVERY_FLOW_BLOCKED = "DELIVERY_FLOW_BLOCKED"


class FlowMetrics(FrozenModel):
    wip: int
    wip_limit: int | None
    aging_items: int
    blocked_items: int
    verify_items: int


class DeliverySignal(FrozenModel):
    signal_id: str
    signal_type: SignalType
    severity: str
    summary: str
    item_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class DeliveryAnalysis(FrozenModel):
    metrics: FlowMetrics
    signals: tuple[DeliverySignal, ...]


def analyze_delivery(
    snapshot: DeliverySnapshot,
    changes: ChangeSet,
    rules: DeliveryPolicyRules | None = None,
) -> DeliveryAnalysis:
    del changes
    policy = rules or DeliveryPolicyRules()
    active = [
        item
        for item in snapshot.items
        if item.stage in {DeliveryStage.ANALYSIS, DeliveryStage.IN_PROGRESS, DeliveryStage.VERIFY}
    ]
    aging = [
        item
        for item in active
        if item.entered_stage_at
        and (snapshot.observed_at - item.entered_stage_at).days
        >= (policy.verify_aging_days if item.stage is DeliveryStage.VERIFY else policy.aging_days)
    ]
    blocked_relations = [
        relation
        for relation in snapshot.relations
        if relation.relation_type is RelationType.BLOCKED_BY
    ]
    signals: list[DeliverySignal] = []
    if snapshot.context.wip_limit and len(active) > snapshot.context.wip_limit:
        signals.append(
            _signal(
                SignalType.WIP_LIMIT_EXCEEDED,
                "high",
                f"WIP is {len(active)} against a limit of {snapshot.context.wip_limit}",
                evidence_id=(
                    f"snapshot:{snapshot.context.source.value}:{snapshot.context.external_id}"
                ),
            )
        )
    for item in aging:
        entered_stage_at = item.entered_stage_at
        if entered_stage_at is None:
            continue
        signal_type = (
            SignalType.VERIFY_QUEUE_AGING
            if item.stage is DeliveryStage.VERIFY
            else SignalType.AGING_WORK
        )
        signals.append(
            _signal(
                signal_type,
                "medium",
                f"{item.external_id} has remained in {item.stage.value} for "
                f"{(snapshot.observed_at - entered_stage_at).days} days",
                item.item_id,
            )
        )
    items = {item.item_id: item for item in snapshot.items}
    for relation in blocked_relations:
        item = items[relation.source_item_id]
        blocked_since = item.blocked_since or relation.observed_at
        days = (snapshot.observed_at - blocked_since).days if blocked_since else 0
        signals.append(
            _signal(
                SignalType.BLOCKER_SLA_EXCEEDED
                if days > policy.blocker_sla_days
                else SignalType.BLOCKER_WITHIN_SLA,
                "critical" if days > policy.blocker_sla_days else "low",
                (
                    f"{item.external_id} has been blocked for {days} days"
                    if blocked_since
                    else f"{item.external_id} is blocked; duration unavailable"
                ),
                item.item_id,
                relation.evidence_id,
            )
        )
        if item.assignee is None:
            signals.append(
                _signal(
                    SignalType.BLOCKER_MISSING_OWNER,
                    "high",
                    f"{item.external_id} is blocked without an owner",
                    item.item_id,
                    relation.evidence_id,
                )
            )
        if item.blocker_eta is None:
            signals.append(
                _signal(
                    SignalType.BLOCKER_MISSING_ETA,
                    "medium",
                    f"{item.external_id} is blocked without an ETA",
                    item.item_id,
                    relation.evidence_id,
                )
            )
        if relation.metadata.get("delivery_flow_blocked") is True:
            signals.append(
                _signal(
                    SignalType.DELIVERY_FLOW_BLOCKED,
                    "critical",
                    f"{item.external_id} blocks delivery with no viable path recorded",
                    item.item_id,
                    relation.evidence_id,
                )
            )
    for relation in snapshot.relations:
        if relation.relation_type is not RelationType.DEPENDS_ON:
            continue
        dependent = items[relation.source_item_id]
        prerequisite = items[relation.target_item_id]
        days_to_target = (
            (snapshot.context.target_date - snapshot.observed_at).days
            if snapshot.context.target_date
            else 999
        )
        threatens = (
            prerequisite.stage is not DeliveryStage.DONE
            and days_to_target <= policy.dependency_threat_days
        )
        signals.append(
            _signal(
                SignalType.DEPENDENCY_THREATENS_TARGET
                if threatens
                else SignalType.DEPENDENCY_HARMLESS,
                "high" if threatens else "low",
                f"{dependent.external_id} depends on {prerequisite.external_id}",
                dependent.item_id,
                relation.evidence_id,
            )
        )
    for item in snapshot.items:
        if (
            item.due_at
            and item.due_at < snapshot.observed_at
            and item.stage is not DeliveryStage.DONE
        ):
            signals.append(
                _signal(
                    SignalType.OVERDUE_WORK,
                    "high",
                    f"{item.external_id} is overdue",
                    item.item_id,
                )
            )
    metrics = FlowMetrics(
        wip=len(active),
        wip_limit=snapshot.context.wip_limit,
        aging_items=len(aging),
        blocked_items=len(blocked_relations),
        verify_items=sum(item.stage is DeliveryStage.VERIFY for item in snapshot.items),
    )
    return DeliveryAnalysis(metrics=metrics, signals=tuple(signals))


def _signal(
    signal_type: SignalType,
    severity: str,
    summary: str,
    item_id: str | None = None,
    evidence_id: str | None = None,
) -> DeliverySignal:
    item_ids = (item_id,) if item_id else ()
    evidence_ids = (evidence_id,) if evidence_id else ((f"item:{item_id}",) if item_id else ())
    return DeliverySignal(
        signal_id=f"signal:{signal_type.value.lower()}:{item_id or 'board'}",
        signal_type=signal_type,
        severity=severity,
        summary=summary,
        item_ids=item_ids,
        evidence_ids=evidence_ids,
    )
