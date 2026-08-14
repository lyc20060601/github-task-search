# Repository Environment Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, fixed-path GitHub Contents API reader for repository environment files without cloning, executing, or parsing them.

**Architecture:** A focused compatibility module will reuse `repo_reader`'s GitHub API root and authentication header helper. It will request ordered candidate groups through an injectable synchronous `httpx.Client`, decode successful Base64 payloads under a 512 KiB limit, and isolate all file-level failures in a structured result.

**Tech Stack:** Python 3, httpx, python-dotenv, pytest, httpx.MockTransport

---

### Task 1: Define Fetcher Behavior With Mocked Tests

**Files:**
- Create: `backend/tests/test_repository_environment_fetcher.py`

- [ ] **Step 1: Add test helpers**

Create a Base64 payload helper and a `MockTransport` client factory. Every
handler must assert `Authorization == "Bearer test-token"` so authentication
reuse is covered without exposing a real credential.

- [ ] **Step 2: Add the ten required behavior tests**

Add independent tests for `README.md`, `requirements.txt`, 404 handling,
README fallback, environment fallback, `Dockerfile`, isolated 500 errors,
timeouts, a payload larger than `MAX_FILE_SIZE_BYTES`, and serialized-result
token absence. Assert the public function signature:

```python
result = fetcher.fetch_repository_environment_files("owner/repo", client=client)
```

- [ ] **Step 3: Verify the tests fail for the missing module**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest tests\test_repository_environment_fetcher.py -q --basetemp=.environment-fetcher-red-temp -p no:cacheprovider
```

Expected: collection fails because
`compatibility.repository_environment_fetcher` does not exist.

### Task 2: Implement Fixed-Path GitHub File Reading

**Files:**
- Create: `backend/compatibility/repository_environment_fetcher.py`

- [ ] **Step 1: Define constants and request-level exception**

Reuse `GITHUB_API_URL` and `_github_headers` from `repo_reader`. Define:

```python
MAX_FILE_SIZE_BYTES = 512 * 1024
REQUEST_TIMEOUT_SECONDS = 15.0

class RepositoryEnvironmentFetchError(RuntimeError):
    pass
```

Define the exact README, environment, compose, and singleton candidate groups
from the approved specification.

- [ ] **Step 2: Implement safe payload decoding**

Validate that the response JSON is a dictionary with Base64 text content. Use
the declared GitHub `size` and decoded byte count to enforce the 512 KiB limit.
Decode UTF-8 with replacement and return only text, byte size, and
`truncated=False`. Oversized payloads must return a skip reason and no content.

- [ ] **Step 3: Implement per-file error isolation**

For each path:

```python
response = http_client.get(
    f"{GITHUB_API_URL}/repos/{normalized_name}/contents/{path}",
    headers=headers,
)
```

Record 404 in `missing_files`; record other HTTP status codes and sanitized
reasons in `errors`; catch `httpx.TimeoutException`, `httpx.NetworkError`, and
malformed payload exceptions without stopping later files. Do not store request
objects, response bodies from errors, headers, or exception representations.

- [ ] **Step 4: Implement grouped fallback and result assembly**

Stop each ordered candidate group only after a successful file read. Return:

```python
{
    "full_name": normalized_name,
    "files": files,
    "found_files": found_files,
    "missing_files": missing_files,
    "skipped_files": skipped_files,
    "errors": errors,
}
```

Create and close a `httpx.Client(timeout=15.0)` only when a client was not
injected. Missing token and invalid `owner/repository` input raise the sanitized
request-level exception.

- [ ] **Step 5: Run targeted tests until green**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest tests\test_repository_environment_fetcher.py -q --basetemp=.environment-fetcher-target-temp -p no:cacheprovider
```

Expected: all new tests pass with no warning.

### Task 3: Regression Verification

**Files:**
- Verify only; no additional production files

- [ ] **Step 1: Run the full backend suite**

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.environment-fetcher-full-temp -p no:cacheprovider
```

Expected: all tests pass and pytest reports no failed, skipped, or warning
entries.

- [ ] **Step 2: Inspect the final diff**

Confirm only the approved design/plan, the new compatibility fetcher, and its
tests were added. Do not modify APIs, frontend, runtime validation, or
compatibility models. No Git commit is created because this project currently
does not require commits.
