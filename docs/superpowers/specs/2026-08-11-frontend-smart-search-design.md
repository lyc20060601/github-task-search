# Frontend Smart Search Design

## Scope

Update only the Next.js frontend. Submit the existing request body to `POST
/smart-search`, read `task_spec`, `generated_queries`, and `repositories`, and
show the first two above the existing repository cards. Do not change the
backend or add README analysis or deeper scoring.

## State And Data Flow

Define frontend `TaskSpec` and `SmartSearchResponse` types. Store the current
TaskSpec and generated query list alongside the existing projects state. On a
successful response, populate all three from the response object. On a failed
request, clear all response-derived state and keep the existing safe error.

## Layout

When a TaskSpec is available, render an unframed context section before the
repository results. “AI理解到的任务” uses a definition list for `task`,
`domain`, `framework`, `hardware`, `must_have`, and `preferences`; empty values
show “未指定”. “自动生成的搜索词” uses a simple list, with an empty-state line
when no query was generated. Existing loading, empty-repository, error, and
repository-card UI remains intact.

## Verification

Update the source-contract tests, run all frontend tests, run a production
build, then perform a real browser search against the running backend and verify
both context sections and repository cards at desktop and mobile widths.
