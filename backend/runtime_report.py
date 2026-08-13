"""Data model for isolated repository runtime validation reports."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RuntimeStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"


class RuntimeReport(BaseModel):
    """Structured results from a future repository runtime validation."""

    model_config = ConfigDict(use_enum_values=True)

    full_name: str

    clone_status: RuntimeStatus = RuntimeStatus.UNKNOWN
    environment_detected: RuntimeStatus = RuntimeStatus.UNKNOWN
    dependency_install_status: RuntimeStatus = RuntimeStatus.UNKNOWN
    entrypoint_detected: RuntimeStatus = RuntimeStatus.UNKNOWN
    smoke_test_status: RuntimeStatus = RuntimeStatus.UNKNOWN

    python_version: str | None = None
    framework: str | None = None
    entrypoint: str | None = None

    install_duration: float | None = None
    test_duration: float | None = None

    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    runtime_score: float | None = None
    runtime_breakdown: dict[str, int] = Field(default_factory=dict)
    runtime_status: RuntimeStatus = RuntimeStatus.UNKNOWN
