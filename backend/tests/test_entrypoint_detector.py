from pathlib import Path

from runtime.entrypoint_detector import detect_entrypoint


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_detects_common_entrypoint_file(tmpdir) -> None:
    tmp_path = Path(str(tmpdir))
    _write(tmp_path / "tools" / "train.py", "raise RuntimeError('must not run')")

    result = detect_entrypoint(tmp_path)

    assert result.entrypoint == "tools/train.py"
    assert result.entrypoint_type == "training"
    assert result.confidence == "high"
    assert result.evidence["source"] == "tools/train.py"


def test_readme_command_takes_priority_over_file_order(tmpdir) -> None:
    tmp_path = Path(str(tmpdir))
    _write(tmp_path / "train.py")
    _write(tmp_path / "demo.py")
    readme = "Run the demo with `python demo.py --checkpoint model.pth`."

    result = detect_entrypoint(tmp_path, readme_text=readme)

    assert result.entrypoint == "demo.py"
    assert result.entrypoint_type == "demo"
    assert result.confidence == "high"
    assert result.evidence["source"] == "README"
    assert result.evidence["command"] == "python demo.py --checkpoint model.pth"


def test_readme_only_entrypoint_has_medium_confidence(tmpdir) -> None:
    tmp_path = Path(str(tmpdir))
    readme = "```bash\npython3 inference.py --input image.jpg\n```"

    result = detect_entrypoint(tmp_path, readme_text=readme)

    assert result.entrypoint == "inference.py"
    assert result.entrypoint_type == "inference"
    assert result.confidence == "medium"
    assert "not found" in result.evidence["reason"].lower()


def test_ignores_readme_commands_outside_supported_entrypoints(tmpdir) -> None:
    tmp_path = Path(str(tmpdir))
    result = detect_entrypoint(
        tmp_path,
        readme_text="Run `python scripts/custom_launcher.py` to start.",
    )

    assert result.entrypoint == "unknown"
    assert result.entrypoint_type == "unknown"
    assert result.confidence == "unknown"
    assert result.evidence["source"] == "unknown"


def test_reads_repository_readme_without_executing_files(tmpdir) -> None:
    tmp_path = Path(str(tmpdir))
    _write(tmp_path / "predict.py", "raise RuntimeError('must not run')")
    _write(tmp_path / "README.md", "Start with `python predict.py input.png`.")

    result = detect_entrypoint(tmp_path)

    assert result.entrypoint == "predict.py"
    assert result.entrypoint_type == "inference"
    assert result.confidence == "high"
    assert result.evidence["source"] == "README.md"


def test_returns_unknown_for_invalid_repository_path(tmpdir) -> None:
    tmp_path = Path(str(tmpdir))
    result = detect_entrypoint(tmp_path / "missing")

    assert result.to_dict() == {
        "entrypoint": "unknown",
        "entrypoint_type": "unknown",
        "confidence": "unknown",
        "evidence": {
            "source": "unknown",
            "reason": "Repository path is not a directory",
        },
    }
