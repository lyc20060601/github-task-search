# Recommend Search Endpoint Design

## Scope

Add `POST /recommend-search` while preserving `/search` and `/smart-search`.
The endpoint orchestrates the existing task parser, query planner, preliminary
GitHub search, bounded batch analyzer, deterministic score, and final Top 5
formatter. The frontend is unchanged.

## Flow

1. Parse the natural-language request into `TaskSpec`.
2. Generate up to five GitHub queries.
3. Search, deduplicate, and preliminary-rank candidates.
4. Pass only the first ten candidates to sequential batch analysis.
5. Score successful profiles and return the final Top 5.

## Counts and Errors

`candidate_count` reports all preliminary candidates. `analyzed_count` reports
successful profiles among the first ten. Task parsing and GitHub search failures
return HTTP 502. Individual repository failures stay isolated in the batch and
produce fewer recommendations; even zero successful analyses is a valid 200
response.

## Test Strategy

Unit endpoint tests replace all orchestration dependencies. The real smoke test
uses FastAPI `TestClient` with a temporary two-candidate search result so the
route is exercised without ten LLM calls.
