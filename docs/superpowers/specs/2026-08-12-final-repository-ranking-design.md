# Final Repository Ranking Design

## Scope

Merge preliminary GitHub repository metadata with successful deep-analysis
results, calculate the existing deterministic task-aware score, sort by final
score, and return at most five repositories. No GitHub or LLM request is made.

## Inputs

- `TaskSpec` for score calculation.
- Ordered repository metadata from preliminary search.
- Batch analysis records containing `full_name`, `profile`, and `error`.

Records are joined by `full_name`. Failed analyses and records without matching
metadata or a `RepoProfile` are excluded.

## Ordering

Repositories are ordered by descending `final_score`. Python's stable sort keeps
the original candidate order when scores are equal. The first five receive ranks
1 through 5.

## Output

Every item includes repository metadata, score and breakdown, the JSON-ready
profile, top-level strengths and weaknesses, and a five-key evidence dictionary.
