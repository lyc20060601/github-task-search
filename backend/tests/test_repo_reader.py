import base64

import httpx
import pytest

import repo_reader


def test_get_repository_details_decodes_readme_and_detects_common_paths(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    readme = "# Segmentation\n"
    root_items = [
        {"name": "README.md", "path": "README.md", "type": "file"},
        {"name": "requirements.txt", "path": "requirements.txt", "type": "file"},
        {"name": "tools", "path": "tools", "type": "dir"},
        {"name": "configs", "path": "configs", "type": "dir"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.url.path.endswith("/readme"):
            return httpx.Response(
                200,
                json={
                    "content": base64.b64encode(readme.encode()).decode(),
                    "encoding": "base64",
                },
            )
        if request.url.path.endswith("/contents/tools/train.py"):
            return httpx.Response(
                200,
                json={"name": "train.py", "path": "tools/train.py", "type": "file"},
            )
        assert request.url.path.endswith("/contents")
        return httpx.Response(200, json=root_items)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = repo_reader.get_repository_details("owner/repo", client=client)

    assert result == {
        "full_name": "owner/repo",
        "readme": readme,
        "root_files": ["README.md", "requirements.txt", "tools", "configs"],
        "common_paths": {
            "requirements.txt": True,
            "pyproject.toml": False,
            "environment.yml": False,
            "setup.py": False,
            "Dockerfile": False,
            "train.py": False,
            "tools/train.py": True,
            "configs/": True,
            "config/": False,
            "datasets/": False,
            "dataset/": False,
            "data/": False,
            "checkpoints/": False,
            "weights/": False,
        },
    }


def test_get_repository_details_requires_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(repo_reader, "load_dotenv", lambda: None)

    with pytest.raises(repo_reader.RepositoryReadError, match="GITHUB_TOKEN"):
        repo_reader.get_repository_details("owner/repo")


def test_get_repository_details_wraps_github_errors(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(repo_reader.RepositoryReadError, match="repository details"):
        repo_reader.get_repository_details("owner/repo", client=client)
