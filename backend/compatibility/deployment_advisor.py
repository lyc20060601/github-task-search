"""Evidence-based deployment plans that never execute deployment actions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .compatibility_models import CompatibilityCheck, CompatibilityResult
from .models import MachineProfile
from .project_requirements import ProjectRequirements


DeploymentDifficulty = Literal["easy", "medium", "hard", "unknown"]


class DeploymentPlan(BaseModel):
    recommended_method: str = "unknown"
    difficulty: DeploymentDifficulty = "unknown"
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    alternative_methods: list[str] = Field(default_factory=list)


def _check_by_component(
    result: CompatibilityResult,
) -> dict[str, CompatibilityCheck]:
    return {check.component: check for check in result.checks}


def _declared(value: object) -> bool:
    return value is not None and str(value).strip().casefold() not in {
        "",
        "unknown",
        "none",
        "null",
    }


def _supports_linux(requirements: ProjectRequirements) -> bool:
    values = [*list(requirements.supported_os or [])]
    if requirements.preferred_os:
        values.append(requirements.preferred_os)
    return any(
        "linux" in str(value).casefold() or "ubuntu" in str(value).casefold()
        for value in values
    )


def _python_requirement(requirements: ProjectRequirements) -> str:
    values = [
        requirements.python_exact_version,
        requirements.python_min_version,
        requirements.python_max_version,
    ]
    return ", ".join(str(value) for value in values if _declared(value)) or "declared version"


def _hardware_blockers(
    requirements: ProjectRequirements,
    checks: dict[str, CompatibilityCheck],
) -> DeploymentPlan | None:
    gpu = checks.get("gpu")
    cuda = checks.get("cuda")
    gpu_memory = checks.get("gpu_memory")

    if gpu_memory and gpu_memory.status == "incompatible":
        required = gpu_memory.required_value or requirements.minimum_gpu_memory_gb
        return DeploymentPlan(
            recommended_method="unknown",
            difficulty="hard",
            warnings=[
                "Current local hardware conditions are insufficient: physical GPU "
                "memory is below the project requirement and cannot be solved by software."
            ],
            required_actions=[
                f"Use hardware with at least {required} GB VRAM before deployment."
            ],
        )

    requires_nvidia = (
        requirements.gpu_required is True
        and str(requirements.gpu_vendor or "").casefold() == "nvidia"
    )
    requires_cuda = requirements.cuda_required is True
    missing_gpu = gpu is not None and gpu.status == "incompatible"
    missing_cuda = cuda is not None and cuda.status == "incompatible"
    if (requires_nvidia and missing_gpu) or (requires_cuda and missing_cuda):
        actions = ["Provide an NVIDIA CUDA-capable environment before deployment."]
        if _declared(requirements.cuda_version):
            actions.append(
                f"Match the declared CUDA requirement: {requirements.cuda_version}."
            )
        return DeploymentPlan(
            recommended_method="unknown",
            difficulty="hard",
            warnings=[
                "Current local hardware conditions are insufficient for the "
                "project's explicit NVIDIA/CUDA requirement."
            ],
            required_actions=actions,
        )

    return None


def _environment_steps(
    method: str,
    requirements: ProjectRequirements,
) -> list[str]:
    steps: list[str] = []
    python_requirement = _python_requirement(requirements)

    if method.startswith("WSL2"):
        steps.append("Confirm that WSL2 is available and open the declared Linux environment.")
    if "Docker" in method:
        steps.extend(
            [
                "Review the repository-provided Dockerfile or Docker configuration.",
                "Build and start the container only after reviewing its documented commands.",
            ]
        )
    elif method == "Conda":
        steps.append(f"Create a Conda environment matching Python {python_requirement}.")
        steps.append("Install dependencies using the project's documented Conda files or commands.")
    elif method == "venv":
        steps.append(f"Create an isolated Python virtual environment matching {python_requirement}.")
        steps.append("Install dependencies using the project's documented pip requirements.")
    elif method == "Native Python":
        steps.append(f"Confirm the local Python version matches {python_requirement}.")
        steps.append("Install dependencies according to the repository documentation.")

    steps.append("Follow the README's documented startup command after reviewing it.")
    return steps


def generate_deployment_plan(
    machine_profile: MachineProfile,
    project_requirements: ProjectRequirements,
    compatibility_result: CompatibilityResult,
) -> DeploymentPlan:
    """Recommend a deployment path using only collected requirements and checks."""

    checks = _check_by_component(compatibility_result)
    blocker = _hardware_blockers(project_requirements, checks)
    if blocker is not None:
        return blocker

    has_environment_evidence = any(
        [
            project_requirements.supported_os,
            _declared(project_requirements.preferred_os),
            _declared(project_requirements.python_min_version),
            _declared(project_requirements.python_max_version),
            _declared(project_requirements.python_exact_version),
            _declared(project_requirements.package_manager),
            project_requirements.docker_supported is True,
        ]
    )
    if not has_environment_evidence:
        return DeploymentPlan(
            warnings=[
                "Project environment information is insufficient to recommend a "
                "reliable deployment method."
            ],
            required_actions=[
                "Collect explicit OS, Python, dependency-manager, and deployment "
                "requirements from the repository."
            ],
        )

    local_windows = "windows" in str(machine_profile.os_name or "").casefold()
    linux_project = _supports_linux(project_requirements)
    docker_ready = (
        project_requirements.docker_supported is True
        and machine_profile.docker_available is True
    )
    package_manager = str(project_requirements.package_manager or "").casefold()
    python_check = checks.get("python")

    warnings = list(compatibility_result.warnings)
    required_actions: list[str] = []
    alternatives: list[str] = []

    if local_windows and linux_project:
        method = "WSL2 + Docker" if docker_ready else "WSL2 + Conda"
        difficulty: DeploymentDifficulty = "medium"
        warnings.append(
            "The project targets Linux while the host is Windows; WSL2 or Docker "
            "is only a recommendation and does not guarantee the project will run."
        )
        alternatives = ["Docker"] if docker_ready else ["WSL2 + venv"]
    elif docker_ready:
        method = "Docker"
        difficulty = "medium"
        alternatives = ["Conda" if "conda" in package_manager else "venv"]
    elif python_check is not None and python_check.status == "incompatible":
        method = "Conda" if "conda" in package_manager else "venv"
        difficulty = "medium"
        required_actions.append(
            f"Create an isolated Python environment matching {_python_requirement(project_requirements)}."
        )
        alternatives = ["venv"] if method == "Conda" else ["Conda"]
    elif "conda" in package_manager:
        method = "Conda"
        difficulty = "easy"
        alternatives = ["venv"]
    elif machine_profile.python_available is True and "pip" in package_manager:
        method = "venv"
        difficulty = "easy"
        alternatives = ["Native Python"]
    elif machine_profile.python_available is True:
        method = "Native Python"
        difficulty = "easy"
    else:
        return DeploymentPlan(
            warnings=[
                "Local Python and a supported deployment method cannot be confirmed."
            ],
            required_actions=[
                "Collect the missing environment requirements before choosing a method."
            ],
        )

    return DeploymentPlan(
        recommended_method=method,
        difficulty=difficulty,
        steps=_environment_steps(method, project_requirements),
        warnings=warnings,
        required_actions=required_actions,
        alternative_methods=alternatives,
    )
