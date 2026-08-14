from unittest.mock import Mock

import pytest

from runtime import validation_gateway
from runtime.validation_jobs import ValidationUnavailable
from runtime_report import RuntimeReport


def test_local_mode_calls_existing_validator(monkeypatch):
    report = RuntimeReport(full_name="owner/repository")
    monkeypatch.delenv("VALIDATION_MODE", raising=False)
    monkeypatch.setattr(
        validation_gateway,
        "validate_repository",
        lambda full_name: report,
    )

    assert validation_gateway.validate_requested_repository("owner/repository") is report


def test_worker_mode_uses_coordinator(monkeypatch):
    report = RuntimeReport(full_name="owner/repository")
    coordinator = Mock()
    coordinator.submit_and_wait.return_value = report
    monkeypatch.setenv("VALIDATION_MODE", "worker")
    monkeypatch.setattr(validation_gateway, "COORDINATOR", coordinator)

    result = validation_gateway.validate_requested_repository(
        "owner/repository",
        timeout_seconds=12,
    )

    assert result is report
    coordinator.submit_and_wait.assert_called_once_with(
        "owner/repository",
        timeout_seconds=12,
    )


def test_disabled_and_invalid_modes_are_unavailable(monkeypatch):
    for mode in ("disabled", "unexpected"):
        monkeypatch.setenv("VALIDATION_MODE", mode)
        with pytest.raises(ValidationUnavailable):
            validation_gateway.validate_requested_repository("owner/repository")


@pytest.mark.parametrize("authorization", [None, "", "Basic value", "Bearer wrong"])
def test_worker_token_rejects_missing_or_wrong_value(monkeypatch, authorization):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "correct")
    with pytest.raises(PermissionError):
        validation_gateway.require_worker_token(authorization)


def test_worker_token_accepts_exact_bearer_value(monkeypatch):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "correct")
    validation_gateway.require_worker_token("Bearer correct")


def test_worker_token_is_required_on_both_sides(monkeypatch):
    monkeypatch.delenv("VALIDATION_WORKER_TOKEN", raising=False)
    with pytest.raises(PermissionError):
        validation_gateway.require_worker_token("Bearer anything")


def test_status_contains_no_secret(monkeypatch):
    coordinator = Mock()
    coordinator.worker_ready.return_value = True
    monkeypatch.setenv("VALIDATION_MODE", "worker")
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "do-not-return")
    monkeypatch.setattr(validation_gateway, "COORDINATOR", coordinator)

    status = validation_gateway.get_validation_status()

    assert status == {"mode": "worker", "worker_ready": True}
    assert "do-not-return" not in str(status)
