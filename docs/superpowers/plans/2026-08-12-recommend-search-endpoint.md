# Recommend Search Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the complete recommendation pipeline through a new FastAPI endpoint without changing existing routes.

**Architecture:** The route is a thin orchestrator over existing modules. Overall task parsing and search failures map to 502; batch-level repository failures remain data and do not fail the request.

**Tech Stack:** FastAPI, Pydantic, pytest, HTTPX TestClient

---

### Task 1: Define route behavior

**Files:**
- Modify: `backend/tests/test_main.py`

- [ ] Test complete response and dependency call order.
- [ ] Test only the first ten candidates reach batch analysis.
- [ ] Test failed repository analyses reduce `analyzed_count` without failing.
- [ ] Test parser and GitHub failures return HTTP 502.
- [ ] Run focused tests and confirm `/recommend-search` returns 404.

### Task 2: Implement endpoint orchestration

**Files:**
- Modify: `backend/main.py`

- [ ] Import batch analysis and final ranking functions.
- [ ] Register `POST /recommend-search` in the shared route registrar.
- [ ] Return task spec, generated queries, counts, and recommendations.
- [ ] Run focused tests until they pass.

### Task 3: Verify

**Files:**
- Test: `backend/tests/test_main.py`

- [ ] Run the complete backend test suite and compilation checks.
- [ ] Use TestClient with two real public repositories through the new route.
- [ ] Confirm `/search` and `/smart-search` remain registered.
