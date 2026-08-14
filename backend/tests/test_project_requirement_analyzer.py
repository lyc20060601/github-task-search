from compatibility.project_requirement_analyzer import analyze_project_requirements
from compatibility.project_requirements import ProjectRequirements


def _fetched(**files: str) -> dict[str, object]:
    return {
        "full_name": "owner/repository",
        "files": {
            name: {
                "content": content,
                "size": len(content.encode("utf-8")),
                "truncated": False,
            }
            for name, content in files.items()
        },
    }


def test_requirements_only_returns_project_requirements() -> None:
    result = analyze_project_requirements(
        _fetched(**{"requirements.txt": "torch==2.4.0\nnumpy>=2\n"})
    )

    assert isinstance(result, ProjectRequirements)
    assert result.framework == "PyTorch"
    assert result.framework_version == "==2.4.0"
    assert result.package_manager == "pip"
    assert result.gpu_required is None


def test_requirements_and_readme_combine_without_guessing_gpu() -> None:
    result = analyze_project_requirements(
        _fetched(
            **{
                "requirements.txt": "torch==2.4.0\n",
                "README.md": (
                    "Requires Python >= 3.10.\n"
                    "Requires at least 16GB RAM.\n"
                ),
            }
        )
    )

    assert result.framework == "PyTorch"
    assert result.python_min_version == "3.10"
    assert result.minimum_ram_gb == 16
    assert result.gpu_required is None
    assert result.minimum_gpu_memory_gb is None


def test_conda_and_readme_combine_explicit_cuda_and_gpu_requirements() -> None:
    result = analyze_project_requirements(
        _fetched(
            **{
                "environment.yml": (
                    "name: vision\n"
                    "dependencies:\n"
                    "  - python=3.10\n"
                    "  - pytorch=2.1\n"
                    "  - cudatoolkit=11.8\n"
                ),
                "README.md": "Requires an NVIDIA CUDA GPU with at least 8 GB VRAM.\n",
            }
        )
    )

    assert result.python_exact_version == "3.10"
    assert result.framework == "PyTorch"
    assert result.cuda_version == "11.8"
    assert result.cuda_required is True
    assert result.gpu_required is True
    assert result.gpu_vendor == "NVIDIA"
    assert result.minimum_gpu_memory_gb == 8
    assert result.package_manager == "conda"


def test_docker_and_readme_do_not_infer_minimum_hardware_from_image() -> None:
    result = analyze_project_requirements(
        _fetched(
            **{
                "Dockerfile": "FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04\n",
                "README.md": "CUDA support is available. Tested on RTX 3090 (24GB).\n",
            }
        )
    )

    assert result.docker_supported is True
    assert result.cuda_version == "12.1.1"
    assert result.cuda_required is None
    assert result.gpu_required is None
    assert result.minimum_gpu_memory_gb is None
    assert result.preferred_os == "Ubuntu"


def test_all_environment_files_are_aggregated_with_evidence() -> None:
    result = analyze_project_requirements(
        _fetched(
            **{
                "requirements.txt": "torch==2.4.0\n",
                "environment.yml": "dependencies:\n  - cudatoolkit=12.1\n",
                "Dockerfile": "FROM python:3.11-slim\n",
                "README.md": (
                    "Supported platforms: Windows and Linux.\n"
                    "Requires at least 32GB RAM.\n"
                    "Docker is supported.\n"
                ),
            }
        )
    )

    assert result.supported_os == ["Windows", "Linux"]
    assert result.framework == "PyTorch"
    assert result.cuda_version == "12.1"
    assert result.minimum_ram_gb == 32
    assert result.docker_supported is True
    assert result.evidence
    sources = {
        item.source_file
        for item in result.evidence
        if hasattr(item, "source_file")
    }
    assert {"requirements.txt", "environment.yml", "Dockerfile", "README.md"} <= sources


def test_nearly_empty_repository_returns_unknown_fields() -> None:
    result = analyze_project_requirements(
        _fetched(**{"README.md": "# Example\nA small demonstration project.\n"})
    )

    assert isinstance(result, ProjectRequirements)
    assert result.supported_os == []
    assert result.python_min_version is None
    assert result.python_exact_version is None
    assert result.framework is None
    assert result.cuda_required is None
    assert result.gpu_required is None
    assert result.minimum_gpu_memory_gb is None
    assert result.minimum_ram_gb is None
    assert result.evidence == []


def test_cuda_image_alone_never_creates_hardware_minimums() -> None:
    result = analyze_project_requirements(
        _fetched(**{"Dockerfile": "FROM nvidia/cuda:11.8.0-runtime\n"})
    )

    assert result.cuda_version == "11.8.0"
    assert result.cuda_required is None
    assert result.gpu_required is None
    assert result.gpu_vendor is None
    assert result.minimum_gpu_memory_gb is None
    assert result.minimum_ram_gb is None
