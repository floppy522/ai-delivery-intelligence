from datetime import UTC, datetime
from pathlib import Path

import pytest

from adi.adapters.demo import DemoAdapter, DemoPhaseStore
from adi.domain.models import ContextRef, DeliveryStage, RelationType, SourceType

ROOT = Path(__file__).parents[4]
T1_NOW = datetime(2026, 9, 3, 9, tzinfo=UTC)
T2_NOW = datetime(2026, 9, 7, 9, tzinfo=UTC)


@pytest.mark.asyncio
async def test_demo_t2_contains_expected_temporal_story() -> None:
    store = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", store)
    context = ContextRef(source=SourceType.DEMO, external_id="northstar")

    t1 = await adapter.collect(context, T1_NOW)
    store.advance()
    t2 = await adapter.collect(context, T2_NOW)

    assert len(t2.items) == 30
    assert sum(item.stage is DeliveryStage.DONE for item in t2.items) == (
        sum(item.stage is DeliveryStage.DONE for item in t1.items) + 1
    )
    assert any(
        relation.source_item_id == "demo:NS-17"
        and relation.relation_type is RelationType.BLOCKED_BY
        for relation in t2.relations
    )
    assert t2.context.wip_limit == 7


def test_demo_phase_store_stops_after_t2() -> None:
    store = DemoPhaseStore()
    assert store.current() == "t1"
    assert store.advance() == "t2"
    assert store.advance() == "t2"
    assert store.reset() == "t1"
