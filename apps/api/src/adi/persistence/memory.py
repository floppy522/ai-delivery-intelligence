from adi.domain.models import DeliverySnapshot
from adi.persistence.models import DeliveryRun


class MemoryRunRepository:
    def __init__(self) -> None:
        self.runs: list[DeliveryRun] = []

    async def save(self, run: DeliveryRun) -> None:
        self.runs.append(run)

    async def previous_snapshot(self, source: str, context_id: str) -> DeliverySnapshot | None:
        matches = [
            run.snapshot
            for run in self.runs
            if run.source == source and run.context_id == context_id
        ]
        return matches[-1] if matches else None

    async def list_runs(self, source: str, context_id: str) -> tuple[DeliveryRun, ...]:
        return tuple(
            reversed(
                [run for run in self.runs if run.source == source and run.context_id == context_id]
            )
        )

    async def get_run(self, run_id: str) -> DeliveryRun | None:
        return next((run for run in self.runs if run.run_id == run_id), None)
