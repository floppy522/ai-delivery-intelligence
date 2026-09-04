import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[4]
sys.path.insert(0, str(ROOT / "evaluation"))

from run import evaluate  # noqa: E402


@pytest.mark.asyncio
async def test_versioned_evaluation_has_25_passing_cases() -> None:
    result = await evaluate()

    assert result["summary"] == {"passed": 25, "total": 25}
    assert result["metrics"]["escalation_accuracy"] == 1.0
    assert result["metrics"]["unsupported_claim_rate"] == 0.0
    assert all(case["passed"] for case in result["cases"])
