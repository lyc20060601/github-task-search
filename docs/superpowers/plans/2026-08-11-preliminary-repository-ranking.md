# Preliminary Repository Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score deduplicated multi-query GitHub results with transparent deterministic rules, sort descending, and return the top 20.

**Architecture:** Add focused keyword, star, recency, and total-score helpers to `backend/github_client.py`. Extend `search_multiple_queries` to track distinct normalized query hits per `full_name`, score copied repository payloads, and stably sort and limit results.

**Tech Stack:** Python 3, standard-library `datetime` and `re`, pytest, pytest monkeypatch

---

### Task 1: Define ranking behavior with failing tests

**Files:**
- Modify: `backend/tests/test_github_client.py`

- [x] **Step 1: Add tests for score components and ranking dominance**

Add integration-style tests with deterministic fakes for `search_repositories`.
Assert that one recent 1,000-star repository with two description keyword hits
scores 1,110 for one query match, and that a repository found by two distinct
queries outranks a 10,000-star recent keyword-matching repository found once.

```python
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
```

- [x] **Step 2: Add tests for distinct query strings and Top 20**

Search the same normalized query twice and assert the repository receives only
one 1,000-point query-match contribution. Return 25 unique repositories across
three queries and assert only the first 20 ranked results are returned.

```python
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
```

- [x] **Step 3: Run focused tests and verify red**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_github_client.py -q
```

Expected: new assertions fail because results do not contain
`preliminary_score`, are not score-sorted, and are not limited to 20.

### Task 2: Implement readable deterministic scoring

**Files:**
- Modify: `backend/github_client.py`

- [x] **Step 1: Add score constants and helpers**

Add constants for query-match weight, star thresholds, recency windows,
description keyword weight and cap, plus helpers that extract keywords, parse
dates safely, and return integer component scores.

```python
QUERY_MATCH_WEIGHT = 1_000
DESCRIPTION_KEYWORD_WEIGHT = 5
MAX_DESCRIPTION_KEYWORD_MATCHES = 5
MAX_MULTI_QUERY_RESULTS = 20
RECENT_UPDATE_DAYS = 180
ACTIVE_UPDATE_DAYS = 365
QUERY_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]*", re.IGNORECASE)
QUERY_STOP_WORDS = frozenset({"and", "for", "from", "the", "with"})


def _extract_keywords(texts: list[str]) -> set[str]:
    return {
        token.casefold()
        for text in texts
        for token in QUERY_TOKEN_PATTERN.findall(text)
        if len(token) >= 3 and token.casefold() not in QUERY_STOP_WORDS
    }


def _star_score(stars: Any) -> int:
    try:
        star_count = int(stars or 0)
    except (TypeError, ValueError):
        return 0
    if star_count >= 10_000:
        return 100
    if star_count >= 1_000:
        return 70
    if star_count >= 100:
        return 40
    if star_count >= 10:
        return 20
    return 0


def _recent_update_score(updated_at: Any, now: datetime) -> int:
    if not isinstance(updated_at, str):
        return 0
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age = now - updated.astimezone(timezone.utc)
    if age <= timedelta(days=RECENT_UPDATE_DAYS):
        return 30
    if age <= timedelta(days=ACTIVE_UPDATE_DAYS):
        return 15
    return 0


def _calculate_preliminary_score(
    repository: dict[str, Any],
    distinct_query_matches: int,
    query_keywords: set[str],
    now: datetime,
) -> int:
    description = repository.get("description") or ""
    description_keywords = _extract_keywords([str(description)])
    keyword_matches = min(
        len(query_keywords & description_keywords),
        MAX_DESCRIPTION_KEYWORD_MATCHES,
    )
    return (
        distinct_query_matches * QUERY_MATCH_WEIGHT
        + _star_score(repository.get("stars"))
        + _recent_update_score(repository.get("updated_at"), now)
        + keyword_matches * DESCRIPTION_KEYWORD_WEIGHT
    )
```

- [x] **Step 2: Extend multi-query aggregation**

For the first five queries, retain the first repository payload for each
`full_name` and collect normalized query strings in a set per repository. After
all calls, copy each repository, calculate `preliminary_score`, stably sort
descending, and slice to 20.

```python
def search_multiple_queries(queries: list[str]) -> list[dict[str, Any]]:
    processed_queries = queries[:MAX_SEARCH_QUERIES]
    query_keywords = _extract_keywords(processed_queries)
    repositories_by_full_name: dict[str, dict[str, Any]] = {}
    matched_queries_by_full_name: dict[str, set[str]] = {}

    for query in processed_queries:
        normalized_query = " ".join(query.split()).casefold()
        for repository in search_repositories(query):
            full_name = repository.get("full_name")
            if full_name not in repositories_by_full_name:
                repositories_by_full_name[full_name] = repository
                matched_queries_by_full_name[full_name] = set()
            matched_queries_by_full_name[full_name].add(normalized_query)

    now = datetime.now(timezone.utc)
    ranked_repositories = []
    for full_name, repository in repositories_by_full_name.items():
        scored_repository = repository.copy()
        scored_repository["preliminary_score"] = _calculate_preliminary_score(
            repository,
            len(matched_queries_by_full_name[full_name]),
            query_keywords,
            now,
        )
        ranked_repositories.append(scored_repository)

    ranked_repositories.sort(
        key=lambda repository: repository["preliminary_score"], reverse=True
    )
    return ranked_repositories[:MAX_MULTI_QUERY_RESULTS]
```

- [x] **Step 3: Run focused tests and verify green**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_github_client.py -q
```

Expected: all GitHub client tests pass.

- [x] **Step 4: Run the complete backend suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all backend tests pass with no failures.

- [x] **Step 5: Record repository limitation**

Do not create a commit because this project is not inside a Git repository and
the user explicitly does not require Git commits.
