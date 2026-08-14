from typing import Literal, TypeAlias

from pydantic import BaseModel, Field

from .evidence import Evidence


UnknownBoolean: TypeAlias = bool | Literal["unknown"]
UnknownNumber: TypeAlias = float | Literal["unknown"]


class ProjectRequirements(BaseModel):
    supported_os: list[str] | None = Field(default_factory=list)
    preferred_os: str | None = None

    python_min_version: str | None = None
    python_max_version: str | None = None
    python_exact_version: str | None = None

    framework: str | None = None
    framework_version: str | None = None

    cuda_required: UnknownBoolean | None = None
    cuda_version: str | None = None

    gpu_required: UnknownBoolean | None = None
    gpu_vendor: str | None = None
    minimum_gpu_memory_gb: UnknownNumber | None = None

    minimum_ram_gb: UnknownNumber | None = None

    docker_supported: UnknownBoolean | None = None
    package_manager: str | None = None

    special_requirements: list[str] | None = Field(default_factory=list)
    evidence: list[Evidence | str] | None = Field(default_factory=list)
