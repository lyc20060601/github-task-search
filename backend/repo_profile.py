"""Data model for structured GitHub repository profiles."""

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """Repository evidence supporting one analysis conclusion."""

    source: str = "unknown"
    reason: str = "no reliable evidence"


class RepoProfile(BaseModel):
    """Structured facts and notes about a GitHub repository.

    The model intentionally contains no extraction or analysis logic. Fields
    that are not available yet remain ``None`` or an empty list.
    """

    full_name: str | None = None
    framework: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)

    has_training_code: bool | None = None
    training_entry: str | None = None
    has_training_code_evidence: Evidence = Field(default_factory=Evidence)

    has_custom_dataset_support: bool | None = None
    has_custom_dataset_support_evidence: Evidence = Field(default_factory=Evidence)
    has_pretrained_weights: bool | None = None
    has_pretrained_weights_evidence: Evidence = Field(default_factory=Evidence)

    framework_evidence: Evidence = Field(default_factory=Evidence)

    has_requirements: bool | None = None
    has_environment_file: bool | None = None
    has_docker: bool | None = None
    has_configs: bool | None = None
    has_dataset_code: bool | None = None

    documentation_quality: str | None = None
    hardware_notes: str | None = None
    hardware_notes_evidence: Evidence = Field(default_factory=Evidence)
    maintenance_notes: str | None = None
    task_match: str | None = None

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
