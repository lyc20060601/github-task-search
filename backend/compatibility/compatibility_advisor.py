"""Deterministic advice generated only from compatibility-check evidence."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

from .compatibility_models import CompatibilityCheck


class CompatibilityAdvice(BaseModel):
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


def _mapping_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _display(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, dict):
        return ", ".join(
            f"{key}={item}" for key, item in value.items() if item is not None
        ) or "unknown"
    return str(value)


def _append_unique(items: list[str], value: str | None) -> None:
    if value and value not in items:
        items.append(value)


def _suggestion_for(check: CompatibilityCheck) -> str | None:
    required = check.required_value

    if check.component == "python" and check.status == "incompatible":
        return (
            "Create a venv or Conda environment with a Python version matching "
            f"the project requirement ({_display(required)}); no environment was "
            "changed automatically."
        )

    if check.component == "os" and check.status in {"partial", "incompatible"}:
        local = str(check.local_value or "").casefold()
        supported = _mapping_value(required, "supported_os") or []
        supports_linux = any("linux" in str(item).casefold() for item in supported)
        if "windows" in local and supports_linux:
            return (
                "Consider using WSL2 to provide the project's declared Linux "
                "environment; verify the repository instructions before use."
            )

    if check.component == "gpu" and check.status == "incompatible":
        required_vendor = _mapping_value(required, "gpu_vendor")
        if required_vendor and str(required_vendor).casefold() == "nvidia":
            return (
                "This requirement needs an NVIDIA CUDA-capable environment; "
                "installing a Python package cannot replace the required hardware."
            )

    if check.component == "gpu_memory" and check.status == "incompatible":
        return (
            "Use a GPU with enough physical VRAM for the declared requirement "
            f"({_display(required)} GB). A physical VRAM shortfall cannot be fixed "
            "by installing software."
        )

    if check.component == "cuda":
        cuda_required = _mapping_value(required, "cuda_required")
        cuda_version = _mapping_value(required, "cuda_version")
        if check.status == "incompatible" and cuda_required is True:
            return (
                "Use an NVIDIA CUDA-capable environment satisfying the project's "
                f"declared CUDA requirement ({cuda_version or 'version unspecified'})."
            )
        if check.status == "unknown" and cuda_required is True:
            return (
                "Confirm the required CUDA version from the repository's official "
                "environment or installation documentation before deployment."
            )

    if check.component == "docker":
        docker_supported = _mapping_value(required, "docker_supported")
        if docker_supported is True and check.local_value is True:
            return (
                "Prefer the repository-provided Dockerfile or Docker configuration "
                "when you want its documented container environment."
            )

    return None


def generate_compatibility_advice(
    checks: Iterable[CompatibilityCheck],
) -> CompatibilityAdvice:
    """Map real component checks to blocking issues, risks, and safe next steps."""

    issues: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []

    for check in checks:
        message = f"{check.component}: {check.reason}"
        if check.status == "incompatible":
            _append_unique(issues, message)
        elif check.status in {"partial", "unknown"}:
            _append_unique(warnings, message)

        _append_unique(suggestions, _suggestion_for(check))

    return CompatibilityAdvice(
        issues=issues,
        warnings=warnings,
        suggestions=suggestions,
    )
