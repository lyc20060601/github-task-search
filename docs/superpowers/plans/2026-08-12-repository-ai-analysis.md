# Repository AI Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyze one GitHub repository against one `TaskSpec` and return a validated, evidence-bound `RepoProfile`.

**Architecture:** `repo_analyzer.py` builds a constrained prompt from already-fetched repository evidence and calls the configured OpenAI-compatible endpoint. Pydantic validates model JSON, while deterministic file flags from `common_paths` remain authoritative.

**Tech Stack:** Python, Pydantic, HTTPX, python-dotenv, pytest

---

### Task 1: Extend the profile schema

**Files:**
- Modify: `backend/repo_profile.py`
- Test: `backend/tests/test_repo_analyzer.py`

- [ ] Add nullable `task_match` for the requested repository-to-task match analysis.
- [ ] Verify the schema accepts complete and unknown-valued profiles.

### Task 2: Implement the single-repository analyzer

**Files:**
- Modify: `backend/repo_analyzer.py`
- Test: `backend/tests/test_repo_analyzer.py`

- [ ] Write failing tests for the desired two-argument API and JSON response.
- [ ] Verify tests fail because the current static-only API has the wrong signature.
- [ ] Add LLM configuration loading, evidence-only prompt construction, JSON mode, Pydantic validation, and explicit exceptions.
- [ ] Keep static file flags authoritative and verify focused tests pass.

### Task 3: Verify the feature

**Files:**
- Test: `backend/tests/test_repo_analyzer.py`

- [ ] Run the full backend test suite.
- [ ] Read and analyze `open-mmlab/mmsegmentation` once using configured GitHub and LLM services.
- [ ] Print only a structured summary and never print credentials.
