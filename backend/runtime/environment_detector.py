"""Static environment detection for a cloned repository.

Only allow-listed text files are read. No configuration file, installer, or
README instruction is executed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


SUPPORTED_FILES = (
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "environment.yml",
    "Pipfile",
    "Dockerfile",
    ".python-version",
    "runtime.txt",
)
README_FILES = ("README.md", "README.rst", "README.txt", "README")


@dataclass
class EnvironmentDetection:
    """Facts inferred from repository text files only."""

    python_version: str = "unknown"
    package_manager: str = "unknown"
    framework: str = "unknown"
    pytorch_version: str = "unknown"
    cuda_version: str = "unknown"

    has_requirements: bool = False
    has_environment_yml: bool = False
    has_dockerfile: bool = False

    detected_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _first_match(patterns: Iterable[str], text: str, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip()
    return None


def _clean_version(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().strip("\"'")
    cleaned = re.split(r"\s*(?:#|,|;|\bor\b)\s*", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    return cleaned.strip() or None


def _detect_python_version(file_text: dict[str, str], readme: str) -> str:
    for filename in (".python-version", "runtime.txt"):
        value = _clean_version(file_text.get(filename, "").splitlines()[0] if file_text.get(filename) else None)
        if value:
            return value

    value = _first_match(
        (
            r"(?:^|\n)\s*-\s*python\s*=\s*([0-9]+(?:\.[0-9]+){1,2})",
            r"(?:^|\n)\s*python(?:_version)?\s*[:=]\s*[\"']?([0-9]+(?:\.[0-9]+){1,2})",
            r"python_requires\s*=\s*[\"'][^\"']*?([0-9]+(?:\.[0-9]+){1,2})",
            r"requires-python\s*=\s*[\"'][^\"']*?([0-9]+(?:\.[0-9]+){1,2})",
            r"python\s*[=:]\s*([0-9]+(?:\.[0-9]+){1,2})",
            r"python\s+([0-9]+(?:\.[0-9]+){1,2})\s*(?:\+|or\s+later)?",
        ),
        "\n".join(file_text.values()) + "\n" + readme,
    )
    return value or "unknown"


def _detect_framework(all_text: str) -> str:
    if re.search(r"\b(?:pytorch|torch|torchvision|torchaudio)\b", all_text, re.IGNORECASE):
        return "PyTorch"
    if re.search(r"\b(?:tensorflow|keras)\b", all_text, re.IGNORECASE):
        return "TensorFlow"
    if re.search(r"\b(?:jax|flax)\b", all_text, re.IGNORECASE):
        return "JAX"
    return "unknown"


def _detect_pytorch_version(all_text: str) -> str:
    value = _first_match(
        (
            r"\btorch(?:vision|audio)?\s*(?:==|>=|~=|=)\s*([0-9]+(?:\.[0-9]+){1,2})",
            r"\bpytorch\s*(?:==|>=|~=|=)\s*([0-9]+(?:\.[0-9]+){1,2})",
            r"\b(?:pytorch|torch)\s+(?:version\s+)?([0-9]+(?:\.[0-9]+){1,2})",
        ),
        all_text,
    )
    return value or "unknown"


def _detect_cuda_version(all_text: str) -> str:
    value = _first_match(
        (
            r"\bcuda(?:toolkit|_version|\s+version)?\s*(?:==|>=|~=|=|:)\s*([0-9]+(?:\.[0-9]+){1,2})",
            r"\bCUDA\s+([0-9]+(?:\.[0-9]+){1,2})",
            r"nvidia/cuda:([0-9]+(?:\.[0-9]+){1,2})",
        ),
        all_text,
    )
    return value or "unknown"


def detect_environment(repository_path: str | Path, readme_text: str | None = None) -> EnvironmentDetection:
    """Inspect allow-listed repository files without executing any of them."""

    path = Path(repository_path)
    result = EnvironmentDetection()
    if not path.is_dir():
        result.errors.append("Repository path is not a directory")
        return result

    file_text: dict[str, str] = {}
    for filename in SUPPORTED_FILES:
        candidate = path / filename
        if candidate.is_file():
            result.detected_files.append(filename)
            file_text[filename] = _read_text(candidate)

    if readme_text is None:
        for filename in README_FILES:
            candidate = path / filename
            if candidate.is_file():
                result.detected_files.append(filename)
                readme_text = _read_text(candidate)
                break
    readme = readme_text or ""
    all_text = "\n".join(file_text.values()) + "\n" + readme

    result.has_requirements = "requirements.txt" in file_text
    result.has_environment_yml = "environment.yml" in file_text
    result.has_dockerfile = "Dockerfile" in file_text
    result.python_version = _detect_python_version(file_text, readme)
    result.framework = _detect_framework(all_text)
    result.pytorch_version = _detect_pytorch_version(all_text)
    result.cuda_version = _detect_cuda_version(all_text)

    if result.has_environment_yml:
        result.package_manager = "conda"
    elif "Pipfile" in file_text:
        result.package_manager = "pipenv"
    elif any(name in file_text for name in ("requirements.txt", "pyproject.toml", "setup.py")):
        result.package_manager = "pip"

    if not result.detected_files:
        result.warnings.append("No supported environment files or README were found")
    return result
