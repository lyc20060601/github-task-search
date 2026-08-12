import pytest

import batch_analyzer
from repo_profile import RepoProfile
from task_parser import TaskSpec


def test_analyze_repositories_processes_three_in_order_and_keeps_failures(monkeypatch):
    calls = []

    def fake_get_repository_details(full_name):
        calls.append(("details", full_name))
        if full_name == "owner/b":
            raise RuntimeError("GitHub unavailable")
        return {"full_name": full_name, "readme": "", "root_files": [], "common_paths": {}}

    def fake_analyze_repository(task_spec, details):
        calls.append(("analyze", details["full_name"]))
        return RepoProfile(full_name=details["full_name"])

    monkeypatch.setattr(batch_analyzer, "get_repository_details", fake_get_repository_details)
    monkeypatch.setattr(batch_analyzer, "analyze_repository", fake_analyze_repository)

    results = batch_analyzer.analyze_repositories(
        [{"full_name": "owner/a"}, {"full_name": "owner/b"}, {"full_name": "owner/c"}],
        TaskSpec(task="semantic segmentation"),
    )

    assert [result["full_name"] for result in results] == [
        "owner/a",
        "owner/b",
        "owner/c",
    ]
    assert isinstance(results[0]["profile"], RepoProfile)
    assert results[0]["error"] is None
    assert results[1]["profile"] is None
    assert results[1]["error"] == "GitHub unavailable"
    assert isinstance(results[2]["profile"], RepoProfile)
    assert calls == [
        ("details", "owner/a"),
        ("analyze", "owner/a"),
        ("details", "owner/b"),
        ("details", "owner/c"),
        ("analyze", "owner/c"),
    ]


def test_analyze_repositories_only_processes_first_ten(monkeypatch):
    processed = []

    monkeypatch.setattr(
        batch_analyzer,
        "get_repository_details",
        lambda full_name: processed.append(full_name)
        or {"full_name": full_name, "readme": "", "root_files": [], "common_paths": {}},
    )
    monkeypatch.setattr(
        batch_analyzer,
        "analyze_repository",
        lambda task_spec, details: RepoProfile(full_name=details["full_name"]),
    )

    repositories = [{"full_name": f"owner/{index}"} for index in range(12)]
    results = batch_analyzer.analyze_repositories(repositories, TaskSpec())

    assert len(results) == 10
    assert processed == [f"owner/{index}" for index in range(10)]


def test_analyze_repositories_records_invalid_repository_entry(monkeypatch):
    monkeypatch.setattr(batch_analyzer, "get_repository_details", pytest.fail)

    results = batch_analyzer.analyze_repositories([{}], TaskSpec())

    assert results == [
        {
            "full_name": None,
            "profile": None,
            "error": "repository result is missing full_name",
        }
    ]
