from __future__ import annotations

from datetime import datetime
from typing import Protocol

from adi.assessment.models import DeliveryAssessment
from adi.domain.models import DeliverySnapshot, FrozenModel
from adi.engine.diff import ChangeSet
from adi.engine.signals import DeliveryAnalysis


class DeliveryRun(FrozenModel):
    run_id: str
    source: str
    context_id: str
    created_at: datetime
    snapshot: DeliverySnapshot
    changes: ChangeSet
    analysis: DeliveryAnalysis
    assessment: DeliveryAssessment


class RunRepository(Protocol):
    async def save(self, run: DeliveryRun) -> None: ...

    async def previous_snapshot(self, source: str, context_id: str) -> DeliverySnapshot | None: ...

    async def list_runs(self, source: str, context_id: str) -> tuple[DeliveryRun, ...]: ...

    async def get_run(self, run_id: str) -> DeliveryRun | None: ...
