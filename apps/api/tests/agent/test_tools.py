import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adi.adapters.demo import DemoAdapter, DemoPhaseStore
from adi.agent.tools import DeliveryToolExecutor, ToolPermissionError
from adi.domain.models import ContextRef, SourceType
from adi.engine.diff import compare_snapshots
from adi.engine.signals import analyze_delivery
from adi.policies.retrieval import PolicyIndex

ROOT = Path(__file__).parents[4]


@pytest.mark.asyncio
async def test_tool_executor_exposes_bounded_read_only_facts() -> None:
    phase = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", phase)
    snapshot = await adapter.collect(
        ContextRef(source=SourceType.DEMO, external_id="northstar"),
        datetime(2026, 9, 3, 9, tzinfo=UTC),
    )
    changes = compare_snapshots(None, snapshot)
    executor = DeliveryToolExecutor(
        snapshot,
        changes,
        analyze_delivery(snapshot, changes),
        PolicyIndex.from_directory(ROOT / "policies"),
    )

    result = json.loads(await executor.execute("get_delivery_snapshot", {}))

    assert result["trust"] == "untrusted_tracker_data"
    assert result["data"][0]["external_id"] == "NS-01"


@pytest.mark.asyncio
async def test_tool_executor_rejects_unapproved_capability() -> None:
    phase = DemoPhaseStore()
    adapter = DemoAdapter(ROOT / "demo", phase)
    snapshot = await adapter.collect(
        ContextRef(source=SourceType.DEMO, external_id="northstar"),
        datetime(2026, 9, 3, 9, tzinfo=UTC),
    )
    changes = compare_snapshots(None, snapshot)
    executor = DeliveryToolExecutor(
        snapshot,
        changes,
        analyze_delivery(snapshot, changes),
        PolicyIndex.from_directory(ROOT / "policies"),
    )

    with pytest.raises(ToolPermissionError):
        await executor.execute("run_shell_command", {"command": "echo unsafe"})
