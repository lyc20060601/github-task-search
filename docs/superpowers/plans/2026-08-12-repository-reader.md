# Repository Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a tested backend helper for reading GitHub repository README and common project paths.

**Architecture:** A focused `repo_reader.py` module owns GitHub contents requests, Base64 decoding, and structured result mapping. It does not call the LLM or participate in existing search routes.

**Tech Stack:** Python, httpx, python-dotenv, pytest.

---

### Task 1: Define the reader contract with tests

**Files:**
- Create: `backend/tests/test_repo_reader.py`

- [ ] Test mocked README/root contents responses, expected fields, and common path booleans.
- [ ] Test missing token and HTTP failures raise `RepositoryReadError`.
- [ ] Run `backend/.venv/Scripts/python.exe -m pytest -q tests/test_repo_reader.py` and observe import failure before implementation.

### Task 2: Implement GitHub repository reading

**Files:**
- Create: `backend/repo_reader.py`

- [ ] Read `GITHUB_TOKEN`, call README and root contents endpoints with the existing GitHub auth headers, decode README Base64, and map the requested paths.
- [ ] Run the focused tests, then the complete backend test suite.

### Task 3: Real repository smoke test

**Files:**
- No production files modified.

- [ ] Invoke `get_repository_details("open-mmlab/mmsegmentation")` with the configured environment.
- [ ] Print only README length, root item count, and true common paths; do not print tokens or full README.
