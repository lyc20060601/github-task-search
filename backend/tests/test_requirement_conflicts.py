from compatibility.requirement_conflicts import ProjectRequirementAnalysis
from compatibility.project_requirement_analyzer import (
    analyze_project_requirements_with_conflicts,
)


def _fetched(**files: str) -> dict[str, object]:
    return {
        "files": {
            name: {
                "content": content,
                "size": len(content.encode("utf-8")),
                "truncated": False,
            }
            for name, content in files.items()
        }
    }


def _conflict(analysis: ProjectRequirementAnalysis, field: str):
    return next(item for item in analysis.conflicts if item.field == field)


def test_python_authoritative_conflict_remains_unresolved() -> None:
    analysis = analyze_project_requirements_with_conflicts(
        _fetched(
            **{
                "pyproject.toml": (
                    "[project]\n"
                    "requires-python = \">=3.9\"\n"
                ),
                "README.md": "Requires Python 3.8.\n",
            }
        )
    )

    conflict = _conflict(analysis, "python_version")
    assert conflict.status == "unresolved"
    assert conflict.selected_value is None
    assert {candidate.source_file for candidate in conflict.candidates} == {
        "pyproject.toml",
        "README.md",
    }
    assert conflict.evidence


def test_cuda_authoritative_conflict_remains_unresolved() -> None:
    analysis = analyze_project_requirements_with_conflicts(
        _fetched(
            **{
                "environment.yml": "dependencies:\n  - cudatoolkit=11.8\n",
                "README.md": "Requires CUDA 12.1.\n",
            }
        )
    )

    conflict = _conflict(analysis, "cuda_version")
    assert conflict.status == "unresolved"
    assert conflict.selected_value is None
    assert {candidate.value for candidate in conflict.candidates} == {"11.8", "12.1"}


def test_recommendation_does_not_override_pyproject_requirement() -> None:
    analysis = analyze_project_requirements_with_conflicts(
        _fetched(
            **{
                "pyproject.toml": "[project]\nrequires-python = \">=3.9\"\n",
                "README.md": "Recommended Python 3.11.\n",
            }
        )
    )

    conflict = _conflict(analysis, "python_version")
    assert conflict.status == "resolved"
    assert conflict.selected_value == ">=3.9"
    assert analysis.requirements.python_min_version == "3.9"
    assert any(candidate.scope == "recommendation" for candidate in conflict.candidates)


def test_docker_version_does_not_override_explicit_readme_requirement() -> None:
    analysis = analyze_project_requirements_with_conflicts(
        _fetched(
            **{
                "Dockerfile": "FROM python:3.10-slim\n",
                "README.md": "Requires Python 3.9.\n",
            }
        )
    )

    conflict = _conflict(analysis, "python_version")
    assert conflict.status == "resolved"
    assert conflict.selected_value == "3.9"
    assert analysis.requirements.python_exact_version == "3.9"
    assert any(candidate.scope == "docker_environment" for candidate in conflict.candidates)


def test_tested_environment_does_not_override_required_minimum() -> None:
    analysis = analyze_project_requirements_with_conflicts(
        _fetched(
            **{
                "README.md": (
                    "Requires CUDA 11.8.\n"
                    "Tested with CUDA 12.1.\n"
                )
            }
        )
    )

    conflict = _conflict(analysis, "cuda_version")
    assert conflict.status == "resolved"
    assert conflict.selected_value == "11.8"
    assert analysis.requirements.cuda_version == "11.8"
    assert any(candidate.scope == "tested_environment" for candidate in conflict.candidates)


def test_compatible_sources_do_not_create_conflict() -> None:
    analysis = analyze_project_requirements_with_conflicts(
        _fetched(
            **{
                "pyproject.toml": "[project]\nrequires-python = \">=3.9\"\n",
                "Dockerfile": "FROM python:3.10-slim\n",
            }
        )
    )

    assert isinstance(analysis, ProjectRequirementAnalysis)
    assert analysis.requirements.python_min_version == "3.9"
    assert analysis.conflicts == []
