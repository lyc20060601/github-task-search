from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from runtime.validation_jobs import (
    InvalidValidationJob,
    ValidationBusy,
    ValidationJob,
    ValidationJobCoordinator,
    ValidationJobResult,
    ValidationTimedOut,
    ValidationUnavailable,
)
from runtime_report import RuntimeReport


def test_validation_job_models_are_strict_and_forbid_extra_fields():
    with pytest.raises(ValidationError):
        ValidationJob(id=1, full_name="owner/repository")

    with pytest.raises(ValidationError):
        ValidationJob(id="job-1", full_name="owner/repository", unexpected=True)

    with pytest.raises(ValidationError):
        ValidationJobResult(
            report=RuntimeReport(full_name="owner/repository"),
            unexpected=True,
        )


@pytest.mark.parametrize("extra_field", ["command", "path"])
def test_validation_job_result_rejects_extra_report_fields(extra_field):
    with pytest.raises(ValidationError):
        ValidationJobResult.model_validate(
            {
                "report": {
                    "full_name": "owner/repository",
                    extra_field: "sensitive detail",
                }
            }
        )


def test_worker_claims_and_completes_waiting_request():
    coordinator = ValidationJobCoordinator(worker_grace_seconds=1)
    coordinator.touch_worker()

    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting = executor.submit(
            coordinator.submit_and_wait,
            "owner/repository",
            timeout_seconds=1,
        )
        job = coordinator.claim_next(wait_seconds=1)
        assert job is not None

        coordinator.complete(job.id, RuntimeReport(full_name=job.full_name))

        assert waiting.result(timeout=1).full_name == "owner/repository"


def test_second_job_is_rejected_while_first_is_queued_or_claimed():
    coordinator = ValidationJobCoordinator()
    coordinator.enqueue("owner/first")

    with pytest.raises(ValidationBusy):
        coordinator.enqueue("owner/second")

    assert coordinator.claim_next(wait_seconds=0) is not None
    with pytest.raises(ValidationBusy):
        coordinator.enqueue("owner/second")


def test_submit_requires_a_ready_worker():
    coordinator = ValidationJobCoordinator()

    with pytest.raises(ValidationUnavailable):
        coordinator.submit_and_wait("owner/repository", timeout_seconds=0.01)


def test_busy_takes_priority_over_worker_unavailable():
    coordinator = ValidationJobCoordinator()
    coordinator.enqueue("owner/first")

    with pytest.raises(ValidationBusy):
        coordinator.submit_and_wait("owner/second", timeout_seconds=0.01)


def test_worker_readiness_expires_after_grace_period(monkeypatch):
    now = 100.0
    monkeypatch.setattr("runtime.validation_jobs.time.monotonic", lambda: now)
    coordinator = ValidationJobCoordinator(worker_grace_seconds=5)

    assert coordinator.worker_ready() is False
    coordinator.touch_worker()
    assert coordinator.worker_ready() is True

    now = 105.01
    assert coordinator.worker_ready() is False
    with pytest.raises(ValidationUnavailable):
        coordinator.submit_and_wait("owner/repository", timeout_seconds=1)


def test_worker_poll_refreshes_readiness(monkeypatch):
    now = 100.0
    monkeypatch.setattr("runtime.validation_jobs.time.monotonic", lambda: now)
    coordinator = ValidationJobCoordinator(worker_grace_seconds=5)

    assert coordinator.worker_ready() is False
    assert coordinator.claim_next(wait_seconds=0) is None
    assert coordinator.worker_ready() is True

    now = 104.0
    assert coordinator.claim_next(wait_seconds=0) is None
    now = 108.0
    assert coordinator.worker_ready() is True


def test_wait_timeout_clears_the_slot_and_rejects_late_result():
    coordinator = ValidationJobCoordinator(worker_grace_seconds=1)
    coordinator.touch_worker()

    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting = executor.submit(
            coordinator.submit_and_wait,
            "owner/first",
            timeout_seconds=0.05,
        )
        job = coordinator.claim_next(wait_seconds=1)
        assert job is not None

        with pytest.raises(ValidationTimedOut):
            waiting.result(timeout=1)

    replacement = coordinator.enqueue("owner/second")
    assert replacement.full_name == "owner/second"
    with pytest.raises(InvalidValidationJob):
        coordinator.complete(job.id, RuntimeReport(full_name=job.full_name))


def test_complete_rejects_a_report_for_a_different_repository():
    coordinator = ValidationJobCoordinator()
    job = coordinator.enqueue("owner/repository")
    assert coordinator.claim_next(wait_seconds=0) == job

    with pytest.raises(InvalidValidationJob):
        coordinator.complete(job.id, RuntimeReport(full_name="other/repository"))

    coordinator.complete(job.id, RuntimeReport(full_name=job.full_name))
    replacement = coordinator.enqueue("owner/next")
    assert replacement.full_name == "owner/next"


def test_complete_rejects_unknown_and_stale_job_ids():
    coordinator = ValidationJobCoordinator()
    first = coordinator.enqueue("owner/first")

    with pytest.raises(InvalidValidationJob):
        coordinator.complete("unknown", RuntimeReport(full_name=first.full_name))

    assert coordinator.claim_next(wait_seconds=0) == first
    coordinator.complete(first.id, RuntimeReport(full_name=first.full_name))
    coordinator.enqueue("owner/second")

    with pytest.raises(InvalidValidationJob):
        coordinator.complete(first.id, RuntimeReport(full_name=first.full_name))


def test_claim_returns_each_job_only_once():
    coordinator = ValidationJobCoordinator()
    queued = coordinator.enqueue("owner/repository")

    assert coordinator.claim_next(wait_seconds=0) == queued
    assert coordinator.claim_next(wait_seconds=0) is None


def test_complete_rejects_an_unclaimed_job():
    coordinator = ValidationJobCoordinator()
    job = coordinator.enqueue("owner/repository")

    with pytest.raises(InvalidValidationJob):
        coordinator.complete(job.id, RuntimeReport(full_name=job.full_name))

    assert coordinator.claim_next(wait_seconds=0) == job
    coordinator.complete(job.id, RuntimeReport(full_name=job.full_name))
