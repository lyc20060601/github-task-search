import base64
import binascii
import os
from typing import Any

import httpx
from dotenv import load_dotenv

from repo_reader import GITHUB_API_URL, _github_headers


MAX_FILE_SIZE_BYTES = 512 * 1024
REQUEST_TIMEOUT_SECONDS = 15.0

FILE_GROUPS = (
    ("README.md", "README", "README.rst"),
    ("requirements.txt",),
    ("pyproject.toml",),
    ("setup.py",),
    ("setup.cfg",),
    ("environment.yml", "environment.yaml"),
    ("Dockerfile",),
    ("docker-compose.yml", "docker-compose.yaml"),
    ("Pipfile",),
    ("runtime.txt",),
    (".python-version",),
)


class RepositoryEnvironmentFetchError(RuntimeError):
    """Raised when an environment file fetch cannot be started safely."""


def _decode_file_payload(payload: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        raise ValueError("GitHub file response must be an object")

    declared_size = payload.get("size")
    if not isinstance(declared_size, int) or isinstance(declared_size, bool):
        raise ValueError("GitHub file response has an invalid size")
    if declared_size > MAX_FILE_SIZE_BYTES:
        return None, f"file exceeds {MAX_FILE_SIZE_BYTES} byte limit"

    content = payload.get("content")
    if payload.get("encoding") != "base64" or not isinstance(content, str):
        raise ValueError("GitHub file response is not Base64 encoded")

    try:
        decoded = base64.b64decode(content, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("GitHub file response contains invalid Base64") from exc
    if len(decoded) > MAX_FILE_SIZE_BYTES:
        return None, f"file exceeds {MAX_FILE_SIZE_BYTES} byte limit"

    return {
        "content": decoded.decode("utf-8", errors="replace"),
        "size": len(decoded),
        "truncated": False,
    }, None


def _error(path: str, status: int | None, reason: str) -> dict[str, Any]:
    return {"path": path, "status": status, "reason": reason}


def fetch_repository_environment_files(
    full_name: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RepositoryEnvironmentFetchError("GITHUB_TOKEN is not configured")

    normalized_name = full_name.strip().strip("/")
    if normalized_name.count("/") != 1 or any(
        not part.strip() for part in normalized_name.split("/")
    ):
        raise RepositoryEnvironmentFetchError(
            "full_name must use the owner/repository format"
        )

    files: dict[str, dict[str, Any]] = {}
    found_files: list[str] = []
    missing_files: list[str] = []
    skipped_files: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []

    headers = _github_headers(token)
    repository_url = f"{GITHUB_API_URL}/repos/{normalized_name}/contents"
    should_close_client = client is None
    http_client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)

    try:
        for group in FILE_GROUPS:
            for path in group:
                try:
                    response = http_client.get(
                        f"{repository_url}/{path}", headers=headers
                    )
                except httpx.TimeoutException:
                    errors.append(
                        _error(path, None, "GitHub request timed out")
                    )
                    continue
                except httpx.NetworkError:
                    errors.append(
                        _error(path, None, "GitHub network request failed")
                    )
                    continue
                except httpx.RequestError:
                    errors.append(
                        _error(path, None, "GitHub request failed")
                    )
                    continue

                if response.status_code == 404:
                    missing_files.append(path)
                    continue
                if not 200 <= response.status_code < 300:
                    errors.append(
                        _error(
                            path,
                            response.status_code,
                            f"GitHub returned HTTP {response.status_code}",
                        )
                    )
                    continue

                try:
                    file_result, skip_reason = _decode_file_payload(response.json())
                except (ValueError, TypeError):
                    errors.append(
                        _error(path, response.status_code, "GitHub file response is invalid")
                    )
                    continue

                if skip_reason is not None:
                    skipped_files.append({"path": path, "reason": skip_reason})
                    continue

                if file_result is not None:
                    files[path] = file_result
                    found_files.append(path)
                    break
    finally:
        if should_close_client:
            http_client.close()

    return {
        "full_name": normalized_name,
        "files": files,
        "found_files": found_files,
        "missing_files": missing_files,
        "skipped_files": skipped_files,
        "errors": errors,
    }
