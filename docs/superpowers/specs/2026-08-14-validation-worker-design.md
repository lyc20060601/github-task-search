# Host Validation Worker Design

**Date:** 2026-08-14

## Goal

Restore `/validate-repository` for the self-hosted Compose deployment without mounting the host Docker socket into the public FastAPI backend container.

The solution keeps repository execution inside the existing restricted Docker Sandbox while moving Docker daemon access into a small, host-only validation worker.

## Non-Goals

- Do not expose the Docker API or Docker socket to the backend container.
- Do not accept arbitrary shell commands, image names, mount paths, or environment variables from HTTP clients.
- Do not run validation automatically after search or recommendation.
- Do not change Runtime Score semantics.
- Do not add cloud infrastructure, queues, databases, or multi-host orchestration.
- Do not make the worker reachable from the LAN or Internet.

## Architecture

```text
Browser
  |
  | POST /validate-repository { full_name }
  v
FastAPI backend container
  ^                         |
  | authenticated poll     | authenticated result
  |                         v
Host Validation Worker (outbound connection only)
  |
  | fixed Python calls into runtime.validator
  v
Restricted Docker Sandbox
  |
  v
RuntimeReport
```

The worker does not listen on any TCP port. It makes an outbound, authenticated request to the backend through the backend's existing host-published port. This avoids Docker Desktop host-loopback differences and prevents LAN clients from connecting directly to a Docker-capable worker.

## Components

### 1. Validation Worker

The worker is a separate Python process launched directly on the trusted host. It imports the existing repository validator and Docker Sandbox modules rather than duplicating validation logic.

Worker behavior:

- Poll `POST /internal/validation/jobs/next` with the worker bearer token.
- Accept only a server-generated job ID and a validated `full_name`.
- Run the existing fixed validation pipeline.
- Post the `RuntimeReport` to `/internal/validation/jobs/{job_id}/result`.
- Retry bounded transient connection failures with a capped delay.

The public request model rejects unknown fields. `full_name` must match the existing public GitHub repository format validation. No command, branch, URL, image, path, timeout, resource setting, or environment variable can be supplied by either the browser or the worker protocol.

### 2. Backend Worker Client

The public backend keeps `/validate-repository`. In worker mode it places one validated request into a bounded in-memory job slot and waits for a matching worker result up to the existing validation timeout.

Configuration:

- `VALIDATION_MODE`, either `local`, `worker`, or `disabled`.
- `VALIDATION_WORKER_TOKEN`, required when `VALIDATION_MODE=worker`.
- `VALIDATION_BACKEND_URL`, used only by the host worker and defaulting to `http://127.0.0.1:8000`.

Behavior:

- `worker`: enqueue and wait for the authenticated host worker.
- `local`: retain current direct-host validator behavior for trusted development.
- `disabled`: return HTTP 503 while search and recommendation remain available.
- Worker absent or disconnected: return HTTP 503 after a short readiness grace period.
- Worker job timeout: return HTTP 504 and invalidate the job ID.
- Unknown, expired, duplicate, or malformed worker results are rejected.

Worker stderr, Docker commands, local paths, tokens, and full installation logs are never returned by the proxy.

### 3. Internal Authentication

The startup script generates a random per-start token when no token is supplied. The same token is passed to the worker process and backend container.

The token is:

- stored only in process environment for that run;
- compared with `secrets.compare_digest`;
- never logged or returned;
- not written to `.env`, source files, Compose images, or README examples;
- distinct from `GITHUB_TOKEN` and `LLM_API_KEY`.

Requests without the correct bearer token return HTTP 401.

## Isolation and Resource Controls

The worker is trusted orchestration code, but repository code remains untrusted. All repository execution continues through `runtime/docker_sandbox.py` with:

- non-root UID/GID 10001;
- no `--privileged`;
- read-only container root filesystem;
- all Linux capabilities dropped;
- `no-new-privileges`;
- CPU, memory, PID, tmpfs, and command timeout limits;
- no user home, SSH directory, or Docker socket mounts;
- no GitHub, LLM, worker, or host secrets in the sandbox environment;
- repository workspace constrained to the project runtime temporary root;
- automatic container removal and timeout cleanup.

The worker API cannot override these limits in the first version.

## Concurrency and Abuse Controls

The first version provides one bounded in-memory job slot and permits one active validation job. A second public request received while validation is queued or running returns HTTP 429 with a retryable message.

Additional controls:

- request body size remains small through the fixed Pydantic model;
- repository names are normalized and validated before cloning;
- one repository failure does not stop the worker process;
- validation timeout remains bounded;
- temporary workspaces are cleaned in `finally` paths;
- the public backend preserves its existing manual-trigger behavior.

This is sufficient for a single-user or trusted-LAN self-hosted installation. It is not a public multi-tenant execution service.

## Startup and Shutdown

### Windows

`scripts/start.ps1` performs these steps:

1. Verify Python, Docker command, and Docker Engine availability.
2. Generate an in-memory worker token.
3. Start Compose with `VALIDATION_MODE=worker` and the generated token.
4. Verify the backend health endpoint.
5. Start the worker using the backend virtual environment and point it at `http://127.0.0.1:8000`.
6. Verify worker readiness through a non-sensitive backend status endpoint.
7. On failure, stop any worker process started by the script and stop Compose services started by the script.

A matching stop path shuts down Compose and only the worker process recorded by the current project startup script.

### Linux and macOS

`scripts/start.sh` follows the same sequence using a project-local virtual environment. It records the worker PID in an ignored runtime file and validates that PID before stopping it.

The startup scripts do not install Python, Docker, or dependencies automatically. Documentation tells users to create the backend virtual environment first.

## Compose Changes

The backend service receives:

- `VALIDATION_MODE=worker`
- `VALIDATION_WORKER_TOKEN` from the startup process environment

The Compose file still has:

- no Docker socket mount;
- no host home or SSH mount;
- no privileged container;
- no validation worker container;
- no `host.docker.internal` dependency;
- no persistent worker token.

## Error Handling

Public API responses remain bounded and user-readable:

- 401 is used only by internal worker endpoints and never exposes the expected token.
- 429 indicates another validation is active.
- 503 indicates worker mode is disabled or no authenticated worker is polling.
- 504 indicates the active validation exceeded the backend request timeout.

The frontend continues displaying the main failure reason without rendering unlimited logs.

## Testing

Automated tests cover:

1. Worker startup, polling, and readiness state.
2. Missing, malformed, and incorrect bearer tokens.
3. Valid job claim and `RuntimeReport` result submission.
4. Rejection of arbitrary commands, paths, URLs, and extra fields.
5. Single-job concurrency and HTTP 429 behavior.
6. Worker exceptions converted to bounded errors.
7. Backend queue success, timeout, unavailable worker, stale result, and authentication failure.
8. Direct-host backward compatibility when worker mode is absent.
9. Sandbox command invariants: non-root, limits, no privileged mode, no socket, no SSH/home mounts, no secret environment.
10. Compose configuration enables worker mode but contains no worker port, host mapping, or Docker socket.
11. Startup script syntax and failure cleanup using mocked processes.
12. Full backend and frontend regression suites.

Integration tests mock cloning and repository execution. A release smoke test may run a controlled fixture repository only after explicit confirmation; it must never execute an arbitrary real repository automatically.

## Security Limitations

The worker necessarily has access to the host Docker CLI. Its safety depends on accepting only server-issued jobs containing a repository identifier and invoking fixed, reviewed validator code. Anyone able to modify the worker source or its host process already has the same local-user privileges as the person running the project.

This architecture is intended for local self-hosting. The internal worker endpoints must not be exposed without their bearer-token authentication. The worker itself opens no listening port.

## Acceptance Criteria

- Compose backend contains no Docker socket mount and no Docker CLI requirement.
- `/validate-repository` succeeds through the outbound-polling host worker when launched by project scripts.
- Search and recommendation remain available when the worker is stopped.
- Worker failure produces a bounded status response rather than crashing the backend.
- Only one validation runs at a time.
- No repository-controlled input can change commands, images, mounts, resource limits, or environment variables.
- All existing backend and frontend tests continue passing.
