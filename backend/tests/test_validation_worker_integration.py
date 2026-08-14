from concurrent.futures import ThreadPoolExecutor
import time
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

import main
from runtime import validation_gateway, validation_worker
from runtime.validation_jobs import ValidationJobCoordinator
from runtime.validation_worker import ValidationWorker
from runtime_report import RuntimeReport


class _TestClientAdapter:
    """Expose TestClient through the small httpx surface used by the Worker."""

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def post(self, url: str, **kwargs: object):
        return self._client.post(urlsplit(url).path, **kwargs)


def test_public_request_round_trips_through_host_worker_without_repository_code(
    monkeypatch,
) -> None:
    token = "integration-worker-token"
    coordinator = ValidationJobCoordinator(worker_grace_seconds=5)
    client = TestClient(main.app)
    report = RuntimeReport(
        full_name="owner/repository",
        clone_status="success",
        runtime_score=91,
    )

    monkeypatch.setenv("VALIDATION_MODE", "worker")
    monkeypatch.setenv("VALIDATION_WORKER_TOKEN", token)
    monkeypatch.setattr(main, "COORDINATOR", coordinator)
    monkeypatch.setattr(validation_gateway, "COORDINATOR", coordinator)
    monkeypatch.setattr(
        validation_worker,
        "validate_repository",
        lambda full_name: report,
    )

    worker = ValidationWorker(
        backend_url="http://testserver",
        token=token,
        client=_TestClientAdapter(client),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        worker_future = executor.submit(worker.run_once)
        deadline = time.monotonic() + 2
        while client.get("/validation-status").json()["worker_ready"] is not True:
            assert not worker_future.done()
            assert time.monotonic() < deadline
            time.sleep(0.01)
        response = client.post(
            "/validate-repository",
            json={"full_name": "owner/repository"},
        )

        assert response.status_code == 200
        assert response.json() == report.model_dump(mode="json")
        assert worker_future.result(timeout=5) is True
