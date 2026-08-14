import os
import stat
from pathlib import Path
from unittest.mock import Mock, call, patch

from runtime.dependency_installer import DependencyInstallResult
from runtime.entrypoint_detector import EntrypointDetection
from runtime.environment_detector import EnvironmentDetection
from runtime.repo_cloner import CloneResult
from runtime.smoke_tester import SmokeTestResult
from runtime.validator import _make_clone_tree_writable, _remove_clone, validate_repository
from runtime.docker_sandbox import PROJECT_TEMP_ROOT


def test_validate_repository_runs_pipeline_and_removes_clone(monkeypatch, tmp_path):
    repository_path = tmp_path / "repository"
    repository_path.mkdir()
    calls = []

    monkeypatch.setattr(
        "runtime.validator.clone_repository",
        lambda full_name: CloneResult(full_name, "success", str(repository_path)),
    )

    def fake_environment(path):
        calls.append(("environment", Path(path)))
        return EnvironmentDetection(
            python_version="3.11",
            framework="PyTorch",
            has_requirements=True,
            detected_files=["requirements.txt", "README.md"],
        )

    def fake_entrypoint(path):
        calls.append(("entrypoint", Path(path)))
        return EntrypointDetection(entrypoint="tools/train.py")

    def fake_install(path):
        calls.append(("install", Path(path)))
        return DependencyInstallResult("success", 12.5)

    def fake_smoke(path, *, entrypoint):
        calls.append(("smoke", Path(path), entrypoint))
        return SmokeTestResult("success", 0, 1.25)

    cleanup = Mock()
    monkeypatch.setattr("runtime.validator.detect_environment", fake_environment)
    monkeypatch.setattr("runtime.validator.detect_entrypoint", fake_entrypoint)
    monkeypatch.setattr("runtime.validator.install_dependencies", fake_install)
    monkeypatch.setattr("runtime.validator.run_smoke_test", fake_smoke)
    monkeypatch.setattr("runtime.validator._remove_clone", cleanup)

    report = validate_repository("owner/repository")

    assert calls == [
        ("environment", repository_path),
        ("entrypoint", repository_path),
        ("install", repository_path),
        ("smoke", repository_path, "tools/train.py"),
    ]
    assert report.clone_status == "success"
    assert report.environment_detected == "success"
    assert report.entrypoint_detected == "success"
    assert report.dependency_install_status == "success"
    assert report.smoke_test_status == "success"
    assert report.python_version == "3.11"
    assert report.framework == "PyTorch"
    assert report.entrypoint == "tools/train.py"
    assert report.install_duration == 12.5
    assert report.test_duration == 1.25
    assert report.runtime_score == 100
    assert report.runtime_status == "success"
    assert report.runtime_breakdown["dependency_install"] == 35
    cleanup.assert_called_once_with(repository_path)


def test_clone_failure_returns_report_and_skips_remaining_pipeline(monkeypatch):
    monkeypatch.setattr(
        "runtime.validator.clone_repository",
        lambda full_name: CloneResult(
            full_name, "failed", error="public repository not found"
        ),
    )
    environment = Mock()
    monkeypatch.setattr("runtime.validator.detect_environment", environment)

    report = validate_repository("owner/missing")

    assert report.clone_status == "failed"
    assert report.environment_detected == "skipped"
    assert report.entrypoint_detected == "skipped"
    assert report.dependency_install_status == "skipped"
    assert report.smoke_test_status == "skipped"
    assert report.runtime_score == 0
    assert report.runtime_status == "failed"
    assert report.errors == ["Clone failed: public repository not found"]
    environment.assert_not_called()


def test_stage_failure_is_recorded_and_later_safe_stages_continue(
    monkeypatch, tmp_path
):
    repository_path = tmp_path / "repository"
    repository_path.mkdir()

    monkeypatch.setattr(
        "runtime.validator.clone_repository",
        lambda full_name: CloneResult(full_name, "success", str(repository_path)),
    )
    monkeypatch.setattr(
        "runtime.validator.detect_environment",
        Mock(side_effect=OSError("cannot read files")),
    )
    monkeypatch.setattr(
        "runtime.validator.detect_entrypoint",
        lambda path: EntrypointDetection(entrypoint="main.py"),
    )
    monkeypatch.setattr(
        "runtime.validator.install_dependencies",
        lambda path: DependencyInstallResult("failed", 2.0, "pip failed"),
    )
    monkeypatch.setattr(
        "runtime.validator.run_smoke_test",
        lambda path, *, entrypoint: SmokeTestResult("failed", 1, 0.5, "import failed"),
    )
    monkeypatch.setattr("runtime.validator._remove_clone", Mock())

    report = validate_repository("owner/repository")

    assert report.environment_detected == "failed"
    assert report.entrypoint_detected == "success"
    assert report.dependency_install_status == "failed"
    assert report.smoke_test_status == "failed"
    assert report.runtime_status == "failed"
    assert report.errors == [
        "Environment detection failed: cannot read files",
        "Dependency installation failed: pip failed",
        "Smoke test failed: import failed",
    ]


def test_remove_clone_handles_read_only_git_files() -> None:
    repository_path = PROJECT_TEMP_ROOT / "validator-read-only-cleanup-test"
    git_objects = repository_path / ".git" / "objects" / "pack"
    git_objects.mkdir(parents=True, exist_ok=True)
    read_only_file = git_objects / "pack-test.idx"
    read_only_file.write_bytes(b"index")
    os.chmod(read_only_file, stat.S_IREAD)

    try:
        _remove_clone(repository_path)
        assert not repository_path.exists()
    finally:
        if read_only_file.exists():
            os.chmod(read_only_file, stat.S_IWRITE)


def test_cleanup_retries_after_restoring_tree_permissions() -> None:
    repository_path = PROJECT_TEMP_ROOT / "validator-permission-retry-test"
    repository_path.mkdir(parents=True, exist_ok=True)

    with (
        patch(
            "runtime.validator.shutil.rmtree",
            side_effect=[PermissionError("denied"), None],
        ) as rmtree,
        patch("runtime.validator._make_clone_tree_writable") as make_writable,
    ):
        _remove_clone(repository_path)

    make_writable.assert_called_once_with(repository_path.resolve())
    assert rmtree.call_count == 2


def test_make_clone_tree_writable_restores_directory_and_file_modes() -> None:
    repository_path = PROJECT_TEMP_ROOT / "validator-mode-repair-test"
    child_directory = repository_path / "locked"
    child_file = repository_path / "locked.txt"

    with (
        patch("runtime.validator.os.walk", return_value=[
            (str(repository_path), [child_directory.name], [child_file.name])
        ]),
        patch("runtime.validator.os.chmod") as chmod,
    ):
        _make_clone_tree_writable(repository_path)

    assert chmod.call_args_list == [
        call(repository_path, stat.S_IRWXU),
        call(child_directory, stat.S_IRWXU),
        call(child_file, stat.S_IRUSR | stat.S_IWUSR),
    ]
