from runtime.environment_detector import detect_environment


def test_detects_versions_and_package_manager_from_static_files(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "torch==2.2.1\ntorchvision>=0.17\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.10,<3.12"\n', encoding="utf-8"
    )
    (tmp_path / ".python-version").write_text("3.11.8\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")

    result = detect_environment(
        tmp_path,
        readme_text="Requires Python 3.10+, PyTorch 2.2.1 and CUDA 12.1.",
    )

    assert result.python_version == "3.11.8"
    assert result.package_manager == "pip"
    assert result.framework == "PyTorch"
    assert result.pytorch_version == "2.2.1"
    assert result.cuda_version == "12.1"
    assert result.has_requirements is True
    assert result.has_environment_yml is False
    assert result.has_dockerfile is True
    assert "requirements.txt" in result.detected_files
    assert result.warnings == []


def test_detects_conda_environment_without_executing_it(tmp_path):
    (tmp_path / "environment.yml").write_text(
        """name: demo
dependencies:
  - python=3.9
  - pytorch=2.0.1
  - cudatoolkit=11.8
""",
        encoding="utf-8",
    )
    (tmp_path / "setup.py").write_text(
        'setup(name="demo", python_requires=">=3.8")\n', encoding="utf-8"
    )

    result = detect_environment(tmp_path)

    assert result.python_version == "3.9"
    assert result.package_manager == "conda"
    assert result.framework == "PyTorch"
    assert result.pytorch_version == "2.0.1"
    assert result.cuda_version == "11.8"
    assert result.has_requirements is False
    assert result.has_environment_yml is True
    assert result.has_dockerfile is False


def test_reads_readme_file_as_a_static_fallback(tmp_path):
    (tmp_path / "Pipfile").write_text(
        '[requires]\npython_version = "3.10"\n', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "Tested with Python 3.10, torch 2.1.0, and CUDA 11.8.", encoding="utf-8"
    )

    result = detect_environment(tmp_path)

    assert result.python_version == "3.10"
    assert result.package_manager == "pipenv"
    assert result.framework == "PyTorch"
    assert result.pytorch_version == "2.1.0"
    assert result.cuda_version == "11.8"


def test_returns_unknown_values_when_no_supported_files_exist(tmp_path):
    (tmp_path / "notes.txt").write_text("do not inspect me", encoding="utf-8")

    result = detect_environment(tmp_path)

    assert result.python_version == "unknown"
    assert result.package_manager == "unknown"
    assert result.framework == "unknown"
    assert result.pytorch_version == "unknown"
    assert result.cuda_version == "unknown"
    assert result.detected_files == []
    assert result.warnings == ["No supported environment files or README were found"]


def test_rejects_a_path_that_is_not_a_directory(tmp_path):
    missing = tmp_path / "missing"

    result = detect_environment(missing)

    assert result.errors == ["Repository path is not a directory"]
    assert result.python_version == "unknown"
