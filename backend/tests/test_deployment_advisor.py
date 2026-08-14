from compatibility.compatibility_models import CompatibilityCheck, CompatibilityResult
from compatibility.deployment_advisor import generate_deployment_plan
from compatibility.models import MachineProfile
from compatibility.project_requirements import ProjectRequirements


def _check(
    component: str,
    status: str,
    *,
    local_value=None,
    required_value=None,
    reason: str | None = None,
) -> CompatibilityCheck:
    return CompatibilityCheck(
        component=component,
        local_value=local_value,
        required_value=required_value,
        status=status,
        reason=reason or f"{component} is {status}",
    )


def _result(*checks: CompatibilityCheck, status: str = "compatible") -> CompatibilityResult:
    return CompatibilityResult(
        overall_status=status,
        compatibility_score=100 if status == "compatible" else 60,
        checks=list(checks),
    )


def test_windows_linux_project_with_docker_recommends_wsl2_docker() -> None:
    plan = generate_deployment_plan(
        MachineProfile(os_name="Windows", docker_available=True, python_available=True),
        ProjectRequirements(
            supported_os=["Linux"],
            preferred_os="Ubuntu 22.04",
            docker_supported=True,
            package_manager="pip",
        ),
        _result(
            _check(
                "os",
                "partial",
                local_value="Windows 11",
                required_value={"supported_os": ["Linux"]},
            ),
            _check(
                "docker",
                "compatible",
                local_value=True,
                required_value={"docker_supported": True, "docker_required": False},
            ),
            status="partial",
        ),
    )

    assert plan.recommended_method == "WSL2 + Docker"
    assert plan.difficulty == "medium"
    assert any("WSL2" in step for step in plan.steps)
    assert any("not guarantee" in warning for warning in plan.warnings)


def test_python_version_conflict_recommends_conda_when_project_uses_conda() -> None:
    plan = generate_deployment_plan(
        MachineProfile(os_name="Windows", python_available=True, python_version="3.12"),
        ProjectRequirements(
            python_exact_version="3.10",
            package_manager="conda",
        ),
        _result(
            _check(
                "python",
                "incompatible",
                local_value="3.12",
                required_value="==3.10",
                reason="Python 3.12 does not satisfy ==3.10.",
            ),
            status="incompatible",
        ),
    )

    assert plan.recommended_method == "Conda"
    assert plan.difficulty == "medium"
    assert any("3.10" in action for action in plan.required_actions)
    assert any("Conda" in step for step in plan.steps)


def test_docker_project_recommends_docker_when_available() -> None:
    plan = generate_deployment_plan(
        MachineProfile(os_name="Linux", docker_available=True),
        ProjectRequirements(
            supported_os=["Linux"],
            docker_supported=True,
            package_manager="pip",
        ),
        _result(
            _check("os", "compatible"),
            _check(
                "docker",
                "compatible",
                local_value=True,
                required_value={"docker_supported": True, "docker_required": False},
            ),
        ),
    )

    assert plan.recommended_method == "Docker"
    assert plan.difficulty == "medium"
    assert "venv" in plan.alternative_methods
    assert any("Dockerfile" in step for step in plan.steps)


def test_directly_compatible_python_project_recommends_venv() -> None:
    plan = generate_deployment_plan(
        MachineProfile(
            os_name="Linux",
            python_available=True,
            python_version="3.11",
            docker_available=False,
        ),
        ProjectRequirements(
            supported_os=["Linux"],
            python_min_version="3.10",
            package_manager="pip",
            docker_supported=False,
        ),
        _result(
            _check("os", "compatible"),
            _check("python", "compatible"),
        ),
    )

    assert plan.recommended_method == "venv"
    assert plan.difficulty == "easy"
    assert "Native Python" in plan.alternative_methods
    assert any("virtual environment" in step for step in plan.steps)


def test_required_cuda_without_nvidia_gpu_blocks_deployment_plan() -> None:
    plan = generate_deployment_plan(
        MachineProfile(nvidia_gpu_available=False, cuda_available=False),
        ProjectRequirements(
            gpu_required=True,
            gpu_vendor="NVIDIA",
            cuda_required=True,
            cuda_version=">=11.8",
        ),
        _result(
            _check(
                "gpu",
                "incompatible",
                local_value={"gpu_vendor": None},
                required_value={"gpu_required": True, "gpu_vendor": "NVIDIA"},
            ),
            _check(
                "cuda",
                "incompatible",
                local_value={"cuda_available": False},
                required_value={"cuda_required": True, "cuda_version": ">=11.8"},
            ),
            status="incompatible",
        ),
    )

    assert plan.recommended_method == "unknown"
    assert plan.difficulty == "hard"
    assert any("hardware conditions are insufficient" in warning for warning in plan.warnings)
    assert any("NVIDIA" in action for action in plan.required_actions)
    assert not any("install dependencies" in step.casefold() for step in plan.steps)


def test_insufficient_vram_blocks_deployment_plan() -> None:
    plan = generate_deployment_plan(
        MachineProfile(gpu_memory_gb=4),
        ProjectRequirements(gpu_required=True, minimum_gpu_memory_gb=8),
        _result(
            _check(
                "gpu_memory",
                "incompatible",
                local_value=4,
                required_value=8,
            ),
            status="incompatible",
        ),
    )

    assert plan.recommended_method == "unknown"
    assert plan.difficulty == "hard"
    assert any("8" in action and "VRAM" in action for action in plan.required_actions)
    assert any("cannot be solved by software" in warning for warning in plan.warnings)


def test_insufficient_environment_information_returns_unknown_plan() -> None:
    plan = generate_deployment_plan(
        MachineProfile(),
        ProjectRequirements(),
        _result(
            _check("python", "unknown"),
            _check("os", "unknown"),
            status="unknown",
        ),
    )

    assert plan.recommended_method == "unknown"
    assert plan.difficulty == "unknown"
    assert plan.steps == []
    assert any("environment information" in warning for warning in plan.warnings)
    assert any("Collect" in action for action in plan.required_actions)
