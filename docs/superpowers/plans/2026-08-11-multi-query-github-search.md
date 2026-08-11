# Multi-Query GitHub Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend helper that searches up to five GitHub queries, merges their repository results, and deduplicates by `full_name`.

**Architecture:** Keep `search_repositories` as the single-query API boundary. Add a small sequential wrapper in the same module that slices input to five queries, calls the existing function, and stores the first occurrence of each repository in insertion order.

**Tech Stack:** Python 3, FastAPI backend module, pytest, pytest monkeypatch

---

### Task 1: Add and verify `search_multiple_queries`

**Files:**
- Modify: `backend/tests/test_github_client.py`
- Modify: `backend/github_client.py`

- [x] **Step 1: Write failing behavior tests**

Append tests that replace `search_repositories` with a deterministic fake:

```python
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
```

- [x] **Step 2: Run focused tests and verify red**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_github_client.py -q
```

Expected: the new tests fail because `github_client.search_multiple_queries` does not exist.

- [x] **Step 3: Add the minimal implementation**

Add to `backend/github_client.py` without changing `search_repositories`:

```python
MAX_SEARCH_QUERIES = 5


def search_multiple_queries(queries: list[str]) -> list[dict[str, Any]]:
    repositories_by_full_name: dict[str, dict[str, Any]] = {}

    for query in queries[:MAX_SEARCH_QUERIES]:
        for repository in search_repositories(query):
            full_name = repository.get("full_name")
            if full_name not in repositories_by_full_name:
                repositories_by_full_name[full_name] = repository

    return list(repositories_by_full_name.values())
```

- [x] **Step 4: Run focused tests and verify green**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_github_client.py -q
```

Expected: all GitHub client tests pass.

- [x] **Step 5: Run the complete backend test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all backend tests pass with no failures.

- [x] **Step 6: Record repository limitation**

No commit is created because `github-task-search` is not inside a Git repository.
