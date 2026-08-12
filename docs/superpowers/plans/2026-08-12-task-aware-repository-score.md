# Task-aware Repository Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a deterministic, explainable 0-100 score for one repository without asking an LLM to choose the score.

**Architecture:** A focused `ranking.deep_score` module maps structured task, profile, and GitHub metadata fields into seven capped integer components. Small private helpers isolate label mapping, capability matching, recency, and Star bands for clear tests.

**Tech Stack:** Python, Pydantic models, pytest

---

### Task 1: Define scoring behavior with tests

**Files:**
- Create: `backend/tests/test_deep_score.py`

- [ ] Test exact/high-quality input and the complete seven-field output.
- [ ] Test that explicitly unsupported custom dataset must-have loses its share.
- [ ] Test that Stars cannot contribute more than five points.
- [ ] Test conservative behavior for unknown profile fields and invalid metadata.
- [ ] Run the focused test file and confirm import failure before implementation.

### Task 2: Implement the deterministic scorer

**Files:**
- Create: `backend/ranking/__init__.py`
- Create: `backend/ranking/deep_score.py`

- [ ] Add capped helpers for task match, completeness, must-have, maintenance, documentation, community, and environment.
- [ ] Add `calculate_repository_score(task_spec, repo_profile, github_metadata, now=None)`.
- [ ] Return the fixed score breakdown and its bounded integer sum.
- [ ] Run focused tests until they pass.

### Task 3: Verify the backend

**Files:**
- Test: `backend/tests/test_deep_score.py`

- [ ] Run Python compilation checks for the new package.
- [ ] Run the complete backend pytest suite.
- [ ] Run `git diff --check` and confirm no frontend scoring change was introduced.
