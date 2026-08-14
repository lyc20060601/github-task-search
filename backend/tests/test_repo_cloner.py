from pathlib import Path
import subprocess

from runtime import repo_cloner


def test_clone_repository_uses_windows_git_transport_settings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(repo_cloner, "_PROJECT_TEMP_ROOT", tmp_path)
    monkeypatch.setattr(repo_cloner.platform, "system", lambda: "Windows")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(repo_cloner.subprocess, "run", fake_run)

    result = repo_cloner.clone_repository("geopy/geopy", timeout_seconds=9)

    assert result.clone_status == "success"
    assert captured["command"][:8] == [
        "git",
        "-c",
        "credential.helper=",
        "-c",
        "http.sslBackend=schannel",
        "-c",
        "http.version=HTTP/1.1",
        "clone",
    ]
    assert "--depth" in captured["command"]
    assert "1" in captured["command"]
    assert captured["kwargs"]["timeout"] == 9
    assert captured["kwargs"]["shell"] is False


def test_clone_repository_keeps_non_windows_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(repo_cloner, "_PROJECT_TEMP_ROOT", tmp_path)
    monkeypatch.setattr(repo_cloner.platform, "system", lambda: "Linux")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(repo_cloner.subprocess, "run", fake_run)

    result = repo_cloner.clone_repository("geopy/geopy", timeout_seconds=9)

    assert result.clone_status == "success"
    assert captured["command"][:4] == ["git", "-c", "credential.helper=", "clone"]
    assert "http.sslBackend=schannel" not in captured["command"]
    assert "http.version=HTTP/1.1" not in captured["command"]
    assert captured["kwargs"]["timeout"] == 9
    assert captured["kwargs"]["shell"] is False


def test_clone_repository_returns_structured_bounded_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(repo_cloner, "_PROJECT_TEMP_ROOT", tmp_path)
    monkeypatch.setattr(repo_cloner.platform, "system", lambda: "Linux")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        target = Path(command[-1])
        target.mkdir(parents=True)
        return subprocess.CompletedProcess(command, 128, "", "x" * 3000)

    monkeypatch.setattr(repo_cloner.subprocess, "run", fake_run)

    result = repo_cloner.clone_repository("geopy/geopy", timeout_seconds=9)

    assert result.clone_status == "failed"
    assert result.path is None
    assert len(result.error or "") == 2000
    assert not any(tmp_path.iterdir())
