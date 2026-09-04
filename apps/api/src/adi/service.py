from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from adi.adapters.base import DeliverySourceAdapter
from adi.adapters.demo import DemoPhaseStore
from adi.agent.openai_agent import OpenAIDeliveryAgent
from adi.agent.tools import DeliveryToolExecutor
from adi.assessment.models import AssessmentMode
from adi.assessment.replay import build_replay_assessment
from adi.assessment.validation import validate_assessment
from adi.domain.models import ContextRef, SourceType
from adi.engine.diff import compare_snapshots
from adi.engine.signals import analyze_delivery
from adi.persistence.models import DeliveryRun, RunRepository
from adi.policies.retrieval import PolicyIndex


class DeliveryService:
    def __init__(
        self,
        *,
        adapters: dict[str, DeliverySourceAdapter],
        policies: PolicyIndex,
        repository: RunRepository,
        demo_phase: DemoPhaseStore | None = None,
        agent: OpenAIDeliveryAgent | None = None,
    ) -> None:
        self.adapters = adapters
        self.policies = policies
        self.repository = repository
        self.demo_phase = demo_phase
        self.agent = agent

    async def analyze(
        self,
        source: SourceType,
        context_id: str,
        observed_at: datetime | None = None,
        *,
        force_current_state: bool = False,
    ) -> DeliveryRun:
        if self.policies.conflicts:
            raise ValueError(
                "Conflicting delivery policy thresholds: " + ", ".join(self.policies.conflicts)
            )
        now = observed_at or datetime.now(UTC)
        adapter = self.adapters[source.value]
        previous = (
            None
            if force_current_state
            else await self.repository.previous_snapshot(source.value, context_id)
        )
        snapshot = await adapter.collect(
            ContextRef(source=source, external_id=context_id),
            now,
        )
        if previous and (previous.configuration_fingerprint != snapshot.configuration_fingerprint):
            previous = None
        changes = compare_snapshots(previous, snapshot, self.policies.rules)
        analysis = analyze_delivery(snapshot, changes, self.policies.rules)
        replay = build_replay_assessment(snapshot, changes, analysis, self.policies)
        validate_assessment(replay, snapshot, changes, self.policies, analysis)
        assessment = replay
        if self.agent:
            executor = DeliveryToolExecutor(snapshot, changes, analysis, self.policies)
            try:
                candidate = (await self.agent.assess(executor)).model_copy(
                    update={"mode": AssessmentMode.LIVE}
                )
                validate_assessment(
                    candidate,
                    snapshot,
                    changes,
                    self.policies,
                    analysis,
                    retrieved_policy_ids=executor.retrieved_policy_ids,
                )
                assessment = candidate
            except Exception:
                assessment = replay.model_copy(
                    update={
                        "mode": AssessmentMode.FAILED_SAFE,
                        "uncertainties": (
                            *replay.uncertainties,
                            "Live agent output was rejected; validated replay assessment shown.",
                        ),
                    }
                )
        run = DeliveryRun(
            run_id=str(uuid4()),
            source=source.value,
            context_id=context_id,
            created_at=now,
            snapshot=snapshot,
            changes=changes,
            analysis=analysis,
            assessment=assessment,
        )
        await self.repository.save(run)
        return run

    async def run_demo_story(self) -> DeliveryRun:
        if self.demo_phase is None:
            raise RuntimeError("demo phase store is unavailable")
        self.demo_phase.reset()
        await self.analyze(
            SourceType.DEMO,
            "northstar",
            datetime(2026, 9, 3, 9, tzinfo=UTC),
            force_current_state=True,
        )
        self.demo_phase.advance()
        return await self.analyze(
            SourceType.DEMO,
            "northstar",
            datetime(2026, 9, 7, 9, tzinfo=UTC),
        )

    async def reset_demo(self) -> DeliveryRun:
        if self.demo_phase is None:
            raise RuntimeError("demo phase store is unavailable")
        self.demo_phase.reset()
        return await self.analyze(
            SourceType.DEMO,
            "northstar",
            datetime(2026, 9, 3, 9, tzinfo=UTC),
            force_current_state=True,
        )

    async def advance_demo(self) -> DeliveryRun:
        if self.demo_phase is None:
            raise RuntimeError("demo phase store is unavailable")
        self.demo_phase.advance()
        return await self.analyze(
            SourceType.DEMO,
            "northstar",
            datetime(2026, 9, 7, 9, tzinfo=UTC),
        )
