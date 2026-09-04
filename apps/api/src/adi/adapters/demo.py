from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adi.domain.models import (
    CapabilityLevel,
    ContextRef,
    DeliveryContext,
    DeliverySnapshot,
    DeliveryStage,
    EvidenceRef,
    RelationType,
    SourceCapabilities,
    SourceType,
    WorkItem,
    WorkRelation,
)


class DemoPhaseStore:
    def __init__(self) -> None:
        self._phase = "t1"

    def current(self) -> str:
        return self._phase

    def advance(self) -> str:
        self._phase = "t2"
        return self._phase

    def reset(self) -> str:
        self._phase = "t1"
        return self._phase


class DemoAdapter:
    def __init__(self, fixture_directory: Path, phase_store: DemoPhaseStore) -> None:
        self.fixture_directory = fixture_directory
        self.phase_store = phase_store

    async def list_contexts(self) -> tuple[DeliveryContext, ...]:
        payload = self._load("t1")
        return (self._context(payload["context"]),)

    async def collect(self, context: ContextRef, observed_at: datetime) -> DeliverySnapshot:
        if context.source is not SourceType.DEMO or context.external_id != "northstar":
            raise ValueError("unknown demo context")
        payload = self._load(self.phase_store.current())
        items = tuple(self._item(entry, observed_at) for entry in payload["items"])
        relations = tuple(self._relation(entry) for entry in payload["relations"])
        evidence = (
            (
                EvidenceRef(
                    evidence_id=f"snapshot:demo:{context.external_id}",
                    kind="snapshot",
                    observed_at=observed_at,
                    attributes={"item_count": len(items)},
                ),
            )
            + tuple(
                EvidenceRef(
                    evidence_id=f"item:{item.item_id}",
                    kind="work_item",
                    item_id=item.item_id,
                    source_url=item.source_url,
                    observed_at=observed_at,
                    attributes={"stage": item.stage.value, "assignee": item.assignee},
                )
                for item in items
            )
            + tuple(
                EvidenceRef(
                    evidence_id=relation.evidence_id,
                    kind="relation",
                    item_id=relation.source_item_id,
                    observed_at=observed_at,
                    attributes={
                        "target_item_id": relation.target_item_id,
                        "relation_type": relation.relation_type.value,
                    },
                )
                for relation in relations
            )
        )
        return DeliverySnapshot(
            context=self._context(payload["context"]),
            observed_at=observed_at,
            items=items,
            relations=relations,
            evidence=evidence,
            configuration_fingerprint=self.configuration_fingerprint(),
        )

    def capabilities(self, context: ContextRef) -> SourceCapabilities:
        del context
        return self._capabilities()

    def configuration_fingerprint(self) -> str:
        return "northstar-demo-v1"

    def _load(self, phase: str) -> dict[str, Any]:
        path = self.fixture_directory / f"northstar-{phase}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _context(self, data: dict[str, Any]) -> DeliveryContext:
        return DeliveryContext(
            source=SourceType.DEMO,
            external_id=data["external_id"],
            name=data["name"],
            source_url="https://demo.example/northstar",
            target_date=_date(data.get("target_date")),
            wip_limit=data.get("wip_limit"),
            capabilities=self._capabilities(),
        )

    def _item(self, data: dict[str, Any], observed_at: datetime) -> WorkItem:
        created_at = _date(data.get("created_at")) or datetime(2026, 8, 1, tzinfo=UTC)
        return WorkItem(
            source=SourceType.DEMO,
            external_id=data["id"],
            title=data["title"],
            stage=DeliveryStage(data["stage"]),
            assignee=data.get("assignee"),
            priority=data.get("priority"),
            created_at=created_at,
            updated_at=observed_at,
            due_at=_date(data.get("due_at")),
            entered_stage_at=_date(data.get("entered_stage_at")),
            completed_at=_date(data.get("completed_at")),
            blocked_since=_date(data.get("blocked_since")),
            blocker_eta=_date(data.get("blocker_eta")),
            labels=tuple(data.get("labels", [])),
            source_url=f"https://demo.example/items/{data['id']}",
        )

    def _relation(self, data: dict[str, Any]) -> WorkRelation:
        source = f"demo:{data['source']}"
        target = f"demo:{data['target']}"
        relation_type = RelationType(data["type"])
        return WorkRelation(
            source_item_id=source,
            target_item_id=target,
            relation_type=relation_type,
            evidence_id=f"relation:{data['source']}:{relation_type.value}:{data['target']}",
            observed_at=_date(data.get("observed_at")),
            metadata=data.get("metadata", {}),
        )

    @staticmethod
    def _capabilities() -> SourceCapabilities:
        return SourceCapabilities(
            work_items=CapabilityLevel.SUPPORTED,
            stages=CapabilityLevel.SUPPORTED,
            due_dates=CapabilityLevel.SUPPORTED,
            assignees=CapabilityLevel.SUPPORTED,
            blockers=CapabilityLevel.SUPPORTED,
            dependencies=CapabilityLevel.SUPPORTED,
            stage_history=CapabilityLevel.SUPPORTED,
            priorities=CapabilityLevel.SUPPORTED,
            labels=CapabilityLevel.SUPPORTED,
            source_urls=CapabilityLevel.SUPPORTED,
        )


def _date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
