# Contributing

Thank you for improving GitHub Task Search. Keep changes focused and preserve the
self-hosted security boundary.

## Development Setup

Follow the README Quick Start once, then use the existing backend virtual
environment and frontend lockfile for local checks. Create a feature branch from
the current reviewed `main`; do not work directly on `main`.

## Before Opening a Pull Request

- Do not commit `.env`, API keys, tokens, authorization headers, private repository data, or local absolute paths.
- Keep GitHub and LLM calls mocked in unit tests.
- Do not execute unfamiliar repository code on the host during tests.
- Preserve Docker Sandbox limits and the explicit user-triggered validation flow.
- Keep Runtime Score and Compatibility Score separate.

## Local Checks

Run the relevant backend and frontend tests before submitting a change:

```sh
cd backend && python -m pytest -q -p no:cacheprovider
cd ../frontend && pnpm test && pnpm build
```

For deployment changes, also run:

```sh
docker compose --env-file .env.example config --quiet
```

Describe any failed or skipped checks in the pull request. Do not paste secret-bearing logs.

GitHub and LLM network calls must be mocked in normal unit tests. A test that
requires real credentials, fixed hardware, or a live external service is not a
unit test and must not run in CI.

## Pull Requests

Explain the user-visible behavior, files changed, tests run, and any known limitations. Keep changes focused and update the README when local setup behavior changes.

Use the pull request template. Security-sensitive changes to the Validation
Worker, Docker Sandbox, token handling, repository cloning, or internal Worker
endpoints need focused tests and an explicit explanation of the preserved
boundary.

## Reporting Security Problems

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md)
and use GitHub private vulnerability reporting.
