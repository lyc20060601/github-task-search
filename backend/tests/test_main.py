from fastapi.testclient import TestClient
import pytest

import main
from github_client import GitHubSearchError
from repo_profile import RepoProfile
from task_parser import TaskParserError, TaskSpec
from runtime.validation_jobs import (
    InvalidValidationJob,
    ValidationBusy,
    ValidationJob,
    ValidationTimedOut,
    ValidationUnavailable,
)
from runtime_report import RuntimeReport


client = TestClient(main.app)


def test_root_returns_api_message() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "GitHub Task Search API"}


def test_vercel_backend_prefix_returns_api_message() -> None:
    response = client.get("/api/backend/")

    assert response.status_code == 200
    assert response.json() == {"message": "GitHub Task Search API"}


def test_search_returns_github_repositories(monkeypatch) -> None:
    repositories = [
        {
            "name": "segmentation-project",
            "full_name": "owner/segmentation-project",
            "description": "A semantic segmentation project",
            "html_url": "https://github.com/owner/segmentation-project",
            "stars": 123,
            "language": "Python",
            "updated_at": "2026-08-11T00:00:00Z",
        }
    ]
    received_queries = []

    def fake_search_repositories(query: str):
        received_queries.append(query)
        return repositories

    monkeypatch.setattr(main, "search_repositories", fake_search_repositories)

    response = client.post("/search", json={"query": "semantic segmentation"})

    assert response.status_code == 200
    assert response.json() == repositories
    assert received_queries == ["semantic segmentation"]


def test_search_returns_bad_gateway_when_github_search_fails(monkeypatch) -> None:
    def failing_search_repositories(query: str):
        raise GitHubSearchError("GitHub repository search failed")

    monkeypatch.setattr(main, "search_repositories", failing_search_repositories)

    response = client.post("/search", json={"query": "semantic segmentation"})

    assert response.status_code == 502
    assert response.json() == {"detail": "GitHub repository search failed"}


def test_search_requires_query() -> None:
    response = client.post("/search", json={})

    assert response.status_code == 422


def test_search_allows_local_frontend_origin() -> None:
    response = client.options(
        "/search",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_allowed_origins_include_normalized_production_origin(monkeypatch) -> None:
    monkeypatch.setenv(
        "FRONTEND_ORIGIN",
        "https://github-task-search.vercel.app/",
    )

    assert main.get_allowed_origins() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://github-task-search.vercel.app",
    ]


def test_smart_search_orchestrates_task_search(monkeypatch) -> None:
    task_spec = TaskSpec(
        task="semantic segmentation",
        domain=["drone"],
        framework=["PyTorch"],
    )
    queries = ["drone semantic segmentation pytorch"]
    repositories = [
        {
            "name": "project",
            "full_name": "owner/project",
            "description": "Semantic segmentation",
            "html_url": "https://github.com/owner/project",
            "stars": 100,
            "language": "Python",
            "updated_at": "2026-08-11T00:00:00Z",
            "preliminary_score": 1_075,
        }
    ]
    calls = []

    def fake_parse(query):
        calls.append(("parse", query))
        return task_spec

    def fake_generate(received_spec):
        calls.append(("generate", received_spec))
        return queries

    def fake_search(received_queries):
        calls.append(("search", received_queries))
        return repositories

    monkeypatch.setattr(main, "parse_task", fake_parse)
    monkeypatch.setattr(main, "generate_queries", fake_generate)
    monkeypatch.setattr(main, "search_multiple_queries", fake_search)

    response = client.post("/smart-search", json={"query": "找无人机分割项目"})

    assert response.status_code == 200
    assert response.json() == {
        "task_spec": task_spec.model_dump(),
        "generated_queries": queries,
        "repositories": repositories,
    }
    assert calls == [
        ("parse", "找无人机分割项目"),
        ("generate", task_spec),
        ("search", queries),
    ]


def test_smart_search_allows_empty_generated_queries(monkeypatch) -> None:
    task_spec = TaskSpec()
    monkeypatch.setattr(main, "parse_task", lambda query: task_spec)
    monkeypatch.setattr(main, "generate_queries", lambda received_spec: [])

    def fake_search(queries):
        assert queries == []
        return []

    monkeypatch.setattr(main, "search_multiple_queries", fake_search)

    response = client.post("/smart-search", json={"query": "找项目"})

    assert response.status_code == 200
    assert response.json() == {
        "task_spec": task_spec.model_dump(),
        "generated_queries": [],
        "repositories": [],
    }


def test_smart_search_returns_bad_gateway_when_task_parser_fails(monkeypatch) -> None:
    def failing_parse(query):
        raise TaskParserError("LLM task parsing request failed")

    monkeypatch.setattr(main, "parse_task", failing_parse)

    response = client.post("/smart-search", json={"query": "找项目"})

    assert response.status_code == 502
    assert response.json() == {"detail": "LLM task parsing request failed"}


def test_smart_search_returns_bad_gateway_when_github_search_fails(monkeypatch) -> None:
    monkeypatch.setattr(main, "parse_task", lambda query: TaskSpec(task="search"))
    monkeypatch.setattr(main, "generate_queries", lambda task_spec: ["search"])

    def failing_search(queries):
        raise GitHubSearchError("GitHub repository search failed")

    monkeypatch.setattr(main, "search_multiple_queries", failing_search)

    response = client.post("/smart-search", json={"query": "找项目"})

    assert response.status_code == 502
    assert response.json() == {"detail": "GitHub repository search failed"}


def test_smart_search_requires_query() -> None:
    response = client.post("/smart-search", json={})

    assert response.status_code == 422


def test_recommend_search_orchestrates_top_ten_and_returns_recommendations(
    monkeypatch,
) -> None:
    task_spec = TaskSpec(task="semantic segmentation", framework=["PyTorch"])
    queries = ["semantic segmentation pytorch"]
    repositories = [
        {
            "full_name": f"owner/repo-{index}",
            "html_url": f"https://github.com/owner/repo-{index}",
            "description": f"Repository {index}",
            "stars": index,
            "language": "Python",
            "updated_at": "2026-08-11T00:00:00Z",
        }
        for index in range(12)
    ]
    analyses = [
        {
            "full_name": repository["full_name"],
            "profile": RepoProfile(full_name=repository["full_name"]),
            "error": None,
        }
        for repository in repositories[:9]
    ] + [
        {
            "full_name": repositories[9]["full_name"],
            "profile": None,
            "error": "analysis failed",
        }
    ]
    recommendations = [
        {
            "rank": 1,
            "full_name": "owner/repo-0",
            "final_score": 90,
        }
    ]
    calls = []

    monkeypatch.setattr(main, "parse_task", lambda query: task_spec)
    monkeypatch.setattr(main, "generate_queries", lambda spec: queries)
    monkeypatch.setattr(main, "search_multiple_queries", lambda values: repositories)

    def fake_analyze(candidates, received_spec):
        calls.append(("analyze", candidates, received_spec))
        return analyses

    def fake_rank(received_spec, candidates, received_analyses):
        calls.append(("rank", received_spec, candidates, received_analyses))
        return recommendations

    monkeypatch.setattr(main, "analyze_repositories", fake_analyze)
    monkeypatch.setattr(main, "rank_repositories", fake_rank)

    response = client.post("/recommend-search", json={"query": "find a project"})

    assert response.status_code == 200
    assert response.json() == {
        "task_spec": task_spec.model_dump(),
        "generated_queries": queries,
        "candidate_count": 12,
        "analyzed_count": 9,
        "recommendations": recommendations,
    }
    assert calls[0] == ("analyze", repositories[:10], task_spec)
    assert calls[1] == ("rank", task_spec, repositories[:10], analyses)


def test_recommend_search_allows_all_repository_analyses_to_fail(monkeypatch):
    task_spec = TaskSpec(task="semantic segmentation")
    repositories = [{"full_name": "owner/repo"}]
    analyses = [
        {"full_name": "owner/repo", "profile": None, "error": "README unavailable"}
    ]

    monkeypatch.setattr(main, "parse_task", lambda query: task_spec)
    monkeypatch.setattr(main, "generate_queries", lambda spec: ["segmentation"])
    monkeypatch.setattr(main, "search_multiple_queries", lambda queries: repositories)
    monkeypatch.setattr(main, "analyze_repositories", lambda candidates, spec: analyses)
    monkeypatch.setattr(main, "rank_repositories", lambda spec, candidates, values: [])

    response = client.post("/recommend-search", json={"query": "find a project"})

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 1
    assert response.json()["analyzed_count"] == 0
    assert response.json()["recommendations"] == []


def test_recommend_search_returns_bad_gateway_for_pipeline_failure(monkeypatch):
    def failing_parse(query):
        raise TaskParserError("LLM task parsing request failed")

    monkeypatch.setattr(main, "parse_task", failing_parse)

    response = client.post("/recommend-search", json={"query": "find a project"})

    assert response.status_code == 502
    assert response.json() == {"detail": "LLM task parsing request failed"}


def test_recommend_search_requires_query() -> None:
    response = client.post("/recommend-search", json={})

    assert response.status_code == 422


def test_validate_repository_is_an_independent_user_triggered_endpoint(monkeypatch):
    received = []
    report = RuntimeReport(
        full_name="owner/repository",
        clone_status="success",
        runtime_score=10,
        runtime_breakdown={"clone": 10},
        runtime_status="unknown",
    )

    def fake_validate(full_name):
        received.append(full_name)
        return report

    monkeypatch.setattr(main, "validate_requested_repository", fake_validate)

    response = client.post(
        "/validate-repository", json={"full_name": "owner/repository"}
    )

    assert response.status_code == 200
    assert response.json() == report.model_dump()
    assert received == ["owner/repository"]


def test_validate_repository_requires_full_name():
    response = client.post("/validate-repository", json={})

    assert response.status_code == 422


def test_validate_repository_declares_runtime_report_response_model():
    schema = client.get("/openapi.json").json()

    response_schema = schema["paths"]["/validate-repository"]["post"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert response_schema["$ref"] == "#/components/schemas/RuntimeReport"


def test_validate_repository_rejects_arbitrary_url():
    response = client.post(
        "/validate-repository",
        json={"full_name": "https://github.com/owner/repository"},
    )
    assert response.status_code == 422


def test_validation_status_is_non_sensitive(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_validation_status",
        lambda: {"mode": "worker", "worker_ready": True},
    )
    response = client.get("/validation-status")
    assert response.status_code == 200
    assert response.json() == {"mode": "worker", "worker_ready": True}


def test_internal_worker_poll_requires_authentication(monkeypatch):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "worker-token")
    response = client.post("/internal/validation/jobs/next")
    assert response.status_code == 401


def test_internal_worker_poll_returns_job(monkeypatch):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "worker-token")
    touched = []
    monkeypatch.setattr(main.COORDINATOR, "touch_worker", lambda: touched.append(True))
    monkeypatch.setattr(
        main.COORDINATOR,
        "claim_next",
        lambda wait_seconds: ValidationJob(id="job-1", full_name="owner/repository"),
    )
    response = client.post(
        "/internal/validation/jobs/next",
        headers={"Authorization": "Bearer worker-token"},
    )
    assert response.status_code == 200
    assert response.json() == {"id": "job-1", "full_name": "owner/repository"}
    assert touched == [True]


def test_internal_worker_idle_poll_returns_no_content(monkeypatch):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "worker-token")
    monkeypatch.setattr(main.COORDINATOR, "touch_worker", lambda: None)
    monkeypatch.setattr(
        main.COORDINATOR,
        "claim_next",
        lambda wait_seconds: None,
    )
    response = client.post(
        "/internal/validation/jobs/next",
        headers={"Authorization": "Bearer worker-token"},
    )
    assert response.status_code == 204
    assert response.content == b""


def test_internal_worker_accepts_matching_result(monkeypatch):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "worker-token")
    completed = []
    monkeypatch.setattr(
        main.COORDINATOR,
        "complete",
        lambda job_id, report: completed.append((job_id, report.full_name)),
    )
    response = client.post(
        "/internal/validation/jobs/job-1/result",
        headers={"Authorization": "Bearer worker-token"},
        json={"report": RuntimeReport(full_name="owner/repository").model_dump()},
    )
    assert response.status_code == 204
    assert completed == [("job-1", "owner/repository")]


def test_internal_worker_result_rejects_extra_report_fields(monkeypatch):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "worker-token")
    report = RuntimeReport(full_name="owner/repository").model_dump()
    report["command"] = "whoami"
    response = client.post(
        "/internal/validation/jobs/job-1/result",
        headers={"Authorization": "Bearer worker-token"},
        json={"report": report},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
    ],
)
def test_internal_worker_result_authenticates_before_parsing_malformed_body(
    monkeypatch,
    headers,
):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "worker-token")

    response = client.post(
        "/internal/validation/jobs/job-1/result",
        headers=headers,
        content=b"not-json",
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid worker credentials"}


def test_internal_worker_result_rejects_oversized_body(monkeypatch):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "worker-token")
    oversized_body = b'{"report":"' + (b"x" * (256 * 1024)) + b'"}'

    response = client.post(
        "/internal/validation/jobs/job-1/result",
        headers={"Authorization": "Bearer worker-token"},
        content=oversized_body,
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "validation result body is too large"}


def test_internal_worker_result_rejects_stale_job(monkeypatch):
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "worker-token")

    def reject(job_id, report):
        raise InvalidValidationJob("unknown or expired validation job")

    monkeypatch.setattr(main.COORDINATOR, "complete", reject)
    response = client.post(
        "/internal/validation/jobs/stale/result",
        headers={"Authorization": "Bearer worker-token"},
        json={"report": RuntimeReport(full_name="owner/repository").model_dump()},
    )
    assert response.status_code == 409


def test_internal_worker_routes_are_hidden_from_openapi():
    paths = client.get("/openapi.json").json()["paths"]
    assert "/internal/validation/jobs/next" not in paths
    assert "/internal/validation/jobs/{job_id}/result" not in paths


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (ValidationBusy("busy"), 429),
        (ValidationUnavailable("unavailable"), 503),
        (ValidationTimedOut("timed out"), 504),
    ],
)
def test_validate_repository_maps_worker_failures(monkeypatch, error, status_code):
    def fail(full_name):
        raise error

    monkeypatch.setattr(main, "validate_requested_repository", fail)
    response = client.post(
        "/validate-repository",
        json={"full_name": "owner/repository"},
    )
    assert response.status_code == status_code
