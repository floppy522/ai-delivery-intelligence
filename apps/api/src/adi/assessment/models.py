from datetime import datetime
from enum import StrEnum

from adi.domain.models import FrozenModel, SourceType
from adi.engine.diff import ChangeType
from adi.engine.signals import SignalType


class DeliveryHealth(StrEnum):
    ON_TRACK = "ON_TRACK"
    ATTENTION = "ATTENTION"
    AT_RISK = "AT_RISK"
    BLOCKED = "BLOCKED"


class AssessmentValidationError(ValueError):
    pass


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssessmentMode(StrEnum):
    REPLAY = "replay"
    LIVE = "live"
    FAILED_SAFE = "failed_safe"


class ActionType(StrEnum):
    ESCALATE_BLOCKER = "ESCALATE_BLOCKER"
    ASSIGN_OWNER = "ASSIGN_OWNER"
    OBTAIN_ETA = "OBTAIN_ETA"
    REBALANCE_WIP = "REBALANCE_WIP"
    REVIEW_AGING_QUEUE = "REVIEW_AGING_QUEUE"
    COORDINATE_DEPENDENCY = "COORDINATE_DEPENDENCY"
    REVIEW_OVERDUE_WORK = "REVIEW_OVERDUE_WORK"
    RESTORE_FLOW_PATH = "RESTORE_FLOW_PATH"
    REVIEW_EVIDENCE = "REVIEW_EVIDENCE"


class Period(FrozenModel):
    from_timestamp: datetime | None = None
    to_timestamp: datetime


class AssessmentChange(FrozenModel):
    change_type: ChangeType
    summary: str
    item_id: str | None = None
    evidence: tuple[str, ...] = ()


class AssessmentSignal(FrozenModel):
    signal_type: SignalType
    severity: Severity
    summary: str
    item_ids: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


class DeliveryRisk(FrozenModel):
    title: str
    severity: Severity
    reason: str
    evidence: tuple[str, ...]
    policy_sources: tuple[str, ...]


class RecommendedAction(FrozenModel):
    action_type: ActionType
    action: str
    rationale: str
    evidence: tuple[str, ...]
    policy_sources: tuple[str, ...]


class DeliveryAssessment(FrozenModel):
    project: str
    source: SourceType
    period: Period
    overall_delivery_status: DeliveryHealth
    mode: AssessmentMode
    current_state_only: bool
    changes: tuple[AssessmentChange, ...]
    flow_signals: tuple[AssessmentSignal, ...]
    risks: tuple[DeliveryRisk, ...]
    recommended_actions: tuple[RecommendedAction, ...]
    escalations: tuple[RecommendedAction, ...]
    uncertainties: tuple[str, ...] = ()
