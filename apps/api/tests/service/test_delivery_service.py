from pathlib import Path

import pytest

from adi.adapters.demo import DemoAdapter, DemoPhaseStore
from adi.assessment.models import DeliveryHealth
from adi.persistence.memory import MemoryRunRepository
from adi.policies.retrieval import PolicyIndex
from adi.service import DeliveryService

ROOT = Path(__file__).parents[4]


@pytest.mark.asyncio
async def test_demo_story_persists_baseline_and_delta_run() -> None:
    phase = DemoPhaseStore()
    repository = MemoryRunRepository()
    service = DeliveryService(
        adapters={"demo": DemoAdapter(ROOT / "demo", phase)},
        policies=PolicyIndex.from_directory(ROOT / "policies"),
        repository=repository,
        demo_phase=phase,
    )

    result = await service.run_demo_story()
    history = await repository.list_runs("demo", "northstar")

    assert result.assessment.overall_delivery_status is DeliveryHealth.AT_RISK
    assert result.assessment.current_state_only is False
    assert len(history) == 2
    assert history[0].assessment.current_state_only is False
    assert history[1].assessment.current_state_only is True

    repeated = await service.run_demo_story()
    assert repeated.assessment.current_state_only is False
    latest = await repository.list_runs("demo", "northstar")
    assert latest[1].assessment.current_state_only is True
