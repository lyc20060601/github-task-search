from datetime import datetime, timezone

from ranking.deep_score import calculate_repository_score
from repo_profile import RepoProfile
from task_parser import TaskSpec


NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _strong_profile() -> RepoProfile:
    return RepoProfile(
        full_name="owner/repo",
        framework=["PyTorch"],
        tasks=["semantic segmentation"],
        domains=["aerial imagery"],
        task_match="exact",
        has_training_code=True,
        has_configs=True,
        has_dataset_code=True,
        has_custom_dataset_support=True,
        has_pretrained_weights=True,
        has_requirements=True,
        has_environment_file=True,
        has_docker=True,
        documentation_quality="excellent",
    )


def test_calculate_repository_score_returns_capped_seven_part_breakdown():
    result = calculate_repository_score(
        TaskSpec(
            task="semantic segmentation",
            framework=["PyTorch"],
            must_have=["custom dataset"],
        ),
        _strong_profile(),
        {"stars": 50_000, "updated_at": "2026-08-01T12:00:00Z"},
        now=NOW,
    )

    assert result == {
        "final_score": 100,
        "score_breakdown": {
            "task_match": 30,
            "completeness": 20,
            "must_have": 20,
            "maintenance": 10,
            "documentation": 10,
            "community": 5,
            "environment": 5,
        },
    }


def test_explicitly_unsupported_must_have_loses_the_mandatory_points():
    task_spec = TaskSpec(must_have=["must support custom dataset"])
    supported = _strong_profile()
    unsupported = supported.model_copy(
        update={"has_custom_dataset_support": False}
    )
    metadata = {"stars": 100, "updated_at": "2026-08-01T12:00:00Z"}

    supported_score = calculate_repository_score(
        task_spec, supported, metadata, now=NOW
    )
    unsupported_score = calculate_repository_score(
        task_spec, unsupported, metadata, now=NOW
    )

    assert supported_score["score_breakdown"]["must_have"] == 20
    assert unsupported_score["score_breakdown"]["must_have"] == 0
    assert supported_score["final_score"] - unsupported_score["final_score"] >= 20


def test_stars_are_limited_to_five_points():
    low = calculate_repository_score(
        TaskSpec(), RepoProfile(), {"stars": 0}, now=NOW
    )
    high = calculate_repository_score(
        TaskSpec(), RepoProfile(), {"stars": 10_000_000}, now=NOW
    )

    assert low["score_breakdown"]["community"] == 0
    assert high["score_breakdown"]["community"] == 5
    assert high["final_score"] - low["final_score"] == 5


def test_unknown_values_receive_conservative_scores_without_errors():
    result = calculate_repository_score(
        TaskSpec(must_have=["custom dataset"]),
        RepoProfile(task_match="unknown", documentation_quality="unknown"),
        {"stars": "invalid", "updated_at": "not-a-date"},
        now=NOW,
    )

    breakdown = result["score_breakdown"]
    assert breakdown["must_have"] == 5
    assert breakdown["maintenance"] == 0
    assert breakdown["documentation"] == 2
    assert breakdown["community"] == 0
    assert 0 <= result["final_score"] <= 100
