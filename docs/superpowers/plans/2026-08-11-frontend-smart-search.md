# Frontend Smart Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the homepage to `/smart-search` and display AI task understanding and generated GitHub queries above repository cards.

**Architecture:** Keep the feature in the existing single-page client component. Add typed response state, derive display strings with one small helper, and add restrained unframed CSS sections that follow the current layout.

**Tech Stack:** Next.js, React, TypeScript, CSS, Node test runner

---

### Task 1: Define the frontend contract with failing tests

**Files:**
- Modify: `frontend/tests/homepage.test.mjs`

- [x] **Step 1: Update the endpoint and response assertions**

Assert that the source fetches `http://127.0.0.1:8000/smart-search`, defines
`SmartSearchResponse`, and assigns `responseData.repositories`,
`responseData.task_spec`, and `responseData.generated_queries` to state.

- [x] **Step 2: Add task-context UI assertions**

Assert that the source contains “AI理解到的任务”, “自动生成的搜索词”, all six
TaskSpec field labels, `generatedQueries.map`, and the “未指定” fallback.

- [x] **Step 3: Run tests and verify red**

Run the frontend Node test command. Expected: the updated test fails because the
page still uses `/search` and does not render smart-search metadata.

### Task 2: Implement typed smart-search state and rendering

**Files:**
- Modify: `frontend/app/page.tsx`

- [x] **Step 1: Add response types and state**

Add `TaskSpec` with the six backend fields and `SmartSearchResponse` with
`task_spec`, `generated_queries`, and `repositories`. Add nullable TaskSpec and
string-array generated-query state plus a helper that joins non-empty arrays or
returns “未指定”.

- [x] **Step 2: Update request handling**

Fetch `/smart-search`, parse one `SmartSearchResponse`, assign its three response
parts, and clear all three on errors. Keep the existing request body, loading,
safe error, and console diagnostics.

- [x] **Step 3: Render the context sections**

Before repository cards, conditionally render a `search-context` section with a
six-row definition list and a generated-query list. Render “未生成搜索词” when
the query list is empty.

### Task 3: Style and verify

**Files:**
- Modify: `frontend/app/globals.css`

- [x] **Step 1: Add responsive context styles**

Add spacing, a top border, compact headings, a two-column TaskSpec definition
grid, wrapping values, and a simple bordered query list. Collapse the definition
grid to one column below 560px.

- [x] **Step 2: Run frontend tests**

Expected: all tests pass.

- [x] **Step 3: Run the production build**

Expected: Next.js build exits successfully with no TypeScript errors.

- [x] **Step 4: Verify the real page**

Use the running frontend and backend to submit the drone segmentation request.
Verify TaskSpec fields, five generated queries, repository cards, no error, and
non-overlapping desktop/mobile layouts.

- [x] **Step 5: Record repository limitation**

Do not create a Git commit because this project is not inside a Git repository
and the user does not require Git commits.
