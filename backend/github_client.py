import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from dotenv import load_dotenv


GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
MAX_SEARCH_QUERIES = 5
MAX_MULTI_QUERY_RESULTS = 20
QUERY_MATCH_WEIGHT = 1_000
DESCRIPTION_KEYWORD_WEIGHT = 5
MAX_DESCRIPTION_KEYWORD_MATCHES = 5
RECENT_UPDATE_DAYS = 180
ACTIVE_UPDATE_DAYS = 365
QUERY_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]*", re.IGNORECASE)
QUERY_STOP_WORDS = frozenset({"and", "for", "from", "the", "with"})


class GitHubSearchError(RuntimeError):
    """Raised when GitHub repository search cannot be completed."""


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


def search_repositories(
    query: str,
    *,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise GitHubSearchError("GITHUB_TOKEN is not configured")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    should_close_client = client is None
    http_client = client or httpx.Client(timeout=10.0)

    try:
        response = http_client.get(
            GITHUB_SEARCH_URL,
            params={"q": query, "per_page": 10},
            headers=headers,
        )
        response.raise_for_status()
        items = response.json()["items"]
        if not isinstance(items, list):
            raise TypeError("items must be a list")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise GitHubSearchError("GitHub repository search failed") from exc
    finally:
        if should_close_client:
            http_client.close()

    return [
        {
            "name": repository.get("name"),
            "full_name": repository.get("full_name"),
            "description": repository.get("description"),
            "html_url": repository.get("html_url"),
            "stars": repository.get("stargazers_count"),
            "language": repository.get("language"),
            "updated_at": repository.get("updated_at"),
        }
        for repository in items[:10]
    ]


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
