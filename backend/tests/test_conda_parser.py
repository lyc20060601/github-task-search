import pytest

from compatibility import conda_parser


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


def test_parses_environment_yml_name_and_dependencies() -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(
            **{
                "environment.yml": (
                    "name: vision\n"
                    "dependencies:\n"
                    "  - python=3.10\n"
                    "  - numpy=1.26\n"
                )
            }
        )
    )

    assert result["environment_name"] == "vision"
    assert result["package_manager"] == "conda"
    assert _dependency(result, "numpy") == {
        "name": "numpy",
        "version_spec": "=1.26",
        "source": "environment.yml",
    }


def test_uses_environment_yaml_when_yml_is_missing() -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(**{"environment.yaml": "name: fallback\ndependencies: []\n"})
    )

    assert result["environment_name"] == "fallback"
    assert {
        "source": "environment.yaml",
        "field": "environment_name",
        "value": "fallback",
    } in result["evidence"]


def test_environment_yml_has_priority_over_environment_yaml() -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(
            **{
                "environment.yml": "name: primary\ndependencies: []\n",
                "environment.yaml": "name: fallback\ndependencies: []\n",
            }
        )
    )

    assert result["environment_name"] == "primary"


@pytest.mark.parametrize(
    ("requirement", "field", "expected"),
    [
        ("python=3.10", "python_exact_version", "3.10"),
        ("python>=3.9", "python_min_version", "3.9"),
        ("python<3.12", "python_max_version", "3.12"),
    ],
)
def test_parses_python_version_requirements(
    requirement: str,
    field: str,
    expected: str,
) -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(
            **{
                "environment.yml": (
                    "dependencies:\n"
                    f"  - {requirement}\n"
                )
            }
        )
    )

    assert result[field] == expected


def test_detects_pytorch_and_version() -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(**{"environment.yml": "dependencies:\n  - pytorch=2.1\n"})
    )

    assert result["framework"] == "PyTorch"
    assert result["framework_version"] == "=2.1"


def test_extracts_explicit_cuda_toolkit_version_without_gpu_inference() -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(**{"environment.yml": "dependencies:\n  - cudatoolkit=11.8\n"})
    )

    assert result["cuda_version"] == "11.8"
    assert "gpu_required" not in result
    assert "minimum_gpu_memory_gb" not in result


def test_parses_nested_pip_dependencies() -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(
            **{
                "environment.yml": (
                    "dependencies:\n"
                    "  - pip\n"
                    "  - pip:\n"
                    "      - transformers==4.44.0\n"
                    "      - opencv-python\n"
                )
            }
        )
    )

    assert _dependency(result, "transformers") == {
        "name": "transformers",
        "version_spec": "==4.44.0",
        "source": "environment.yml:pip",
    }
    assert _dependency(result, "opencv-python")["source"] == "environment.yml:pip"
    assert result["package_manager"] == "conda"


def test_missing_name_is_allowed() -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(**{"environment.yml": "dependencies:\n  - numpy\n"})
    )

    assert result["environment_name"] is None
    assert not result["errors"]


def test_missing_python_is_allowed() -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(**{"environment.yml": "name: tools\ndependencies:\n  - numpy\n"})
    )

    assert result["python_min_version"] is None
    assert result["python_max_version"] is None
    assert result["python_exact_version"] is None


def test_invalid_yaml_fails_safely() -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(**{"environment.yml": "name: [invalid\n"})
    )

    assert result["dependencies"] == []
    assert result["errors"] == [
        {"source": "environment.yml", "reason": "YAML content is invalid"}
    ]


@pytest.mark.parametrize(
    ("dependency", "framework"),
    [
        ("tensorflow=2.16", "TensorFlow"),
        ("jaxlib=0.4.30", "JAX"),
    ],
)
def test_detects_other_framework_families(
    dependency: str,
    framework: str,
) -> None:
    result = conda_parser.parse_conda_environment(
        _fetched(
            **{"environment.yml": f"dependencies:\n  - {dependency}\n"}
        )
    )

    assert result["framework"] == framework


def test_missing_environment_files_returns_empty_result() -> None:
    result = conda_parser.parse_conda_environment({})

    assert result == {
        "environment_name": None,
        "python_min_version": None,
        "python_max_version": None,
        "python_exact_version": None,
        "framework": None,
        "framework_version": None,
        "cuda_version": None,
        "package_manager": None,
        "dependencies": [],
        "evidence": [],
        "errors": [],
    }
