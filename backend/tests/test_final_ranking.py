from datetime import datetime, timezone

from ranking.final_ranking import rank_repositories
from repo_profile import Evidence, RepoProfile
from task_parser import TaskSpec


NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _metadata(index: int) -> dict:
    return {
        "full_name": f"owner/repo-{index}",
        "html_url": f"https://github.com/owner/repo-{index}",
        "description": f"Repository {index}",
        "stars": 100 + index,
        "language": "Python",
        "updated_at": "2026-08-01T00:00:00Z",
    }


def _profile(index: int, task_match: str) -> RepoProfile:
    return RepoProfile(
        full_name=f"owner/repo-{index}",
        task_match=task_match,
        framework=["PyTorch"],
        framework_evidence=Evidence(
            source="README.md", reason="README identifies PyTorch."
        ),
        has_training_code=True,
        training_entry="tools/train.py",
        has_training_code_evidence=Evidence(
            source="tools/train.py", reason="Explicit training entry."
        ),
        has_custom_dataset_support=True,
        has_custom_dataset_support_evidence=Evidence(
            source="README.md", reason="README documents custom datasets."
        ),
        has_pretrained_weights=True,
        has_pretrained_weights_evidence=Evidence(
            source="README.md", reason="README links model weights."
        ),
        hardware_notes="GPU recommended",
        hardware_notes_evidence=Evidence(
            source="README.md", reason="README mentions GPU usage."
        ),
        strengths=["Complete training workflow"],
        weaknesses=["Hardware model is not specified"],
    )


def test_rank_repositories_sorts_scores_and_formats_required_fields():
    repositories = [_metadata(1), _metadata(2), _metadata(3)]
    analyses = [
        {"full_name": "owner/repo-1", "profile": _profile(1, "low"), "error": None},
        {"full_name": "owner/repo-2", "profile": _profile(2, "exact"), "error": None},
        {"full_name": "owner/repo-3", "profile": _profile(3, "high"), "error": None},
    ]

    results = rank_repositories(TaskSpec(), repositories, analyses, now=NOW)

    assert [result["full_name"] for result in results] == [
        "owner/repo-2",
        "owner/repo-3",
        "owner/repo-1",
    ]
    assert [result["rank"] for result in results] == [1, 2, 3]
    first = results[0]
    assert first["html_url"] == "https://github.com/owner/repo-2"
    assert first["description"] == "Repository 2"
    assert first["stars"] == 102
    assert first["language"] == "Python"
    assert isinstance(first["final_score"], int)
    assert set(first["score_breakdown"]) == {
        "task_match",
        "completeness",
        "must_have",
        "maintenance",
        "documentation",
        "community",
        "environment",
    }
    assert first["repo_profile"]["full_name"] == "owner/repo-2"
    assert first["strengths"] == ["Complete training workflow"]
    assert first["weaknesses"] == ["Hardware model is not specified"]
    assert set(first["evidence"]) == {
        "has_training_code",
        "has_custom_dataset_support",
        "has_pretrained_weights",
        "framework",
        "hardware_notes",
    }
    assert first["evidence"]["has_training_code"]["source"] == "tools/train.py"


def test_rank_repositories_returns_only_top_five_and_keeps_ties_stable():
    repositories = [_metadata(index) for index in range(7)]
    analyses = [
        {
            "full_name": repository["full_name"],
            "profile": _profile(index, "high"),
            "error": None,
        }
        for index, repository in enumerate(repositories)
    ]

    results = rank_repositories(TaskSpec(), repositories, analyses, now=NOW)

    assert len(results) == 5
    assert [result["full_name"] for result in results] == [
        f"owner/repo-{index}" for index in range(5)
    ]


def test_rank_repositories_skips_failed_missing_and_invalid_profiles():
    repositories = [_metadata(1), _metadata(2), _metadata(3)]
    analyses = [
        {"full_name": "owner/repo-1", "profile": _profile(1, "high"), "error": None},
        {"full_name": "owner/repo-2", "profile": None, "error": "analysis failed"},
        {"full_name": "owner/repo-3", "profile": {"task_match": "exact"}, "error": None},
        {"full_name": "owner/missing", "profile": _profile(9, "exact"), "error": None},
    ]

    results = rank_repositories(TaskSpec(), repositories, analyses, now=NOW)

    assert [result["full_name"] for result in results] == ["owner/repo-1"]
