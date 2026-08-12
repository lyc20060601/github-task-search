# Task-aware Repository Score Design

## Scope

Calculate one deterministic 0-100 repository score from `TaskSpec`,
`RepoProfile`, and GitHub metadata. The scorer performs no network or LLM calls,
does not rank a collection, and does not change the frontend.

## Score Breakdown

- Task match: 30
- Training and usage completeness: 20
- Must-have satisfaction: 20
- Maintenance: 10
- Documentation: 10
- Community: 5
- Environment completeness: 5

Every component is independently capped. The final integer score is the sum of
the seven integer components and is constrained to 0-100.

## Rules

`task_match` labels are authoritative when recognized; otherwise normalized
token overlap across task, domains, and framework provides a conservative
fallback. Completeness uses training code, configs, dataset support, and
pretrained weights. Must-have entries map to known structured capabilities;
explicitly unsupported requirements receive zero for their share, unknown
requirements receive only a small fraction, and fulfilled requirements receive
their full share. When no must-have is specified, the repository receives the
full 20 points because no mandatory condition is unmet.

Maintenance uses `updated_at` age bands. Documentation maps known quality labels.
Community uses Star bands capped at five points. Environment uses requirements,
environment files, and Docker indicators.

## Output

The public function returns `final_score` and a `score_breakdown` dictionary
with exactly the seven named components.
