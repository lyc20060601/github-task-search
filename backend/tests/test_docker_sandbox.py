from pathlib import Path
from subprocess import TimeoutExpired
from unittest.mock import call, patch

import pytest

from runtime.docker_sandbox import (
    PROJECT_TEMP_ROOT,
    SandboxLimits,
    build_docker_command,
    run_in_sandbox,
)


def _workspace(name: str) -> Path:
    path = PROJECT_TEMP_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_docker_command_contains_required_isolation_flags() -> None:
    workspace = _workspace("sandbox-command-test")

    command = build_docker_command(
        workspace,
        ["python", "--version"],
        container_name="sandbox-test",
    )

    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--user=10001:10001" in command
    assert "--cpus=1.0" in command
    assert "--memory=512m" in command
    assert "--pids-limit=64" in command
    assert "--privileged" not in command
    assert "--rm" in command
    assert command[-2:] == ["python", "--version"]


def test_docker_command_only_mounts_workspace_read_only() -> None:
    workspace = _workspace("sandbox-mount-test")

    command = build_docker_command(workspace, ["python", "--version"])
    combined = " ".join(command)

    mount = next(value for value in command if value.startswith("--mount=type=bind,"))
    assert f"source={workspace.resolve()}" in mount
    assert "target=/workspace" in mount
    assert "readonly" in mount
    assert ".ssh" not in combined.lower()
    assert "docker.sock" not in combined.lower()
    assert "GITHUB_TOKEN" not in combined
    assert "LLM_API_KEY" not in combined


def test_dependency_directory_can_be_mounted_read_only_inside_sandbox() -> None:
    workspace = _workspace("sandbox-dependency-mount-test")
    dependency_directory = workspace / ".runtime-dependencies"
    dependency_directory.mkdir(exist_ok=True)

    command = build_docker_command(
        workspace,
        ["python", "--version"],
        dependency_directory=dependency_directory,
        dependency_directory_read_only=True,
    )

    assert any(
        f"source={dependency_directory.resolve()},target=/opt/dependencies,readonly" in part
        for part in command
    )


def test_dependency_directory_write_mount_remains_scoped_to_workspace() -> None:
    workspace = _workspace("sandbox-dependency-write-test")
    dependency_directory = workspace / ".runtime-dependencies"
    dependency_directory.mkdir(exist_ok=True)

    command = build_docker_command(
        workspace,
        ["python", "--version"],
        dependency_directory=dependency_directory,
        dependency_directory_read_only=False,
    )
    mount = next(part for part in command if "target=/opt/dependencies" in part)

    assert "readonly" not in mount


def test_rejects_dependency_directory_outside_repository_workspace() -> None:
    workspace = _workspace("sandbox-dependency-scope-test")
    outside = _workspace("sandbox-dependency-outside-test")

    with pytest.raises(ValueError, match="inside the repository workspace"):
        build_docker_command(
            workspace,
            ["python", "--version"],
            dependency_directory=outside,
        )


def test_rejects_mounts_outside_project_temp_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="project runtime temporary directory"):
        build_docker_command(tmp_path, ["python", "--version"])


def test_rejects_invalid_resource_limits() -> None:
    workspace = _workspace("sandbox-limits-test")

    with pytest.raises(ValueError, match="cpu_count"):
        build_docker_command(
            workspace,
            ["python", "--version"],
            limits=SandboxLimits(cpu_count=0),
        )


def test_rejects_secret_markers_in_command() -> None:
    workspace = _workspace("sandbox-secret-test")

    with pytest.raises(ValueError, match="secrets"):
        build_docker_command(workspace, ["python", "--version", "GITHUB_TOKEN=secret"])


def test_timeout_force_removes_the_container() -> None:
    workspace = _workspace("sandbox-timeout-test")
    timeout = TimeoutExpired(cmd=["docker", "run"], timeout=1)

    with patch("runtime.docker_sandbox.subprocess.run") as run:
        run.side_effect = [timeout, None]
        result = run_in_sandbox(
            workspace,
            ["python", "--version"],
            limits=SandboxLimits(timeout_seconds=1),
            container_name="sandbox-timeout",
        )

    assert result.status == "failed"
    assert result.timed_out is True
    assert "timed out" in result.error
    cleanup_call = run.call_args_list[1]
    assert cleanup_call.args == (["docker", "rm", "-f", "sandbox-timeout"],)
    assert cleanup_call.kwargs["check"] is False
    assert cleanup_call.kwargs["capture_output"] is True
    assert cleanup_call.kwargs["text"] is True
    assert cleanup_call.kwargs["timeout"] == 10
    assert cleanup_call.kwargs["shell"] is False
    assert cleanup_call.kwargs["env"] == {"PATH": ""} or "PATH" in cleanup_call.kwargs["env"]


def test_run_assigns_a_container_name_when_caller_omits_one() -> None:
    workspace = _workspace("sandbox-auto-name-test")

    with patch("runtime.docker_sandbox.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = ""
        run.return_value.stderr = ""
        result = run_in_sandbox(workspace, ["python", "--version"])

    name_argument = next(part for part in result.command if part.startswith("--name="))
    assert name_argument.startswith("--name=github-task-sandbox-")
