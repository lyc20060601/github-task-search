from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_compose_configures_an_outbound_host_worker_only() -> None:
    compose = _read("docker-compose.yml")
    lowered = compose.lower()

    assert "VALIDATION_MODE: ${VALIDATION_MODE:-disabled}" in compose
    assert "VALIDATION_WORKER_TOKEN: ${VALIDATION_WORKER_TOKEN:-}" in compose
    assert "docker.sock" not in lowered
    assert "privileged" not in lowered
    assert "host.docker.internal" not in lowered
    service_names = re.findall(r"^\s{2}([a-zA-Z0-9_-]+):\s*$", compose, re.MULTILINE)
    assert "backend" in service_names
    assert "frontend" in service_names
    assert not any("worker" in name.lower() for name in service_names)


def test_example_environments_disable_validation_without_a_token() -> None:
    for relative_path in (".env.example", "backend/.env.example"):
        example = _read(relative_path)
        assert re.search(r"^VALIDATION_MODE=disabled\s*$", example, re.MULTILINE)
        assert not re.search(
            r"^\s*(?:export\s+)?VALIDATION_WORKER_TOKEN\s*=",
            example,
            re.MULTILINE,
        )


def test_runtime_state_is_ignored() -> None:
    assert re.search(r"^\.runtime/\s*$", _read(".gitignore"), re.MULTILINE)


def test_start_scripts_generate_ephemeral_tokens_without_printing_them() -> None:
    powershell = _read("scripts/start.ps1")
    shell = _read("scripts/start.sh")

    assert "RandomNumberGenerator" in powershell
    assert ".GetBytes($tokenBytes)" in powershell
    assert "-m runtime.validation_worker" in powershell
    assert "Wait-ForWorker" in powershell
    assert "/validation-status" in powershell
    assert "[switch]$ValidateOnly" in powershell
    assert '"--detach"' in powershell
    assert "secrets.token_urlsafe(32)" in shell
    assert "-m runtime.validation_worker" in shell
    assert "/validation-status" in shell
    assert "--validate-only" in shell
    assert "--detach" in shell

    for script in (powershell, shell):
        lowered = script.lower()
        assert "validation-worker.pid" in lowered
        assert "pkill" not in lowered
        assert "killall" not in lowered
        assert not re.search(r"(?:echo|write-(?:host|output))[^\n]*worker_token", lowered)


def test_stop_scripts_only_terminate_the_recorded_numeric_pid() -> None:
    powershell = _read("scripts/stop.ps1")
    shell = _read("scripts/stop.sh")

    assert "TryParse" in powershell
    assert "Stop-Process -Id $workerPid" in powershell
    assert "docker compose down" in powershell
    assert "pkill" not in powershell.lower()
    assert "killall" not in powershell.lower()

    assert "validation-worker.pid" in shell
    assert re.search(r"kill\s+\"\$worker_pid\"", shell)
    assert 'ps -p "$candidate_pid" -o command=' in shell
    assert 'kill -KILL "$worker_pid"' in shell
    assert "pid_file_can_be_removed" in shell
    assert "its PID file was retained" in shell
    assert "docker compose down" in shell
    assert "pkill" not in shell.lower()
    assert "killall" not in shell.lower()
    assert "kill *" not in shell


def test_self_hosted_smoke_isolates_compose_and_verifies_cleanup() -> None:
    smoke = _read("tests/self_hosted_smoke.ps1")

    assert "$composeProject" in smoke
    assert "--project-name $composeProject" in smoke
    assert '@("down", "--remove-orphans")' in smoke
    assert "ps --all --quiet" in smoke
    assert "Self-hosted smoke test passed." in smoke
    assert smoke.index('@("down", "--remove-orphans")') < smoke.index(
        'Write-Host "Self-hosted smoke test passed."'
    )


def test_self_hosted_smoke_clears_and_restores_host_configuration() -> None:
    smoke = _read("tests/self_hosted_smoke.ps1")

    for name in (
        "GITHUB_TOKEN",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "FRONTEND_ORIGIN",
        "NEXT_PUBLIC_API_BASE_URL",
        "VALIDATION_MODE",
        "VALIDATION_WORKER_TOKEN",
    ):
        assert f'"{name}"' in smoke
    assert 'SetEnvironmentVariable($name, $null, "Process")' in smoke
    assert 'SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")' in smoke


def test_controlled_worker_smoke_covers_the_published_protocol() -> None:
    smoke = _read("tests/validation_worker_smoke.ps1")
    controlled_worker = _read("backend/tests/controlled_validation_worker.py")

    assert "/validation-status" in smoke
    assert "/validate-repository" in smoke
    assert "/internal/validation/jobs/next" in smoke
    assert "429" in smoke
    assert "401" in smoke
    assert "503" in smoke
    assert "Stop-ControlledWorker" in smoke
    assert "validation_worker.main()" in controlled_worker
    assert "validation_worker.validate_repository = controlled_validate_repository" in (
        controlled_worker
    )
    assert "RuntimeReport" in controlled_worker


def test_controlled_worker_smoke_confirms_worker_exit_on_every_path() -> None:
    smoke = _read("tests/validation_worker_smoke.ps1")

    assert "[switch]$FailAfterWorkerReady" in smoke
    assert 'throw "Intentional Worker smoke-test failure."' in smoke
    assert "function Stop-ControlledWorker" in smoke
    assert smoke.count("Stop-ControlledWorker") >= 3
    assert 'throw "Controlled validation Worker did not stop."' in smoke
    assert "$cleanupFailure" in smoke
