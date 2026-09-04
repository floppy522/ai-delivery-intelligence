from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceType(StrEnum):
    DEMO = "demo"
    KAITEN = "kaiten"
    JIRA = "jira"


class CapabilityLevel(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class DeliveryStage(StrEnum):
    BACKLOG = "BACKLOG"
    ANALYSIS = "ANALYSIS"
    IN_PROGRESS = "IN_PROGRESS"
    VERIFY = "VERIFY"
    DONE = "DONE"
    UNKNOWN = "UNKNOWN"


class RelationType(StrEnum):
    BLOCKS = "BLOCKS"
    BLOCKED_BY = "BLOCKED_BY"
    DEPENDS_ON = "DEPENDS_ON"
    DEPENDED_ON_BY = "DEPENDED_ON_BY"


class SourceCapabilities(FrozenModel):
    work_items: CapabilityLevel = CapabilityLevel.UNAVAILABLE
    stages: CapabilityLevel = CapabilityLevel.UNAVAILABLE
    due_dates: CapabilityLevel = CapabilityLevel.UNAVAILABLE
    assignees: CapabilityLevel = CapabilityLevel.UNAVAILABLE
    blockers: CapabilityLevel = CapabilityLevel.UNAVAILABLE
    dependencies: CapabilityLevel = CapabilityLevel.UNAVAILABLE
    stage_history: CapabilityLevel = CapabilityLevel.UNAVAILABLE
    priorities: CapabilityLevel = CapabilityLevel.UNAVAILABLE
    labels: CapabilityLevel = CapabilityLevel.UNAVAILABLE
    source_urls: CapabilityLevel = CapabilityLevel.UNAVAILABLE


class ContextRef(FrozenModel):
    source: SourceType
    external_id: str = Field(min_length=1)
    parent_external_id: str | None = None


class DeliveryContext(FrozenModel):
    source: SourceType
    external_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source_url: str | None = None
    target_date: datetime | None = None
    wip_limit: int | None = Field(default=None, ge=1)
    capabilities: SourceCapabilities

    @model_validator(mode="after")
    def validate_url(self) -> DeliveryContext:
        _validate_https(self.source_url)
        return self


class EvidenceRef(FrozenModel):
    evidence_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    item_id: str | None = None
    source_url: str | None = None
    observed_at: datetime | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_url(self) -> EvidenceRef:
        _validate_https(self.source_url)
        return self


class WorkItem(FrozenModel):
    source: SourceType
    external_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    stage: DeliveryStage
    assignee: str | None = None
    priority: str | None = None
    created_at: datetime
    updated_at: datetime
    due_at: datetime | None = None
    entered_stage_at: datetime | None = None
    completed_at: datetime | None = None
    blocked_since: datetime | None = None
    blocker_eta: datetime | None = None
    labels: tuple[str, ...] = ()
    source_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def item_id(self) -> str:
        return f"{self.source.value}:{self.external_id}"

    @model_validator(mode="after")
    def validate_item(self) -> WorkItem:
        _validate_https(self.source_url)
        for value in (
            self.created_at,
            self.updated_at,
            self.due_at,
            self.entered_stage_at,
            self.completed_at,
            self.blocked_since,
            self.blocker_eta,
        ):
            _validate_aware(value)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class WorkRelation(FrozenModel):
    source_item_id: str = Field(min_length=1)
    target_item_id: str = Field(min_length=1)
    relation_type: RelationType
    evidence_id: str = Field(min_length=1)
    observed_at: datetime | None = None
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliverySnapshot(FrozenModel):
    context: DeliveryContext
    observed_at: datetime
    items: tuple[WorkItem, ...]
    relations: tuple[WorkRelation, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    configuration_fingerprint: str = "demo-v1"

    @model_validator(mode="after")
    def validate_snapshot(self) -> DeliverySnapshot:
        _validate_aware(self.observed_at)
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("duplicate work item IDs")
        if any(item.source is not self.context.source for item in self.items):
            raise ValueError("work item source differs from context source")
        known_items = set(item_ids)
        for relation in self.relations:
            endpoints_exist = (
                relation.source_item_id in known_items and relation.target_item_id in known_items
            )
            if not endpoints_exist:
                raise ValueError("relation references unknown work item")
        evidence_ids = [entry.evidence_id for entry in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate evidence IDs")
        return self


def _validate_https(value: str | None) -> None:
    if value is not None and not value.startswith("https://"):
        raise ValueError("source URL must use https")


def _validate_aware(value: datetime | None) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
