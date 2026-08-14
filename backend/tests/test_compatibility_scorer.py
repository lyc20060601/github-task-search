from compatibility.compatibility_models import CompatibilityCheck
from compatibility.compatibility_scorer import score_compatibility


COMPONENTS = (
    "python",
    "os",
    "ram",
    "gpu",
    "gpu_memory",
    "cuda",
    "docker",
)


def _check(component: str, status: str) -> CompatibilityCheck:
    return CompatibilityCheck(
        component=component,
        status=status,
        reason=f"{component} is {status}",
    )


def _all(status: str = "compatible") -> list[CompatibilityCheck]:
    return [_check(component, status) for component in COMPONENTS]


def _replace(
    checks: list[CompatibilityCheck], component: str, status: str
) -> list[CompatibilityCheck]:
    return [
        _check(item.component, status) if item.component == component else item
        for item in checks
    ]


def test_all_requirements_satisfied_scores_100() -> None:
    result = score_compatibility(_all())

    assert result.compatibility_score == 100.0
    assert result.overall_status == "compatible"
    assert result.issues == []


def test_gpu_critical_failure_caps_score() -> None:
    result = score_compatibility(_replace(_all(), "gpu", "incompatible"))

    assert result.compatibility_score <= 30
    assert result.overall_status == "incompatible"
    assert any("gpu" in issue.casefold() for issue in result.issues)


def test_python_failure_caps_score() -> None:
    result = score_compatibility(_replace(_all(), "python", "incompatible"))

    assert result.compatibility_score <= 45
    assert result.overall_status == "incompatible"


def test_python_failure_uses_component_advisor_suggestion() -> None:
    checks = _all()
    checks[0] = CompatibilityCheck(
        component="python",
        local_value="3.9",
        required_value=">=3.10",
        status="incompatible",
        reason="Local Python 3.9 does not satisfy >=3.10.",
    )

    result = score_compatibility(checks)

    assert any("venv or Conda" in item for item in result.suggestions)


def test_partial_os_produces_partial_result() -> None:
    result = score_compatibility(_replace(_all(), "os", "partial"))

    assert 80 < result.compatibility_score < 100
    assert result.overall_status == "partial"
    assert any("os" in warning.casefold() for warning in result.warnings)


def test_many_unknown_checks_reduce_coverage_without_scoring_zero() -> None:
    checks = [_check("python", "compatible"), _check("os", "compatible")]
    checks.extend(_check(component, "unknown") for component in COMPONENTS[2:])

    result = score_compatibility(checks)

    assert 50 < result.compatibility_score < 100
    assert result.overall_status == "unknown"
    assert any("coverage" in warning.casefold() for warning in result.warnings)


def test_all_unknown_checks_receive_neutral_score_and_unknown_status() -> None:
    result = score_compatibility(_all("unknown"))

    assert result.compatibility_score == 50.0
    assert result.overall_status == "unknown"


def test_missing_checks_are_treated_as_unknown_coverage() -> None:
    result = score_compatibility([_check("python", "compatible")])

    assert result.compatibility_score == 59.0
    assert result.overall_status == "unknown"
    assert any("coverage" in warning.casefold() for warning in result.warnings)


def test_optional_docker_unavailable_is_partial_not_incompatible() -> None:
    checks = _replace(_all(), "docker", "partial")
    docker = next(item for item in checks if item.component == "docker")
    docker.required_value = {
        "docker_supported": True,
        "docker_required": False,
    }

    result = score_compatibility(checks)

    assert result.compatibility_score > 90
    assert result.overall_status == "partial"
    assert result.issues == []


def test_insufficient_ram_caps_score_and_is_incompatible() -> None:
    result = score_compatibility(_replace(_all(), "ram", "incompatible"))

    assert result.compatibility_score <= 55
    assert result.overall_status == "incompatible"
