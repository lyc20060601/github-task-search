# GitHub Task Search

GitHub Task Search is a self-hosted tool for finding GitHub repositories from natural-language technical requirements. It turns a request into structured task requirements, generates multiple GitHub search queries, searches public repositories, and can produce task-aware recommendations.

The project is designed to run on the user's own computer. It does not require a cloud server.

## Features

- Natural-language GitHub repository search
- Task parsing and English query generation
- Multi-query search with de-duplication
- Task-aware repository recommendations
- README, dependency, Docker, and environment inspection
- Local machine compatibility analysis
- Optional, user-triggered repository runtime validation in a restricted Docker Sandbox

Runtime validation is never started automatically for search results. It runs only after the user explicitly selects a repository. It is a bounded smoke test, not a guarantee that a project will train successfully.

## Requirements

- Docker Desktop with a running Docker Engine on Windows or macOS, or Docker Engine on Linux
- Python 3.12 on the host when repository runtime validation is needed. On
  Windows, install the official Python Launcher and open a new PowerShell
  window after installation.
- GitHub account and a GitHub token for GitHub API access
- DeepSeek-compatible API key for task parsing and repository analysis
- At least 4 GB RAM available to Docker; more may be needed for repository validation
- Internet access for image/dependency downloads and API requests

The application itself does not require an NVIDIA GPU. A GPU/CUDA repository may still be reported as incompatible with the local machine.

## Quick Start

From the directory containing this README:

### Windows PowerShell

```powershell
Copy-Item .env.example .env
notepad .env
py -3.12 -m venv .\backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

### Linux or macOS

```sh
cp .env.example .env
$EDITOR .env
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
chmod +x scripts/start.sh scripts/stop.sh
./scripts/start.sh
```

Then open [http://localhost:3000](http://localhost:3000).

To view service status:

```sh
docker compose ps
```

To stop the application:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

On Linux or macOS:

```sh
./scripts/stop.sh
```

To rebuild after a code update:

```sh
docker compose up --build
```

Running `docker compose up` directly leaves runtime validation disabled. Use the
project start script when the host Validation Worker is required.

## Configuration

Copy `.env.example` to `.env` and fill in your own values:

```env
GITHUB_TOKEN=your_github_token_here
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
FRONTEND_ORIGIN=http://localhost:3000
VALIDATION_MODE=disabled
```

Never commit `.env`. Never put real credentials in README files, Dockerfiles, frontend code, `NEXT_PUBLIC_*` variables, screenshots, or issue reports. `GITHUB_TOKEN` and `LLM_API_KEY` are passed only to the backend container. The frontend receives only the public backend URL.

Use your own credentials. GitHub API limits and DeepSeek API charges are associated with the account that owns the credentials. DeepSeek API usage is billed by token usage; check the provider's current pricing before enabling analysis.

## Service Layout

```text
frontend  http://localhost:3000  Next.js user interface
backend   http://localhost:8000  FastAPI API
worker    outbound HTTP only     Host-side Docker Sandbox coordinator
```

The Compose file does not mount a home directory, SSH directory, or Docker socket. Both application images run as non-root users. The host Worker opens no listening port; it polls authenticated internal backend endpoints and creates a temporary restricted Sandbox only when the user explicitly requests validation. The start script creates a random per-start Worker token in process memory. It is not written to `.env` or an image.

## API Endpoints

- `GET /` backend health response
- `POST /search` direct GitHub repository search
- `POST /smart-search` task parsing and multi-query search
- `POST /recommend-search` deep repository recommendations
- `POST /validate-repository` explicit single-repository runtime validation

The final endpoint can be slow and may download dependencies inside a temporary sandbox. Do not use it for repositories you have not intentionally selected.

## Troubleshooting

### Docker is not running

Start Docker Desktop and wait until the Engine reports that it is running. Then run the start command again.

### Port 3000 or 8000 is already in use

Stop the process using the port, or change the published ports in `docker-compose.yml`. If you change the backend port, update `NEXT_PUBLIC_API_BASE_URL` in `.env` before rebuilding the frontend.

### Search fails

Check that `GITHUB_TOKEN` is valid and has access to public repository search. Check the backend logs without sharing them publicly:

```sh
docker compose logs --tail 100 backend
```

### AI parsing fails

Check `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. Do not paste the key into an issue or terminal screenshot. API quotas, provider outages, network restrictions, or invalid model names can cause this failure.

### Repository validation fails

The selected repository may require a GPU, CUDA, large memory, unavailable system packages, or a dependency download that exceeds the configured timeout. The validator intentionally limits CPU, memory, process count, network access, and execution time. A failed validation does not execute the project on the host machine.

If `/validate-repository` returns HTTP 503, check `GET /validation-status`. A
`worker_ready` value of `false` means the host Worker is not running or has not
completed its authenticated poll. Run the project start script after creating
`backend/.venv`. Search, smart search, and recommendations continue to work while
runtime validation is disabled.

### No NVIDIA GPU or CUDA

Search and static analysis still work. Compatibility analysis will report limitations for repositories that explicitly require NVIDIA/CUDA hardware. Installing software cannot create missing physical GPU memory.

## Development

Backend tests:

```sh
cd backend
python -m pytest
```

Frontend checks:

```sh
cd frontend
pnpm test
pnpm build
```

Docker is the supported reproducible path for end-to-end local startup.

## Security

Read [SECURITY.md](SECURITY.md) before reporting a vulnerability. Never submit credentials, authorization headers, `.env` contents, or private repository data in an issue.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
