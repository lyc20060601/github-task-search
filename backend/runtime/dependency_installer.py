"""Dependency installation checks executed only inside the Docker Sandbox."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Iterable

from .docker_sandbox import (
    DEPENDENCY_DIRECTORY_NAME,
    PROJECT_TEMP_ROOT,
    SANDBOX_DEPENDENCY_TARGET,
    SandboxLimits,
    run_in_sandbox,
)


DEFAULT_INSTALL_TIMEOUT_SECONDS = 600
DEFAULT_MAX_LOG_CHARS = 20_000
INSTALL_TARGET = SANDBOX_DEPENDENCY_TARGET


@dataclass(frozen=True)
class DependencyInstallResult:
    dependency_install_status: str
    install_duration: float
    install_error: str | None = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def install_dependencies(
    repository_path: str | Path,
    *,
    timeout_seconds: int = DEFAULT_INSTALL_TIMEOUT_SECONDS,
    max_log_chars: int = DEFAULT_MAX_LOG_CHARS,
) -> DependencyInstallResult:
    """Install one repository's dependencies in an ephemeral networked container."""
    path = _validated_repository_path(repository_path)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_log_chars <= 0:
        raise ValueError("max_log_chars must be positive")

    requirements = path / "requirements.txt"
    pyproject = path / "pyproject.toml"
    if requirements.is_file():
        install_command = _pip_base_command() + ["-r", "requirements.txt"]
    elif pyproject.is_file():
        error = _validate_installable_pyproject(pyproject)
        if error:
            return DependencyInstallResult(
                dependency_install_status="failed",
                install_duration=0.0,
                install_error=error,
            )
        install_command = _pip_base_command() + ["--use-pep517", "."]
    else:
        return DependencyInstallResult(
            dependency_install_status="skipped",
            install_duration=0.0,
            install_error="No supported dependency file was found",
        )

    limits = SandboxLimits(
        timeout_seconds=timeout_seconds,
        tmpfs_size="1g",
    )
    dependency_directory = path / DEPENDENCY_DIRECTORY_NAME
    dependency_directory.mkdir(exist_ok=True)
    started = perf_counter()
    sandbox_result = run_in_sandbox(
        path,
        install_command,
        limits=limits,
        network_enabled=True,
        dependency_directory=dependency_directory,
        dependency_directory_read_only=False,
    )
    duration = round(perf_counter() - started, 3)
    stdout = _bounded_log(sandbox_result.stdout, max_log_chars)
    stderr = _bounded_log(sandbox_result.stderr, max_log_chars)
    if sandbox_result.status == "success":
        return DependencyInstallResult(
            dependency_install_status="success",
            install_duration=duration,
            stdout=stdout,
            stderr=stderr,
        )

    return DependencyInstallResult(
        dependency_install_status="failed",
        install_duration=duration,
        install_error=_final_error(sandbox_result.error, stderr, stdout),
        stdout=stdout,
        stderr=stderr,
    )


def install_dependencies_for_repositories(
    repository_paths: Iterable[str | Path],
    *,
    timeout_seconds: int = DEFAULT_INSTALL_TIMEOUT_SECONDS,
    max_log_chars: int = DEFAULT_MAX_LOG_CHARS,
) -> list[DependencyInstallResult]:
    """Install sequentially; one repository failure never aborts later repositories."""
    results: list[DependencyInstallResult] = []
    for repository_path in repository_paths:
        started = perf_counter()
        try:
            result = install_dependencies(
                repository_path,
                timeout_seconds=timeout_seconds,
                max_log_chars=max_log_chars,
            )
        except Exception as exc:
            result = DependencyInstallResult(
                dependency_install_status="failed",
                install_duration=round(perf_counter() - started, 3),
                install_error=str(exc) or exc.__class__.__name__,
            )
        results.append(result)
    return results


def _pip_base_command() -> list[str]:
    return [
        "python",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--no-cache-dir",
        "--target",
        INSTALL_TARGET,
    ]


def _validated_repository_path(repository_path: str | Path) -> Path:
    path = Path(repository_path).resolve()
    if not path.is_dir():
        raise ValueError("repository_path must be an existing directory")
    try:
        path.relative_to(PROJECT_TEMP_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("repository_path must be inside the project runtime temporary directory") from exc
    return path


def _validate_installable_pyproject(path: Path) -> str | None:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return f"Unable to parse pyproject.toml: {exc}"

    tool = data.get("tool", {})
    has_project_metadata = isinstance(data.get("project"), dict)
    has_build_system = isinstance(data.get("build-system"), dict)
    has_known_tool = isinstance(tool, dict) and any(
        isinstance(tool.get(name), dict) for name in ("poetry", "flit", "setuptools", "hatch")
    )
    if not (has_project_metadata or has_build_system or has_known_tool):
        return "pyproject.toml does not describe an installable Python project"
    return None


def _bounded_log(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return "[truncated]\n" + value[-max_chars:]


def _final_error(error: str, stderr: str, stdout: str) -> str:
    if error:
        return _bounded_log(error, 2_000)
    for log in (stderr, stdout):
        lines = [line.strip() for line in log.splitlines() if line.strip()]
        if lines:
            return lines[-1][-2_000:]
    return "Dependency installation failed without an error message"
