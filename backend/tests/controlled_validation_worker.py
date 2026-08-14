"""Process-level Worker fixture for the local Compose acceptance test."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from runtime import validation_worker  # noqa: E402
from runtime_report import RuntimeReport  # noqa: E402


def controlled_validate_repository(full_name: str) -> RuntimeReport:
    """Return a fixed report without network, Docker, or repository execution."""

    time.sleep(float(os.getenv("VALIDATION_CONTROLLED_DELAY_SECONDS", "2")))
    return RuntimeReport(
        full_name=full_name,
        clone_status="success",
        environment_detected="success",
        dependency_install_status="success",
        entrypoint_detected="success",
        smoke_test_status="success",
        runtime_score=100,
    )


validation_worker.validate_repository = controlled_validate_repository


if __name__ == "__main__":
    raise SystemExit(validation_worker.main())
