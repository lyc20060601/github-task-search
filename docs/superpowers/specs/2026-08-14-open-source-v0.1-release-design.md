# Open Source v0.1 Release Design

## Goal

Prepare the existing `lyc20060601/github-task-search` repository for a reliable
self-hosted v0.1 release that another user can clone and run on their own
computer without access to the maintainer's local environment.

## Scope

The release work is limited to source consistency, reproducible validation,
community contribution files, and deployment documentation. Search,
recommendation, compatibility, and runtime-validation API contracts remain
unchanged.

## Source Of Truth

The repository root is the only supported distribution unit. Release-acceptance
fixes verified in the separate local validation checkout must be incorporated
into this repository before release. Local validation copies, virtual
environments, runtime state, build outputs, and credentials are not release
artifacts.

## Release Automation

GitHub Actions will validate the backend test suite, frontend test/build, Docker
Compose configuration, lifecycle script syntax, and a tracked-file credential
scan. CI uses placeholders only and must not require GitHub or LLM credentials.

## Community Files

The repository will provide bug, deployment, and feature request templates plus
a pull request template. Every template warns contributors not to attach API
keys, `.env` contents, authorization headers, private repository data, or
unredacted logs.

## Documentation

The README remains the primary self-hosting guide. It must explain the supported
deployment boundary, first-time setup, lifecycle scripts, runtime-validation
worker, failure diagnosis, credential ownership, and current limitations. A
changelog and release checklist make the v0.1 state explicit.

## Acceptance Criteria

- A fresh user can follow the README from clone to a working local UI.
- CI passes without secrets or live external API calls.
- Backend tests, frontend tests/build, Compose validation, and script parsing
  pass locally.
- Tracked files contain no real credentials, local absolute paths, runtime
  state, virtual environments, or generated frontend output.
- The GitHub source contains all fixes that passed release acceptance.
