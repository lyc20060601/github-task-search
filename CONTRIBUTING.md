# Contributing

## Before Opening a Pull Request

- Do not commit `.env`, API keys, tokens, authorization headers, private repository data, or local absolute paths.
- Keep GitHub and LLM calls mocked in unit tests.
- Do not execute unfamiliar repository code on the host during tests.
- Preserve Docker Sandbox limits and the explicit user-triggered validation flow.
- Keep Runtime Score and Compatibility Score separate.

## Local Checks

Run the relevant backend and frontend tests before submitting a change:

```sh
cd backend && python -m pytest
cd ../frontend && pnpm test && pnpm build
```

For deployment changes, also run:

```sh
docker compose config
docker compose up --build
```

Describe any failed or skipped checks in the pull request. Do not paste secret-bearing logs.

## Pull Requests

Explain the user-visible behavior, files changed, tests run, and any known limitations. Keep changes focused and update the README when local setup behavior changes.
