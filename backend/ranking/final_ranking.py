"""Stable Top 5 formatting for scored repository analysis results."""

from datetime import datetime
from typing import Any

from repo_profile import RepoProfile
from task_parser import TaskSpec

from .deep_score import calculate_repository_score


TOP_REPOSITORIES = 5
EVIDENCE_FIELDS = {
    "has_training_code": "has_training_code_evidence",
    "has_custom_dataset_support": "has_custom_dataset_support_evidence",
    "has_pretrained_weights": "has_pretrained_weights_evidence",
    "framework": "framework_evidence",
    "hardware_notes": "hardware_notes_evidence",
}


def _profile_evidence(profile: RepoProfile) -> dict[str, dict[str, str]]:
    return {
        conclusion: getattr(profile, evidence_field).model_dump()
        for conclusion, evidence_field in EVIDENCE_FIELDS.items()
    }


def rank_repositories(
    task_spec: TaskSpec,
    repositories: list[dict[str, Any]],
    analysis_results: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Score successful analyses, sort them, and return a JSON-ready Top 5."""

    metadata_by_full_name = {
        repository.get("full_name"): repository
        for repository in repositories
        if isinstance(repository.get("full_name"), str)
    }
    analysis_by_full_name = {
        result.get("full_name"): result
        for result in analysis_results
        if isinstance(result.get("full_name"), str)
    }

    scored = []
    for repository in repositories:
        full_name = repository.get("full_name")
        if full_name not in metadata_by_full_name:
            continue
        analysis = analysis_by_full_name.get(full_name)
        if not analysis or analysis.get("error") is not None:
            continue
        profile = analysis.get("profile")
        if not isinstance(profile, RepoProfile):
            continue

        score = calculate_repository_score(
            task_spec,
            profile,
            repository,
            now=now,
        )
        scored.append(
            {
                "full_name": full_name,
                "html_url": repository.get("html_url"),
                "description": repository.get("description"),
                "stars": repository.get("stars"),
                "language": repository.get("language"),
                "final_score": score["final_score"],
                "score_breakdown": score["score_breakdown"],
                "repo_profile": profile.model_dump(),
                "strengths": profile.strengths,
                "weaknesses": profile.weaknesses,
                "evidence": _profile_evidence(profile),
            }
        )

    scored.sort(key=lambda result: result["final_score"], reverse=True)
    top_results = scored[:TOP_REPOSITORIES]
    for rank, result in enumerate(top_results, start=1):
        result["rank"] = rank
    return top_results
