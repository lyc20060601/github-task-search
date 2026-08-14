from pathlib import Path
from unittest.mock import patch

from runtime.docker_sandbox import PROJECT_TEMP_ROOT, SandboxResult
from runtime.smoke_tester import run_smoke_test


def _workspace(name: str) -> Path:
    path = PROJECT_TEMP_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_entrypoint_help_runs_in_disconnected_sandbox() -> None:
    workspace = _workspace("smoke-entrypoint-test")
    (workspace / "train.py").write_text("raise RuntimeError('must only run in Docker')", encoding="utf-8")
    dependency_directory = workspace / ".runtime-dependencies"
    dependency_directory.mkdir(exist_ok=True)

    with (
        patch("runtime.smoke_tester.run_in_sandbox") as run,
        patch("runtime.smoke_tester.perf_counter", side_effect=[5.0, 6.25]),
    ):
        run.return_value = SandboxResult(status="success", exit_code=0)
        result = run_smoke_test(workspace, entrypoint="train.py", timeout_seconds=20)

    assert result.smoke_test_status == "success"
    assert result.exit_code == 0
    assert result.test_duration == 1.25
    assert result.error is None
    assert run.call_args.args[1] == [
        "env",
        "PYTHONPATH=/opt/dependencies",
        "python",
        "-B",
        "train.py",
        "--help",
    ]
    assert run.call_args.kwargs["dependency_directory"] == dependency_directory
    assert run.call_args.kwargs["dependency_directory_read_only"] is True
    assert run.call_args.kwargs["network_enabled"] is False
    assert run.call_args.kwargs["limits"].timeout_seconds == 20


def test_import_check_uses_validated_package_as_separate_argument() -> None:
    workspace = _workspace("smoke-import-test")

    with patch("runtime.smoke_tester.run_in_sandbox") as run:
        run.return_value = SandboxResult(status="success", exit_code=0)
        result = run_smoke_test(workspace, package_name="sample_package")

    assert result.smoke_test_status == "success"
    command = run.call_args.args[1]
    assert command[:3] == ["python", "-B", "-c"]
    assert command[-1] == "sample_package"
    assert "import_module(sys.argv[1])" in command[-2]


def test_rejects_shell_script_without_running_container() -> None:
    workspace = _workspace("smoke-shell-test")
    (workspace / "run.sh").write_text("echo unsafe", encoding="utf-8")

    with patch("runtime.smoke_tester.run_in_sandbox") as run:
        result = run_smoke_test(workspace, entrypoint="run.sh")

    assert result.smoke_test_status == "skipped"
    assert result.exit_code is None
    assert "safe Python entrypoint" in (result.error or "")
    run.assert_not_called()


def test_rejects_invalid_package_name_without_running_container() -> None:
    workspace = _workspace("smoke-package-validation-test")

    with patch("runtime.smoke_tester.run_in_sandbox") as run:
        result = run_smoke_test(workspace, package_name="pkg; shutdown")

    assert result.smoke_test_status == "skipped"
    assert "valid Python package" in (result.error or "")
    run.assert_not_called()


def test_failure_preserves_exit_code_and_bounds_stderr() -> None:
    workspace = _workspace("smoke-failure-test")
    (workspace / "demo.py").write_text("", encoding="utf-8")

    with patch("runtime.smoke_tester.run_in_sandbox") as run:
        run.return_value = SandboxResult(
            status="failed",
            exit_code=2,
            stderr="e" * 100,
            error="command failed",
        )
        result = run_smoke_test(workspace, entrypoint="demo.py", max_stderr_chars=32)

    assert result.smoke_test_status == "failed"
    assert result.exit_code == 2
    assert result.error == "command failed"
    assert result.stderr.startswith("[truncated]\n")
    assert len(result.stderr) <= 44


def test_timeout_is_reported_without_exit_code() -> None:
    workspace = _workspace("smoke-timeout-test")
    (workspace / "main.py").write_text("", encoding="utf-8")

    with patch("runtime.smoke_tester.run_in_sandbox") as run:
        run.return_value = SandboxResult(
            status="failed",
            timed_out=True,
            error="sandbox timed out after 1 seconds",
        )
        result = run_smoke_test(workspace, entrypoint="main.py", timeout_seconds=1)

    assert result.smoke_test_status == "failed"
    assert result.exit_code is None
    assert "timed out" in (result.error or "")


def test_detects_top_level_package_when_no_entrypoint_exists() -> None:
    workspace = _workspace("smoke-package-detection-test")
    package = workspace / "vision_toolkit"
    package.mkdir(exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")

    with patch("runtime.smoke_tester.run_in_sandbox") as run:
        run.return_value = SandboxResult(status="success", exit_code=0)
        result = run_smoke_test(workspace)

    assert result.smoke_test_status == "success"
    assert run.call_args.args[1][-1] == "vision_toolkit"
