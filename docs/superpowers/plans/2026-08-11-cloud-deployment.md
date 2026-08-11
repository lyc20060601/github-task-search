# Cloud Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the existing Next.js and FastAPI applications from a private GitHub repository to Vercel and an always-on Render web service.

**Architecture:** Preserve the monorepo and local development defaults. Vercel injects the public FastAPI base URL into the frontend build, while Render injects the public Vercel origin and API credentials into the backend process.

**Tech Stack:** Next.js 16, React, TypeScript, FastAPI, Python, pytest, GitHub, Vercel, Render

---

### Task 1: Add repository secret and artifact exclusions

**Files:**
- Create: `.gitignore`

- [x] **Step 1: Create the repository-level ignore file**

```gitignore
.env
**/.env
**/.env.*
!**/.env.example
**/node_modules/
**/.next/
**/.venv/
**/__pycache__/
**/.pytest_cache/
*.py[cod]
*.log
```

- [x] **Step 2: Verify the real backend environment file is ignored**

Run: `git check-ignore -v backend/.env frontend/node_modules frontend/.next`

Expected: all three paths are matched by an ignore rule.

### Task 2: Configure the frontend API base URL with TDD

**Files:**
- Modify: `frontend/tests/homepage.test.mjs`
- Modify: `frontend/app/page.tsx`

- [x] **Step 1: Write a failing frontend source-contract assertion**

Replace the hardcoded-fetch assertion with:

```js
assert.match(
  source,
  /process\.env\.NEXT_PUBLIC_API_BASE_URL \?\? "http:\/\/127\.0\.0\.1:8000"/,
);
assert.match(source, /fetch\(`\$\{apiBaseUrl\}\/smart-search`/);
assert.doesNotMatch(
  source,
  /fetch\("http:\/\/127\.0\.0\.1:8000\/smart-search"/,
);
```

- [x] **Step 2: Run the frontend test and verify RED**

Run: `node --test frontend/tests/homepage.test.mjs`

Expected: FAIL because `page.tsx` still fetches the complete localhost URL.

- [x] **Step 3: Implement the environment-based API URL**

Add near the existing placeholder constant:

```ts
const apiBaseUrl = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");
```

Change the request to:

```ts
const response = await fetch(`${apiBaseUrl}/smart-search`, {
```

- [x] **Step 4: Run the frontend test and verify GREEN**

Run: `node --test frontend/tests/homepage.test.mjs`

Expected: all frontend tests pass.

### Task 3: Configure the production CORS origin with TDD

**Files:**
- Modify: `backend/tests/test_main.py`
- Modify: `backend/main.py`

- [x] **Step 1: Write a failing production-origin test**

```python
def test_allowed_origins_include_normalized_production_origin(monkeypatch) -> None:
    monkeypatch.setenv(
        "FRONTEND_ORIGIN",
        "https://github-task-search.vercel.app/",
    )

    assert main.get_allowed_origins() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://github-task-search.vercel.app",
    ]
```

- [x] **Step 2: Run the focused backend test and verify RED**

Run from `backend`: `.venv/Scripts/python.exe -m pytest tests/test_main.py -q`

Expected: FAIL because `get_allowed_origins` does not exist.

- [x] **Step 3: Implement the origin builder and use it in middleware**

Add after `load_dotenv()`:

```python
LOCAL_FRONTEND_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def get_allowed_origins() -> list[str]:
    origins = list(LOCAL_FRONTEND_ORIGINS)
    production_origin = os.getenv("FRONTEND_ORIGIN", "").strip().rstrip("/")
    if production_origin and production_origin not in origins:
        origins.append(production_origin)
    return origins
```

Change middleware configuration to:

```python
allow_origins=get_allowed_origins(),
```

- [x] **Step 4: Run the backend tests and verify GREEN**

Run from `backend`: `.venv/Scripts/python.exe -m pytest tests -q`

Expected: all backend tests pass.

### Task 4: Verify and commit the deployable application

**Files:**
- Modify: `.gitignore`
- Modify: `frontend/tests/homepage.test.mjs`
- Modify: `frontend/app/page.tsx`
- Modify: `backend/tests/test_main.py`
- Modify: `backend/main.py`
- Include: all existing application source, tests, examples, and design documents

- [x] **Step 1: Run all local verification**

Run:

```powershell
Push-Location backend
.venv/Scripts/python.exe -m pytest tests -q
Pop-Location
node --test frontend/tests/homepage.test.mjs
Push-Location frontend
node node_modules/next/dist/bin/next build
Pop-Location
```

Expected: backend tests pass, six frontend tests pass, and Next.js builds `/`.

- [x] **Step 2: Audit tracked candidates for secrets and generated files**

Run:

```powershell
git status --short
git check-ignore -v backend/.env frontend/node_modules frontend/.next backend/.venv
```

Expected: secrets and generated directories are ignored and are absent from
the staged set.

- [ ] **Step 3: Commit the verified application**

```powershell
git add .
git diff --cached --check
git commit -m "feat: prepare GitHub task search for cloud deployment"
```

Expected: a commit containing source, tests, lockfiles, examples, and docs, with
no `.env`, dependency directory, cache, or build output.

### Task 5: Create and push the private GitHub repository

**Files:** none

- [ ] **Step 1: Authenticate GitHub CLI through the logged-in browser**

Run: `gh auth login --hostname github.com --git-protocol https --web`

Expected: GitHub CLI reports the account `lyc20060601` as authenticated.

- [ ] **Step 2: Create the private repository and push main**

Run:

```powershell
gh repo create github-task-search --private --source . --remote origin --push
```

Expected: `origin` points to
`https://github.com/lyc20060601/github-task-search.git`, and the GitHub
repository visibility is private.

### Task 6: Deploy the FastAPI backend to Render

**Files:** none

- [ ] **Step 1: Connect Render to the private GitHub repository**

In Render, create a Web Service from
`lyc20060601/github-task-search`, granting repository access when prompted.

- [ ] **Step 2: Configure the service**

Use service name `github-task-search-api`, branch `main`, Python runtime, root
directory `backend`, build command `pip install -r requirements.txt`, and start
command `uvicorn main:app --host 0.0.0.0 --port $PORT`.

- [ ] **Step 3: Transfer backend environment variables without displaying them**

Set `GITHUB_TOKEN`, `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` from
`backend/.env`. Do not set `FRONTEND_ORIGIN` until Vercel assigns its URL.

- [ ] **Step 4: Confirm Starter billing and create the service**

Read the exact Starter instance price shown by Render, obtain user confirmation,
then create the paid service.

- [ ] **Step 5: Verify backend health and smart search**

Run HTTP checks against:

```text
https://github-task-search-api.onrender.com/
https://github-task-search-api.onrender.com/smart-search
```

Expected: root returns HTTP 200 and a real smart search returns structured task
data, generated queries, and repositories.

### Task 7: Deploy the Next.js frontend and finish CORS

**Files:** none

- [ ] **Step 1: Import the private repository into Vercel**

Create project `github-task-search`, choose `frontend` as Root Directory, and
retain Next.js auto-detected build settings.

- [ ] **Step 2: Set the production API URL and deploy**

Set:

```text
NEXT_PUBLIC_API_BASE_URL=https://github-task-search-api.onrender.com
```

Deploy and record the production `vercel.app` URL.

- [ ] **Step 3: Add the production frontend origin to Render**

Set Render `FRONTEND_ORIGIN` to the exact Vercel production origin, without a
trailing slash, and redeploy the backend.

- [ ] **Step 4: Verify the public end-to-end workflow**

Submit the drone semantic-segmentation request from the public frontend.
Verify structured AI fields, generated English queries, repository cards,
HTTP success, no CORS failure, and no browser-console error at desktop and
390px mobile widths.
