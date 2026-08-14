# Host Validation Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/validate-repository` work in the self-hosted Compose deployment through an authenticated host worker without exposing the Docker socket to the backend container.

**Architecture:** The backend owns one bounded in-memory job slot. A Python worker on the trusted host polls authenticated internal endpoints, runs the existing fixed `validate_repository()` pipeline, and submits `RuntimeReport`. The worker opens no listening port and search/recommendation remain independent of it.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, httpx, threading, Docker Compose, PowerShell, POSIX shell, pytest.

**Git policy:** Do not commit or push because the user has not authorized Git publication and the worktree contains user-owned changes.

---

## File Map

- Create `backend/runtime/validation_jobs.py`: fixed job/result models and thread-safe single-slot coordinator.
- Create `backend/runtime/validation_gateway.py`: mode selection, worker authentication, and public dispatch.
- Create `backend/runtime/validation_worker.py`: outbound-polling host worker.
- Modify `backend/main.py`: hidden internal endpoints and public validation routing.
- Create `backend/tests/test_validation_jobs.py`, `test_validation_gateway.py`, `test_validation_worker.py`, and `test_worker_configuration.py`.
- Modify `backend/tests/test_main.py`: API integration coverage.
- Modify `docker-compose.yml`, `.env.example`, `backend/.env.example`, and `.gitignore`.
- Modify `scripts/start.ps1` and `scripts/start.sh`; create matching `stop.ps1` and `stop.sh`.
- Modify `README.md`, `SECURITY.md`, and the self-hosted verification record.

---

### Task 1: Single-Slot Job Coordinator

**Files:**
- Create: `backend/runtime/validation_jobs.py`
- Test: `backend/tests/test_validation_jobs.py`

- [ ] **Step 1: Write failing tests**

Test enqueue/claim/complete, capacity one, readiness expiry, wait timeout cleanup, mismatched repository result, and stale job rejection:

```python
def test_worker_claims_and_completes_waiting_request():
    coordinator = ValidationJobCoordinator(worker_grace_seconds=1)
    coordinator.touch_worker()
    received = []
    thread = Thread(target=lambda: received.append(
        coordinator.submit_and_wait("owner/repository", timeout_seconds=1)
    ))
    thread.start()
    job = coordinator.claim_next(wait_seconds=1)
    coordinator.complete(job.id, RuntimeReport(full_name=job.full_name))
    thread.join(timeout=1)
    assert received[0].full_name == "owner/repository"


def test_second_job_is_rejected():
    coordinator = ValidationJobCoordinator()
    coordinator.enqueue("owner/first")
    with pytest.raises(ValidationBusy):
        coordinator.enqueue("owner/second")
```

- [ ] **Step 2: Verify tests fail**

Run `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_validation_jobs.py -q`.

Expected: import failure for `runtime.validation_jobs`.

- [ ] **Step 3: Implement strict models and coordinator**

Use these public contracts:

```python
class ValidationJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    full_name: str


class ValidationJobResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report: RuntimeReport


class ValidationBusy(RuntimeError):
    pass


class ValidationUnavailable(RuntimeError):
    pass


class ValidationTimedOut(RuntimeError):
    pass


class InvalidValidationJob(RuntimeError):
    pass
```

Implement `ValidationJobCoordinator` with `threading.Condition`, `time.monotonic`, and `uuid4().hex`. Its API is:

```python
touch_worker() -> None
worker_ready() -> bool
enqueue(full_name: str) -> ValidationJob
submit_and_wait(full_name: str, *, timeout_seconds: float) -> RuntimeReport
claim_next(*, wait_seconds: float) -> ValidationJob | None
complete(job_id: str, report: RuntimeReport) -> None
```

Only one queued or claimed job may exist. Timeout clears the slot and invalidates late results. `complete` verifies both job ID and `report.full_name`.

- [ ] **Step 4: Verify coordinator tests pass**

Run `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_validation_jobs.py -q`.

Expected: all tests pass with no warning.

---

### Task 2: Validation Modes, Authentication, and API

**Files:**
- Create: `backend/runtime/validation_gateway.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_validation_gateway.py`
- Modify: `backend/tests/test_main.py`

- [ ] **Step 1: Write failing mode and endpoint tests**

Cover `local`, `worker`, `disabled`; missing/incorrect token; 204 idle poll; valid claim/result; expired result; 429 busy; 503 unavailable; 504 timeout; and hidden internal OpenAPI paths.

```python
def test_internal_poll_rejects_missing_token(client, monkeypatch):
    monkeypatch.setenv("VALIDATION_MODE", "worker")
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", "test-token")
    assert client.post("/internal/validation/jobs/next").status_code == 401


def test_internal_paths_are_hidden(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/internal/validation/jobs/next" not in paths
```

- [ ] **Step 2: Verify focused tests fail**

Run `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_validation_gateway.py tests/test_main.py -q`.

- [ ] **Step 3: Implement the gateway**

Create a module-level `COORDINATOR`. Implement:

```python
def get_validation_mode() -> Literal["local", "worker", "disabled"]:
    value = os.getenv("VALIDATION_MODE", "local").strip().lower()
    return value if value in {"local", "worker", "disabled"} else "disabled"


def require_worker_token(authorization: str | None) -> None:
    expected = os.getenv("VALIDATION_WORKER_TOKEN", "")
    supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        raise PermissionError("invalid validation worker credentials")


def validate_requested_repository(full_name: str, *, timeout_seconds: float = 600) -> RuntimeReport:
    mode = get_validation_mode()
    if mode == "local":
        return validate_repository(full_name)
    if mode == "worker":
        return COORDINATOR.submit_and_wait(full_name, timeout_seconds=timeout_seconds)
    raise ValidationUnavailable("repository validation is disabled")
```

- [ ] **Step 4: Register bounded routes**

Add hidden `POST /internal/validation/jobs/next` and `POST /internal/validation/jobs/{job_id}/result` routes using `Header`, `Response`, and `include_in_schema=False`. Add public `GET /validation-status` returning only `mode` and `worker_ready`. Route `/validate-repository` through the gateway.

Map exceptions exactly: auth 401, invalid/stale job 409, busy 429, unavailable/disabled 503, timeout 504. Never return tokens, Docker commands, local paths, or exception reprs.

- [ ] **Step 5: Verify focused tests pass**

Run `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_validation_gateway.py tests/test_main.py -q`.

---

### Task 3: Outbound-Polling Host Worker

**Files:**
- Create: `backend/runtime/validation_worker.py`
- Test: `backend/tests/test_validation_worker.py`

- [ ] **Step 1: Write failing worker tests**

Mock all HTTP and validation calls. Test 204 idle, valid job/report, malformed job, 401/403 fatal exit, transient retry, structured validator failure, Ctrl+C, and absence of GitHub/LLM secrets from requests.

```python
class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "worker request failed",
                request=httpx.Request("POST", "http://test"),
                response=httpx.Response(self.status_code),
            )


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append(SimpleNamespace(url=url, **kwargs))
        return next(self.responses)


def test_worker_validates_and_submits(monkeypatch):
    report = RuntimeReport(full_name="owner/repository", clone_status="success")
    client = FakeClient([
        FakeResponse(200, {"id": "job-1", "full_name": "owner/repository"}),
        FakeResponse(204, None),
    ])
    monkeypatch.setattr("runtime.validation_worker.validate_repository", lambda _: report)
    worker = ValidationWorker(backend_url="http://127.0.0.1:8000", token="token", client=client)
    assert worker.run_once() is True
    assert client.requests[1].json == {"report": report.model_dump(mode="json")}
```

- [ ] **Step 2: Verify tests fail**

Run `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_validation_worker.py -q`.

- [ ] **Step 3: Implement worker and CLI**

`ValidationWorker` accepts only `backend_url`, `token`, and optional injected `httpx.Client`. `run_once()` polls the fixed endpoint, validates `ValidationJob`, calls existing `validate_repository(job.full_name)`, wraps it in `ValidationJobResult`, and posts to the fixed result endpoint.

`main()` reads only `VALIDATION_BACKEND_URL` and `VALIDATION_WORKER_TOKEN`, handles SIGINT/SIGTERM, retries connection failures at 1/2/4/5 seconds, and exits on 401/403. It must not log the token, environment, authorization header, Docker command, or full local path.

- [ ] **Step 4: Verify worker tests pass**

Run `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_validation_worker.py -q`.

Expected: tests pass without network, GitHub, or Docker access.

---

### Task 4: Compose and Lifecycle Scripts

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `backend/.env.example`
- Modify: `.gitignore`
- Modify: `scripts/start.ps1`
- Modify: `scripts/start.sh`
- Create: `scripts/stop.ps1`
- Create: `scripts/stop.sh`
- Test: `backend/tests/test_worker_configuration.py`

- [ ] **Step 1: Write failing configuration safety tests**

Assert Compose contains `VALIDATION_MODE` and `VALIDATION_WORKER_TOKEN` but no `docker.sock`, `privileged`, worker service, worker port, or `host.docker.internal`. Assert example env files contain `VALIDATION_MODE=disabled` and no worker token assignment. Assert scripts never print the token and never use `pkill`, `killall`, or wildcard process termination.

- [ ] **Step 2: Verify tests fail**

Run `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_worker_configuration.py -q`.

- [ ] **Step 3: Update Compose and ignored state**

Add to backend environment only:

```yaml
VALIDATION_MODE: ${VALIDATION_MODE:-disabled}
VALIDATION_WORKER_TOKEN: ${VALIDATION_WORKER_TOKEN:-}
```

Add `.runtime/` to `.gitignore`. Do not add a socket, privileged mode, host mount, host mapping, worker container, persistent token, or token example.

- [ ] **Step 4: Implement Windows start/stop**

`start.ps1` must verify `backend/.venv/Scripts/python.exe`, generate 32 random bytes using `RandomNumberGenerator`, set token/mode only in process environment, start Compose detached, wait for backend health, start hidden `python -m runtime.validation_worker`, and store only its PID in `.runtime/validation-worker.pid`. On failure, stop the created worker and Compose. Clear the token variable in `finally`.

`stop.ps1` must parse a numeric PID, verify it belongs to this project when command-line metadata is available, stop only that PID, remove the PID file, and run `docker compose down`.

- [ ] **Step 5: Implement POSIX start/stop**

`start.sh` generates the token with `python -c "import secrets; print(secrets.token_urlsafe(32))"`, exports it only to Compose/worker children, records `$!`, and clears the shell variable. `stop.sh` validates a numeric PID, sends TERM to that PID only, waits with a bounded loop, removes the PID file, and runs Compose down.

- [ ] **Step 6: Verify configuration and syntax**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_worker_configuration.py -q
cd ..
docker compose --env-file .env.example config --quiet
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -ValidateOnly
```

Validate shell syntax in a network-disabled, read-only Alpine container with `sh -n /scripts/start.sh /scripts/stop.sh`. Add `-ValidateOnly` as a non-mutating script switch before using it.

---

### Task 5: Documentation and Security Boundary

**Files:**
- Modify: `README.md`
- Modify: `SECURITY.md`
- Modify: `docs/superpowers/plans/2026-08-14-self-hosted-verification.md`

- [ ] **Step 1: Document exact setup**

Explain that runtime validation requires host Python, `backend/.venv`, installed backend requirements, and Docker Engine. Document Windows and POSIX start/stop commands, 503 worker-not-ready behavior, and that search/recommendation work with `VALIDATION_MODE=disabled`.

- [ ] **Step 2: Document security constraints**

State that the worker has local-user Docker privileges but accepts only server-issued repository jobs; token persistence, socket mounts, privileged containers, and public multi-tenant exposure are unsupported. The ephemeral worker token must not enter `.env`, logs, screenshots, issues, commits, or images.

- [ ] **Step 3: Update blocker status carefully**

Change the prior release blocker to “pending integration verification.” Preserve the original reasoning and do not mark it resolved until Task 6 passes.

- [ ] **Step 4: Scan documentation for secrets**

Run a filename-only scan for GitHub PAT and `sk-` patterns. Expected: zero matches. Do not print matching values.

---

### Task 6: Regression and Integration Gate

**Files:**
- Modify only files directly responsible for failures introduced above.
- Update: `docs/superpowers/plans/2026-08-14-self-hosted-verification.md`

- [x] **Step 1: Run complete backend tests**

Run `cd backend; .\.venv\Scripts\python.exe -m pytest -q`.

Expected: the existing 319 tests and all new tests pass. Record passed, failed, skipped, and warning counts.

- [x] **Step 2: Run frontend regression tests**

Run `node --test` in a network-disabled, read-only, non-root Node container with a read-only frontend mount.

Expected: existing 9 tests pass with zero failures/skips.

- [x] **Step 3: Verify disabled mode**

Build/start Compose with `.env.example`. Verify frontend/backend healthy, `/validate-repository` returns bounded 503, search routes remain covered, and no Docker socket/home/SSH mount, privileged mode, or baked worker token exists. Stop and clean containers/network.

- [x] **Step 4: Verify worker protocol without a real repository**

Start Compose with an ephemeral token and run the worker with `validate_repository` replaced at test level by a controlled fixture. Verify readiness, one successful RuntimeReport, concurrent 429, incorrect-token 401, stopped-worker 503, and no GitHub clone or repository execution.

- [x] **Step 5: Re-run Sandbox invariant tests**

Confirm generated commands contain `--rm`, non-root user, read-only root, dropped capabilities, no-new-privileges, CPU/memory/PID/timeout limits, and constrained workspace. Confirm absence of `--privileged`, socket/SSH/home mounts, and GitHub/LLM/worker secrets.

- [x] **Step 6: Run final release checks**

Run:

```powershell
git diff --check
git status --short
docker compose --env-file .env.example config --quiet
```

Run filename-only secret scanning and confirm no worker process, PID file, Compose container, or network remains.

- [x] **Step 7: Update acceptance record**

Mark the blocker resolved only if the backend has no Docker socket, the worker opens no listening port, authenticated polling succeeds, search/recommendation work without the worker, and every test/cleanup/secret check passes. Do not commit, push, publish, or create a release.
