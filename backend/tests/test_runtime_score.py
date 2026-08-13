from runtime.runtime_score import calculate_runtime_score
from runtime_report import RuntimeReport


def _successful_report(**overrides):
    values = {
        "full_name": "example/project",
        "clone_status": "success",
        "environment_detected": "success",
        "entrypoint_detected": "success",
        "dependency_install_status": "success",
        "smoke_test_status": "success",
        "python_version": "3.11",
        "framework": "PyTorch",
        "entrypoint": "tools/train.py",
    }
    values.update(overrides)
    return RuntimeReport(**values)


def test_successful_runtime_report_receives_full_score():
    result = calculate_runtime_score(_successful_report())

    assert result == {
        "runtime_score": 100,
        "runtime_breakdown": {
            "clone": 10,
            "environment_detection": 10,
            "entrypoint_detection": 15,
            "dependency_install": 35,
            "smoke_test": 25,
            "environment_documentation": 5,
            "dependency_failure_cap": 0,
        },
        "runtime_status": "success",
    }


def test_dependency_install_failure_caps_score_at_60():
    result = calculate_runtime_score(
        _successful_report(dependency_install_status="failed")
    )

    assert result["runtime_score"] == 60
    assert result["runtime_breakdown"]["dependency_install"] == 0
    assert result["runtime_breakdown"]["dependency_failure_cap"] == -5
    assert sum(result["runtime_breakdown"].values()) == 60
    assert result["runtime_status"] == "failed"


def test_smoke_test_failure_loses_all_smoke_test_points():
    result = calculate_runtime_score(
        _successful_report(smoke_test_status="failed")
    )

    assert result["runtime_score"] == 75
    assert result["runtime_breakdown"]["smoke_test"] == 0
    assert result["runtime_status"] == "failed"


def test_environment_documentation_is_scored_from_known_fields():
    result = calculate_runtime_score(
        _successful_report(python_version="unknown", framework=None)
    )

    assert result["runtime_score"] == 95
    assert result["runtime_breakdown"]["environment_documentation"] == 0


def test_unfinished_runtime_report_remains_unknown():
    result = calculate_runtime_score(
        RuntimeReport(full_name="example/project", clone_status="success")
    )

    assert result["runtime_score"] == 10
    assert result["runtime_status"] == "unknown"


def test_skipped_critical_runtime_checks_report_skipped():
    result = calculate_runtime_score(
        RuntimeReport(
            full_name="example/project",
            clone_status="success",
            dependency_install_status="skipped",
            smoke_test_status="skipped",
        )
    )

    assert result["runtime_status"] == "skipped"
