from pathlib import Path

import httpx
import pytest

from adi.adapters.demo import DemoAdapter, DemoPhaseStore
from adi.api import create_app
from adi.persistence.memory import MemoryRunRepository
from adi.policies.retrieval import PolicyIndex
from adi.service import DeliveryService

ROOT = Path(__file__).parents[4]


@pytest.mark.asyncio
async def test_demo_api_returns_decision_first_assessment_and_history() -> None:
    phase = DemoPhaseStore()
    repository = MemoryRunRepository()
    service = DeliveryService(
        adapters={"demo": DemoAdapter(ROOT / "demo", phase)},
        policies=PolicyIndex.from_directory(ROOT / "policies"),
        repository=repository,
        demo_phase=phase,
    )
    transport = httpx.ASGITransport(app=create_app(service=service))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/demo/run")
        history = await client.get(
            "/api/runs",
            params={"source": "demo", "context_id": "northstar"},
        )

    assert response.status_code == 200
    assert response.json()["assessment"]["overall_delivery_status"] == "AT_RISK"
    assert response.json()["assessment"]["changes"]
    assert len(history.json()) == 2
