"""Static parsing of Docker and Compose environment hints.

This module deliberately treats Docker configuration as text/data only. It
never invokes Docker, pulls images, executes RUN instructions, or evaluates
Compose build definitions.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from .evidence import make_evidence


_DOCKERFILE_NAMES = ("Dockerfile",)
_COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml")
_FROM_PATTERN = re.compile(
    r"^\s*FROM(?:\s+--platform=\S+)?\s+(?P<image>\S+)"
    r"(?:\s+AS\s+\S+)?\s*(?:#.*)?$",
    re.IGNORECASE,
)
_VERSION_PATTERN = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,3})(?!\d)")
_CUDA_PATTERN = re.compile(r"(?:cuda|cudatoolkit)[^0-9]*(\d+(?:\.\d+){1,3})", re.I)


def _empty_result() -> dict[str, Any]:
    return {
        "docker_supported": None,
        "base_image": None,
        "base_images": [],
        "preferred_os": None,
        "supported_os": [],
        "python_version": None,
        "framework": None,
        "framework_version": None,
        "cuda_version": None,
        "nvidia_runtime": None,
        "compose_services": [],
        "evidence": [],
        "errors": [],
    }


def _add_evidence(
    result: dict[str, Any], source: str, reason: str, value: Any
) -> None:
    record = make_evidence(
        field=reason,
        value=value,
        source_file=source,
        raw_text=str(value),
        evidence_type="explicit",
    )
    if record is not None:
        record["reason"] = reason
        result["evidence"].append(record)


def _first_version(value: str) -> str | None:
    match = _VERSION_PATTERN.search(value)
    return match.group(1) if match else None


def _tag(image: str) -> str | None:
    image_without_digest = image.split("@", 1)[0]
    last_component = image_without_digest.rsplit("/", 1)[-1]
    if ":" not in last_component:
        return None
    return last_component.split(":", 1)[1]


def _image_metadata(
    result: dict[str, Any], image: str, source: str
) -> None:
    image = image.strip()
    if not image:
        return
    if image not in result["base_images"]:
        result["base_images"].append(image)
    if result["base_image"] is None:
        result["base_image"] = image

    lower_image = image.lower()
    tag = _tag(image)

    if lower_image.startswith("python:") or "/python:" in lower_image:
        python_version = _first_version(tag or "")
        if python_version is not None and result["python_version"] is None:
            result["python_version"] = python_version
            _add_evidence(result, source, "Python version is present in the image tag", python_version)

    if (
        lower_image.startswith("ubuntu:")
        or "/ubuntu:" in lower_image
        or re.search(r"(?:^|[-:])ubuntu\d", lower_image) is not None
    ):
        if result["preferred_os"] is None:
            result["preferred_os"] = "Ubuntu"
            _add_evidence(result, source, "Ubuntu base image", "Ubuntu")

    if "windows" in lower_image or lower_image.startswith("mcr.microsoft.com/windows"):
        if "Windows" not in result["supported_os"]:
            result["supported_os"].append("Windows")
    elif "Linux" not in result["supported_os"]:
        result["supported_os"].append("Linux")

    framework: str | None = None
    if lower_image.startswith("pytorch/pytorch:"):
        framework = "PyTorch"
    elif lower_image.startswith("tensorflow/tensorflow:"):
        framework = "TensorFlow"
    elif lower_image.startswith("jax:") or lower_image.startswith("jax-:"):
        framework = "JAX"

    if framework is not None:
        if result["framework"] is None:
            result["framework"] = framework
            _add_evidence(result, source, f"{framework} base image", image)
        if result["framework_version"] is None and tag:
            framework_version = _first_version(tag)
            if framework_version is not None:
                result["framework_version"] = framework_version
                _add_evidence(result, source, "Framework version is present in the image tag", framework_version)

    cuda_match = _CUDA_PATTERN.search(lower_image)
    if cuda_match is None and lower_image.startswith("nvidia/cuda:"):
        cuda_match = _VERSION_PATTERN.search(tag or "")
    if cuda_match is not None:
        cuda_version = cuda_match.group(1)
        if result["cuda_version"] is None:
            result["cuda_version"] = cuda_version
            _add_evidence(result, source, "CUDA version is present in the image reference", cuda_version)
        result["nvidia_runtime"] = True
    elif "nvidia" in lower_image or "cuda" in lower_image or "-gpu" in lower_image:
        result["nvidia_runtime"] = True
        _add_evidence(result, source, "Image reference indicates NVIDIA/CUDA runtime", image)


def _parse_dockerfile(result: dict[str, Any], content: str) -> None:
    for line in content.splitlines():
        match = _FROM_PATTERN.match(line)
        if match is not None:
            _image_metadata(result, match.group("image"), "Dockerfile")


def _parse_compose(result: dict[str, Any], filename: str, content: str) -> None:
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        result["errors"].append(
            {"source": filename, "reason": "YAML content is invalid"}
        )
        return

    if not isinstance(document, dict):
        result["errors"].append(
            {"source": filename, "reason": "Compose root must be a mapping"}
        )
        return

    services = document.get("services")
    if not isinstance(services, dict):
        return

    for service_name, service in services.items():
        if not isinstance(service_name, str) or not isinstance(service, dict):
            continue
        image = service.get("image")
        build = service.get("build")
        if isinstance(image, str):
            _image_metadata(result, image, filename)
        if isinstance(image, str) or isinstance(build, (str, dict)):
            result["compose_services"].append(
                {
                    "service": service_name,
                    "image": image if isinstance(image, str) else None,
                    "build": build if isinstance(build, (str, dict)) else None,
                    "source": filename,
                }
            )


def parse_docker_environment(repository_environment: dict[str, Any]) -> dict[str, Any]:
    """Extract Docker environment clues from fetched plain-text files."""

    result = _empty_result()
    files = repository_environment.get("files", {})
    if not isinstance(files, dict):
        return result

    dockerfile = files.get("Dockerfile")
    compose_files = [name for name in _COMPOSE_NAMES if name in files]
    has_docker_configuration = isinstance(dockerfile, dict) or bool(compose_files)
    if not has_docker_configuration:
        return result

    result["docker_supported"] = True
    if isinstance(dockerfile, dict) and isinstance(dockerfile.get("content"), str):
        _parse_dockerfile(result, dockerfile["content"])

    for filename in compose_files:
        file_data = files.get(filename)
        if isinstance(file_data, dict) and isinstance(file_data.get("content"), str):
            _parse_compose(result, filename, file_data["content"])

    return result
