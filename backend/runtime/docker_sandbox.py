"""Restricted Docker execution primitives for untrusted repository smoke tests.

This module does not clone repositories and does not execute any repository by
itself. Callers must provide an already prepared workspace under ``runtime/.tmp``.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence
from uuid import uuid4


PROJECT_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"
SANDBOX_IMAGE = "github-task-search-sandbox:latest"
SANDBOX_USER = "10001:10001"


@dataclass(frozen=True)
class SandboxLimits:
    cpu_count: float = 1.0
    memory: str = "512m"
    pids_limit: int = 64
    timeout_seconds: int = 120
    tmpfs_size: str = "64m"

    def validate(self) -> None:
        if self.cpu_count <= 0:
            raise ValueError("cpu_count must be positive")
        if not self.memory:
            raise ValueError("memory must not be empty")
        if self.pids_limit <= 0:
            raise ValueError("pids_limit must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self.tmpfs_size:
            raise ValueError("tmpfs_size must not be empty")


@dataclass(frozen=True)
class SandboxResult:
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    timed_out: bool = False
    command: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_docker_command(
    workspace: str | Path,
    command: Sequence[str],
    *,
    limits: SandboxLimits | None = None,
    container_name: str | None = None,
    image: str = SANDBOX_IMAGE,
    network_enabled: bool = False,
) -> list[str]:
    """Build a deny-by-default Docker command without running it."""
    active_limits = limits or SandboxLimits()
    active_limits.validate()
    workspace_path = Path(workspace).resolve()
    temp_root = PROJECT_TEMP_ROOT.resolve()
    if not workspace_path.is_dir():
        raise ValueError("workspace must be an existing directory")
    try:
        workspace_path.relative_to(temp_root)
    except ValueError as exc:
        raise ValueError("workspace must be inside the project runtime temporary directory") from exc
    if not command or any(not isinstance(part, str) or not part for part in command):
        raise ValueError("command must contain non-empty strings")
    forbidden_markers = (
        "GITHUB_TOKEN",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        ".ssh",
        "docker.sock",
    )
    if not image or any(
        marker.lower() in part.lower()
        for part in (*command, image)
        for marker in forbidden_markers
    ):
        raise ValueError("secrets are not allowed in sandbox commands")

    docker_command = [
        "docker",
        "run",
        "--rm",
        f"--network={'bridge' if network_enabled else 'none'}",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--user={SANDBOX_USER}",
        f"--cpus={active_limits.cpu_count}",
        f"--memory={active_limits.memory}",
        f"--pids-limit={active_limits.pids_limit}",
        f"--tmpfs=/tmp:rw,noexec,nosuid,nodev,size={active_limits.tmpfs_size}",
        f"--mount=type=bind,source={workspace_path},target=/workspace,readonly",
    ]
    if container_name:
        docker_command.append(f"--name={container_name}")
    docker_command.extend([image, *command])
    return docker_command


def run_in_sandbox(
    workspace: str | Path,
    command: Sequence[str],
    *,
    limits: SandboxLimits | None = None,
    container_name: str | None = None,
    image: str = SANDBOX_IMAGE,
    network_enabled: bool = False,
) -> SandboxResult:
    """Run a caller-provided command under the restricted Docker contract."""
    active_limits = limits or SandboxLimits()
    active_container_name = container_name or f"github-task-sandbox-{uuid4().hex}"
    docker_command = build_docker_command(
        workspace,
        command,
        limits=active_limits,
        container_name=active_container_name,
        image=image,
        network_enabled=network_enabled,
    )
    clean_env = {"PATH": os.environ.get("PATH", "")}
    try:
        completed = subprocess.run(
            docker_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=active_limits.timeout_seconds,
            shell=False,
            env=clean_env,
        )
    except subprocess.TimeoutExpired:
        _remove_container(active_container_name, clean_env)
        return SandboxResult(
            status="failed",
            error=f"sandbox timed out after {active_limits.timeout_seconds} seconds",
            timed_out=True,
            command=docker_command,
        )
    except FileNotFoundError:
        return SandboxResult(
            status="failed",
            error="docker command is not available",
            command=docker_command,
        )
    except OSError as exc:
        return SandboxResult(
            status="failed",
            error=f"unable to start Docker: {exc}",
            command=docker_command,
        )

    return SandboxResult(
        status="success" if completed.returncode == 0 else "failed",
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        error="" if completed.returncode == 0 else (completed.stderr or "docker command failed").strip(),
        command=docker_command,
    )


def _remove_container(container_name: str, env: dict[str, str]) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
