from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from adi.domain.models import (
    CapabilityLevel,
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

NOW = datetime(2026, 9, 3, 12, tzinfo=UTC)


def _context() -> DeliveryContext:
    return DeliveryContext(
        source=SourceType.DEMO,
        external_id="northstar",
        name="Northstar Platform",
        source_url="https://example.test/northstar",
        capabilities=SourceCapabilities(
            work_items=CapabilityLevel.SUPPORTED,
            stages=CapabilityLevel.SUPPORTED,
        ),
    )


def _item() -> WorkItem:
    return WorkItem(
        source=SourceType.DEMO,
        external_id="NS-1",
        title="Design delivery contract",
        stage=DeliveryStage.ANALYSIS,
        created_at=NOW,
        updated_at=NOW,
        source_url="https://example.test/items/NS-1",
    )


def test_snapshot_rejects_duplicate_item_ids() -> None:
    item = _item()
    with pytest.raises(ValidationError, match="duplicate work item"):
        DeliverySnapshot(context=_context(), observed_at=NOW, items=[item, item])


def test_item_id_is_source_qualified() -> None:
    assert _item().item_id == "demo:NS-1"


def test_source_url_must_be_https() -> None:
    with pytest.raises(ValidationError):
        WorkItem(
            source=SourceType.DEMO,
            external_id="NS-2",
            title="Unsafe link",
            stage=DeliveryStage.BACKLOG,
            created_at=NOW,
            updated_at=NOW,
            source_url="http://example.test/NS-2",
        )


def test_unknown_stage_is_explicit() -> None:
    assert DeliveryStage.UNKNOWN.value == "UNKNOWN"


def test_relation_endpoints_must_exist_in_snapshot() -> None:
    relation = WorkRelation(
        source_item_id="demo:NS-1",
        target_item_id="demo:NS-404",
        relation_type=RelationType.DEPENDS_ON,
        evidence_id="relation:NS-1:NS-404",
    )
    with pytest.raises(ValidationError, match="unknown work item"):
        DeliverySnapshot(
            context=_context(),
            observed_at=NOW,
            items=[_item()],
            relations=[relation],
            evidence=[EvidenceRef(evidence_id="relation:NS-1:NS-404", kind="relation")],
        )


def test_snapshot_rejects_duplicate_evidence_ids() -> None:
    evidence = EvidenceRef(evidence_id="item:NS-1", kind="work_item")
    with pytest.raises(ValidationError, match="duplicate evidence"):
        DeliverySnapshot(
            context=_context(),
            observed_at=NOW,
            items=[_item()],
            evidence=[evidence, evidence],
        )
