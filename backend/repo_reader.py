import base64
import os
from typing import Any

import httpx
from dotenv import load_dotenv


GITHUB_API_URL = "https://api.github.com"
COMMON_ROOT_PATHS = (
    "requirements.txt",
    "pyproject.toml",
    "environment.yml",
    "setup.py",
    "Dockerfile",
    "train.py",
)
COMMON_DIRECTORIES = (
    "configs/",
    "config/",
    "datasets/",
    "dataset/",
    "data/",
    "checkpoints/",
    "weights/",
)


class RepositoryReadError(RuntimeError):
    """Raised when GitHub repository details cannot be read."""


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _decode_readme(payload: dict[str, Any]) -> str:
    if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        raise ValueError("README response is not Base64 encoded")
    return base64.b64decode(payload["content"], validate=False).decode(
        "utf-8", errors="replace"
    )


def get_repository_details(
    full_name: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RepositoryReadError("GITHUB_TOKEN is not configured")

    normalized_name = full_name.strip().strip("/")
    if normalized_name.count("/") != 1:
        raise RepositoryReadError("full_name must use the owner/repository format")

    headers = _github_headers(token)
    repository_url = f"{GITHUB_API_URL}/repos/{normalized_name}"
    should_close_client = client is None
    http_client = client or httpx.Client(timeout=15.0)

    try:
        readme_response = http_client.get(f"{repository_url}/readme", headers=headers)
        readme_response.raise_for_status()
        readme = _decode_readme(readme_response.json())

        root_response = http_client.get(f"{repository_url}/contents", headers=headers)
        root_response.raise_for_status()
        root_items = root_response.json()
        if not isinstance(root_items, list):
            raise TypeError("repository root response must be a list")

        nested_response = http_client.get(
            f"{repository_url}/contents/tools/train.py", headers=headers
        )
        tools_train_exists = nested_response.status_code == 200
        if nested_response.status_code not in (200, 404):
            nested_response.raise_for_status()

        root_files = [
            item["name"]
            for item in root_items
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        root_names = set(root_files)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise RepositoryReadError("GitHub repository details request failed") from exc
    finally:
        if should_close_client:
            http_client.close()

    common_paths = {path: path in root_names for path in COMMON_ROOT_PATHS}
    common_paths["tools/train.py"] = tools_train_exists
    common_paths.update(
        {directory: directory.rstrip("/") in root_names for directory in COMMON_DIRECTORIES}
    )

    return {
        "full_name": normalized_name,
        "readme": readme,
        "root_files": root_files,
        "common_paths": common_paths,
    }
