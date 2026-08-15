# Open Source v0.1 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a reproducible self-hosted v0.1 source release from the existing GitHub repository.

**Architecture:** Keep the existing Next.js, FastAPI, Docker Compose, and host validation Worker architecture unchanged. Bring verified acceptance fixes into the source-of-truth branch, add repository-level CI and contributor metadata, then verify the same commands documented for users.

**Tech Stack:** Python 3.12, FastAPI, pytest, Node.js 22, pnpm, Next.js, Docker Compose, GitHub Actions

---

### Task 1: Synchronize Release-Acceptance Fixes

**Files:**
- Modify: `backend/task_parser.py`
- Modify: `backend/runtime/repo_cloner.py`
- Modify: `backend/runtime/dependency_installer.py`
- Modify: `backend/runtime/docker_sandbox.py`
- Modify: `backend/runtime/validator.py`
- Modify: corresponding files under `backend/tests/`

- [x] Import the verified commits from the release-acceptance checkout without importing its local runtime state.
- [x] Run the focused task parser, clone, dependency, sandbox, and validator tests.
- [x] Confirm the source branch contains no unreviewed release-checkout artifacts.

### Task 2: Add Continuous Integration

**Files:**
- Create: `.github/workflows/ci.yml`

- [x] Add a Python 3.12 job that installs `backend/requirements.txt` and runs `python -m pytest -q -p no:cacheprovider`.
- [x] Add a Node.js 22 job that enables Corepack, installs the frozen pnpm lockfile, runs tests, and builds the frontend with a local placeholder API URL.
- [x] Add repository checks for Compose configuration, PowerShell/POSIX lifecycle script parsing, and tracked-file credential patterns.

### Task 3: Add Community Templates

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/deployment_problem.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`

- [x] Collect reproducible environment details without requesting secrets.
- [x] Route security reports to `SECURITY.md` instead of a public issue.
- [x] Require pull requests to list behavior, tests, limitations, and security-boundary impact.

### Task 4: Publish Version And Operations Documentation

**Files:**
- Create: `CHANGELOG.md`
- Create: `docs/RELEASE_CHECKLIST.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`

- [x] Document v0.1 features, security boundaries, and known limitations.
- [x] Make the clone-to-start and stop commands explicit for Windows and POSIX systems.
- [x] Document the CI-equivalent local checks and the release maintainer checklist.

### Task 5: Verify The Release Candidate

**Files:**
- Verify only; no product behavior changes.

- [x] Run the complete backend test suite.
- [x] Run frontend tests and production build.
- [x] Run `docker compose --env-file .env.example config --quiet`.
- [x] Parse PowerShell lifecycle scripts and run `sh -n` on POSIX scripts.
- [x] Run `git diff --check`, inspect ignored artifacts, and scan tracked files for credential-shaped values and local absolute paths.
