from pathlib import Path
from unittest.mock import patch

from runtime.dependency_installer import (
    DependencyInstallResult,
    install_dependencies,
    install_dependencies_for_repositories,
)
from runtime.docker_sandbox import PROJECT_TEMP_ROOT, SandboxResult


def _workspace(name: str) -> Path:
    path = PROJECT_TEMP_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_installs_requirements_inside_networked_sandbox() -> None:
    workspace = _workspace("dependency-requirements-test")
    (workspace / "requirements.txt").write_text("requests==2.32.3\n", encoding="utf-8")

    with (
        patch("runtime.dependency_installer.run_in_sandbox") as run,
        patch("runtime.dependency_installer.perf_counter", side_effect=[10.0, 12.5]),
    ):
        run.return_value = SandboxResult(status="success", exit_code=0, stdout="installed\n")
        result = install_dependencies(workspace, timeout_seconds=300)

    assert result.dependency_install_status == "success"
    assert result.install_duration == 2.5
    assert result.install_error is None
    assert result.stdout == "installed\n"
    command = run.call_args.args[1]
    assert command[-2:] == ["-r", "requirements.txt"]
    assert "--target" in command
    assert "/opt/dependencies" in command
    dependency_directory = workspace / ".runtime-dependencies"
    assert dependency_directory.is_dir()
    assert run.call_args.kwargs["dependency_directory"] == dependency_directory
    assert run.call_args.kwargs["dependency_directory_read_only"] is False
    assert run.call_args.kwargs["network_enabled"] is True
    assert run.call_args.kwargs["limits"].timeout_seconds == 300


def test_installs_pep621_pyproject_with_standard_pip_command() -> None:
    workspace = _workspace("dependency-pyproject-test")
    (workspace / "pyproject.toml").write_text(
        '[build-system]\nrequires=["setuptools"]\nbuild-backend="setuptools.build_meta"\n'
        '[project]\nname="sample"\nversion="0.1.0"\n',
        encoding="utf-8",
    )

    with patch("runtime.dependency_installer.run_in_sandbox") as run:
        run.return_value = SandboxResult(status="success", exit_code=0)
        result = install_dependencies(workspace)

    assert result.dependency_install_status == "success"
    command = run.call_args.args[1]
    assert command[-1] == "."
    assert "--use-pep517" in command


def test_skips_repository_without_supported_dependency_file() -> None:
    workspace = _workspace("dependency-missing-test")

    result = install_dependencies(workspace)

    assert result.dependency_install_status == "skipped"
    assert result.install_duration == 0.0
    assert result.install_error == "No supported dependency file was found"


def test_rejects_non_installable_pyproject_without_running_container() -> None:
    workspace = _workspace("dependency-invalid-pyproject-test")
    (workspace / "pyproject.toml").write_text('[tool.black]\nline-length=100\n', encoding="utf-8")

    with patch("runtime.dependency_installer.run_in_sandbox") as run:
        result = install_dependencies(workspace)

    assert result.dependency_install_status == "failed"
    assert "installable Python project" in (result.install_error or "")
    run.assert_not_called()


def test_failure_logs_are_bounded_and_final_reason_is_recorded() -> None:
    workspace = _workspace("dependency-log-test")
    (workspace / "requirements.txt").write_text("missing-package\n", encoding="utf-8")

    with patch("runtime.dependency_installer.run_in_sandbox") as run:
        run.return_value = SandboxResult(
            status="failed",
            exit_code=1,
            stdout="o" * 100,
            stderr="e" * 100,
            error="pip failed",
        )
        result = install_dependencies(workspace, max_log_chars=32)

    assert result.dependency_install_status == "failed"
    assert result.install_error == "pip failed"
    assert result.stdout.startswith("[truncated]\n")
    assert result.stderr.startswith("[truncated]\n")
    assert len(result.stdout) <= 44
    assert len(result.stderr) <= 44


def test_batch_continues_after_one_repository_raises() -> None:
    first = _workspace("dependency-batch-first")
    second = _workspace("dependency-batch-second")
    success = DependencyInstallResult(dependency_install_status="success", install_duration=1.0)

    with patch(
        "runtime.dependency_installer.install_dependencies",
        side_effect=[RuntimeError("unexpected"), success],
    ):
        results = install_dependencies_for_repositories([first, second])

    assert [result.dependency_install_status for result in results] == ["failed", "success"]
    assert results[0].install_error == "unexpected"
