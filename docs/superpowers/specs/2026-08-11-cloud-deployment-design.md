# Cloud Deployment Design

## Goal

Deploy GitHub Task Search so it remains publicly available when the developer
computer is offline. Keep local development working and do not add a database.

## Selected Architecture

- Source: one private GitHub repository named `github-task-search`.
- Frontend: the existing Next.js application on Vercel Hobby.
- Backend: the existing FastAPI application on a paid Render Starter web
  service so it does not spin down when idle.
- External services: the existing GitHub Search and DeepSeek-compatible LLM
  credentials, stored only as encrypted Render environment variables.

The user selected this architecture over two alternatives:

1. Hosting both applications on Render, which is operationally simpler but is
   less natural for the existing Next.js frontend.
2. Hosting both applications on a VPS, which offers more control but requires
   ongoing operating-system, reverse-proxy, TLS, and process maintenance.

## Application Configuration

### Frontend

The frontend reads `NEXT_PUBLIC_API_BASE_URL`. When it is absent, it falls back
to `http://127.0.0.1:8000` so the current local workflow remains unchanged.
The smart-search request is sent to `${API_BASE_URL}/smart-search`.

### Backend

The backend reads `FRONTEND_ORIGIN`. CORS always permits the existing local
origins and additionally permits the configured production Vercel origin.
Trailing slashes are normalized so the configured value matches browser Origin
headers reliably.

### Secret Handling

The repository must ignore all `.env` files, dependency directories, build
artifacts, Python caches, and test caches. `.env.example` remains tracked.
The existing credential values are transferred from `backend/.env` directly to
Render without printing them or committing them.

The user explicitly chose to keep the previously exposed GitHub and DeepSeek
credentials. This is accepted for this deployment, with the known risk that
those credentials may be abused and should be rotated later.

## Repository Layout

The existing monorepo layout is preserved:

```text
github-task-search/
  frontend/
  backend/
```

Vercel uses `frontend` as its root directory. Render uses `backend` as its root
directory.

## Render Service

- Service name: `github-task-search-api`
- Runtime: Python
- Branch: `main`
- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health endpoint: `GET /`
- Instance: Starter, selected only after the user confirms the current price
  displayed by Render at the final creation step.
- Environment variables: `GITHUB_TOKEN`, `LLM_API_KEY`, `LLM_BASE_URL`,
  `LLM_MODEL`, and later `FRONTEND_ORIGIN`.

## Vercel Project

- Team: `github-task-search`
- Project name: `github-task-search`
- Framework: Next.js auto-detection
- Root directory: `frontend`
- Environment variable:
  `NEXT_PUBLIC_API_BASE_URL=https://github-task-search-api.onrender.com`

After Vercel assigns the production URL, Render receives that exact URL as
`FRONTEND_ORIGIN` and redeploys.

## Deployment Flow

1. Add configuration tests and verify they fail for the missing behavior.
2. Implement frontend API-base configuration, backend production CORS, and a
   repository-level `.gitignore`.
3. Run frontend tests, backend tests, and the Next.js production build.
4. Initialize Git on `main`, commit the verified project, create the private
   GitHub repository, and push.
5. Connect Render to the private repository, configure the backend service and
   secrets, confirm the displayed Starter price, and deploy.
6. Import the private repository into Vercel, configure the frontend root and
   backend URL, and deploy.
7. Add the Vercel origin to Render and redeploy the backend.
8. Verify the public backend health endpoint and run a real smart search from
   the public frontend on desktop and mobile widths.

## Error Handling And Rollback

- A missing frontend environment variable continues to use the local backend.
- A missing production origin does not prevent the backend from starting; it
  simply limits CORS to the two local origins.
- Existing frontend error handling remains unchanged.
- Both platforms deploy from Git. A failed deployment leaves the last
  successful deployment available, and a code rollback is performed by
  reverting the relevant Git commit and redeploying.

## Verification Criteria

- No real secret appears in tracked files or Git history.
- All backend tests pass, including production-origin CORS coverage.
- All frontend tests pass, including environment-based API URL coverage.
- The Next.js production build succeeds.
- The Render root endpoint returns HTTP 200 publicly.
- A public `/smart-search` request returns `task_spec`,
  `generated_queries`, and repositories.
- The Vercel page completes a real Chinese-language search without CORS or
  browser-console errors.
