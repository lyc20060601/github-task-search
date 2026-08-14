"""Pydantic models for machine compatibility information."""

from typing import Optional

from pydantic import BaseModel


class MachineProfile(BaseModel):
    """A snapshot of host capabilities used for compatibility decisions.

    Fields are optional because this model is intentionally independent from
    the system-detection step and may represent unknown values.
    """

    os_name: Optional[str] = None
    os_version: Optional[str] = None
    architecture: Optional[str] = None

    cpu_name: Optional[str] = None
    cpu_cores: Optional[int] = None

    memory_total_gb: Optional[float] = None

    gpu_vendor: Optional[str] = None
    gpu_name: Optional[str] = None
    gpu_memory_gb: Optional[float] = None

    nvidia_gpu_available: Optional[bool] = None
    cuda_available: Optional[bool] = None
    cuda_version: Optional[str] = None

    python_available: Optional[bool] = None
    python_version: Optional[str] = None

    docker_available: Optional[bool] = None
    git_available: Optional[bool] = None
