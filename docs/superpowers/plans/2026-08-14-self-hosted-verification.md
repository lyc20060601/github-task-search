# Self-Hosted Release Verification

Date: 2026-08-14

## Passed

- Backend test suite: 384 passed, 0 failed, 0 skipped.
- Frontend test suite: 9 passed, 0 failed, 0 skipped.
- Compose configuration validation passed with `.env.example`.
- Backend and frontend production images built successfully.
- Both Compose services became healthy.
- The frontend title and backend `/` response were verified over HTTP.
- The tracked-file secret pattern scan found no GitHub PAT or `sk-` API key values.
- Temporary Compose containers and network were removed after verification.
- The clean-environment smoke test (`tests/self_hosted_smoke.ps1`) rebuilt both
  images, verified both HTTP services and all public route registrations, then
  removed its containers and network.
- The smoke test used a unique Compose project, treated cleanup failure as a
  test failure, and left zero stopped or running project containers.
- A sentinel run confirmed that inherited GitHub, LLM, and Worker variables are
  cleared for the test and restored afterwards instead of entering Compose.
- Image and runtime inspection confirmed UID/GID `10001:10001`, no privileged
  containers, no host mounts, no `.env` files, and no sensitive runtime variable
  names baked into either image.
- Disabled mode returned a bounded HTTP 503 for `/validate-repository` while
  frontend and backend health checks remained available.
- A controlled in-process integration test completed the public request,
  authenticated job claim, fixed validator result, and result submission flow
  without GitHub access, Docker, or repository execution.
- A process-level controlled Worker then exercised the real Compose backend:
  readiness, a successful RuntimeReport, concurrent HTTP 429, incorrect-token
  HTTP 401, and HTTP 503 after the Worker stopped all passed. Its validator was
  replaced by a fixed test fixture, so no GitHub clone or repository code ran.
- The Windows lifecycle script started an authenticated host Validation Worker;
  `/validation-status` reported `worker_ready=true`.
- Worker-mode Compose inspection confirmed a non-root, non-privileged backend
  with no host mounts or Docker socket.
- The stop script removed the exact Worker process, PID file, Compose containers,
  and Compose network.
- POSIX shutdown behavior tests confirmed TERM/KILL cleanup and rejection of an
  unrelated PID.

## Scope Notes

- `/search`, `/smart-search`, and `/recommend-search` are covered by mocked backend tests. The release verification did not make live external API calls with placeholder credentials.
- The local Windows host does not expose `node` on `PATH`, so the frontend test suite ran in a read-only, non-root, network-disabled Node container.

## Resolved Release Blocker: Host Validation Worker

`/validate-repository` cannot create its Docker Sandbox from the current backend application container. The secure Compose configuration intentionally provides neither a Docker socket nor a Docker CLI.

Mounting the host Docker socket would violate the release security boundary by giving the application container control over the host Docker daemon. Do not use that workaround.

The selected resolution is an outbound-polling host Validation Worker with a
narrow authenticated protocol. The Worker opens no listening port and the
backend container still receives no Docker socket.

The implementation now passes the controlled Worker protocol test, real local
startup/readiness/shutdown verification, Sandbox invariant tests, disabled-mode
Compose verification, and complete backend/frontend regression suites. The
backend container remains isolated from the host Docker daemon.

GitHub publication remains pending. No commit or push was performed during this
verification.
