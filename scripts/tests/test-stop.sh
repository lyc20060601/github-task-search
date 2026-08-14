#!/usr/bin/env sh
set -eu

SOURCE_ROOT=${1:?project root is required}
TEST_ROOT=$(mktemp -d)
ORIGINAL_PATH=$PATH

cleanup() {
  if [ -n "${worker_pid:-}" ]; then
    kill -KILL "$worker_pid" 2>/dev/null || true
  fi
  if [ -n "${unrelated_pid:-}" ]; then
    kill -KILL "$unrelated_pid" 2>/dev/null || true
  fi
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT INT TERM

make_fixture() {
  fixture=$1
  mkdir -p "$fixture/scripts" "$fixture/backend/.venv/bin" "$fixture/.runtime" "$fixture/fake-bin"
  cp "$SOURCE_ROOT/scripts/stop.sh" "$fixture/scripts/stop.sh"
  cat >"$fixture/fake-bin/docker" <<'EOF'
#!/usr/bin/env sh
exit 0
EOF
  cat >"$fixture/fake-bin/sleep" <<'EOF'
#!/usr/bin/env sh
exit 0
EOF
  chmod +x "$fixture/scripts/stop.sh" "$fixture/fake-bin/docker" "$fixture/fake-bin/sleep"
}

owned_fixture="$TEST_ROOT/owned"
make_fixture "$owned_fixture"
cat >"$owned_fixture/backend/.venv/bin/python" <<'EOF'
trap '' TERM
while :; do /bin/sleep 1; done
EOF
cat >"$owned_fixture/launch-worker" <<EOF
#!/usr/bin/env sh
/bin/sh "$owned_fixture/backend/.venv/bin/python" runtime.validation_worker &
child_pid=\$!
printf '%s\\n' "\$child_pid" >"$owned_fixture/.runtime/validation-worker.pid"
wait "\$child_pid"
EOF
chmod +x "$owned_fixture/launch-worker"
sh "$owned_fixture/launch-worker" &
launcher_pid=$!
attempts=0
while [ ! -s "$owned_fixture/.runtime/validation-worker.pid" ] && [ "$attempts" -lt 100 ]; do
  /bin/sleep 0.01
  attempts=$((attempts + 1))
done
worker_pid=$(sed -n '1p' "$owned_fixture/.runtime/validation-worker.pid")

PATH="$owned_fixture/fake-bin:$ORIGINAL_PATH" sh "$owned_fixture/scripts/stop.sh"

if kill -0 "$worker_pid" 2>/dev/null; then
  echo "owned worker survived stop.sh" >&2
  exit 1
fi
wait "$launcher_pid" 2>/dev/null || true
worker_pid=
if [ -e "$owned_fixture/.runtime/validation-worker.pid" ]; then
  echo "owned worker PID file was not removed after confirmed termination" >&2
  exit 1
fi

unrelated_fixture="$TEST_ROOT/unrelated"
make_fixture "$unrelated_fixture"
while :; do :; done &
unrelated_pid=$!
printf '%s\n' "$unrelated_pid" >"$unrelated_fixture/.runtime/validation-worker.pid"

if PATH="$unrelated_fixture/fake-bin:$ORIGINAL_PATH" sh "$unrelated_fixture/scripts/stop.sh"; then
  echo "stop.sh succeeded for an unrelated PID" >&2
  exit 1
fi
if ! kill -0 "$unrelated_pid" 2>/dev/null; then
  echo "stop.sh terminated an unrelated PID" >&2
  exit 1
fi
if [ ! -e "$unrelated_fixture/.runtime/validation-worker.pid" ]; then
  echo "stop.sh removed the PID file for an unrelated process" >&2
  exit 1
fi

echo "stop.sh behavioral shutdown tests passed"
