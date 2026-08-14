import pytest

from compatibility import dependency_parser


def _fetched(**files: str) -> dict[str, object]:
    return {
        "files": {
            name: {
                "content": content,
                "size": len(content.encode("utf-8")),
                "truncated": False,
            }
            for name, content in files.items()
        }
    }


def _dependency(result: dict[str, object], name: str) -> dict[str, object]:
    return next(
        item
        for item in result["dependencies"]
        if isinstance(item, dict) and item["name"] == name
    )


def test_requirements_parses_ordinary_dependencies() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(**{"requirements.txt": "numpy\nrequests\n# comment\n"})
    )

    assert result["dependencies"] == [
        {"name": "numpy", "version_spec": None, "source": "requirements.txt"},
        {"name": "requests", "version_spec": None, "source": "requirements.txt"},
    ]
    assert result["package_manager"] == "pip"


def test_requirements_preserves_dependency_versions() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(**{"requirements.txt": "numpy>=1.26,<3\nrequests==2.32.3\n"})
    )

    assert _dependency(result, "numpy")["version_spec"] == ">=1.26,<3"
    assert _dependency(result, "requests")["version_spec"] == "==2.32.3"


def test_pyproject_parses_python_range() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(
            **{
                "pyproject.toml": (
                    "[project]\n"
                    'requires-python = ">=3.9,<3.12"\n'
                    "dependencies = []\n"
                )
            }
        )
    )

    assert result["python_min_version"] == "3.9"
    assert result["python_max_version"] == "3.12"
    assert {
        "source": "pyproject.toml",
        "field": "python_requirement",
        "value": ">=3.9,<3.12",
    } in result["evidence"]


def test_pyproject_parses_dependencies() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(
            **{
                "pyproject.toml": (
                    "[project]\n"
                    'dependencies = ["fastapi>=0.116", "httpx"]\n'
                )
            }
        )
    )

    assert _dependency(result, "fastapi") == {
        "name": "fastapi",
        "version_spec": ">=0.116",
        "source": "pyproject.toml",
    }
    assert _dependency(result, "httpx")["version_spec"] is None


def test_setup_cfg_parses_python_and_dependencies() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(
            **{
                "setup.cfg": (
                    "[options]\n"
                    "python_requires = >=3.8\n"
                    "install_requires =\n"
                    "    click>=8\n"
                    "    pydantic<3\n"
                )
            }
        )
    )

    assert result["python_min_version"] == "3.8"
    assert _dependency(result, "click")["version_spec"] == ">=8"
    assert _dependency(result, "pydantic")["version_spec"] == "<3"


def test_python_version_file_sets_exact_version() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(**{".python-version": "3.10.13\n"})
    )

    assert result["python_exact_version"] == "3.10.13"


def test_runtime_txt_sets_exact_version() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(**{"runtime.txt": "python-3.11.8\n"})
    )

    assert result["python_exact_version"] == "3.11.8"


def test_python_version_file_takes_precedence_over_manifest_exact_version() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(
            **{
                ".python-version": "3.10.13\n",
                "pyproject.toml": (
                    "[project]\n"
                    'requires-python = "==3.11.8"\n'
                ),
            }
        )
    )

    assert result["python_exact_version"] == "3.10.13"


@pytest.mark.parametrize(
    ("requirement", "framework", "version"),
    [
        ("torch>=2.1", "PyTorch", ">=2.1"),
        ("tensorflow==2.16.1", "TensorFlow", "==2.16.1"),
        ("jaxlib~=0.4.30", "JAX", "~=0.4.30"),
    ],
)
def test_detects_framework_from_dependency_name(
    requirement: str,
    framework: str,
    version: str,
) -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(**{"requirements.txt": requirement})
    )

    assert result["framework"] == framework
    assert result["framework_version"] == version


def test_malformed_file_records_error_and_other_files_continue() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(
            **{
                "pyproject.toml": "[project\ninvalid",
                "requirements.txt": "numpy==2.0\n",
            }
        )
    )

    assert _dependency(result, "numpy")["version_spec"] == "==2.0"
    assert {
        "source": "pyproject.toml",
        "reason": "TOML content is invalid",
    } in result["errors"]


def test_missing_files_returns_unknown_fields() -> None:
    result = dependency_parser.parse_python_dependencies({})

    assert result == {
        "python_min_version": None,
        "python_max_version": None,
        "python_exact_version": None,
        "framework": None,
        "framework_version": None,
        "package_manager": None,
        "dependencies": [],
        "evidence": [],
        "errors": [],
    }


def test_setup_py_is_parsed_without_execution() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(
            **{
                "setup.py": (
                    'raise RuntimeError("must never execute")\n'
                    "from setuptools import setup\n"
                    "setup(\n"
                    '    python_requires=">=3.9",\n'
                    '    install_requires=["rich>=13", "torch==2.3.1"],\n'
                    ")\n"
                )
            }
        )
    )

    assert result["python_min_version"] == "3.9"
    assert _dependency(result, "rich")["source"] == "setup.py"
    assert result["framework"] == "PyTorch"


def test_pipfile_parses_packages_and_python_version() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(
            **{
                "Pipfile": (
                    "[requires]\n"
                    'python_full_version = "3.12.2"\n'
                    "[packages]\n"
                    'flask = "==3.0.3"\n'
                    'httpx = "*"\n'
                )
            }
        )
    )

    assert result["python_exact_version"] == "3.12.2"
    assert result["package_manager"] == "pipenv"
    assert _dependency(result, "flask")["version_spec"] == "==3.0.3"
    assert _dependency(result, "httpx")["version_spec"] is None


def test_dependency_and_framework_evidence_keeps_source() -> None:
    result = dependency_parser.parse_python_dependencies(
        _fetched(**{"requirements.txt": "torchvision>=0.18\n"})
    )

    assert {
        "source": "requirements.txt",
        "field": "dependency",
        "value": "torchvision>=0.18",
    } in result["evidence"]
    assert {
        "source": "requirements.txt",
        "field": "framework",
        "value": "PyTorch",
    } in result["evidence"]
