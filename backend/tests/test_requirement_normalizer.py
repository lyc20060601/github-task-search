import pytest

from compatibility.project_requirements import ProjectRequirements
from compatibility.requirement_normalizer import (
    normalize_capacity,
    normalize_cuda_version,
    normalize_os_requirement,
    normalize_project_requirements,
    normalize_python_version,
)


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("Python 3.10+", ">=3.10"),
        (">=3.10", ">=3.10"),
        ("python>=3.10", ">=3.10"),
        ("3.9-3.11", ">=3.9,<=3.11"),
        ("==3.10", "==3.10"),
        ("~=3.10", "~=3.10"),
    ],
)
def test_normalize_python_versions(raw: str, normalized: str) -> None:
    result = normalize_python_version(raw)

    assert result.raw == raw
    assert result.normalized == normalized


def test_normalize_project_python_fields_keep_field_semantics() -> None:
    result = normalize_project_requirements(
        ProjectRequirements(
            python_min_version="3.9",
            python_max_version="3.11",
            python_exact_version="3.10",
        )
    )

    assert result.normalized["python_min_version"] == {
        "raw": "3.9",
        "normalized": ">=3.9",
    }
    assert result.normalized["python_max_version"]["normalized"] == "<=3.11"
    assert result.normalized["python_exact_version"]["normalized"] == "==3.10"


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("CUDA 11.8", "==11.8"),
        ("CUDA11.8", "==11.8"),
        ("CUDA >=11.8", ">=11.8"),
        ("CUDA 11.8+", ">=11.8"),
        ("cu118", "==11.8"),
        ("cu121", "==12.1"),
    ],
)
def test_normalize_cuda_versions(raw: str, normalized: str) -> None:
    result = normalize_cuda_version(raw)

    assert result.raw == raw
    assert result.normalized == normalized


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("8GB VRAM", {"gigabytes": 8.0, "operator": None}),
        ("8 GB GPU memory", {"gigabytes": 8.0, "operator": None}),
        (">=8G VRAM", {"gigabytes": 8.0, "operator": ">="}),
        ("at least 12GB VRAM", {"gigabytes": 12.0, "operator": ">="}),
        ("16 GB RAM", {"gigabytes": 16.0, "operator": None}),
        ("Memory >=32GB", {"gigabytes": 32.0, "operator": ">="}),
        ("at least 16G RAM", {"gigabytes": 16.0, "operator": ">="}),
    ],
)
def test_normalize_capacity(raw: str, normalized: dict[str, object]) -> None:
    result = normalize_capacity(raw)

    assert result.raw == raw
    assert result.normalized == normalized


def test_project_capacity_uses_minimum_semantics_without_guessing_units() -> None:
    result = normalize_project_requirements(
        ProjectRequirements(minimum_gpu_memory_gb=8, minimum_ram_gb=16)
    )

    assert result.normalized["minimum_gpu_memory_gb"]["normalized"] == {
        "gigabytes": 8.0,
        "operator": ">=",
    }
    assert result.normalized["minimum_ram_gb"]["normalized"] == {
        "gigabytes": 16.0,
        "operator": ">=",
    }


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("Windows", {"family": "Windows", "version": None, "distribution": None}),
        ("Windows 10", {"family": "Windows", "version": "10", "distribution": None}),
        ("Windows 11", {"family": "Windows", "version": "11", "distribution": None}),
        ("Linux", {"family": "Linux", "version": None, "distribution": None}),
        (
            "Ubuntu 22.04",
            {"family": "Linux", "version": "22.04", "distribution": "Ubuntu"},
        ),
        ("macOS", {"family": "macOS", "version": None, "distribution": None}),
    ],
)
def test_normalize_operating_systems(raw: str, normalized: dict[str, str | None]) -> None:
    result = normalize_os_requirement(raw)

    assert result.raw == raw
    assert result.normalized == normalized


@pytest.mark.parametrize(
    "raw",
    ["Python latest", "CUDA latest", "cu12", "8 TB VRAM", "Solaris"],
)
def test_unreliable_values_have_null_normalized_value(raw: str) -> None:
    if raw.startswith("Python"):
        result = normalize_python_version(raw)
    elif raw.startswith("CUDA") or raw.startswith("cu"):
        result = normalize_cuda_version(raw)
    elif "VRAM" in raw:
        result = normalize_capacity(raw)
    else:
        result = normalize_os_requirement(raw)

    assert result.raw == raw
    assert result.normalized is None


def test_project_result_preserves_raw_requirements_and_unknowns() -> None:
    requirements = ProjectRequirements(
        supported_os=["Windows", "Linux"],
        preferred_os="unknown",
        python_min_version=None,
        cuda_version=None,
        minimum_ram_gb=None,
    )

    result = normalize_project_requirements(requirements)

    assert result.raw == requirements
    assert result.normalized["supported_os"][0] == {
        "raw": "Windows",
        "normalized": {
            "family": "Windows",
            "version": None,
            "distribution": None,
        },
    }
    assert result.normalized["preferred_os"]["normalized"] is None
    assert result.normalized["python_min_version"]["normalized"] is None
