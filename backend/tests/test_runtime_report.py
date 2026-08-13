import pytest
from pydantic import ValidationError

from runtime_report import RuntimeReport, RuntimeStatus


def test_runtime_report_defaults_to_unknown_statuses_and_empty_diagnostics():
    report = RuntimeReport(full_name="open-mmlab/mmsegmentation")

    assert report.full_name == "open-mmlab/mmsegmentation"
    assert report.clone_status == RuntimeStatus.UNKNOWN
    assert report.environment_detected == RuntimeStatus.UNKNOWN
    assert report.dependency_install_status == RuntimeStatus.UNKNOWN
    assert report.entrypoint_detected == RuntimeStatus.UNKNOWN
    assert report.smoke_test_status == RuntimeStatus.UNKNOWN
    assert report.errors == []
    assert report.warnings == []
    assert report.runtime_score is None
    assert report.runtime_breakdown == {}
    assert report.runtime_status == RuntimeStatus.UNKNOWN


def test_runtime_report_accepts_all_documented_status_values():
    report = RuntimeReport(
        full_name="example/project",
        clone_status="success",
        environment_detected="failed",
        dependency_install_status="skipped",
        entrypoint_detected="unknown",
        smoke_test_status=RuntimeStatus.SUCCESS,
        python_version="3.11.9",
        framework="PyTorch",
        entrypoint="tools/train.py",
        install_duration=12.5,
        test_duration=3.25,
        errors=["dependency unavailable"],
        warnings=["GPU not detected"],
        runtime_score=62.0,
        runtime_breakdown={"clone": 10, "smoke_test": 0},
        runtime_status="failed",
    )

    assert report.model_dump()["clone_status"] == "success"
    assert report.environment_detected == RuntimeStatus.FAILED
    assert report.dependency_install_status == RuntimeStatus.SKIPPED
    assert report.entrypoint_detected == RuntimeStatus.UNKNOWN
    assert report.smoke_test_status == RuntimeStatus.SUCCESS
    assert report.install_duration == 12.5
    assert report.test_duration == 3.25
    assert report.runtime_breakdown == {"clone": 10, "smoke_test": 0}
    assert report.runtime_status == RuntimeStatus.FAILED


def test_runtime_report_rejects_unsupported_status_values():
    with pytest.raises(ValidationError):
        RuntimeReport(full_name="example/project", clone_status="running")
