# Smart Search Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FastAPI endpoint that orchestrates task parsing, query planning, ranked multi-query GitHub search, and a structured response.

**Architecture:** Keep orchestration in `backend/main.py` because it only coordinates three existing modules. Reuse `SearchRequest`, convert known external-service failures to HTTP 502, and leave `/search` unchanged.

**Tech Stack:** Python 3, FastAPI, Pydantic, pytest, FastAPI TestClient

---

### Task 1: Define the endpoint contract with failing tests

**Files:**
- Modify: `backend/tests/test_main.py`

- [x] **Step 1: Add the successful orchestration test**

```python
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
```

- [x] **Step 2: Add error and request validation tests**

```python
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
```

- [x] **Step 3: Run endpoint tests and verify red**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_main.py -q
```

Expected: the new requests return HTTP 404 because `/smart-search` does not
exist.

### Task 2: Implement the endpoint

**Files:**
- Modify: `backend/main.py`

- [x] **Step 1: Import existing orchestration dependencies**

```python
from github_client import (
    GitHubSearchError,
    search_multiple_queries,
    search_repositories,
)
from query_planner import generate_queries
from task_parser import TaskParserError, parse_task
```

- [x] **Step 2: Add the smart endpoint**

```python
@app.post("/smart-search")
def smart_search(request: SearchRequest) -> dict[str, Any]:
    try:
        task_spec = parse_task(request.query)
        generated_queries = generate_queries(task_spec)
        repositories = search_multiple_queries(generated_queries)
    except (TaskParserError, GitHubSearchError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "task_spec": task_spec.model_dump(),
        "generated_queries": generated_queries,
        "repositories": repositories,
    }
```

- [x] **Step 3: Run endpoint tests and verify green**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_main.py -q
```

Expected: all endpoint tests pass.

- [x] **Step 4: Run the complete backend test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all backend tests pass.

### Task 3: Verify the real service path

**Files:**
- No code changes

- [x] **Step 1: Restart the backend on port 8000**

Start the updated FastAPI application with external network access so it can
reach DeepSeek and GitHub.

- [x] **Step 2: Send a real smart-search request**

Post a Chinese natural-language drone semantic-segmentation request to
`http://127.0.0.1:8000/smart-search` and verify HTTP 200, a structured TaskSpec,
one to five generated queries, no more than 20 repositories, descending
`preliminary_score` values, and unique `full_name` values.

- [x] **Step 3: Record repository limitation**

Do not create a Git commit because the project is not inside a Git repository
and the user does not require Git commits.
