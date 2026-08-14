"""Thread-safe coordination for host-side repository validation."""

from dataclasses import dataclass
import threading
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, field_validator

from runtime_report import RuntimeReport


class ValidationJob(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    full_name: str


class ValidationJobResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    report: RuntimeReport

    @field_validator("report", mode="before")
    @classmethod
    def reject_extra_report_fields(cls, value: object) -> object:
        if isinstance(value, dict):
            extra_fields = value.keys() - RuntimeReport.model_fields.keys()
            if extra_fields:
                names = ", ".join(sorted(extra_fields))
                raise ValueError(f"unexpected validation report fields: {names}")
        return value


class ValidationBusy(RuntimeError):
    pass


class ValidationUnavailable(RuntimeError):
    pass


class ValidationTimedOut(RuntimeError):
    pass


class InvalidValidationJob(RuntimeError):
    pass


@dataclass
class _JobSlot:
    job: ValidationJob
    claimed: bool = False
    report: RuntimeReport | None = None


class ValidationJobCoordinator:
    """Coordinate at most one queued or claimed validation job."""

    def __init__(self, *, worker_grace_seconds: float = 15) -> None:
        self._worker_grace_seconds = worker_grace_seconds
        self._worker_touched_at: float | None = None
        self._slot: _JobSlot | None = None
        self._condition = threading.Condition()

    def touch_worker(self) -> None:
        with self._condition:
            self._worker_touched_at = time.monotonic()
            self._condition.notify_all()

    def worker_ready(self) -> bool:
        with self._condition:
            return self._worker_ready_locked(time.monotonic())

    def enqueue(self, full_name: str) -> ValidationJob:
        with self._condition:
            return self._enqueue_locked(full_name).job

    def submit_and_wait(
        self,
        full_name: str,
        *,
        timeout_seconds: float,
    ) -> RuntimeReport:
        with self._condition:
            if self._slot is not None:
                raise ValidationBusy("another repository validation is in progress")

            now = time.monotonic()
            if not self._worker_ready_locked(now):
                raise ValidationUnavailable("validation worker is unavailable")

            slot = self._enqueue_locked(full_name)
            deadline = now + max(0, timeout_seconds)
            while slot.report is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if self._slot is slot:
                        self._slot = None
                        self._condition.notify_all()
                    raise ValidationTimedOut("repository validation timed out")
                self._condition.wait(remaining)

            return slot.report

    def claim_next(self, *, wait_seconds: float) -> ValidationJob | None:
        with self._condition:
            now = time.monotonic()
            self._worker_touched_at = now
            deadline = now + max(0, wait_seconds)
            while True:
                if self._slot is not None and not self._slot.claimed:
                    self._slot.claimed = True
                    return self._slot.job

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)

    def complete(self, job_id: str, report: RuntimeReport) -> None:
        with self._condition:
            slot = self._slot
            if slot is None or slot.job.id != job_id:
                raise InvalidValidationJob("validation job is unknown or expired")
            if not slot.claimed:
                raise InvalidValidationJob("validation job has not been claimed")
            if report.full_name != slot.job.full_name:
                raise InvalidValidationJob("validation report repository does not match job")

            slot.report = report
            self._slot = None
            self._condition.notify_all()

    def _worker_ready_locked(self, now: float) -> bool:
        return (
            self._worker_touched_at is not None
            and now - self._worker_touched_at <= self._worker_grace_seconds
        )

    def _enqueue_locked(self, full_name: str) -> _JobSlot:
        if self._slot is not None:
            raise ValidationBusy("another repository validation is in progress")

        slot = _JobSlot(
            job=ValidationJob(id=uuid4().hex, full_name=full_name),
        )
        self._slot = slot
        self._condition.notify_all()
        return slot
