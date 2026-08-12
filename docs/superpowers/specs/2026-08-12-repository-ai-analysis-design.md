# Repository AI Analysis Design

## Scope

Analyze exactly one repository at a time. The analyzer accepts a `TaskSpec` and
the structured result from `get_repository_details()`. It does not search
GitHub, analyze multiple repositories, change `/smart-search`, or modify the
frontend.

## Data Flow

1. Serialize the user task, README, root file list, and detected common paths.
2. Send only that evidence to the configured OpenAI-compatible LLM endpoint.
3. Require a JSON object matching `RepoProfile`.
4. Validate the response with Pydantic and return a `RepoProfile` instance.
5. Override file-presence fields with deterministic static facts so the model
   cannot contradict known repository contents.

## Evidence Rules

The prompt prohibits outside knowledge. Unsupported textual conclusions use
`"unknown"`; unsupported boolean capabilities use `false`. Static file facts
are derived only from `common_paths`.

## Errors

Missing LLM configuration, HTTP failures, malformed response envelopes,
invalid JSON, and schema errors raise a repository-analysis-specific exception.

## Testing

Mock transport tests cover request evidence, structured response validation,
static fact enforcement, configuration errors, and malformed JSON. One real
public repository is then read and analyzed through the configured services.
