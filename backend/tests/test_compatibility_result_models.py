import pytest

from compatibility.compatibility_models import (
    CompatibilityCheck,
    CompatibilityResult,
)
from compatibility.evidence import Evidence


def test_compatibility_check_can_be_created() -> None:
    evidence = Evidence(
        field="python_version",
        value=">=3.10",
        source_file="pyproject.toml",
        raw_text='requires-python = ">=3.10"',
    )

    check = CompatibilityCheck(
        component="Python",
        local_value="3.11.8",
        required_value=">=3.10",
        status="compatible",
        reason="The local Python version satisfies the requirement.",
        evidence=[evidence],
    )

    assert check.component == "Python"
    assert check.status == "compatible"
    assert check.evidence == [evidence]


@pytest.mark.parametrize(
    "status",
    ["compatible", "partial", "incompatible", "unknown"],
)
def test_compatibility_check_accepts_all_statuses(status: str) -> None:
    check = CompatibilityCheck(
        component="CUDA",
        status=status,
        reason="Test status",
    )

    assert check.status == status


def test_compatibility_check_accepts_unknown_and_null_values() -> None:
    check = CompatibilityCheck(
        component="GPU memory",
        local_value=None,
        required_value="unknown",
        status="unknown",
        reason="The available information is insufficient.",
        evidence=["README.md"],
    )

    assert check.local_value is None
    assert check.required_value == "unknown"
    assert check.evidence == ["README.md"]


def test_compatibility_result_can_be_created() -> None:
    check = CompatibilityCheck(
        component="Operating system",
        local_value="Windows 11",
        required_value=["Windows", "Linux"],
        status="compatible",
        reason="Windows is listed as supported.",
    )

    result = CompatibilityResult(
        overall_status="compatible",
        compatibility_score=95,
        checks=[check],
        warnings=["Docker deployment was not checked."],
        issues=[],
        suggestions=["Use the documented Python environment."],
    )

    assert result.overall_status == "compatible"
    assert result.compatibility_score == 95
    assert result.checks == [check]


def test_compatibility_result_allows_null_score_and_safe_empty_lists() -> None:
    first = CompatibilityResult(overall_status="unknown")
    second = CompatibilityResult(overall_status="unknown")

    first.warnings.append("Missing project evidence")

    assert first.compatibility_score is None
    assert first.checks == []
    assert first.issues == []
    assert first.suggestions == []
    assert second.warnings == []
