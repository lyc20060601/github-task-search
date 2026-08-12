"""Sequential AI analysis for a bounded list of repository candidates."""

from typing import Any

from repo_analyzer import analyze_repository
from repo_reader import get_repository_details
from task_parser import TaskSpec


MAX_REPOSITORIES = 10


def analyze_repositories(
    repositories: list[dict[str, Any]],
    task_spec: TaskSpec,
) -> list[dict[str, Any]]:
    """Analyze at most ten repositories without failing the whole batch."""

    results: list[dict[str, Any]] = []
    for repository in repositories[:MAX_REPOSITORIES]:
        full_name = repository.get("full_name")
        if not isinstance(full_name, str) or not full_name.strip():
            results.append(
                {
                    "full_name": None,
                    "profile": None,
                    "error": "repository result is missing full_name",
                }
            )
            continue

        try:
            details = get_repository_details(full_name)
            profile = analyze_repository(task_spec, details)
            results.append(
                {
                    "full_name": full_name,
                    "profile": profile,
                    "error": None,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "full_name": full_name,
                    "profile": None,
                    "error": str(exc) or exc.__class__.__name__,
                }
            )

    return results
