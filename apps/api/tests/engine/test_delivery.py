from datetime import UTC, datetime
from pathlib import Path

import pytest

from adi.adapters.demo import DemoAdapter, DemoPhaseStore
from adi.domain.models import ContextRef, SourceType
from adi.engine.diff import ChangeType, compare_snapshots
from adi.engine.signals import SignalType, analyze_delivery

ROOT = Path(__file__).parents[4]


@pytest.mark.asyncio
async def test_northstar_t2_detects_expected_changes_and_signals() -> None:
    store = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", store)
    context = ContextRef(source=SourceType.DEMO, external_id="northstar")
    t1 = await adapter.collect(context, datetime(2026, 9, 3, 9, tzinfo=UTC))
    store.advance()
    t2 = await adapter.collect(context, datetime(2026, 9, 7, 9, tzinfo=UTC))

    changes = compare_snapshots(t1, t2)
    analysis = analyze_delivery(t2, changes)

    assert changes.current_state_only is False
    assert {change.change_type for change in changes.changes} >= {
        ChangeType.ITEM_COMPLETED,
        ChangeType.STAGE_CHANGED,
        ChangeType.BLOCKER_APPEARED,
        ChangeType.BLOCKER_RESOLVED,
        ChangeType.WIP_LIMIT_CROSSED,
    }
    assert analysis.metrics.wip == 10
    assert analysis.metrics.wip_limit == 7
    assert {signal.signal_type for signal in analysis.signals} >= {
        SignalType.WIP_LIMIT_EXCEEDED,
        SignalType.BLOCKER_SLA_EXCEEDED,
        SignalType.VERIFY_QUEUE_AGING,
        SignalType.DEPENDENCY_THREATENS_TARGET,
    }


@pytest.mark.asyncio
async def test_first_run_has_no_fabricated_changes() -> None:
    adapter = DemoAdapter(ROOT / "demo", DemoPhaseStore())
    snapshot = await adapter.collect(
        ContextRef(source=SourceType.DEMO, external_id="northstar"),
        datetime(2026, 9, 3, 9, tzinfo=UTC),
    )
    changes = compare_snapshots(None, snapshot)
    assert changes.current_state_only is True
    assert changes.changes == ()
