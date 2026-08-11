from datetime import datetime, timezone

import httpx
import pytest

import github_client


def test_search_repositories_maps_first_ten_results(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    items = [
        {
            "name": f"repo-{index}",
            "full_name": f"owner/repo-{index}",
            "description": f"Repository {index}",
            "html_url": f"https://github.com/owner/repo-{index}",
            "stargazers_count": 100 - index,
            "language": "Python",
            "updated_at": "2026-08-11T00:00:00Z",
        }
        for index in range(12)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search/repositories"
        assert request.url.params["q"] == "semantic segmentation"
        assert request.url.params["per_page"] == "10"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"items": items})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    results = github_client.search_repositories("semantic segmentation", client=client)

    assert len(results) == 10
    assert results[0] == {
        "name": "repo-0",
        "full_name": "owner/repo-0",
        "description": "Repository 0",
        "html_url": "https://github.com/owner/repo-0",
        "stars": 100,
        "language": "Python",
        "updated_at": "2026-08-11T00:00:00Z",
    }


def test_search_repositories_requires_github_token(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(github_client, "load_dotenv", lambda: None)

    with pytest.raises(github_client.GitHubSearchError, match="GITHUB_TOKEN"):
        github_client.search_repositories("fastapi")


def test_search_repositories_wraps_request_errors(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(github_client.GitHubSearchError, match="GitHub repository search failed"):
        github_client.search_repositories("fastapi", client=client)


def test_search_multiple_queries_uses_first_five_and_deduplicates(monkeypatch) -> None:
    calls = []
    results_by_query = {
        "query-1": [
            {"full_name": "owner/shared", "name": "shared-first"},
            {"full_name": "owner/one", "name": "one"},
        ],
        "query-2": [
            {"full_name": "owner/shared", "name": "shared-later"},
            {"full_name": "owner/two", "name": "two"},
        ],
        "query-3": [],
        "query-4": [],
        "query-5": [{"full_name": "owner/five", "name": "five"}],
    }

    def fake_search(query):
        calls.append(query)
        return results_by_query[query]

    monkeypatch.setattr(github_client, "search_repositories", fake_search)

    results = github_client.search_multiple_queries(
        ["query-1", "query-2", "query-3", "query-4", "query-5", "query-6"]
    )

    assert calls == ["query-1", "query-2", "query-3", "query-4", "query-5"]
    assert [result["full_name"] for result in results] == [
        "owner/shared",
        "owner/one",
        "owner/two",
        "owner/five",
    ]
    assert results[0]["name"] == "shared-first"


def test_search_multiple_queries_returns_empty_for_empty_input(monkeypatch) -> None:
    def unexpected_search(query):
        raise AssertionError(f"unexpected search: {query}")

    monkeypatch.setattr(github_client, "search_repositories", unexpected_search)

    assert github_client.search_multiple_queries([]) == []


def test_search_multiple_queries_propagates_search_errors(monkeypatch) -> None:
    error = github_client.GitHubSearchError("search failed")

    def failing_search(query):
        raise error

    monkeypatch.setattr(github_client, "search_repositories", failing_search)

    with pytest.raises(github_client.GitHubSearchError) as exc_info:
        github_client.search_multiple_queries(["query-1"])

    assert exc_info.value is error


def test_search_multiple_queries_calculates_preliminary_score(monkeypatch) -> None:
    recent = datetime.now(timezone.utc).isoformat()
    repository = {
        "full_name": "owner/scored",
        "stars": 1_000,
        "updated_at": recent,
        "description": "Semantic segmentation toolkit",
    }
    monkeypatch.setattr(
        github_client, "search_repositories", lambda query: [repository]
    )

    results = github_client.search_multiple_queries(
        ["semantic segmentation pytorch"]
    )

    assert results[0]["preliminary_score"] == 1_110


def test_multiple_query_matches_dominate_secondary_scores(monkeypatch) -> None:
    recent = datetime.now(timezone.utc).isoformat()
    shared = {
        "full_name": "owner/shared",
        "stars": 0,
        "updated_at": "2000-01-01T00:00:00Z",
        "description": None,
    }
    popular = {
        "full_name": "owner/popular",
        "stars": 10_000,
        "updated_at": recent,
        "description": "Semantic segmentation pytorch",
    }
    results_by_query = {
        "semantic segmentation pytorch": [popular, shared],
        "aerial segmentation": [shared],
    }
    monkeypatch.setattr(
        github_client,
        "search_repositories",
        lambda query: results_by_query[query],
    )

    results = github_client.search_multiple_queries(list(results_by_query))

    assert [result["full_name"] for result in results] == [
        "owner/shared",
        "owner/popular",
    ]


def test_duplicate_query_strings_count_as_one_match(monkeypatch) -> None:
    repository = {
        "full_name": "owner/repo",
        "stars": 0,
        "updated_at": "2000-01-01T00:00:00Z",
        "description": None,
    }
    monkeypatch.setattr(
        github_client, "search_repositories", lambda query: [repository]
    )

    results = github_client.search_multiple_queries(
        [" semantic segmentation ", "SEMANTIC SEGMENTATION"]
    )

    assert results[0]["preliminary_score"] == 1_000


def test_search_multiple_queries_returns_top_twenty(monkeypatch) -> None:
    repositories = [
        {
            "full_name": f"owner/repo-{index}",
            "stars": 0,
            "updated_at": "2000-01-01T00:00:00Z",
            "description": None,
        }
        for index in range(25)
    ]
    results_by_query = {
        "query-one": repositories[:10],
        "query-two": repositories[10:20],
        "query-three": repositories[20:],
    }
    monkeypatch.setattr(
        github_client,
        "search_repositories",
        lambda query: results_by_query[query],
    )

    results = github_client.search_multiple_queries(list(results_by_query))

    assert len(results) == 20
    assert [result["full_name"] for result in results] == [
        f"owner/repo-{index}" for index in range(20)
    ]
