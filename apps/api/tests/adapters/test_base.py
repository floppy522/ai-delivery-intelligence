from datetime import UTC, datetime

import pytest

from adi.adapters.base import DeliverySourceError, SourceErrorCode


def test_source_error_exposes_safe_code_without_secret() -> None:
    error = DeliverySourceError(
        code=SourceErrorCode.AUTHENTICATION_FAILED,
        message="Provider rejected credentials",
        occurred_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    assert error.safe_detail == {
        "code": "AUTHENTICATION_FAILED",
        "message": "Provider rejected credentials",
    }


def test_source_error_rejects_secret_shaped_message() -> None:
    with pytest.raises(ValueError, match="secret-like"):
        DeliverySourceError(
            code=SourceErrorCode.PROVIDER_ERROR,
            message="Authorization: Bearer abc123",
            occurred_at=datetime(2026, 9, 3, tzinfo=UTC),
        )
