import pytest

from compatibility import docker_environment_parser as parser


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


def test_parses_python_base_image() -> None:
    result = parser.parse_docker_environment(
        _fetched(**{"Dockerfile": "FROM python:3.10-slim\n"})
    )

    assert result["docker_supported"] is True
    assert result["base_image"] == "python:3.10-slim"
    assert result["python_version"] == "3.10"
    assert result["supported_os"] == ["Linux"]


def test_parses_ubuntu_base_image() -> None:
    result = parser.parse_docker_environment(
        _fetched(**{"Dockerfile": "FROM ubuntu:22.04\n"})
    )

    assert result["base_image"] == "ubuntu:22.04"
    assert result["preferred_os"] == "Ubuntu"
    assert result["supported_os"] == ["Linux"]


def test_parses_nvidia_cuda_image() -> None:
    result = parser.parse_docker_environment(
        _fetched(**{"Dockerfile": "FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04\n"})
    )

    assert result["cuda_version"] == "11.8.0"
    assert result["nvidia_runtime"] is True
    assert result["preferred_os"] == "Ubuntu"


def test_parses_pytorch_image_and_framework_version() -> None:
    result = parser.parse_docker_environment(
        _fetched(**{"Dockerfile": "FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime\n"})
    )

    assert result["framework"] == "PyTorch"
    assert result["framework_version"] == "2.1.0"
    assert result["cuda_version"] == "11.8"
    assert result["nvidia_runtime"] is True


def test_parses_tensorflow_image() -> None:
    result = parser.parse_docker_environment(
        _fetched(**{"Dockerfile": "FROM tensorflow/tensorflow:2.15.0-gpu\n"})
    )

    assert result["framework"] == "TensorFlow"
    assert result["framework_version"] == "2.15.0"


def test_retains_all_recognized_multistage_images() -> None:
    result = parser.parse_docker_environment(
        _fetched(
            **{
                "Dockerfile": (
                    "FROM python:3.11 AS builder\n"
                    "FROM ubuntu:22.04\n"
                )
            }
        )
    )

    assert result["base_image"] == "python:3.11"
    assert result["base_images"] == ["python:3.11", "ubuntu:22.04"]
    assert result["python_version"] == "3.11"


def test_dockerfile_missing_returns_unknown() -> None:
    result = parser.parse_docker_environment(_fetched())

    assert result["docker_supported"] is None
    assert result["base_image"] is None
    assert result["errors"] == []


def test_parses_compose_image_without_executing_compose() -> None:
    result = parser.parse_docker_environment(
        _fetched(
            **{
                "docker-compose.yml": (
                    "services:\n"
                    "  app:\n"
                    "    image: python:3.11\n"
                )
            }
        )
    )

    assert result["docker_supported"] is True
    assert result["base_image"] == "python:3.11"
    assert result["python_version"] == "3.11"


def test_unrecognized_image_is_safe_and_still_marks_docker_supported() -> None:
    result = parser.parse_docker_environment(
        _fetched(**{"Dockerfile": "FROM company/internal:latest\n"})
    )

    assert result["docker_supported"] is True
    assert result["base_image"] == "company/internal:latest"
    assert result["base_images"] == ["company/internal:latest"]
    assert result["framework"] is None
    assert result["python_version"] is None


def test_records_compose_build_without_running_it() -> None:
    result = parser.parse_docker_environment(
        _fetched(
            **{
                "docker-compose.yml": (
                    "services:\n"
                    "  app:\n"
                    "    build:\n"
                    "      context: .\n"
                    "      dockerfile: Dockerfile.dev\n"
                )
            }
        )
    )

    assert result["docker_supported"] is True
    assert result["compose_services"] == [
        {
            "service": "app",
            "image": None,
            "build": {"context": ".", "dockerfile": "Dockerfile.dev"},
            "source": "docker-compose.yml",
        }
    ]


def test_invalid_compose_yaml_records_error() -> None:
    result = parser.parse_docker_environment(
        _fetched(**{"docker-compose.yaml": "services: [invalid\n"})
    )

    assert result["docker_supported"] is True
    assert result["errors"] == [
        {"source": "docker-compose.yaml", "reason": "YAML content is invalid"}
    ]


@pytest.mark.parametrize(
    ("image", "framework"),
    [
        ("pytorch/pytorch:latest", "PyTorch"),
        ("tensorflow/tensorflow:latest", "TensorFlow"),
    ],
)
def test_unknown_framework_image_version_remains_unknown(
    image: str, framework: str
) -> None:
    result = parser.parse_docker_environment(
        _fetched(**{"Dockerfile": f"FROM {image}\n"})
    )

    assert result["framework"] == framework
    assert result["framework_version"] is None
