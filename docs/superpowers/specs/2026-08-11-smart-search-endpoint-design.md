# Smart Search Endpoint Design

## Scope

Add `POST /smart-search` to the existing FastAPI application. Keep `POST
/search` unchanged. Do not modify the frontend or add README analysis or deeper
AI repository scoring.

## Data Flow

The endpoint accepts the existing `SearchRequest` shape, calls `parse_task`,
passes the resulting `TaskSpec` to `generate_queries`, and passes those queries
to `search_multiple_queries`. The response contains the serialized TaskSpec,
the generated queries, and the ranked repository results.

```json
{
  "task_spec": {},
  "generated_queries": [],
  "repositories": []
}
```

`generate_queries` remains responsible for the five-query limit.
`search_multiple_queries` remains responsible for merging, deduplication,
preliminary scoring, descending ranking, and the 20-result limit.

## Errors

Convert `TaskParserError` and `GitHubSearchError` to HTTP 502 responses with the
existing exception message in `detail`. Missing request fields continue to use
FastAPI's HTTP 422 validation. An empty generated-query list is valid and
returns an empty repository list.

## Testing

Use FastAPI `TestClient` and monkeypatch the three orchestration dependencies to
prove call order, exact response structure, parser failure, GitHub failure,
request validation, and preservation of the existing `/search` behavior. After
the full automated suite passes, restart the backend and perform one real HTTP
request using the configured DeepSeek and GitHub credentials.
