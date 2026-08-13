"""Orchestrate one explicitly requested repository runtime validation."""

from __future__ import annotations

import shutil
from pathlib import Path

from runtime_report import RuntimeReport

from .dependency_installer import install_dependencies
from .docker_sandbox import PROJECT_TEMP_ROOT
from .entrypoint_detector import detect_entrypoint
from .environment_detector import EnvironmentDetection, detect_environment
from .repo_cloner import clone_repository
from .runtime_score import calculate_runtime_score
from .smoke_tester import run_smoke_test


def _environment_was_detected(environment: EnvironmentDetection) -> bool:
    return bool(
        environment.detected_files
        or environment.python_version != "unknown"
        or environment.framework != "unknown"
        or environment.package_manager != "unknown"
    )


def _append_diagnostic(
    target: list[str],
    stage: str,
    message: str | None,
) -> None:
    if message:
        target.append(f"{stage}: {message}")


def _remove_clone(repository_path: Path) -> None:
    resolved_path = repository_path.resolve()
    resolved_path.relative_to(PROJECT_TEMP_ROOT.resolve())
    shutil.rmtree(resolved_path)


def _score_report(report: RuntimeReport) -> RuntimeReport:
    return report.model_copy(update=calculate_runtime_score(report))


def validate_repository(full_name: str) -> RuntimeReport:
    """Validate one public repository and always return a structured report."""

    try:
        clone = clone_repository(full_name)
    except Exception as exc:
        report = RuntimeReport(
            full_name=full_name,
            clone_status="failed",
            environment_detected="skipped",
            entrypoint_detected="skipped",
            dependency_install_status="skipped",
            smoke_test_status="skipped",
            errors=[f"Clone failed: {exc or exc.__class__.__name__}"],
        )
        return _score_report(report)

    if clone.clone_status != "success" or not clone.path:
        report = RuntimeReport(
            full_name=full_name,
            clone_status="failed",
            environment_detected="skipped",
            entrypoint_detected="skipped",
            dependency_install_status="skipped",
            smoke_test_status="skipped",
            errors=[f"Clone failed: {clone.error or 'unknown clone error'}"],
        )
        return _score_report(report)

    repository_path = Path(clone.path)
    report = RuntimeReport(full_name=full_name, clone_status="success")

    try:
        try:
            environment = detect_environment(repository_path)
            report.python_version = environment.python_version
            report.framework = environment.framework
            report.environment_detected = (
                "failed"
                if environment.errors
                else "success"
                if _environment_was_detected(environment)
                else "unknown"
            )
            for error in environment.errors:
                _append_diagnostic(report.errors, "Environment detection failed", error)
            for warning in environment.warnings:
                _append_diagnostic(report.warnings, "Environment detection warning", warning)
        except Exception as exc:
            report.environment_detected = "failed"
            _append_diagnostic(
                report.errors,
                "Environment detection failed",
                str(exc) or exc.__class__.__name__,
            )

        try:
            entrypoint = detect_entrypoint(repository_path)
            report.entrypoint = entrypoint.entrypoint
            report.entrypoint_detected = (
                "success" if entrypoint.entrypoint != "unknown" else "unknown"
            )
        except Exception as exc:
            report.entrypoint_detected = "failed"
            _append_diagnostic(
                report.errors,
                "Entrypoint detection failed",
                str(exc) or exc.__class__.__name__,
            )

        try:
            installation = install_dependencies(repository_path)
            report.dependency_install_status = installation.dependency_install_status
            report.install_duration = installation.install_duration
            if installation.dependency_install_status == "failed":
                _append_diagnostic(
                    report.errors,
                    "Dependency installation failed",
                    installation.install_error,
                )
            elif installation.dependency_install_status == "skipped":
                _append_diagnostic(
                    report.warnings,
                    "Dependency installation skipped",
                    installation.install_error,
                )
        except Exception as exc:
            report.dependency_install_status = "failed"
            _append_diagnostic(
                report.errors,
                "Dependency installation failed",
                str(exc) or exc.__class__.__name__,
            )

        try:
            confirmed_entrypoint = (
                report.entrypoint if report.entrypoint_detected == "success" else None
            )
            smoke = run_smoke_test(
                repository_path,
                entrypoint=confirmed_entrypoint,
            )
            report.smoke_test_status = smoke.smoke_test_status
            report.test_duration = smoke.test_duration
            if smoke.smoke_test_status == "failed":
                _append_diagnostic(report.errors, "Smoke test failed", smoke.error)
            elif smoke.smoke_test_status == "skipped":
                _append_diagnostic(report.warnings, "Smoke test skipped", smoke.error)
        except Exception as exc:
            report.smoke_test_status = "failed"
            _append_diagnostic(
                report.errors,
                "Smoke test failed",
                str(exc) or exc.__class__.__name__,
            )
    finally:
        try:
            _remove_clone(repository_path)
        except (OSError, ValueError) as exc:
            _append_diagnostic(
                report.warnings,
                "Clone cleanup failed",
                str(exc) or exc.__class__.__name__,
            )

    return _score_report(report)
