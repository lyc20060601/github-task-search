# Multi-Query GitHub Search Design

## Scope

Add `search_multiple_queries(queries)` to `backend/github_client.py`. Keep the
existing `search_repositories` function unchanged. Do not modify the frontend,
README analysis, AI integration, or scoring.

## Behavior

- Accept an iterable of GitHub repository search query strings.
- Process only the first five queries and ignore any remaining queries.
- Call `search_repositories(query)` once for each processed query. Each call
  continues to return at most ten repositories.
- Merge results in query order and repository result order.
- Deduplicate repositories by `full_name`; retain the first occurrence and its
  data.
- Return an empty list for empty input.
- Propagate `GitHubSearchError` if any individual search fails, rather than
  returning incomplete results.

## Testing

Add focused tests to `backend/tests/test_github_client.py` that verify:

- queries are processed sequentially and only the first five are used;
- duplicate `full_name` values are removed while first-occurrence order is kept;
- empty input returns an empty list without making a search call;
- failures from `search_repositories` propagate unchanged.
