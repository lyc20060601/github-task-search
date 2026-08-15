"""Safe shallow cloning for public GitHub repositories.

This module only downloads repository contents. It never invokes a command
from the cloned repository and never executes README content.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4


CLONE_TIMEOUT_SECONDS = 120
_FULL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_PROJECT_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


@dataclass(frozen=True)
class CloneResult:
    """Structured result returned by :func:`clone_repository`."""

    full_name: str
    clone_status: str
    path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def _failure(full_name: str, message: str) -> CloneResult:
    return CloneResult(full_name=full_name, clone_status="failed", error=message)


def clone_repository(
    full_name: str,
    *,
    timeout_seconds: int = CLONE_TIMEOUT_SECONDS,
) -> CloneResult:
    """Clone one public GitHub repository into the project's temporary area.

    ``full_name`` must be an owner/repository pair. The command uses an
    argument list (never a shell), shallow history, and no credentials, so a
    private repository is not accepted by this public-only operation.
    """

    if not isinstance(full_name, str) or not _FULL_NAME_PATTERN.fullmatch(full_name):
        return _failure(full_name if isinstance(full_name, str) else "", "full_name must be owner/repository")
    if timeout_seconds <= 0:
        return _failure(full_name, "timeout_seconds must be positive")

    owner, repository = full_name.split("/", maxsplit=1)
    clone_url = f"https://github.com/{owner}/{repository}.git"
    _PROJECT_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    target = _PROJECT_TEMP_ROOT / f"{owner}-{repository}-{uuid4().hex}"

    command = ["git", "-c", "credential.helper="]
    if platform.system() == "Windows":
        command.extend(
            [
                "-c",
                "http.sslBackend=schannel",
                "-c",
                "http.version=HTTP/1.1",
            ]
        )
    command.extend(["clone", "--depth", "1", clone_url, str(target)])

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
    except FileNotFoundError:
        return _failure(full_name, "git command is not available")
    except subprocess.TimeoutExpired:
        shutil.rmtree(target, ignore_errors=True)
        return _failure(full_name, f"clone timed out after {timeout_seconds} seconds")
    except OSError as exc:
        shutil.rmtree(target, ignore_errors=True)
        return _failure(full_name, f"unable to start git clone: {exc}")

    if completed.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        detail = (completed.stderr or completed.stdout or "git clone failed").strip()
        return _failure(full_name, detail[-2000:])

    return CloneResult(
        full_name=full_name,
        clone_status="success",
        path=str(target),
    )
