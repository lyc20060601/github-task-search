"""Outbound-only host worker for repository runtime validation."""

from __future__ import annotations

import os
import re
import signal
import sys
import threading
import time
from types import FrameType
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from runtime_report import RuntimeReport

from .validation_jobs import ValidationJob, ValidationJobResult
from .validator import validate_repository


_POLL_PATH = "/internal/validation/jobs/next"
_RESULT_PATH = "/internal/validation/jobs/{job_id}/result"
_RETRY_DELAYS_SECONDS = (1, 2, 4, 5)
_HTTP_TIMEOUT = httpx.Timeout(35.0, connect=5.0)
_MAX_DIAGNOSTICS = 10
_MAX_DIAGNOSTIC_LENGTH = 500
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)\b[A-Z]:[\\/][^\s\"'<>|]+")
_POSIX_ABSOLUTE_PATH = re.compile(r"(?<![:\w])/(?:[^\s\"'<>]+)")
_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
)


class WorkerAuthenticationError(RuntimeError):
    """The backend rejected the worker's credentials."""


def _sanitize_diagnostic(message: str) -> str:
    sanitized = _WINDOWS_ABSOLUTE_PATH.sub("<host-path>", message)
    sanitized = _POSIX_ABSOLUTE_PATH.sub("<host-path>", sanitized)
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("<redacted>", sanitized)
    for environment_name in (
        "GITHUB_TOKEN",
        "LLM_API_KEY",
        "VALIDATION_WORKER_TOKEN",
    ):
        secret = os.getenv(environment_name, "")
        if secret:
            sanitized = sanitized.replace(secret, "<redacted>")
    if len(sanitized) > _MAX_DIAGNOSTIC_LENGTH:
        return sanitized[: _MAX_DIAGNOSTIC_LENGTH - 3] + "..."
    return sanitized


def _sanitize_report(report: RuntimeReport) -> RuntimeReport:
    return report.model_copy(
        update={
            "errors": [
                _sanitize_diagnostic(message)
                for message in report.errors[:_MAX_DIAGNOSTICS]
            ],
            "warnings": [
                _sanitize_diagnostic(message)
                for message in report.warnings[:_MAX_DIAGNOSTICS]
            ],
        }
    )


class ValidationWorker:
    """Poll the backend, run its fixed validator, and submit one result."""

    def __init__(
        self,
        *,
        backend_url: str,
        token: str,
        client: httpx.Client | None = None,
    ) -> None:
        if not token:
            raise ValueError("validation worker token is required")

        self._backend_url = backend_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._client = client or httpx.Client(
            timeout=_HTTP_TIMEOUT,
            trust_env=False,
        )
        self._owns_client = client is None
        self._stopped = threading.Event()

    def run_once(self) -> bool:
        """Process at most one job, returning whether a job was processed."""

        response = self._post_with_retry(_POLL_PATH)
        if response.status_code == 204:
            return False

        try:
            job = ValidationJob.model_validate(response.json())
        except (ValidationError, TypeError, ValueError) as exc:
            raise ValueError("invalid validation job response") from exc

        try:
            report = validate_repository(job.full_name)
        except Exception:
            report = RuntimeReport(
                full_name=job.full_name,
                clone_status="failed",
                environment_detected="skipped",
                dependency_install_status="skipped",
                entrypoint_detected="skipped",
                smoke_test_status="skipped",
                errors=["Validation failed unexpectedly"],
            )

        result = ValidationJobResult(report=_sanitize_report(report))
        job_id = quote(job.id, safe="")
        self._post_with_retry(
            _RESULT_PATH.format(job_id=job_id),
            json=result.model_dump(mode="json"),
        )
        return True

    def run(self) -> bool:
        """Retry transient failures until one bounded poll attempt succeeds."""

        try:
            return self.run_once()
        except InterruptedError:
            return False

    def stop(self) -> None:
        """Request shutdown without opening or managing any listener."""

        self._stopped.set()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _post_with_retry(
        self,
        path: str,
        *,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        failure_count = 0
        while not self._stopped.is_set():
            request_kwargs: dict[str, object] = {"headers": self._headers}
            if json is not None:
                request_kwargs["json"] = json

            try:
                response = self._client.post(
                    f"{self._backend_url}{path}",
                    **request_kwargs,
                )
                self._raise_for_worker_status(response)
                return response
            except httpx.RequestError:
                pass
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise

            delay = _RETRY_DELAYS_SECONDS[
                min(failure_count, len(_RETRY_DELAYS_SECONDS) - 1)
            ]
            failure_count += 1
            time.sleep(delay)

        raise InterruptedError("validation worker stopped")

    @staticmethod
    def _raise_for_worker_status(response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise WorkerAuthenticationError(
                "validation worker authentication failed"
            )
        response.raise_for_status()


def main() -> int:
    """Run the validation worker from its two dedicated environment values."""

    backend_url = os.getenv(
        "VALIDATION_BACKEND_URL",
        "http://127.0.0.1:8000",
    ).strip()
    token = os.getenv("VALIDATION_WORKER_TOKEN", "")
    if not token:
        print("VALIDATION_WORKER_TOKEN is required", file=sys.stderr)
        return 2

    try:
        worker = ValidationWorker(backend_url=backend_url, token=token)
    except ValueError:
        print("Validation worker configuration is invalid", file=sys.stderr)
        return 2

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        worker.stop()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    try:
        while not worker._stopped.is_set():
            try:
                worker.run()
            except WorkerAuthenticationError:
                print(
                    "Validation worker authentication failed",
                    file=sys.stderr,
                )
                return 3
            except (ValueError, httpx.HTTPStatusError):
                print(
                    "Validation worker received an invalid backend response",
                    file=sys.stderr,
                )
                time.sleep(_RETRY_DELAYS_SECONDS[-1])
    except KeyboardInterrupt:
        worker.stop()
    finally:
        worker.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
