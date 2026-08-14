#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKEND_ROOT="$PROJECT_ROOT/backend"
PYTHON="$BACKEND_ROOT/.venv/bin/python"
RUNTIME_ROOT="$PROJECT_ROOT/.runtime"
PID_FILE="$RUNTIME_ROOT/validation-worker.pid"
worker_pid=""
compose_started=0
cd "$PROJECT_ROOT"

check_prerequisites() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker command was not found. Install Docker Desktop or Docker Engine first." >&2
    exit 1
  fi
  if [ ! -x "$PYTHON" ]; then
    echo "Backend virtual environment was not found. Create backend/.venv and install backend requirements first." >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose is not available." >&2
    exit 1
  fi
}

cleanup_on_exit() {
  status=$?
  unset worker_token VALIDATION_WORKER_TOKEN VALIDATION_BACKEND_URL VALIDATION_MODE
  if [ "$status" -ne 0 ]; then
    if [ -n "$worker_pid" ] && kill -0 "$worker_pid" 2>/dev/null; then
      kill "$worker_pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    if [ "$compose_started" -eq 1 ]; then
      docker compose down >/dev/null 2>&1 || true
    fi
  fi
}

check_prerequisites
if [ "${1:-}" = "--validate-only" ]; then
  if [ "$#" -ne 1 ]; then
    echo "--validate-only does not accept additional arguments." >&2
    exit 2
  fi
  echo "Lifecycle prerequisites are valid."
  exit 0
fi
if [ "$#" -ne 0 ]; then
  echo "Usage: $0 [--validate-only]" >&2
  exit 2
fi

trap cleanup_on_exit EXIT
trap 'exit 130' HUP INT TERM

if ! docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
  echo "Docker Engine is not running. Start Docker Desktop and run this script again." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "Warning: .env was not found. Copy .env.example to .env and add your own API keys before using search." >&2
fi

if [ -f "$PID_FILE" ]; then
  existing_pid=$(sed -n '1p' "$PID_FILE")
  case "$existing_pid" in
    ''|*[!0-9]*) ;;
    *)
      if kill -0 "$existing_pid" 2>/dev/null; then
        echo "A validation worker recorded for this project is already running." >&2
        exit 1
      fi
      ;;
  esac
  rm -f "$PID_FILE"
fi

worker_token=$("$PYTHON" -c "import secrets; print(secrets.token_urlsafe(32))")
VALIDATION_MODE=worker
VALIDATION_WORKER_TOKEN=$worker_token
VALIDATION_BACKEND_URL=http://127.0.0.1:8000
export VALIDATION_MODE VALIDATION_WORKER_TOKEN VALIDATION_BACKEND_URL

compose_started=1
docker compose up --build --detach

attempt=0
until "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2).read()" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "Backend did not become healthy within 60 seconds." >&2
    exit 1
  fi
  sleep 1
done

cd "$BACKEND_ROOT"
nohup "$PYTHON" -m runtime.validation_worker >/dev/null 2>&1 &
worker_pid=$!
cd "$PROJECT_ROOT"

mkdir -p "$RUNTIME_ROOT"
printf '%s\n' "$worker_pid" >"$PID_FILE"

attempt=0
until "$PYTHON" -c "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/validation-status', timeout=2)); raise SystemExit(0 if data.get('mode') == 'worker' and data.get('worker_ready') is True else 1)" >/dev/null 2>&1; do
  if ! kill -0 "$worker_pid" 2>/dev/null; then
    echo "Validation worker exited before becoming ready." >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "Validation worker did not become ready within 30 seconds." >&2
    exit 1
  fi
  sleep 1
done

unset worker_token VALIDATION_WORKER_TOKEN VALIDATION_BACKEND_URL VALIDATION_MODE
trap - EXIT HUP INT TERM
echo "Application and validation worker started."
