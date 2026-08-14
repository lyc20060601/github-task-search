import base64
import json
from collections.abc import Callable

import httpx

from compatibility import repository_environment_fetcher as fetcher


def _payload(content: str, *, size: int | None = None) -> dict[str, object]:
    encoded = content.encode("utf-8")
    return {
        "content": base64.b64encode(encoded).decode("ascii"),
        "encoding": "base64",
        "size": len(encoded) if size is None else size,
    }


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _path(request: httpx.Request) -> str:
    prefix = "/repos/owner/repo/contents/"
    assert request.url.path.startswith(prefix)
    assert request.headers["Authorization"] == "Bearer test-token"
    return request.url.path.removeprefix(prefix)


def _response_for(
    request: httpx.Request,
    files: dict[str, str],
) -> httpx.Response:
    path = _path(request)
    if path in files:
        return httpx.Response(200, json=_payload(files[path]), request=request)
    return httpx.Response(404, request=request)


def test_fetches_readme_md_and_stops_readme_fallbacks(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(_path(request))
        return _response_for(request, {"README.md": "# Project\n"})

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    assert result["files"]["README.md"]["content"] == "# Project\n"
    assert "README.md" in result["found_files"]
    assert "README" not in requested
    assert "README.rst" not in requested


def test_fetches_requirements_txt(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return _response_for(request, {"requirements.txt": "torch==2.4.0\n"})

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    assert result["files"]["requirements.txt"] == {
        "content": "torch==2.4.0\n",
        "size": 13,
        "truncated": False,
    }


def test_records_file_not_found_as_normal_missing_file(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        _path(request)
        return httpx.Response(404, request=request)

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    assert "requirements.txt" in result["missing_files"]
    assert not result["errors"]


def test_falls_back_from_readme_md_to_readme(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = _path(request)
        requested.append(path)
        if path == "README":
            return httpx.Response(200, json=_payload("Project readme"), request=request)
        return httpx.Response(404, request=request)

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    assert result["files"]["README"]["content"] == "Project readme"
    assert "README.md" in result["missing_files"]
    assert "README.rst" not in requested


def test_falls_back_to_environment_yaml(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = _path(request)
        requested.append(path)
        if path == "environment.yaml":
            return httpx.Response(
                200, json=_payload("name: project\n"), request=request
            )
        return httpx.Response(404, request=request)

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    assert result["files"]["environment.yaml"]["content"] == "name: project\n"
    assert requested.index("environment.yml") < requested.index("environment.yaml")


def test_fetches_dockerfile_as_plain_text(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return _response_for(request, {"Dockerfile": "FROM python:3.11\n"})

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    assert result["files"]["Dockerfile"]["content"] == "FROM python:3.11\n"


def test_file_server_error_does_not_stop_other_files(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        path = _path(request)
        if path == "requirements.txt":
            return httpx.Response(500, request=request)
        if path == "Dockerfile":
            return httpx.Response(200, json=_payload("FROM python\n"), request=request)
        return httpx.Response(404, request=request)

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    assert result["files"]["Dockerfile"]["content"] == "FROM python\n"
    assert {
        "path": "requirements.txt",
        "status": 500,
        "reason": "GitHub returned HTTP 500",
    } in result["errors"]


def test_timeout_is_recorded_and_other_files_continue(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        path = _path(request)
        if path == "requirements.txt":
            raise httpx.ReadTimeout("secret diagnostic", request=request)
        if path == "Dockerfile":
            return httpx.Response(200, json=_payload("FROM python\n"), request=request)
        return httpx.Response(404, request=request)

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    assert result["files"]["Dockerfile"]["content"] == "FROM python\n"
    assert {
        "path": "requirements.txt",
        "status": None,
        "reason": "GitHub request timed out",
    } in result["errors"]


def test_oversized_file_is_skipped_without_content(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        path = _path(request)
        if path == "requirements.txt":
            payload = _payload("small", size=fetcher.MAX_FILE_SIZE_BYTES + 1)
            return httpx.Response(200, json=payload, request=request)
        return httpx.Response(404, request=request)

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    assert "requirements.txt" not in result["files"]
    assert result["skipped_files"] == [
        {
            "path": "requirements.txt",
            "reason": f"file exceeds {fetcher.MAX_FILE_SIZE_BYTES} byte limit",
        }
    ]


def test_returned_result_does_not_leak_token(monkeypatch) -> None:
    token = "test-token-never-return"
    monkeypatch.setenv("GITHUB_TOKEN", token)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {token}"
        if request.url.path.endswith("/README.md"):
            return httpx.Response(401, request=request)
        return httpx.Response(404, request=request)

    result = fetcher.fetch_repository_environment_files(
        "owner/repo", client=_client(handler)
    )

    serialized = json.dumps(result)
    assert token not in serialized
    assert "Authorization" not in serialized
