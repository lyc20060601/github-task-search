from compatibility.compatibility_checker import (
    check_cuda_compatibility,
    check_docker_compatibility,
    check_gpu_compatibility,
    check_gpu_memory_compatibility,
    check_os_compatibility,
    check_python_compatibility,
    check_ram_compatibility,
)
from compatibility.evidence import Evidence
from compatibility.models import MachineProfile
from compatibility.project_requirements import ProjectRequirements


def test_python_minimum_requirement_is_satisfied() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version="3.11.8"),
        ProjectRequirements(python_min_version="3.10"),
    )

    assert check.component == "python"
    assert check.local_value == "3.11.8"
    assert check.required_value == ">=3.10"
    assert check.status == "compatible"
    assert "3.11.8" in check.reason
    assert ">=3.10" in check.reason


def test_python_minimum_requirement_is_not_satisfied() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version="3.9.18"),
        ProjectRequirements(python_min_version=">=3.10"),
    )

    assert check.status == "incompatible"
    assert "does not satisfy" in check.reason


def test_python_exact_requirement_is_satisfied() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version="3.10"),
        ProjectRequirements(python_exact_version="3.10"),
    )

    assert check.required_value == "==3.10"
    assert check.status == "compatible"


def test_python_exact_requirement_is_strict() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version="3.10.1"),
        ProjectRequirements(python_exact_version="3.10"),
    )

    assert check.status == "incompatible"
    assert "3.10.1" in check.reason
    assert "==3.10" in check.reason


def test_python_minimum_and_maximum_range_is_satisfied() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version="3.10.13"),
        ProjectRequirements(
            python_min_version="3.9",
            python_max_version="3.11",
        ),
    )

    assert check.required_value == ">=3.9,<=3.11"
    assert check.status == "compatible"


def test_python_minimum_and_maximum_range_is_not_satisfied() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version="3.12"),
        ProjectRequirements(
            python_min_version="3.9",
            python_max_version="3.11",
        ),
    )

    assert check.status == "incompatible"


def test_missing_project_python_requirement_is_unknown() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version="3.12"),
        ProjectRequirements(),
    )

    assert check.required_value is None
    assert check.status == "unknown"
    assert "does not declare" in check.reason


def test_unknown_local_python_version_is_unknown() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version=None),
        ProjectRequirements(python_min_version="3.10"),
    )

    assert check.local_value is None
    assert check.required_value == ">=3.10"
    assert check.status == "unknown"
    assert "cannot be determined" in check.reason


def test_unavailable_python_is_incompatible_when_project_requires_it() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=False, python_version=None),
        ProjectRequirements(python_min_version="3.10"),
    )

    assert check.local_value == "unavailable"
    assert check.required_value == ">=3.10"
    assert check.status == "incompatible"
    assert "not available" in check.reason


def test_unparseable_project_requirement_is_unknown() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version="3.11"),
        ProjectRequirements(python_min_version="latest"),
    )

    assert check.required_value == "latest"
    assert check.status == "unknown"
    assert "cannot be parsed" in check.reason


def test_unparseable_local_version_is_unknown() -> None:
    check = check_python_compatibility(
        MachineProfile(python_available=True, python_version="unknown"),
        ProjectRequirements(python_exact_version="3.10"),
    )

    assert check.status == "unknown"
    assert "cannot be parsed" in check.reason


def test_windows_is_compatible_with_windows_support() -> None:
    check = check_os_compatibility(
        MachineProfile(os_name="Windows", os_version="11"),
        ProjectRequirements(supported_os=["Windows"]),
    )

    assert check.component == "os"
    assert check.local_value == "Windows 11"
    assert check.required_value == {
        "supported_os": ["Windows"],
        "preferred_os": None,
    }
    assert check.status == "compatible"
    assert "Windows 11" in check.reason


def test_linux_is_compatible_with_linux_support() -> None:
    check = check_os_compatibility(
        MachineProfile(os_name="Linux", os_version="Ubuntu 22.04"),
        ProjectRequirements(supported_os=["Linux"]),
    )

    assert check.status == "compatible"


def test_windows_linux_multi_value_supports_windows() -> None:
    check = check_os_compatibility(
        MachineProfile(os_name="Windows", os_version="11"),
        ProjectRequirements(supported_os=["Windows", "Linux"]),
    )

    assert check.status == "compatible"


def test_linux_only_is_incompatible_with_windows() -> None:
    evidence = Evidence(
        field="supported_os",
        value=["Linux"],
        source_file="README.md",
        raw_text="This project is supported on Linux only.",
    )
    check = check_os_compatibility(
        MachineProfile(os_name="Windows", os_version="11"),
        ProjectRequirements(supported_os=["Linux"], evidence=[evidence]),
    )

    assert check.status == "incompatible"
    assert check.evidence == [evidence]
    assert "only" in check.reason


def test_nonexclusive_linux_support_on_windows_is_partial() -> None:
    check = check_os_compatibility(
        MachineProfile(os_name="Windows", os_version="11"),
        ProjectRequirements(supported_os=["Linux"]),
    )

    assert check.status == "partial"
    assert "does not explicitly exclude" in check.reason


def test_preferred_ubuntu_does_not_override_supported_linux() -> None:
    check = check_os_compatibility(
        MachineProfile(os_name="Linux", os_version=None),
        ProjectRequirements(supported_os=["Linux"], preferred_os="Ubuntu 22.04"),
    )

    assert check.status == "compatible"
    assert "preferred" in check.reason.casefold()
    assert "Ubuntu 22.04" in check.reason


def test_missing_supported_os_is_unknown() -> None:
    check = check_os_compatibility(
        MachineProfile(os_name="Windows", os_version="11"),
        ProjectRequirements(supported_os=[]),
    )

    assert check.required_value == {
        "supported_os": [],
        "preferred_os": None,
    }
    assert check.status == "unknown"
    assert "does not declare" in check.reason


def test_ram_requirement_is_satisfied() -> None:
    check = check_ram_compatibility(
        MachineProfile(memory_total_gb=64),
        ProjectRequirements(minimum_ram_gb=32),
    )

    assert check.component == "ram"
    assert check.local_value == 64.0
    assert check.required_value == 32.0
    assert check.status == "compatible"
    assert "64" in check.reason
    assert "32" in check.reason


def test_ram_requirement_is_not_satisfied() -> None:
    check = check_ram_compatibility(
        MachineProfile(memory_total_gb=16),
        ProjectRequirements(minimum_ram_gb=32),
    )

    assert check.status == "incompatible"
    assert "below" in check.reason


def test_unknown_ram_requirement_is_unknown() -> None:
    check = check_ram_compatibility(
        MachineProfile(memory_total_gb=32),
        ProjectRequirements(minimum_ram_gb="unknown"),
    )

    assert check.required_value == "unknown"
    assert check.status == "unknown"
    assert "does not declare" in check.reason


def test_unknown_local_ram_is_unknown() -> None:
    check = check_ram_compatibility(
        MachineProfile(memory_total_gb=None),
        ProjectRequirements(minimum_ram_gb=16),
    )

    assert check.local_value is None
    assert check.required_value == 16.0
    assert check.status == "unknown"
    assert "cannot be determined" in check.reason


def test_31_point_8_gb_satisfies_32_gb_with_display_tolerance() -> None:
    check = check_ram_compatibility(
        MachineProfile(memory_total_gb=31.8),
        ProjectRequirements(minimum_ram_gb=32),
    )

    assert check.status == "compatible"
    assert "display tolerance" in check.reason


def test_ram_below_display_tolerance_is_still_incompatible() -> None:
    check = check_ram_compatibility(
        MachineProfile(memory_total_gb=31.5),
        ProjectRequirements(minimum_ram_gb=32),
    )

    assert check.status == "incompatible"


def test_gpu_is_not_required() -> None:
    check = check_gpu_compatibility(
        MachineProfile(nvidia_gpu_available=False),
        ProjectRequirements(gpu_required=False),
    )

    assert check.component == "gpu"
    assert check.status == "compatible"
    assert check.required_value == {"gpu_required": False, "gpu_vendor": None}
    assert "not require" in check.reason


def test_unknown_gpu_requirement_is_unknown() -> None:
    check = check_gpu_compatibility(
        MachineProfile(
            gpu_vendor="NVIDIA",
            gpu_name="RTX 4090",
            nvidia_gpu_available=True,
        ),
        ProjectRequirements(gpu_required="unknown"),
    )

    assert check.status == "unknown"
    assert "unknown" in check.reason


def test_required_gpu_is_missing() -> None:
    check = check_gpu_compatibility(
        MachineProfile(
            gpu_vendor=None,
            gpu_name=None,
            nvidia_gpu_available=False,
        ),
        ProjectRequirements(gpu_required=True),
    )

    assert check.local_value == {
        "gpu_vendor": None,
        "gpu_name": None,
        "nvidia_gpu_available": False,
    }
    assert check.status == "incompatible"
    assert "no recognizable GPU" in check.reason


def test_nvidia_requirement_is_satisfied() -> None:
    check = check_gpu_compatibility(
        MachineProfile(
            gpu_vendor="NVIDIA",
            gpu_name="RTX 4090",
            nvidia_gpu_available=True,
        ),
        ProjectRequirements(gpu_required=True, gpu_vendor="NVIDIA"),
    )

    assert check.status == "compatible"
    assert "RTX 4090" in check.reason
    assert "NVIDIA" in check.reason


def test_nvidia_requirement_is_not_satisfied_by_amd() -> None:
    check = check_gpu_compatibility(
        MachineProfile(
            gpu_vendor="AMD",
            gpu_name="Radeon RX 7900 XTX",
            nvidia_gpu_available=False,
        ),
        ProjectRequirements(gpu_required=True, gpu_vendor="NVIDIA"),
    )

    assert check.status == "incompatible"
    assert "AMD" in check.reason
    assert "NVIDIA" in check.reason


def test_gpu_memory_requirement_is_satisfied() -> None:
    check = check_gpu_memory_compatibility(
        MachineProfile(gpu_memory_gb=24),
        ProjectRequirements(minimum_gpu_memory_gb=12),
    )

    assert check.component == "gpu_memory"
    assert check.local_value == 24.0
    assert check.required_value == 12.0
    assert check.status == "compatible"


def test_gpu_memory_requirement_is_not_satisfied() -> None:
    check = check_gpu_memory_compatibility(
        MachineProfile(gpu_memory_gb=8),
        ProjectRequirements(minimum_gpu_memory_gb=12),
    )

    assert check.status == "incompatible"
    assert "below" in check.reason


def test_unknown_local_gpu_memory_is_unknown() -> None:
    check = check_gpu_memory_compatibility(
        MachineProfile(gpu_name="RTX 3090", gpu_memory_gb=None),
        ProjectRequirements(minimum_gpu_memory_gb=8),
    )

    assert check.local_value is None
    assert check.required_value == 8.0
    assert check.status == "unknown"
    assert "cannot be determined" in check.reason


def test_cuda_is_not_required() -> None:
    check = check_cuda_compatibility(
        MachineProfile(cuda_available=False, cuda_version=None),
        ProjectRequirements(cuda_required=False),
    )

    assert check.component == "cuda"
    assert check.status == "compatible"
    assert check.required_value == {"cuda_required": False, "cuda_version": None}
    assert "not require" in check.reason


def test_unknown_cuda_requirement_is_unknown() -> None:
    check = check_cuda_compatibility(
        MachineProfile(cuda_available=True, cuda_version="12.1"),
        ProjectRequirements(cuda_required="unknown", cuda_version=None),
    )

    assert check.status == "unknown"
    assert "unknown" in check.reason


def test_required_cuda_is_missing() -> None:
    check = check_cuda_compatibility(
        MachineProfile(
            nvidia_gpu_available=True,
            cuda_available=False,
            cuda_version=None,
        ),
        ProjectRequirements(cuda_required=True, cuda_version=">=11.8"),
    )

    assert check.local_value == {
        "nvidia_gpu_available": True,
        "cuda_available": False,
        "cuda_version": None,
    }
    assert check.status == "incompatible"
    assert "not available" in check.reason


def test_cuda_minimum_version_is_satisfied() -> None:
    check = check_cuda_compatibility(
        MachineProfile(cuda_available=True, cuda_version="12.1"),
        ProjectRequirements(cuda_required=True, cuda_version=">=11.8"),
    )

    assert check.required_value == {"cuda_required": True, "cuda_version": ">=11.8"}
    assert check.status == "compatible"
    assert "12.1" in check.reason
    assert ">=11.8" in check.reason


def test_cuda_minimum_version_is_not_satisfied() -> None:
    check = check_cuda_compatibility(
        MachineProfile(cuda_available=True, cuda_version="11.7"),
        ProjectRequirements(cuda_required=True, cuda_version=">=11.8"),
    )

    assert check.status == "incompatible"
    assert "does not satisfy" in check.reason


def test_cuda_bare_version_is_an_exact_requirement() -> None:
    matching = check_cuda_compatibility(
        MachineProfile(cuda_available=True, cuda_version="11.8"),
        ProjectRequirements(cuda_required=True, cuda_version="11.8"),
    )
    newer = check_cuda_compatibility(
        MachineProfile(cuda_available=True, cuda_version="12.1"),
        ProjectRequirements(cuda_required=True, cuda_version="11.8"),
    )

    assert matching.status == "compatible"
    assert matching.required_value["cuda_version"] == "==11.8"
    assert newer.status == "incompatible"


def test_unknown_project_cuda_version_is_unknown() -> None:
    check = check_cuda_compatibility(
        MachineProfile(cuda_available=True, cuda_version="12.1"),
        ProjectRequirements(cuda_required=True, cuda_version="unknown"),
    )

    assert check.status == "unknown"
    assert "does not declare a comparable CUDA version" in check.reason


def test_unknown_local_cuda_version_is_unknown() -> None:
    check = check_cuda_compatibility(
        MachineProfile(cuda_available=True, cuda_version=None),
        ProjectRequirements(cuda_required=True, cuda_version=">=11.8"),
    )

    assert check.local_value["cuda_version"] is None
    assert check.status == "unknown"
    assert "cannot be determined" in check.reason


def test_docker_supported_and_locally_available_is_compatible() -> None:
    check = check_docker_compatibility(
        MachineProfile(docker_available=True),
        ProjectRequirements(docker_supported=True),
    )

    assert check.component == "docker"
    assert check.local_value is True
    assert check.required_value == {
        "docker_supported": True,
        "docker_required": False,
    }
    assert check.status == "compatible"
    assert "optional Docker deployment path" in check.reason


def test_docker_supported_but_locally_unavailable_is_partial() -> None:
    check = check_docker_compatibility(
        MachineProfile(docker_available=False),
        ProjectRequirements(docker_supported=True),
    )

    assert check.status == "partial"
    assert "not a hard requirement" in check.reason


def test_docker_required_but_locally_unavailable_is_incompatible() -> None:
    evidence = Evidence(
        field="docker_supported",
        value=True,
        source_file="README.md",
        raw_text="Docker is required to run this project.",
    )
    check = check_docker_compatibility(
        MachineProfile(docker_available=False),
        ProjectRequirements(docker_supported=True, evidence=[evidence]),
    )

    assert check.required_value == {
        "docker_supported": True,
        "docker_required": True,
    }
    assert check.status == "incompatible"
    assert check.evidence == [evidence]
    assert "explicitly requires Docker" in check.reason


def test_docker_required_can_be_detected_from_special_requirements() -> None:
    check = check_docker_compatibility(
        MachineProfile(docker_available=True),
        ProjectRequirements(
            docker_supported=True,
            special_requirements=["You must use Docker to run the application."],
        ),
    )

    assert check.required_value["docker_required"] is True
    assert check.status == "compatible"


def test_missing_project_docker_information_is_unknown() -> None:
    check = check_docker_compatibility(
        MachineProfile(docker_available=True),
        ProjectRequirements(docker_supported=None),
    )

    assert check.required_value == {
        "docker_supported": None,
        "docker_required": False,
    }
    assert check.status == "unknown"
    assert "does not declare Docker support or a Docker requirement" in check.reason
