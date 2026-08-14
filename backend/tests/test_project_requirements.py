from compatibility.project_requirements import ProjectRequirements


def test_complete_project_requirements_can_be_created() -> None:
    requirements = ProjectRequirements(
        supported_os=["Windows", "Linux"],
        preferred_os="Linux",
        python_min_version="3.9",
        python_max_version="3.12",
        python_exact_version=None,
        framework="PyTorch",
        framework_version="2.4",
        cuda_required=True,
        cuda_version="12.1",
        gpu_required=True,
        gpu_vendor="NVIDIA",
        minimum_gpu_memory_gb=8,
        minimum_ram_gb=16,
        docker_supported=True,
        package_manager="pip",
        special_requirements=["Linux build tools"],
        evidence=["README.md", "requirements.txt", "Dockerfile"],
    )

    assert requirements.framework == "PyTorch"
    assert requirements.cuda_required is True
    assert requirements.minimum_gpu_memory_gb == 8


def test_project_requirements_accepts_unknown_and_null_values() -> None:
    requirements = ProjectRequirements(
        supported_os=None,
        preferred_os="unknown",
        python_min_version=None,
        framework="unknown",
        cuda_required="unknown",
        gpu_required="unknown",
        minimum_gpu_memory_gb=None,
        minimum_ram_gb="unknown",
        docker_supported="unknown",
        special_requirements=None,
        evidence=None,
    )

    assert requirements.supported_os is None
    assert requirements.cuda_required == "unknown"
    assert requirements.minimum_ram_gb == "unknown"
    assert requirements.evidence is None


def test_project_requirements_supports_multiple_operating_systems() -> None:
    requirements = ProjectRequirements(supported_os=["Windows", "Linux", "macOS"])

    assert requirements.supported_os == ["Windows", "Linux", "macOS"]


def test_project_requirements_preserves_evidence_sources() -> None:
    sources = ["README.md", "requirements.txt", "environment.yml", "Dockerfile"]
    requirements = ProjectRequirements(evidence=sources)

    assert requirements.evidence == sources
