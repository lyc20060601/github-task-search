import pytest

from compatibility import readme_requirement_parser as parser


def _evidence(result: dict[str, object], field: str) -> list[dict[str, object]]:
    return [
        item
        for item in result["evidence"]
        if isinstance(item, dict) and item.get("field") == field
    ]


def test_parses_python_minimum_version() -> None:
    result = parser.parse_readme_requirements(
        "## Requirements\nRequires Python >= 3.10.\n"
    )

    assert result["python_min_version"] == "3.10"
    assert _evidence(result, "python_min_version")


def test_parses_explicit_cuda_requirement() -> None:
    result = parser.parse_readme_requirements(
        "## Requirements\nRequires CUDA 11.8 to run.\n"
    )

    assert result["cuda_required"] is True
    assert result["cuda_version"] == "11.8"


def test_cuda_support_without_requirement_stays_unknown() -> None:
    result = parser.parse_readme_requirements(
        "CUDA support is available, but CPU mode is also supported.\n"
    )

    assert result["cuda_required"] is None
    assert result["cuda_version"] is None


def test_parses_explicit_nvidia_gpu_requirement() -> None:
    result = parser.parse_readme_requirements(
        "Requires an NVIDIA CUDA GPU with at least 8 GB VRAM.\n"
    )

    assert result["gpu_required"] is True
    assert result["gpu_vendor"] == "NVIDIA"
    assert result["cuda_required"] is True
    assert result["minimum_gpu_memory_gb"] == 8


def test_parses_minimum_vram() -> None:
    result = parser.parse_readme_requirements(
        "Minimum GPU memory: 12 GB VRAM.\n"
    )

    assert result["minimum_gpu_memory_gb"] == 12


def test_parses_minimum_ram_but_not_recommended_ram() -> None:
    result = parser.parse_readme_requirements(
        "Requires at least 16GB RAM.\nRecommended: 32GB RAM.\n"
    )

    assert result["minimum_ram_gb"] == 16
    assert not any(
        "32GB" in item.get("text", "")
        for item in _evidence(result, "minimum_ram_gb")
    )


def test_linux_only_requirement() -> None:
    result = parser.parse_readme_requirements(
        "This project is supported on Linux only.\n"
    )

    assert result["supported_os"] == ["Linux"]
    assert result["preferred_os"] == "Linux"


def test_windows_and_linux_are_both_supported() -> None:
    result = parser.parse_readme_requirements(
        "Supported platforms: Windows and Linux.\n"
    )

    assert result["supported_os"] == ["Windows", "Linux"]
    assert result["preferred_os"] is None


def test_parses_docker_support_and_framework_version() -> None:
    result = parser.parse_readme_requirements(
        "Environment: PyTorch 2.1\nDocker is supported.\n"
    )

    assert result["framework"] == "PyTorch"
    assert result["framework_version"] == "2.1"
    assert result["docker_supported"] is True


def test_detects_package_manager_and_special_requirement() -> None:
    result = parser.parse_readme_requirements(
        "Install with pip install -r requirements.txt.\nRequires ffmpeg.\n"
    )

    assert result["package_manager"] == "pip"
    assert "Requires ffmpeg." in result["special_requirements"]


def test_tested_gpu_is_not_minimum_requirement() -> None:
    result = parser.parse_readme_requirements(
        "Tested on RTX 3090 (24GB).\n"
    )

    assert result["gpu_required"] is None
    assert result["gpu_vendor"] is None
    assert result["minimum_gpu_memory_gb"] is None
    assert any(item.get("kind") == "tested" for item in result["soft_hints"])


def test_readme_without_environment_information_returns_unknowns() -> None:
    result = parser.parse_readme_requirements("# A project\nThis is a demo.\n")

    assert result["supported_os"] == []
    assert result["python_min_version"] is None
    assert result["framework"] is None
    assert result["cuda_required"] is None
    assert result["gpu_required"] is None
    assert result["minimum_ram_gb"] is None
    assert result["evidence"] == []


@pytest.mark.parametrize(
    ("text", "framework", "version"),
    [
        ("Uses TensorFlow 2.15.", "TensorFlow", "2.15"),
        ("JAX 0.4 is required.", "JAX", "0.4"),
    ],
)
def test_parses_supported_frameworks(
    text: str, framework: str, version: str
) -> None:
    result = parser.parse_readme_requirements(text)

    assert result["framework"] == framework
    assert result["framework_version"] == version
