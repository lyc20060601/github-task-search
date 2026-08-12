"""Deterministic task-aware scoring for one analyzed GitHub repository."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from repo_profile import RepoProfile
from task_parser import TaskSpec


SCORE_LIMITS = {
    "task_match": 30,
    "completeness": 20,
    "must_have": 20,
    "maintenance": 10,
    "documentation": 10,
    "community": 5,
    "environment": 5,
}
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]*", re.IGNORECASE)
STOP_WORDS = frozenset({"a", "an", "and", "for", "must", "support", "the", "with"})


def _tokens(values: list[str | None]) -> set[str]:
    return {
        token.casefold()
        for value in values
        if value
        for token in TOKEN_PATTERN.findall(value)
        if token.casefold() not in STOP_WORDS
    }


def _task_match_score(task_spec: TaskSpec, profile: RepoProfile) -> int:
    label = (profile.task_match or "").strip().casefold()
    label_scores = {
        "exact": 30,
        "very high": 30,
        "high": 27,
        "medium": 20,
        "moderate": 20,
        "low": 10,
        "no": 0,
        "none": 0,
        "mismatch": 0,
    }
    if label in label_scores:
        return label_scores[label]

    requested = _tokens(
        [task_spec.task, *task_spec.domain, *task_spec.framework]
    )
    if not requested:
        return 0
    available = _tokens([*profile.tasks, *profile.domains, *profile.framework])
    return round(30 * len(requested & available) / len(requested))


def _completeness_score(profile: RepoProfile) -> int:
    return min(
        20,
        (8 if profile.has_training_code is True else 0)
        + (4 if profile.has_configs is True else 0)
        + (
            4
            if profile.has_custom_dataset_support is True
            or profile.has_dataset_code is True
            else 0
        )
        + (4 if profile.has_pretrained_weights is True else 0),
    )


def _requirement_status(requirement: str, profile: RepoProfile) -> bool | None:
    normalized = " ".join(requirement.casefold().replace("_", " ").split())
    if "custom dataset" in normalized or "自定义数据集" in normalized:
        return profile.has_custom_dataset_support
    if "pretrained" in normalized or "pre-trained" in normalized or "预训练" in normalized:
        return profile.has_pretrained_weights
    if "train" in normalized or "训练" in normalized:
        return profile.has_training_code
    if "docker" in normalized:
        return profile.has_docker
    if "config" in normalized or "配置" in normalized:
        return profile.has_configs
    if "dataset" in normalized or "数据集" in normalized:
        return profile.has_dataset_code

    profile_frameworks = {value.casefold() for value in profile.framework}
    for framework in ("pytorch", "tensorflow", "jax", "keras"):
        if framework in normalized:
            return framework in profile_frameworks if profile_frameworks else None
    return None


def _must_have_score(task_spec: TaskSpec, profile: RepoProfile) -> int:
    if not task_spec.must_have:
        return 20

    satisfaction = 0.0
    for requirement in task_spec.must_have:
        status = _requirement_status(requirement, profile)
        if status is True:
            satisfaction += 1.0
        elif status is None:
            satisfaction += 0.25
    return round(20 * satisfaction / len(task_spec.must_have))


def _maintenance_score(updated_at: Any, now: datetime) -> int:
    if not isinstance(updated_at, str):
        return 0
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age = now - updated.astimezone(timezone.utc)
    if age <= timedelta(days=90):
        return 10
    if age <= timedelta(days=180):
        return 8
    if age <= timedelta(days=365):
        return 6
    if age <= timedelta(days=730):
        return 3
    return 1


def _documentation_score(quality: str | None) -> int:
    label = (quality or "unknown").strip().casefold()
    return {
        "excellent": 10,
        "very good": 9,
        "good": 8,
        "fair": 5,
        "average": 5,
        "poor": 2,
        "unknown": 2,
    }.get(label, 2)


def _community_score(stars: Any) -> int:
    try:
        count = int(stars or 0)
    except (TypeError, ValueError):
        return 0
    if count >= 10_000:
        return 5
    if count >= 1_000:
        return 4
    if count >= 100:
        return 3
    if count >= 10:
        return 2
    if count > 0:
        return 1
    return 0


def _environment_score(profile: RepoProfile) -> int:
    return (
        (2 if profile.has_requirements is True else 0)
        + (2 if profile.has_environment_file is True else 0)
        + (1 if profile.has_docker is True else 0)
    )


def calculate_repository_score(
    task_spec: TaskSpec,
    repo_profile: RepoProfile,
    github_metadata: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a deterministic final score and its seven capped components."""

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    breakdown = {
        "task_match": _task_match_score(task_spec, repo_profile),
        "completeness": _completeness_score(repo_profile),
        "must_have": _must_have_score(task_spec, repo_profile),
        "maintenance": _maintenance_score(
            github_metadata.get("updated_at"), current_time
        ),
        "documentation": _documentation_score(repo_profile.documentation_quality),
        "community": _community_score(github_metadata.get("stars")),
        "environment": _environment_score(repo_profile),
    }
    capped_breakdown = {
        name: max(0, min(score, SCORE_LIMITS[name]))
        for name, score in breakdown.items()
    }
    return {
        "final_score": max(0, min(sum(capped_breakdown.values()), 100)),
        "score_breakdown": capped_breakdown,
    }
