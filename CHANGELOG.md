# Changelog

All notable changes to this project are documented in this file. The format is
based on Keep a Changelog, and the project uses semantic versioning for public
releases.

## [Unreleased]

### Added

- GitHub Actions checks for backend, frontend, Compose, lifecycle scripts, and
  credential-shaped tracked values.
- Structured bug, deployment, feature request, and pull request templates.
- A maintainer release checklist for reproducible self-hosted releases.

### Fixed

- Preserved complete task requirements when an LLM returns incomplete JSON.
- Improved public repository cloning on Windows.
- Hardened dependency installation and clone cleanup in the Docker Sandbox.

## [0.1.0] - 2026-08-14

### Added

- Natural-language task parsing and multi-query GitHub repository search.
- Task-aware Top 5 recommendations with evidence and deterministic scoring.
- Static repository environment and local machine compatibility analysis.
- Explicit, user-triggered runtime validation through a restricted Docker
  Sandbox and a host-side Validation Worker.
- Docker Compose deployment, lifecycle scripts, MIT License, contribution
  guidance, and a security policy.

[Unreleased]: https://github.com/lyc20060601/github-task-search/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lyc20060601/github-task-search/releases/tag/v0.1.0
