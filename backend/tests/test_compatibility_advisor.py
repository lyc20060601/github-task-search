from compatibility.compatibility_advisor import generate_compatibility_advice
from compatibility.compatibility_models import CompatibilityCheck


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


def test_python_incompatibility_generates_issue_and_environment_suggestion() -> None:
    advice = generate_compatibility_advice(
        [
            _check(
                "python",
                "incompatible",
                local_value="3.9",
                required_value=">=3.10",
                reason="Local Python 3.9 does not satisfy >=3.10.",
            )
        ]
    )

    assert advice.issues == ["python: Local Python 3.9 does not satisfy >=3.10."]
    assert any("venv or Conda" in item for item in advice.suggestions)
    assert any(">=3.10" in item for item in advice.suggestions)


def test_windows_linux_partial_generates_warning_and_wsl2_suggestion() -> None:
    advice = generate_compatibility_advice(
        [
            _check(
                "os",
                "partial",
                local_value="Windows 11",
                required_value={
                    "supported_os": ["Linux"],
                    "preferred_os": "Ubuntu 22.04",
                },
                reason="Windows is not listed, but Linux is not exclusive.",
            )
        ]
    )

    assert advice.warnings == [
        "os: Windows is not listed, but Linux is not exclusive."
    ]
    assert any("WSL2" in item for item in advice.suggestions)


def test_unknown_cuda_version_generates_warning_not_issue() -> None:
    advice = generate_compatibility_advice(
        [
            _check(
                "cuda",
                "unknown",
                local_value={"cuda_available": True, "cuda_version": "12.1"},
                required_value={"cuda_required": True, "cuda_version": None},
                reason="The project does not declare a comparable CUDA version.",
            )
        ]
    )

    assert advice.issues == []
    assert any("cuda" in item.casefold() for item in advice.warnings)
    assert any("CUDA version" in item for item in advice.suggestions)


def test_unknown_ram_requirement_generates_warning() -> None:
    advice = generate_compatibility_advice(
        [
            _check(
                "ram",
                "unknown",
                local_value=32,
                required_value=None,
                reason="The project does not declare a minimum RAM requirement.",
            )
        ]
    )

    assert advice.issues == []
    assert any("minimum RAM" in item for item in advice.warnings)


def test_gpu_memory_failure_explains_physical_limit() -> None:
    advice = generate_compatibility_advice(
        [
            _check(
                "gpu_memory",
                "incompatible",
                local_value=4,
                required_value=8,
                reason="Detected GPU memory is 4 GB, below the required 8 GB.",
            )
        ]
    )

    assert len(advice.issues) == 1
    assert any("physical VRAM" in item for item in advice.suggestions)
    assert any("cannot be fixed by installing software" in item for item in advice.suggestions)


def test_missing_required_nvidia_gpu_generates_hardware_suggestion() -> None:
    advice = generate_compatibility_advice(
        [
            _check(
                "gpu",
                "incompatible",
                local_value={"gpu_vendor": "AMD", "gpu_name": "Radeon"},
                required_value={"gpu_required": True, "gpu_vendor": "NVIDIA"},
                reason="The project explicitly requires NVIDIA.",
            ),
            _check(
                "cuda",
                "incompatible",
                local_value={"cuda_available": False},
                required_value={"cuda_required": True, "cuda_version": ">=11.8"},
                reason="CUDA is not available locally.",
            ),
        ]
    )

    assert len(advice.issues) == 2
    assert any("NVIDIA CUDA-capable environment" in item for item in advice.suggestions)


def test_available_project_docker_path_generates_dockerfile_suggestion() -> None:
    advice = generate_compatibility_advice(
        [
            _check(
                "docker",
                "compatible",
                local_value=True,
                required_value={
                    "docker_supported": True,
                    "docker_required": False,
                },
                reason="An optional Docker path is available.",
            )
        ]
    )

    assert advice.issues == []
    assert advice.warnings == []
    assert any("Dockerfile" in item for item in advice.suggestions)


def test_compatible_checks_without_actionable_path_generate_no_advice() -> None:
    advice = generate_compatibility_advice(
        [_check("python", "compatible", local_value="3.11", required_value=">=3.10")]
    )

    assert advice.issues == []
    assert advice.warnings == []
    assert advice.suggestions == []
