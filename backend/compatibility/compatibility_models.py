"""Data models for machine-to-project compatibility results."""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, Field

from .evidence import Evidence


CompatibilityStatus: TypeAlias = Literal[
    "compatible",
    "partial",
    "incompatible",
    "unknown",
]


class CompatibilityCheck(BaseModel):
    """The compatibility outcome for one environment component."""

    component: str
    local_value: Any | None = None
    required_value: Any | None = None
    status: CompatibilityStatus
    reason: str
    evidence: list[Evidence | str] = Field(default_factory=list)


class CompatibilityResult(BaseModel):
    """A collection of component checks and their eventual summary."""

    overall_status: CompatibilityStatus
    compatibility_score: float | None = None
    checks: list[CompatibilityCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
