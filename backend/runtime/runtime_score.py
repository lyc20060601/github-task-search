"""Deterministic scoring for an isolated repository runtime report."""

from typing import Any

from runtime_report import RuntimeReport, RuntimeStatus


SCORE_LIMITS = {
    "clone": 10,
    "environment_detection": 10,
    "entrypoint_detection": 15,
    "dependency_install": 35,
    "smoke_test": 25,
    "environment_documentation": 5,
}
DEPENDENCY_FAILURE_SCORE_CAP = 60


def _status_value(status: RuntimeStatus | str) -> str:
    return status.value if isinstance(status, RuntimeStatus) else status


def _is_known(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip().casefold() != "unknown")


def _environment_documentation_score(report: RuntimeReport) -> int:
    return (3 if _is_known(report.python_version) else 0) + (
        2 if _is_known(report.framework) else 0
    )


def _runtime_status(report: RuntimeReport) -> str:
    critical_statuses = (
        _status_value(report.clone_status),
        _status_value(report.dependency_install_status),
        _status_value(report.smoke_test_status),
    )

    if RuntimeStatus.FAILED.value in critical_statuses:
        return RuntimeStatus.FAILED.value
    if all(status == RuntimeStatus.SUCCESS.value for status in critical_statuses):
        return RuntimeStatus.SUCCESS.value
    if RuntimeStatus.SKIPPED.value in critical_statuses:
        return RuntimeStatus.SKIPPED.value
    return RuntimeStatus.UNKNOWN.value


def calculate_runtime_score(report: RuntimeReport) -> dict[str, Any]:
    """Return a transparent 100-point score without executing repository code."""

    breakdown = {
        "clone": (
            SCORE_LIMITS["clone"]
            if _status_value(report.clone_status) == RuntimeStatus.SUCCESS.value
            else 0
        ),
        "environment_detection": (
            SCORE_LIMITS["environment_detection"]
            if _status_value(report.environment_detected)
            == RuntimeStatus.SUCCESS.value
            else 0
        ),
        "entrypoint_detection": (
            SCORE_LIMITS["entrypoint_detection"]
            if _status_value(report.entrypoint_detected)
            == RuntimeStatus.SUCCESS.value
            else 0
        ),
        "dependency_install": (
            SCORE_LIMITS["dependency_install"]
            if _status_value(report.dependency_install_status)
            == RuntimeStatus.SUCCESS.value
            else 0
        ),
        "smoke_test": (
            SCORE_LIMITS["smoke_test"]
            if _status_value(report.smoke_test_status)
            == RuntimeStatus.SUCCESS.value
            else 0
        ),
        "environment_documentation": _environment_documentation_score(report),
    }

    raw_score = sum(breakdown.values())
    applied_cap = 0
    if (
        _status_value(report.dependency_install_status)
        == RuntimeStatus.FAILED.value
        and raw_score > DEPENDENCY_FAILURE_SCORE_CAP
    ):
        applied_cap = DEPENDENCY_FAILURE_SCORE_CAP - raw_score

    breakdown["dependency_failure_cap"] = applied_cap
    runtime_score = max(0, min(sum(breakdown.values()), 100))

    return {
        "runtime_score": runtime_score,
        "runtime_breakdown": breakdown,
        "runtime_status": _runtime_status(report),
    }
