from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from adi.domain.models import DeliverySnapshot, FrozenModel, RelationType, WorkItem
from adi.policies.retrieval import DeliveryPolicyRules


class ChangeType(StrEnum):
    ITEM_CREATED = "ITEM_CREATED"
    ITEM_COMPLETED = "ITEM_COMPLETED"
    STAGE_CHANGED = "STAGE_CHANGED"
    OWNER_CHANGED = "OWNER_CHANGED"
    DUE_DATE_CHANGED = "DUE_DATE_CHANGED"
    ITEM_BECAME_OVERDUE = "ITEM_BECAME_OVERDUE"
    BLOCKER_APPEARED = "BLOCKER_APPEARED"
    BLOCKER_RESOLVED = "BLOCKER_RESOLVED"
    DEPENDENCY_APPEARED = "DEPENDENCY_APPEARED"
    DEPENDENCY_RESOLVED = "DEPENDENCY_RESOLVED"
    WIP_CHANGED = "WIP_CHANGED"
    WIP_LIMIT_CROSSED = "WIP_LIMIT_CROSSED"
    AGING_THRESHOLD_CROSSED = "AGING_THRESHOLD_CROSSED"


class DeliveryChange(FrozenModel):
    change_id: str
    change_type: ChangeType
    item_id: str | None = None
    summary: str
    before: Any = None
    after: Any = None
    evidence_ids: tuple[str, ...] = ()


class ChangeSet(FrozenModel):
    current_state_only: bool
    from_timestamp: datetime | None = None
    changes: tuple[DeliveryChange, ...] = Field(default_factory=tuple)


ACTIVE_STAGES = {"ANALYSIS", "IN_PROGRESS", "VERIFY"}


def compare_snapshots(
    previous: DeliverySnapshot | None,
    current: DeliverySnapshot,
    rules: DeliveryPolicyRules | None = None,
) -> ChangeSet:
    policy = rules or DeliveryPolicyRules()
    if previous is None:
        return ChangeSet(current_state_only=True)
    changes: list[DeliveryChange] = []
    old = {item.item_id: item for item in previous.items}
    new = {item.item_id: item for item in current.items}
    for item_id in sorted(new.keys() - old.keys()):
        changes.append(_change(ChangeType.ITEM_CREATED, new[item_id], "Item created"))
    for item_id in sorted(old.keys() & new.keys()):
        before, after = old[item_id], new[item_id]
        if before.stage != after.stage:
            changes.append(
                _change(
                    ChangeType.ITEM_COMPLETED
                    if after.stage.value == "DONE"
                    else ChangeType.STAGE_CHANGED,
                    after,
                    f"Stage changed from {before.stage.value} to {after.stage.value}",
                    before.stage.value,
                    after.stage.value,
                )
            )
        if before.assignee != after.assignee:
            changes.append(
                _change(
                    ChangeType.OWNER_CHANGED,
                    after,
                    "Owner changed",
                    before.assignee,
                    after.assignee,
                )
            )
        if before.due_at != after.due_at:
            changes.append(
                _change(
                    ChangeType.DUE_DATE_CHANGED,
                    after,
                    "Due date changed",
                    before.due_at,
                    after.due_at,
                )
            )
        if before.due_at and after.due_at and before.due_at >= previous.observed_at:
            if after.due_at < current.observed_at and after.stage.value != "DONE":
                changes.append(
                    _change(ChangeType.ITEM_BECAME_OVERDUE, after, "Item became overdue")
                )
        if before.entered_stage_at and after.entered_stage_at:
            old_age = previous.observed_at - before.entered_stage_at
            new_age = current.observed_at - after.entered_stage_at
            threshold = (
                policy.verify_aging_days if after.stage.value == "VERIFY" else policy.aging_days
            )
            if old_age.days < threshold <= new_age.days and after.stage.value in ACTIVE_STAGES:
                changes.append(
                    _change(
                        ChangeType.AGING_THRESHOLD_CROSSED,
                        after,
                        "Aging threshold crossed",
                    )
                )
    changes.extend(_relation_changes(previous, current))
    old_wip = _wip(previous)
    new_wip = _wip(current)
    if old_wip != new_wip:
        changes.append(
            DeliveryChange(
                change_id="change:wip",
                change_type=ChangeType.WIP_CHANGED,
                summary=f"WIP changed from {old_wip} to {new_wip}",
                before=old_wip,
                after=new_wip,
            )
        )
    limit = current.context.wip_limit
    if limit and old_wip <= limit < new_wip:
        changes.append(
            DeliveryChange(
                change_id="change:wip-limit-crossed",
                change_type=ChangeType.WIP_LIMIT_CROSSED,
                summary=f"WIP crossed the configured limit of {limit}",
                before=old_wip,
                after=new_wip,
            )
        )
    return ChangeSet(
        current_state_only=False,
        from_timestamp=previous.observed_at,
        changes=tuple(changes),
    )


def _relation_changes(
    previous: DeliverySnapshot, current: DeliverySnapshot
) -> list[DeliveryChange]:
    def key(relation: Any) -> tuple[str, str, RelationType]:
        return (relation.source_item_id, relation.target_item_id, relation.relation_type)

    old = {key(relation): relation for relation in previous.relations}
    new = {key(relation): relation for relation in current.relations}
    result: list[DeliveryChange] = []
    for relation_key in sorted(new.keys() - old.keys()):
        relation = new[relation_key]
        blocker = relation.relation_type in {RelationType.BLOCKS, RelationType.BLOCKED_BY}
        result.append(
            DeliveryChange(
                change_id=f"change:{relation.evidence_id}:appeared",
                change_type=(
                    ChangeType.BLOCKER_APPEARED if blocker else ChangeType.DEPENDENCY_APPEARED
                ),
                item_id=relation.source_item_id,
                summary=f"{relation.relation_type.value} relation appeared",
                after=relation.target_item_id,
                evidence_ids=(relation.evidence_id,),
            )
        )
    for relation_key in sorted(old.keys() - new.keys()):
        relation = old[relation_key]
        blocker = relation.relation_type in {RelationType.BLOCKS, RelationType.BLOCKED_BY}
        result.append(
            DeliveryChange(
                change_id=f"change:{relation.evidence_id}:resolved",
                change_type=(
                    ChangeType.BLOCKER_RESOLVED if blocker else ChangeType.DEPENDENCY_RESOLVED
                ),
                item_id=relation.source_item_id,
                summary=f"{relation.relation_type.value} relation resolved",
                before=relation.target_item_id,
                evidence_ids=(relation.evidence_id,),
            )
        )
    return result


def _change(
    change_type: ChangeType,
    item: WorkItem,
    summary: str,
    before: Any = None,
    after: Any = None,
) -> DeliveryChange:
    return DeliveryChange(
        change_id=f"change:{item.external_id}:{change_type.value.lower()}",
        change_type=change_type,
        item_id=item.item_id,
        summary=summary,
        before=before,
        after=after,
        evidence_ids=(f"item:{item.item_id}",),
    )


def _wip(snapshot: DeliverySnapshot) -> int:
    return sum(item.stage.value in ACTIVE_STAGES for item in snapshot.items)
