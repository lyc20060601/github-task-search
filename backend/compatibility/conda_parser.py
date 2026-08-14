"""Safe, static parsing for Conda environment files."""

from __future__ import annotations

import re
from typing import Any

import yaml

from .evidence import make_evidence


ENVIRONMENT_FILES = ("environment.yml", "environment.yaml")

FRAMEWORK_PACKAGES = {
    "pytorch": "PyTorch",
    "torch": "PyTorch",
    "torchvision": "PyTorch",
    "torchaudio": "PyTorch",
    "tensorflow": "TensorFlow",
    "tensorflow-cpu": "TensorFlow",
    "tensorflow-gpu": "TensorFlow",
    "jax": "JAX",
    "jaxlib": "JAX",
}

CUDA_PACKAGES = {"cuda", "cudatoolkit", "pytorch-cuda"}

_PACKAGE_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<constraint>.*)$"
)
_VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+){0,3})")
_PYTHON_CONSTRAINT_PATTERN = re.compile(
    r"(?P<operator>===|==|~=|>=|<=|=|>|<)\s*(?P<version>\d+(?:\.\d+){0,3})"
)


def _empty_result() -> dict[str, Any]:
    return {
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


def _select_environment_file(
    repository_environment: dict[str, Any],
) -> tuple[str | None, str | None]:
    files = repository_environment.get("files", {})
    if not isinstance(files, dict):
        return None, None

    for filename in ENVIRONMENT_FILES:
        file_data = files.get(filename)
        if not isinstance(file_data, dict):
            continue
        content = file_data.get("content")
        if isinstance(content, str):
            return filename, content

    return None, None


def _normalise_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _parse_dependency(value: str, source: str) -> dict[str, str] | None:
    raw_value = value.strip()
    if not raw_value or raw_value.startswith(("#", "-e ", "http://", "https://")):
        return None

    # Conda channel prefixes, such as pytorch::pytorch=2.1, do not change the
    # package identity. The original text is retained separately in evidence.
    package_value = raw_value.rsplit("::", 1)[-1]
    match = _PACKAGE_PATTERN.match(package_value)
    if match is None:
        return None

    name = _normalise_package_name(match.group("name"))
    constraint = match.group("constraint").strip()
    if not name:
        return None

    # A second Conda equality usually introduces a build string. It is not a
    # version constraint and is deliberately not interpreted.
    if constraint.startswith("=") and not constraint.startswith("=="):
        version_and_build = constraint[1:].split("=", 1)
        constraint = f"={version_and_build[0]}"

    return {"name": name, "version_spec": constraint, "source": source}


def _add_evidence(
    result: dict[str, Any], source: str, field: str, value: Any
) -> None:
    record = make_evidence(
        field=field,
        value=value,
        source_file=source,
        raw_text=str(value),
        evidence_type="dependency" if field == "dependencies" else "explicit",
    )
    if record is not None:
        result["evidence"].append(record)


def _apply_python_constraint(
    result: dict[str, Any], version_spec: str, source: str
) -> None:
    for match in _PYTHON_CONSTRAINT_PATTERN.finditer(version_spec):
        operator = match.group("operator")
        version = match.group("version")

        if operator in {"=", "==", "==="}:
            result["python_exact_version"] = version
            field = "python_exact_version"
        elif operator in {">", ">=", "~="}:
            result["python_min_version"] = version
            field = "python_min_version"
        else:
            result["python_max_version"] = version
            field = "python_max_version"

        _add_evidence(result, source, field, version_spec)


def _version_from_constraint(version_spec: str) -> str | None:
    match = _VERSION_PATTERN.search(version_spec)
    return match.group(1) if match else None


def _apply_dependency_metadata(
    result: dict[str, Any], dependency: dict[str, str], raw_value: str
) -> None:
    name = dependency["name"]
    version_spec = dependency["version_spec"]
    source = dependency["source"]

    result["dependencies"].append(dependency)
    _add_evidence(result, source, "dependencies", raw_value)

    if name == "python":
        _apply_python_constraint(result, version_spec, source)

    framework = FRAMEWORK_PACKAGES.get(name)
    if framework is not None and result["framework"] is None:
        result["framework"] = framework
        result["framework_version"] = version_spec or None
        _add_evidence(result, source, "framework", raw_value)
        if result["framework_version"] is not None:
            _add_evidence(result, source, "framework_version", raw_value)

    if name in CUDA_PACKAGES and result["cuda_version"] is None:
        cuda_version = _version_from_constraint(version_spec)
        if cuda_version is not None:
            result["cuda_version"] = cuda_version
            _add_evidence(result, source, "cuda_version", raw_value)


def parse_conda_environment(repository_environment: dict[str, Any]) -> dict[str, Any]:
    """Parse fetched Conda environment text without executing any project code."""

    result = _empty_result()
    filename, content = _select_environment_file(repository_environment)
    if filename is None or content is None:
        return result

    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        result["errors"].append(
            {"source": filename, "reason": "YAML content is invalid"}
        )
        return result

    if not isinstance(document, dict):
        result["errors"].append(
            {"source": filename, "reason": "Conda environment root must be a mapping"}
        )
        return result

    dependencies = document.get("dependencies", [])
    if not isinstance(dependencies, list):
        result["errors"].append(
            {"source": filename, "reason": "Conda dependencies must be a list"}
        )
        return result

    result["package_manager"] = "conda"
    _add_evidence(result, filename, "package_manager", "conda")

    environment_name = document.get("name")
    if isinstance(environment_name, str) and environment_name.strip():
        result["environment_name"] = environment_name.strip()
        _add_evidence(result, filename, "environment_name", environment_name.strip())

    for item in dependencies:
        if isinstance(item, str):
            dependency = _parse_dependency(item, filename)
            if dependency is not None:
                _apply_dependency_metadata(result, dependency, item)
            continue

        if not isinstance(item, dict):
            continue

        pip_dependencies = item.get("pip")
        if not isinstance(pip_dependencies, list):
            continue

        pip_source = f"{filename}:pip"
        for pip_item in pip_dependencies:
            if not isinstance(pip_item, str):
                continue
            dependency = _parse_dependency(pip_item, pip_source)
            if dependency is not None:
                _apply_dependency_metadata(result, dependency, pip_item)

    return result
