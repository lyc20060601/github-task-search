"""Minimal repository smoke tests executed exclusively in the Docker Sandbox."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from .docker_sandbox import (
    DEPENDENCY_DIRECTORY_NAME,
    PROJECT_TEMP_ROOT,
    SANDBOX_DEPENDENCY_TARGET,
    SandboxLimits,
    run_in_sandbox,
)
from .entrypoint_detector import COMMON_ENTRYPOINTS, detect_entrypoint


DEFAULT_SMOKE_TIMEOUT_SECONDS = 30
DEFAULT_MAX_STDERR_CHARS = 4_000
_PACKAGE_PATTERN = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
_IMPORT_SCRIPT = "import importlib,sys; importlib.import_module(sys.argv[1])"


@dataclass(frozen=True)
class SmokeTestResult:
    smoke_test_status: str
    exit_code: int | None
    test_duration: float
    error: str | None = None
    stderr: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_smoke_test(
    repository_path: str | Path,
    *,
    entrypoint: str | None = None,
    package_name: str | None = None,
    timeout_seconds: int = DEFAULT_SMOKE_TIMEOUT_SECONDS,
    max_stderr_chars: int = DEFAULT_MAX_STDERR_CHARS,
) -> SmokeTestResult:
    """Run one bounded, non-interactive Python check in a disconnected container."""
    path = _validated_repository_path(repository_path)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_stderr_chars <= 0:
        raise ValueError("max_stderr_chars must be positive")

    command, validation_error = _select_command(path, entrypoint, package_name)
    if validation_error:
        return SmokeTestResult(
            smoke_test_status="skipped",
            exit_code=None,
            test_duration=0.0,
            error=validation_error,
        )

    dependency_directory = path / DEPENDENCY_DIRECTORY_NAME
    if dependency_directory.is_dir():
        command = ["env", f"PYTHONPATH={SANDBOX_DEPENDENCY_TARGET}", *command]
    else:
        dependency_directory = None

    started = perf_counter()
    result = run_in_sandbox(
        path,
        command,
        limits=SandboxLimits(timeout_seconds=timeout_seconds),
        network_enabled=False,
        dependency_directory=dependency_directory,
        dependency_directory_read_only=True,
    )
    duration = round(perf_counter() - started, 3)
    stderr = _bounded_text(result.stderr, max_stderr_chars)
    if result.status == "success":
        return SmokeTestResult(
            smoke_test_status="success",
            exit_code=result.exit_code,
            test_duration=duration,
            stderr=stderr,
        )

    return SmokeTestResult(
        smoke_test_status="failed",
        exit_code=result.exit_code,
        test_duration=duration,
        error=_failure_reason(result.error, stderr),
        stderr=stderr,
    )


def _select_command(
    path: Path,
    entrypoint: str | None,
    package_name: str | None,
) -> tuple[list[str], str | None]:
    if entrypoint is not None:
        normalized = entrypoint.replace("\\", "/")
        if normalized not in COMMON_ENTRYPOINTS or not (path / normalized).is_file():
            return [], "No safe Python entrypoint was confirmed"
        return ["python", "-B", normalized, "--help"], None

    detected = detect_entrypoint(path)
    if detected.entrypoint in COMMON_ENTRYPOINTS and (path / detected.entrypoint).is_file():
        return ["python", "-B", detected.entrypoint, "--help"], None

    selected_package = package_name or _detect_package(path)
    if selected_package is None or not _PACKAGE_PATTERN.fullmatch(selected_package):
        return [], "No valid Python package was confirmed for an import check"
    return ["python", "-B", "-c", _IMPORT_SCRIPT, selected_package], None


def _detect_package(path: Path) -> str | None:
    candidates = sorted(
        child.name
        for child in path.iterdir()
        if child.is_dir()
        and _PACKAGE_PATTERN.fullmatch(child.name)
        and (child / "__init__.py").is_file()
    )
    return candidates[0] if len(candidates) == 1 else None


def _validated_repository_path(repository_path: str | Path) -> Path:
    path = Path(repository_path).resolve()
    if not path.is_dir():
        raise ValueError("repository_path must be an existing directory")
    try:
        path.relative_to(PROJECT_TEMP_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("repository_path must be inside the project runtime temporary directory") from exc
    return path


def _bounded_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return "[truncated]\n" + value[-max_chars:]


def _failure_reason(error: str, stderr: str) -> str:
    if error:
        return _bounded_text(error, 2_000)
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if lines:
        return lines[-1][-2_000:]
    return "Smoke test failed without an error message"
