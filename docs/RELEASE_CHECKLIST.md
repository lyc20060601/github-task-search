# Release Checklist

Use this checklist from a clean clone of the release candidate. Do not use real
credentials in CI, logs, screenshots, or release artifacts.

## Source And Metadata

- [ ] The release branch is based on the latest reviewed `main`.
- [ ] `git status --short` is clean.
- [ ] `CHANGELOG.md` contains the release version and date.
- [ ] README setup commands match the lifecycle scripts.
- [ ] `.env`, `.runtime`, virtual environments, dependency outputs, and frontend
      build output are not tracked.
- [ ] The release contains no maintainer-specific absolute paths or credentials.

## Automated Checks

Run from the repository root:

```powershell
backend\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider backend\tests
pnpm --dir frontend test
pnpm --dir frontend build
docker compose --env-file .env.example config --quiet
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -ValidateOnly
git diff --check
```

On Linux or macOS also run:

```sh
sh -n scripts/start.sh scripts/stop.sh
./scripts/start.sh --validate-only
```

## Manual Self-Hosted Acceptance

- [ ] Copy `.env.example` to `.env` and insert temporary maintainer-owned test
      credentials locally.
- [ ] Start with the platform lifecycle script.
- [ ] Confirm `http://localhost:3000` loads and `http://localhost:8000` responds.
- [ ] Run one smart search and one deep recommendation.
- [ ] Explicitly validate one small public repository and confirm the Worker
      reports completion or a bounded structured failure.
- [ ] Stop with the platform lifecycle script.
- [ ] Confirm temporary containers and the Validation Worker are gone.
- [ ] Revoke temporary credentials if they were exposed during testing.

## Publish

- [ ] Merge through a reviewed pull request with passing CI.
- [ ] Create an annotated `vMAJOR.MINOR.PATCH` tag on the merge commit.
- [ ] Create a GitHub release from the matching changelog entry.
- [ ] Perform a final clone-and-start check from the release tag.
