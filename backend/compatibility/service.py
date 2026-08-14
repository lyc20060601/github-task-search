"""Unified, read-only repository compatibility analysis service."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from .compatibility_checker import (
    check_cuda_compatibility,
    check_docker_compatibility,
    check_gpu_compatibility,
    check_gpu_memory_compatibility,
    check_os_compatibility,
    check_python_compatibility,
    check_ram_compatibility,
)
from .compatibility_models import CompatibilityResult
from .compatibility_scorer import score_compatibility
from .deployment_advisor import DeploymentPlan, generate_deployment_plan
from .machine_detector import detect_machine_profile
from .models import MachineProfile
from .project_requirement_analyzer import analyze_project_requirements_with_conflicts
from .project_requirements import ProjectRequirements
from .repository_environment_fetcher import fetch_repository_environment_files
from .requirement_conflicts import RequirementConflict


_SECRET_ASSIGNMENT = re.compile(
    r"(?:GITHUB_TOKEN|LLM_API_KEY)\s*=\s*[^\s]+",
    re.IGNORECASE,
)
_TOKEN_VALUE = re.compile(
    r"(?:github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{8,})",
    re.IGNORECASE,
)
_ENV_PATH = re.compile(r"(?:[A-Za-z]:)?[^\s]*[\\/]\.env\b", re.IGNORECASE)


class RepositoryCompatibilityAnalysis(BaseModel):
    full_name: str
    machine_profile: MachineProfile
    project_requirements: ProjectRequirements
    compatibility_result: CompatibilityResult
    deployment_plan: DeploymentPlan
    conflicts: list[RequirementConflict] = Field(default_factory=list)
    fetch_errors: list[str] = Field(default_factory=list)


def _empty_environment(full_name: str) -> dict[str, Any]:
    return {
        "full_name": full_name,
        "files": {},
        "found_files": [],
        "missing_files": [],
        "skipped_files": [],
        "errors": [],
    }


def _fetch_error_messages(environment: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for item in environment.get("errors", []):
        if not isinstance(item, dict):
            continue
        path = item.get("path") or "unknown file"
        status = item.get("status")
        reason = item.get("reason") or "environment file read failed"
        status_text = f" (HTTP {status})" if status is not None else ""
        messages.append(f"{path}{status_text}: {reason}")
    return messages


def _safe_error_message(error: Exception) -> str:
    message = str(error) or error.__class__.__name__
    message = _SECRET_ASSIGNMENT.sub("[REDACTED]", message)
    message = _TOKEN_VALUE.sub("[REDACTED]", message)
    message = _ENV_PATH.sub("[REDACTED]", message)
    return message


def analyze_repository_compatibility(
    full_name: str,
) -> RepositoryCompatibilityAnalysis:
    """Run the complete static compatibility chain for one GitHub repository."""

    normalized_name = full_name.strip().strip("/")
    machine_profile = detect_machine_profile()
    fetch_errors: list[str] = []

    try:
        environment = fetch_repository_environment_files(normalized_name)
        fetch_errors.extend(_fetch_error_messages(environment))
    except Exception as exc:
        # Fetch failures are returned as data. Static parsing continues with no files.
        fetch_errors.append(_safe_error_message(exc))
        environment = _empty_environment(normalized_name)

    requirement_analysis = analyze_project_requirements_with_conflicts(environment)
    requirements = requirement_analysis.requirements
    checks = [
        check_python_compatibility(machine_profile, requirements),
        check_os_compatibility(machine_profile, requirements),
        check_ram_compatibility(machine_profile, requirements),
        check_gpu_compatibility(machine_profile, requirements),
        check_gpu_memory_compatibility(machine_profile, requirements),
        check_cuda_compatibility(machine_profile, requirements),
        check_docker_compatibility(machine_profile, requirements),
    ]
    compatibility_result = score_compatibility(checks)
    deployment_plan = generate_deployment_plan(
        machine_profile,
        requirements,
        compatibility_result,
    )

    return RepositoryCompatibilityAnalysis(
        full_name=normalized_name,
        machine_profile=machine_profile,
        project_requirements=requirements,
        compatibility_result=compatibility_result,
        deployment_plan=deployment_plan,
        conflicts=requirement_analysis.conflicts,
        fetch_errors=fetch_errors,
    )
