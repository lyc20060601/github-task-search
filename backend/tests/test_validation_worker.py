from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from runtime.validation_worker import (
    ValidationWorker,
    WorkerAuthenticationError,
    main,
)
from runtime_report import RuntimeReport


class FakeResponse:
    def __init__(self, status_code: int, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.request = httpx.Request("POST", "http://test")

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "worker request failed",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


class FakeClient:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = iter(responses)
        self.requests: list[SimpleNamespace] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append(SimpleNamespace(url=url, **kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def _worker(client: FakeClient, *, token: str = "worker-token") -> ValidationWorker:
    return ValidationWorker(
        backend_url="http://127.0.0.1:8000/",
        token=token,
        client=client,
    )


def test_run_once_returns_false_when_poll_is_idle() -> None:
    client = FakeClient([FakeResponse(204)])

    assert _worker(client).run_once() is False
    assert client.requests[0].url == (
        "http://127.0.0.1:8000/internal/validation/jobs/next"
    )


def test_worker_validates_and_submits(monkeypatch: pytest.MonkeyPatch) -> None:
    report = RuntimeReport(full_name="owner/repository", clone_status="success")
    client = FakeClient(
        [
            FakeResponse(200, {"id": "job-1", "full_name": "owner/repository"}),
            FakeResponse(204),
        ]
    )
    monkeypatch.setattr(
        "runtime.validation_worker.validate_repository", lambda _: report
    )

    assert _worker(client).run_once() is True
    assert client.requests[1].url == (
        "http://127.0.0.1:8000/internal/validation/jobs/job-1/result"
    )
    assert client.requests[1].json == {
        "report": report.model_dump(mode="json")
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"id": "job-1"},
        {"id": "job-1", "full_name": "owner/repository", "command": "whoami"},
        ["job-1", "owner/repository"],
    ],
)
def test_malformed_job_is_rejected_without_running_validator(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
) -> None:
    client = FakeClient([FakeResponse(200, payload)])
    called = False

    def unexpected_validator(_: str) -> RuntimeReport:
        nonlocal called
        called = True
        return RuntimeReport(full_name="unexpected/repository")

    monkeypatch.setattr(
        "runtime.validation_worker.validate_repository", unexpected_validator
    )

    with pytest.raises(ValueError, match="invalid validation job response"):
        _worker(client).run_once()

    assert called is False
    assert len(client.requests) == 1


@pytest.mark.parametrize("status_code", [401, 403])
def test_authentication_failure_is_fatal(status_code: int) -> None:
    client = FakeClient([FakeResponse(status_code)])

    with pytest.raises(WorkerAuthenticationError):
        _worker(client).run_once()


def test_transient_connection_failure_is_retried_with_bounded_delays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("POST", "http://127.0.0.1:8000")
    client = FakeClient(
        [
            httpx.ConnectError("backend unavailable", request=request),
            httpx.ConnectError("backend unavailable", request=request),
            httpx.ConnectError("backend unavailable", request=request),
            httpx.ConnectError("backend unavailable", request=request),
            httpx.ConnectError("backend unavailable", request=request),
            FakeResponse(204),
        ]
    )
    delays: list[float] = []
    monkeypatch.setattr("runtime.validation_worker.time.sleep", delays.append)

    _worker(client).run()

    assert delays == [1, 2, 4, 5, 5]
    assert len(client.requests) == 6


def test_transient_server_failure_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient([FakeResponse(503), FakeResponse(204)])
    delays: list[float] = []
    monkeypatch.setattr("runtime.validation_worker.time.sleep", delays.append)

    _worker(client).run()

    assert delays == [1]


def test_transient_result_failure_retries_the_same_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("POST", "http://127.0.0.1:8000")
    report = RuntimeReport(full_name="owner/repository", clone_status="success")
    client = FakeClient(
        [
            FakeResponse(200, {"id": "job-1", "full_name": "owner/repository"}),
            httpx.ConnectError("result connection interrupted", request=request),
            FakeResponse(204),
        ]
    )
    delays: list[float] = []
    monkeypatch.setattr("runtime.validation_worker.time.sleep", delays.append)
    monkeypatch.setattr(
        "runtime.validation_worker.validate_repository", lambda _: report
    )

    assert _worker(client).run() is True

    assert delays == [1]
    assert [call.url for call in client.requests] == [
        "http://127.0.0.1:8000/internal/validation/jobs/next",
        "http://127.0.0.1:8000/internal/validation/jobs/job-1/result",
        "http://127.0.0.1:8000/internal/validation/jobs/job-1/result",
    ]
    assert client.requests[1].json == client.requests[2].json


def test_validator_exception_is_submitted_as_bounded_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "github_pat_must_not_escape"
    client = FakeClient(
        [
            FakeResponse(200, {"id": "job-1", "full_name": "owner/repository"}),
            FakeResponse(204),
        ]
    )

    def failed_validator(_: str) -> RuntimeReport:
        raise RuntimeError(f"validator exploded: {secret}")

    monkeypatch.setattr("runtime.validation_worker.validate_repository", failed_validator)

    assert _worker(client).run_once() is True
    submitted = client.requests[1].json["report"]
    assert submitted["full_name"] == "owner/repository"
    assert submitted["clone_status"] == "failed"
    assert submitted["environment_detected"] == "skipped"
    assert submitted["dependency_install_status"] == "skipped"
    assert submitted["entrypoint_detected"] == "skipped"
    assert submitted["smoke_test_status"] == "skipped"
    assert submitted["errors"] == ["Validation failed unexpectedly"]
    assert secret not in str(submitted)


def test_successful_report_diagnostics_are_bounded_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_secret = "github_" + "pat_" + ("a" * 48)
    llm_secret = "sk-" + ("b" * 32)
    host_path = r"C:\Users\alice\project\backend\runtime-temp\clone-1"
    messages = [
        f"failure {index}: {host_path} {github_secret} {llm_secret} " + ("x" * 700)
        for index in range(20)
    ]
    report = RuntimeReport(
        full_name="owner/repository",
        errors=messages,
        warnings=messages,
    )
    client = FakeClient(
        [
            FakeResponse(200, {"id": "job-1", "full_name": "owner/repository"}),
            FakeResponse(204),
        ]
    )
    monkeypatch.setenv("GITHUB_TOKEN", github_secret)
    monkeypatch.setenv("LLM_API_KEY", llm_secret)
    monkeypatch.setattr(
        "runtime.validation_worker.validate_repository", lambda _: report
    )

    _worker(client).run_once()

    submitted = client.requests[1].json["report"]
    assert len(submitted["errors"]) == 10
    assert len(submitted["warnings"]) == 10
    assert all(len(item) <= 500 for item in submitted["errors"])
    rendered = str(submitted)
    assert host_path not in rendered
    assert github_secret not in rendered
    assert llm_secret not in rendered


def test_requests_do_not_leak_unrelated_environment_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_secret = "github_pat_secret"
    llm_secret = "sk-secret"
    monkeypatch.setenv("GITHUB_TOKEN", github_secret)
    monkeypatch.setenv("LLM_API_KEY", llm_secret)
    report = RuntimeReport(full_name="owner/repository")
    monkeypatch.setattr(
        "runtime.validation_worker.validate_repository", lambda _: report
    )
    client = FakeClient(
        [
            FakeResponse(200, {"id": "job-1", "full_name": "owner/repository"}),
            FakeResponse(204),
        ]
    )

    _worker(client).run_once()

    serialized_requests = str(client.requests)
    assert github_secret not in serialized_requests
    assert llm_secret not in serialized_requests
    for request_call in client.requests:
        assert request_call.headers == {
            "Authorization": "Bearer worker-token"
        }


def test_main_handles_keyboard_interrupt_without_printing_secrets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worker_token = "worker-token-must-not-print"
    github_secret = "github-token-must-not-print"
    llm_secret = "llm-key-must-not-print"
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", worker_token)
    monkeypatch.setenv("VALIDATION_BACKEND_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("GITHUB_TOKEN", github_secret)
    monkeypatch.setenv("LLM_API_KEY", llm_secret)
    monkeypatch.setattr(
        "runtime.validation_worker.ValidationWorker.run",
        lambda self: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert main() == 0
    output = capsys.readouterr()
    rendered = output.out + output.err
    assert worker_token not in rendered
    assert github_secret not in rendered
    assert llm_secret not in rendered


def test_main_exits_on_authentication_failure_without_printing_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worker_token = "worker-token-must-not-print"
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", worker_token)
    monkeypatch.setattr(
        "runtime.validation_worker.ValidationWorker.run",
        lambda self: (_ for _ in ()).throw(WorkerAuthenticationError()),
    )

    assert main() == 3
    rendered = capsys.readouterr().err
    assert "authentication failed" in rendered.lower()
    assert worker_token not in rendered


def test_main_rejects_missing_worker_token_without_dumping_environment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("VALIDATION_WORKER_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "github-token-must-not-print")
    monkeypatch.setenv("LLM_API_KEY", "llm-key-must-not-print")

    assert main() == 2
    rendered = capsys.readouterr().err
    assert "VALIDATION_WORKER_TOKEN is required" in rendered
    assert "github-token-must-not-print" not in rendered
    assert "llm-key-must-not-print" not in rendered
