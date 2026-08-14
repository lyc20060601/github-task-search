"""Dispatch explicit repository validation without exposing Docker to the API container."""

from __future__ import annotations

import os
import secrets
from typing import Literal

from runtime_report import RuntimeReport

from .validation_jobs import ValidationJobCoordinator, ValidationUnavailable
from .validator import validate_repository


ValidationMode = Literal["local", "worker", "disabled"]
VALIDATION_MODES: set[str] = {"local", "worker", "disabled"}
COORDINATOR = ValidationJobCoordinator()


def get_validation_mode() -> ValidationMode:
    value = os.getenv("VALIDATION_MODE", "local").strip().lower()
    if value in VALIDATION_MODES:
        return value  # type: ignore[return-value]
    return "disabled"


def require_worker_token(authorization: str | None) -> None:
    expected = os.getenv("VALIDATION_WORKER_TOKEN", "")
    supplied = ""
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        raise PermissionError("invalid validation worker credentials")


def validate_requested_repository(
    full_name: str,
    *,
    timeout_seconds: float = 600,
) -> RuntimeReport:
    mode = get_validation_mode()
    if mode == "local":
        return validate_repository(full_name)
    if mode == "worker":
        return COORDINATOR.submit_and_wait(
            full_name,
            timeout_seconds=timeout_seconds,
        )
    raise ValidationUnavailable("repository validation is disabled")


def get_validation_status() -> dict[str, str | bool]:
    mode = get_validation_mode()
    return {
        "mode": mode,
        "worker_ready": mode == "worker" and COORDINATOR.worker_ready(),
    }
