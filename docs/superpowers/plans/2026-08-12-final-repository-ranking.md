# Final Repository Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return a stable Top 5 list from analyzed repository profiles and deterministic final scores.

**Architecture:** A pure ranking function joins metadata and analysis records by `full_name`, calls the existing task-aware scorer, excludes failed analyses, performs a stable descending sort, and formats a fixed response contract.

**Tech Stack:** Python, Pydantic models, pytest

---

### Task 1: Define output and ordering behavior

**Files:**
- Create: `backend/tests/test_final_ranking.py`

- [ ] Test descending score order and ranks.
- [ ] Test the Top 5 limit and stable ordering for ties.
- [ ] Test failed or missing analysis records are skipped.
- [ ] Test metadata, profile, strengths, weaknesses, and evidence output fields.
- [ ] Run focused tests and confirm the module import fails.

### Task 2: Implement final ranking

**Files:**
- Create: `backend/ranking/final_ranking.py`
- Modify: `backend/ranking/__init__.py`

- [ ] Join ordered metadata with successful profiles by `full_name`.
- [ ] Call `calculate_repository_score` for each joined item.
- [ ] Sort stably, limit to five, assign ranks, and format output.
- [ ] Run focused tests until they pass.

### Task 3: Verify backend integrity

**Files:**
- Test: `backend/tests/test_final_ranking.py`

- [ ] Compile the new ranking module.
- [ ] Run the complete backend test suite.
- [ ] Run `git diff --check` and confirm frontend remains untouched by this task.
