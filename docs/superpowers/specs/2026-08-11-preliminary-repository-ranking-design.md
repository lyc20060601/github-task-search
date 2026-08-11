# Preliminary Repository Ranking Design

## Scope

Enhance `search_multiple_queries` with deterministic preliminary scoring,
descending sorting, and a 20-result limit. Keep `search_repositories` unchanged.
Do not modify the frontend or add LLM, README, or AI scoring behavior.

## Score

Each deduplicated repository receives an integer `preliminary_score`:

```text
distinct query matches * 1000
+ star score
+ recent update score
+ description keyword score
```

- Star score: 100 for at least 10,000 stars, 70 for at least 1,000, 40 for
  at least 100, 20 for at least 10, otherwise 0.
- Recent update score: 30 when updated within 180 days, 15 within 365 days,
  otherwise 0. Missing or invalid dates score 0.
- Description score: extract case-insensitive technical tokens from the first
  five queries and description, ignore common English stop words, and award 5
  points for each shared token up to 25 points.
- Repeated query strings count as one distinct query match.

Secondary factors can total at most 155 points, so one additional query match
always outranks every possible secondary-factor difference.

## Result Behavior

Keep the first repository payload seen for each `full_name`, add its score, sort
all deduplicated repositories by `preliminary_score` descending using stable
ordering for ties, and return the first 20.

## Testing

Tests prove the exact score components, dominance of multi-query matches,
case-insensitive distinct-query counting, descending order, and the Top 20
limit. Existing single-query, limit, deduplication, empty-input, and error tests
remain intact.
