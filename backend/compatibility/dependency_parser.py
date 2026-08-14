from __future__ import annotations

import ast
import configparser
import re
import tomllib
from collections.abc import Iterable
from typing import Any

from .evidence import make_evidence


SUPPORTED_FILES = frozenset(
    {
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Pipfile",
        "runtime.txt",
        ".python-version",
    }
)
FILE_PRIORITY = (
    "requirements.txt",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "Pipfile",
)
DEPENDENCY_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<rest>.*)$"
)
VERSION_RE = re.compile(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)")
FRAMEWORKS = {
    "torch": "PyTorch",
    "torchvision": "PyTorch",
    "torchaudio": "PyTorch",
    "tensorflow": "TensorFlow",
    "tensorflow-cpu": "TensorFlow",
    "tensorflow-gpu": "TensorFlow",
    "jax": "JAX",
    "jaxlib": "JAX",
}


def _empty_result() -> dict[str, Any]:
    return {
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


def _evidence(source: str, field: str, value: Any) -> dict[str, Any]:
    record = make_evidence(
        field=field,
        value=value,
        source_file=source,
        raw_text=str(value),
        evidence_type="dependency" if field == "dependency" else "explicit",
    )
    return record or {"source": source, "field": field, "value": value}


def _add_error(result: dict[str, Any], source: str, reason: str) -> None:
    result["errors"].append({"source": source, "reason": reason})


def _content(files: dict[str, Any], name: str) -> str | None:
    entry = files.get(name)
    if not isinstance(entry, dict) or not isinstance(entry.get("content"), str):
        return None
    return entry["content"]


def _parse_dependency(value: str, source: str) -> dict[str, Any] | None:
    line = value.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith(("-", "--", ".", "/", "\\")):
        return None
    if "://" in line or line.startswith(("git+", "file:")):
        return None
    line = line.split(" #", 1)[0].strip()
    match = DEPENDENCY_RE.match(line)
    if not match:
        return None
    name = match.group("name").replace("_", "-").lower()
    rest = match.group("rest").strip()
    return {
        "name": name,
        "version_spec": rest or None,
        "source": source,
    }


def _add_dependency(
    result: dict[str, Any],
    raw: str,
    source: str,
) -> None:
    dependency = _parse_dependency(raw, source)
    if dependency is None:
        return
    key = (
        dependency["name"].casefold(),
        dependency["version_spec"] or "",
        source,
    )
    existing_keys = {
        (item["name"].casefold(), item["version_spec"] or "", item["source"])
        for item in result["dependencies"]
    }
    if key in existing_keys:
        return
    result["dependencies"].append(dependency)
    result["evidence"].append(_evidence(source, "dependency", raw.strip()))


def _parse_dependency_values(result: dict[str, Any], values: Iterable[Any], source: str) -> None:
    for value in values:
        if isinstance(value, str):
            _add_dependency(result, value, source)


def _version_values(spec: str) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for operator, version in re.findall(
        r"(===|==|~=|>=|<=|>|<)\s*(\d+\.\d+(?:\.\d+)?)", spec
    ):
        values.append((operator, version))
    return values


def _apply_python_spec(result: dict[str, Any], spec: str, source: str) -> None:
    result["evidence"].append(_evidence(source, "python_requirement", spec))
    for operator, version in _version_values(spec):
        if operator in {"==", "==="}:
            result["python_exact_version"] = version
        elif operator in {">", ">=", "~=", "==="}:
            if result["python_min_version"] is None:
                result["python_min_version"] = version
        elif operator in {"<", "<="}:
            if result["python_max_version"] is None:
                result["python_max_version"] = version


def _parse_requirements(result: dict[str, Any], text: str, source: str) -> None:
    for line in text.splitlines():
        _add_dependency(result, line, source)


def _parse_pyproject(result: dict[str, Any], text: str, source: str) -> None:
    data = tomllib.loads(text)
    project = data.get("project", {})
    if isinstance(project, dict):
        requires_python = project.get("requires-python")
        if isinstance(requires_python, str):
            _apply_python_spec(result, requires_python, source)
        dependencies = project.get("dependencies", [])
        if isinstance(dependencies, list):
            _parse_dependency_values(result, dependencies, source)

    poetry = data.get("tool", {}).get("poetry", {})
    if isinstance(poetry, dict):
        poetry_dependencies = poetry.get("dependencies", {})
        if isinstance(poetry_dependencies, dict):
            python_spec = poetry_dependencies.get("python")
            if isinstance(python_spec, str):
                _apply_python_spec(result, python_spec, source)
            for name, spec in poetry_dependencies.items():
                if name == "python":
                    continue
                raw = name if not isinstance(spec, str) or spec == "*" else f"{name}{spec}"
                _add_dependency(result, raw, source)


def _parse_setup_cfg(result: dict[str, Any], text: str, source: str) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    if not parser.has_section("options"):
        return
    if parser.has_option("options", "python_requires"):
        _apply_python_spec(result, parser.get("options", "python_requires"), source)
    if parser.has_option("options", "install_requires"):
        _parse_requirements(result, parser.get("options", "install_requires"), source)


def _literal_strings(node: ast.AST) -> list[str]:
    value = ast.literal_eval(node)
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return list(value)
    raise ValueError("value is not a static string collection")


def _parse_setup_py(result: dict[str, Any], text: str, source: str) -> None:
    tree = ast.parse(text, filename=source, mode="exec")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        is_setup = isinstance(node.func, ast.Name) and node.func.id == "setup"
        is_setup = is_setup or (
            isinstance(node.func, ast.Attribute) and node.func.attr == "setup"
        )
        if not is_setup:
            continue
        for keyword in node.keywords:
            if keyword.arg == "python_requires":
                values = _literal_strings(keyword.value)
                if values:
                    _apply_python_spec(result, values[0], source)
            elif keyword.arg == "install_requires":
                _parse_dependency_values(result, _literal_strings(keyword.value), source)


def _parse_pipfile(result: dict[str, Any], text: str, source: str) -> None:
    data = tomllib.loads(text)
    requires = data.get("requires", {})
    if isinstance(requires, dict):
        for key in ("python_full_version", "python_version"):
            value = requires.get(key)
            if isinstance(value, str):
                if key == "python_full_version" or VERSION_RE.fullmatch(value.strip()):
                    result["python_exact_version"] = value.strip()
                    result["evidence"].append(_evidence(source, key, value.strip()))
                    break
    for section in ("packages", "dev-packages"):
        packages = data.get(section, {})
        if not isinstance(packages, dict):
            continue
        for name, spec in packages.items():
            if not isinstance(name, str):
                continue
            if isinstance(spec, str):
                raw = name if spec == "*" else f"{name}{spec}"
            elif isinstance(spec, dict) and isinstance(spec.get("version"), str):
                raw = f"{name}{spec['version']}"
            else:
                raw = name
            _add_dependency(result, raw, source)


def _extract_exact_version(text: str) -> str | None:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    match = re.search(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", first_line)
    return match.group(1) if match else None


def _detect_framework(result: dict[str, Any]) -> None:
    for source in FILE_PRIORITY:
        for dependency in result["dependencies"]:
            if dependency["source"] != source:
                continue
            framework = FRAMEWORKS.get(dependency["name"])
            if framework is None:
                continue
            if result["framework"] is None:
                result["framework"] = framework
                result["framework_version"] = dependency["version_spec"]
                result["evidence"].append(_evidence(source, "framework", framework))
            return


def parse_python_dependencies(environment_files: dict[str, object]) -> dict[str, Any]:
    result = _empty_result()
    raw_files = environment_files.get("files") if isinstance(environment_files, dict) else None
    if not isinstance(raw_files, dict):
        return result

    files: dict[str, Any] = {}
    for name in SUPPORTED_FILES:
        if name not in raw_files:
            continue
        value = _content(raw_files, name)
        if value is None:
            _add_error(result, name, "file content is invalid")
        else:
            files[name] = value

    parsers = {
        "requirements.txt": _parse_requirements,
        "pyproject.toml": _parse_pyproject,
        "setup.cfg": _parse_setup_cfg,
        "setup.py": _parse_setup_py,
        "Pipfile": _parse_pipfile,
    }
    for name in FILE_PRIORITY:
        text = files.get(name)
        if text is None:
            continue
        try:
            parsers[name](result, text, name)
        except (SyntaxError, ValueError, TypeError, configparser.Error, tomllib.TOMLDecodeError):
            reason = "TOML content is invalid" if name in {"pyproject.toml", "Pipfile"} else "file content is invalid"
            _add_error(result, name, reason)

    dedicated_version: tuple[str, str] | None = None
    for name in (".python-version", "runtime.txt"):
        text = files.get(name)
        if text is None:
            continue
        version = _extract_exact_version(text)
        if version is not None and dedicated_version is None:
            dedicated_version = (name, version)
    if dedicated_version is not None:
        source, version = dedicated_version
        result["python_exact_version"] = version
        result["evidence"].append(_evidence(source, "python_exact_version", version))

    if any(name in files for name in ("requirements.txt", "pyproject.toml", "setup.cfg", "setup.py")):
        result["package_manager"] = "pip"
        result["evidence"].append(_evidence("package manifests", "package_manager", "pip"))
    elif "Pipfile" in files:
        result["package_manager"] = "pipenv"
        result["evidence"].append(_evidence("Pipfile", "package_manager", "pipenv"))

    _detect_framework(result)
    return result
