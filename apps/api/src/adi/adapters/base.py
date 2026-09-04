from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from adi.domain.models import ContextRef, DeliveryContext, DeliverySnapshot, SourceCapabilities


class SourceErrorCode(StrEnum):
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class DeliverySourceError(Exception):
    def __init__(self, *, code: SourceErrorCode, message: str, occurred_at: datetime) -> None:
        lowered = message.lower()
        forbidden = ("authorization:", "bearer ", "api_token", "password=")
        if any(marker in lowered for marker in forbidden):
            raise ValueError("source error contains secret-like material")
        super().__init__(message)
        self.code = code
        self.message = message
        self.occurred_at = occurred_at

    @property
    def safe_detail(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


class DeliverySourceAdapter(Protocol):
    async def list_contexts(self) -> tuple[DeliveryContext, ...]: ...

    async def collect(self, context: ContextRef, observed_at: datetime) -> DeliverySnapshot: ...

    def capabilities(self, context: ContextRef) -> SourceCapabilities: ...

    def configuration_fingerprint(self) -> str: ...
