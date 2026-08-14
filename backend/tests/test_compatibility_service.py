from __future__ import annotations

import pytest

from compatibility import service
from compatibility.models import MachineProfile


def _environment(**files: str) -> dict:
    return {
        "full_name": "owner/repository",
        "files": {
            name: {"content": content, "size": len(content), "truncated": False}
            for name, content in files.items()
        },
        "found_files": list(files),
        "missing_files": [],
        "skipped_files": [],
        "errors": [],
    }


def _run(monkeypatch: pytest.MonkeyPatch, files: dict, machine: MachineProfile):
    calls = {"machine": 0}

    monkeypatch.setattr(
        service,
        "fetch_repository_environment_files",
        lambda full_name: files,
    )

    def detect() -> MachineProfile:
        calls["machine"] += 1
        return machine

    monkeypatch.setattr(service, "detect_machine_profile", detect)
    result = service.analyze_repository_compatibility("owner/repository")
    assert calls["machine"] == 1
    return result


def _status(result, component: str) -> str:
    return next(
        check.status
        for check in result.compatibility_result.checks
        if check.component == component
    )


def test_python_project_is_compatible_with_matching_machine(monkeypatch) -> None:
    result = _run(
        monkeypatch,
        _environment(
            **{
                "pyproject.toml": (
                    "[project]\nrequires-python = \">=3.10\"\n"
                    "dependencies = [\"torch==2.4.0\"]\n"
                ),
                "README.md": "Supported platforms: Linux.\n",
            }
        ),
        MachineProfile(
            os_name="Linux",
            python_available=True,
            python_version="3.11",
            memory_total_gb=32,
            docker_available=False,
        ),
    )

    assert result.project_requirements.python_min_version == "3.10"
    assert _status(result, "python") == "compatible"
    assert result.compatibility_result.compatibility_score is not None
    assert result.deployment_plan.recommended_method in {"venv", "Native Python"}


def test_specific_python_requirement_can_be_incompatible(monkeypatch) -> None:
    result = _run(
        monkeypatch,
        _environment(**{".python-version": "3.10.13\n"}),
        MachineProfile(python_available=True, python_version="3.12.1"),
    )

    assert result.project_requirements.python_exact_version == "3.10.13"
    assert _status(result, "python") == "incompatible"
    assert result.compatibility_result.overall_status == "incompatible"
    assert result.deployment_plan.recommended_method in {"venv", "Conda"}


def test_linux_project_on_windows_is_partial(monkeypatch) -> None:
    result = _run(
        monkeypatch,
        _environment(**{"Dockerfile": "FROM ubuntu:22.04\n"}),
        MachineProfile(os_name="Windows", os_version="11", python_available=True),
    )

    assert result.project_requirements.supported_os == ["Linux"]
    assert _status(result, "os") == "partial"
    assert result.deployment_plan.recommended_method == "WSL2 + Conda"


def test_required_nvidia_gpu_is_incompatible_when_machine_has_no_gpu(monkeypatch) -> None:
    result = _run(
        monkeypatch,
        _environment(
            **{"README.md": "Requires an NVIDIA CUDA GPU with at least 8 GB VRAM.\n"}
        ),
        MachineProfile(
            nvidia_gpu_available=False,
            cuda_available=False,
            gpu_memory_gb=None,
        ),
    )

    assert result.project_requirements.gpu_required is True
    assert _status(result, "gpu") == "incompatible"
    assert result.deployment_plan.recommended_method == "unknown"
    assert result.deployment_plan.difficulty == "hard"


def test_minimum_vram_is_incompatible_when_machine_is_below_it(monkeypatch) -> None:
    result = _run(
        monkeypatch,
        _environment(**{"README.md": "Minimum GPU memory: 8 GB VRAM.\n"}),
        MachineProfile(gpu_memory_gb=4),
    )

    assert result.project_requirements.minimum_gpu_memory_gb == 8
    assert _status(result, "gpu_memory") == "incompatible"
    assert result.deployment_plan.recommended_method == "unknown"
    assert any("VRAM" in item for item in result.deployment_plan.required_actions)


def test_cuda_version_mismatch_is_incompatible(monkeypatch) -> None:
    result = _run(
        monkeypatch,
        _environment(**{"README.md": "Requires CUDA 12.1 to run.\n"}),
        MachineProfile(
            nvidia_gpu_available=True,
            cuda_available=True,
            cuda_version="11.8",
        ),
    )

    assert result.project_requirements.cuda_version == "12.1"
    assert _status(result, "cuda") == "incompatible"
    assert result.compatibility_result.compatibility_score <= 30


def test_docker_project_produces_docker_plan(monkeypatch) -> None:
    result = _run(
        monkeypatch,
        _environment(
            **{
                "Dockerfile": "FROM python:3.11-slim\n",
                "requirements.txt": "requests==2.32.0\n",
            }
        ),
        MachineProfile(
            os_name="Linux",
            python_available=True,
            python_version="3.11",
            docker_available=True,
        ),
    )

    assert result.project_requirements.docker_supported is True
    assert _status(result, "docker") == "compatible"
    assert result.deployment_plan.recommended_method == "Docker"


def test_missing_repository_files_return_unknowns_without_crashing(monkeypatch) -> None:
    result = _run(monkeypatch, _environment(), MachineProfile())

    assert result.project_requirements.framework is None
    assert result.project_requirements.evidence == []
    assert result.compatibility_result.overall_status == "unknown"
    assert all(check.status == "unknown" for check in result.compatibility_result.checks)
    assert result.deployment_plan.recommended_method == "unknown"


def test_fetcher_returned_errors_are_preserved_and_analysis_continues(monkeypatch) -> None:
    environment = _environment()
    environment["errors"] = [
        {"path": "README.md", "status": 503, "reason": "GitHub returned HTTP 503"}
    ]
    result = _run(monkeypatch, environment, MachineProfile(python_version=None))

    assert result.fetch_errors
    assert "503" in result.fetch_errors[0]
    assert result.compatibility_result.overall_status == "unknown"


def test_fetch_exception_returns_safe_unknown_result(monkeypatch) -> None:
    calls = {"machine": 0}

    def fail(_full_name: str):
        raise RuntimeError("GitHub environment files unavailable")

    def detect() -> MachineProfile:
        calls["machine"] += 1
        return MachineProfile(os_name="Windows", gpu_memory_gb=None)

    monkeypatch.setattr(service, "fetch_repository_environment_files", fail)
    monkeypatch.setattr(service, "detect_machine_profile", detect)

    result = service.analyze_repository_compatibility("owner/repository")

    assert calls["machine"] == 1
    assert result.fetch_errors == ["GitHub environment files unavailable"]
    assert result.compatibility_result.overall_status == "unknown"
    assert result.deployment_plan.recommended_method == "unknown"


def test_fetch_exception_does_not_expose_secrets_or_env_paths(monkeypatch) -> None:
    def fail(_full_name: str):
        raise RuntimeError(
            "GITHUB_TOKEN=github_pat_fake_secret LLM_API_KEY=sk-fake-secret-value "
            "from C:/project/.env"
        )

    monkeypatch.setattr(service, "fetch_repository_environment_files", fail)
    monkeypatch.setattr(service, "detect_machine_profile", MachineProfile)

    result = service.analyze_repository_compatibility("owner/repository")
    serialized = " ".join(result.fetch_errors)

    assert "github_pat_fake_secret" not in serialized
    assert "sk-fake-secret-value" not in serialized
    assert ".env" not in serialized
    assert "[REDACTED]" in serialized


def test_unknown_machine_fields_remain_unknown_in_checks(monkeypatch) -> None:
    result = _run(
        monkeypatch,
        _environment(
            **{
                "README.md": "Requires at least 16GB RAM.\n",
                "pyproject.toml": "[project]\nrequires-python = \">=3.10\"\n",
            }
        ),
        MachineProfile(memory_total_gb=None, python_available=None, python_version=None),
    )

    assert _status(result, "ram") == "unknown"
    assert _status(result, "python") == "unknown"
    assert 0 <= result.compatibility_result.compatibility_score <= 100


def test_service_returns_conflicts_and_all_structured_sections(monkeypatch) -> None:
    result = _run(
        monkeypatch,
        _environment(
            **{
                "pyproject.toml": "[project]\nrequires-python = \">=3.10\"\n",
                "README.md": "Requires Python 3.8.\n",
            }
        ),
        MachineProfile(python_available=True, python_version="3.10"),
    )

    payload = result.model_dump()
    assert set(payload) == {
        "full_name",
        "machine_profile",
        "project_requirements",
        "compatibility_result",
        "deployment_plan",
        "conflicts",
        "fetch_errors",
    }
    assert result.machine_profile.python_version == "3.10"
    assert result.compatibility_result.compatibility_score is not None
    assert result.deployment_plan is not None
