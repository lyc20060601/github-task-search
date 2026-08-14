#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"
PID_FILE="$PROJECT_ROOT/.runtime/validation-worker.pid"
worker_error=""
cd "$PROJECT_ROOT"

process_belongs_to_project() {
  candidate_pid=$1
  if ! kill -0 "$candidate_pid" 2>/dev/null; then
    return 1
  fi

  if [ -r "/proc/$candidate_pid/cmdline" ]; then
    tr '\000' ' ' <"/proc/$candidate_pid/cmdline" \
      | grep -F "$PYTHON" \
      | grep -F "runtime.validation_worker" >/dev/null 2>&1
    return $?
  fi

  if command -v ps >/dev/null 2>&1; then
    command_line=$(ps -p "$candidate_pid" -o command= 2>/dev/null || true)
    case "$command_line" in
      *"$PYTHON"*"runtime.validation_worker"*) return 0 ;;
      *) return 1 ;;
    esac
  fi

  return 1
}

pid_file_can_be_removed=0
if [ -f "$PID_FILE" ]; then
  worker_pid=$(sed -n '1p' "$PID_FILE")
  case "$worker_pid" in
    ''|*[!0-9]*)
      worker_error="Invalid validation worker PID file; it was retained."
      ;;
    *)
      if kill -0 "$worker_pid" 2>/dev/null; then
        if process_belongs_to_project "$worker_pid"; then
          kill "$worker_pid"
          attempts=0
          while kill -0 "$worker_pid" 2>/dev/null && [ "$attempts" -lt 20 ]; do
            sleep 1
            attempts=$((attempts + 1))
          done

          if kill -0 "$worker_pid" 2>/dev/null; then
            if process_belongs_to_project "$worker_pid"; then
              kill -KILL "$worker_pid"
              attempts=0
              while kill -0 "$worker_pid" 2>/dev/null && [ "$attempts" -lt 10 ]; do
                sleep 1
                attempts=$((attempts + 1))
              done
            else
              worker_error="Validation worker PID changed ownership during shutdown; it was not force-stopped."
            fi
          fi

          if kill -0 "$worker_pid" 2>/dev/null; then
            if [ -z "$worker_error" ]; then
              worker_error="Validation worker did not stop; its PID file was retained."
            fi
          else
            pid_file_can_be_removed=1
          fi
        else
          worker_error="Recorded PID does not belong to this project's validation worker; it was not stopped and its PID file was retained."
        fi
      else
        pid_file_can_be_removed=1
      fi
      ;;
  esac
  if [ "$pid_file_can_be_removed" -eq 1 ]; then
    rm -f "$PID_FILE"
  fi
fi

docker compose down

if [ -n "$worker_error" ]; then
  echo "$worker_error" >&2
  exit 1
fi
