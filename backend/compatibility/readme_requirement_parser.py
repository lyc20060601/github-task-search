"""Deterministic extraction of explicit environment requirements from README text."""

from __future__ import annotations

import re
from typing import Any

from .evidence import make_evidence


_VERSION = r"\d+(?:\.\d+){0,3}"
_HARD_WORDS = re.compile(
    r"\b(?:require(?:s|d)?|must|need(?:s|ed)?|minimum|at\s+least|only)\b",
    re.IGNORECASE,
)
_PYTHON = re.compile(
    rf"\bpython(?:\s+version)?\s*(?P<operator>>=|<=|==|=|>|<|~=)?\s*(?P<version>{_VERSION})\b",
    re.IGNORECASE,
)
_CUDA = re.compile(rf"\bcuda(?:\s+version)?\s*(?P<version>{_VERSION})?\b", re.IGNORECASE)
_MEMORY = re.compile(
    rf"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>GB|GiB)\b", re.IGNORECASE
)
_FRAMEWORK = re.compile(
    rf"\b(?P<name>pytorch|tensorflow|jax)(?:\s*(?:version\s*)?(?P<version>{_VERSION}))?\b",
    re.IGNORECASE,
)


def _empty_result() -> dict[str, Any]:
    return {
        "supported_os": [],
        "preferred_os": None,
        "python_min_version": None,
        "python_max_version": None,
        "python_exact_version": None,
        "framework": None,
        "framework_version": None,
        "cuda_required": None,
        "cuda_version": None,
        "gpu_required": None,
        "gpu_vendor": None,
        "minimum_gpu_memory_gb": None,
        "minimum_ram_gb": None,
        "docker_supported": None,
        "package_manager": None,
        "special_requirements": [],
        "evidence": [],
        "soft_hints": [],
        "errors": [],
    }


def _evidence(
    result: dict[str, Any], field: str, line_number: int, text: str, **extra: Any
) -> None:
    item: dict[str, Any] = {
        "source": "README.md",
        "field": field,
        "line": line_number,
        "text": text,
    }
    record = make_evidence(
        field=field,
        value=extra.get("value"),
        source_file="README.md",
        raw_text=text,
        confidence=extra.get("confidence", "high"),
        evidence_type=extra.get("evidence_type", "explicit"),
        location=f"line {line_number}",
    )
    if record is not None:
        record.update(item)
        record.update(extra)
        result["evidence"].append(record)


def _soft_hint(result: dict[str, Any], line_number: int, text: str, kind: str) -> None:
    result["soft_hints"].append(
        {"source": "README.md", "line": line_number, "text": text, "kind": kind}
    )


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _parse_python(result: dict[str, Any], line: str, number: int, hard: bool) -> None:
    match = _PYTHON.search(line)
    if not match or not hard:
        return
    version = match.group("version")
    operator = match.group("operator") or "="
    if operator in {">", ">=", "~="}:
        result["python_min_version"] = version
        field = "python_min_version"
    elif operator in {"<", "<="}:
        result["python_max_version"] = version
        field = "python_max_version"
    else:
        result["python_exact_version"] = version
        field = "python_exact_version"
    _evidence(result, field, number, line)


def _parse_framework(result: dict[str, Any], line: str, number: int) -> None:
    match = _FRAMEWORK.search(line)
    if not match:
        return
    names = {"pytorch": "PyTorch", "tensorflow": "TensorFlow", "jax": "JAX"}
    framework = names[match.group("name").lower()]
    if result["framework"] is None:
        result["framework"] = framework
        _evidence(result, "framework", number, line)
    version = match.group("version")
    if version and result["framework_version"] is None:
        result["framework_version"] = version
        _evidence(result, "framework_version", number, line)


def _parse_os(result: dict[str, Any], line: str, number: int) -> None:
    lower = line.lower()
    has_linux = bool(re.search(r"\blinux\b", lower))
    has_windows = bool(re.search(r"\bwindows\b", lower))
    if not (has_linux or has_windows):
        return
    only = bool(re.search(r"\b(?:only|exclusively)\b", lower))
    if only:
        selected = "Linux" if has_linux and not has_windows else "Windows"
        result["supported_os"] = [selected]
        result["preferred_os"] = selected
        _evidence(result, "supported_os", number, line)
    elif has_linux and has_windows:
        result["supported_os"] = ["Windows", "Linux"]
        _evidence(result, "supported_os", number, line)


def _parse_memory(
    result: dict[str, Any], line: str, number: int, hard: bool
) -> None:
    if not hard:
        return
    matches = list(_MEMORY.finditer(line))
    if not matches:
        return
    lower = line.lower()
    value = float(matches[0].group("value"))
    if value.is_integer():
        parsed_value: int | float = int(value)
    else:
        parsed_value = value
    if "vram" in lower or "gpu memory" in lower or "video memory" in lower:
        result["minimum_gpu_memory_gb"] = parsed_value
        _evidence(result, "minimum_gpu_memory_gb", number, line)
    elif re.search(r"\b(?:ram|system memory|memory)\b", lower):
        result["minimum_ram_gb"] = parsed_value
        _evidence(result, "minimum_ram_gb", number, line)


def parse_readme_requirements(readme_text: str) -> dict[str, Any]:
    """Extract only explicit README environment requirements.

    The input is treated as untrusted plain text. No Markdown, shell, Python,
    Docker, or other README content is executed.
    """

    result = _empty_result()
    if not isinstance(readme_text, str) or not readme_text.strip():
        return result

    for line_number, raw_line in enumerate(readme_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        hard = bool(_HARD_WORDS.search(line))
        recommended = bool(re.search(r"\brecommend(?:ed|s)?\b|suggested", lower))
        tested = bool(re.search(r"\btested\s+(?:on|with)\b|verified\s+(?:on|with)", lower))
        supports = bool(re.search(r"\bsupport(?:s|ed)?\b|available", lower))

        if tested:
            _soft_hint(result, line_number, line, "tested")
        elif recommended:
            _soft_hint(result, line_number, line, "recommended")
        elif supports and not hard:
            _soft_hint(result, line_number, line, "supported")

        _parse_os(result, line, line_number)
        _parse_framework(result, line, line_number)
        _parse_python(result, line, line_number, hard)
        _parse_memory(result, line, line_number, hard and not recommended and not tested)

        cuda_match = _CUDA.search(line)
        if cuda_match:
            cuda_version = cuda_match.group("version")
            if cuda_version and result["cuda_version"] is None:
                result["cuda_version"] = cuda_version
                _evidence(result, "cuda_version", line_number, line)
            if hard and not recommended and not tested:
                result["cuda_required"] = True
                _evidence(result, "cuda_required", line_number, line)

        if hard and not recommended and not tested:
            if re.search(r"\bNVIDIA\b.*\bGPU\b|\bGPU\b.*\bNVIDIA\b", line, re.I):
                result["gpu_required"] = True
                result["gpu_vendor"] = "NVIDIA"
                _evidence(result, "gpu_required", line_number, line)
                _evidence(result, "gpu_vendor", line_number, line)
                if "cuda" in lower:
                    result["cuda_required"] = True
                    _evidence(result, "cuda_required", line_number, line)
            elif re.search(r"\bGPU\b.*\b(?:required|necessary|needed)\b", line, re.I):
                result["gpu_required"] = True
                _evidence(result, "gpu_required", line_number, line)

        if re.search(r"\bdocker\b", lower) and re.search(
            r"\b(?:supported|support|use|using|requires?|recommended)\b", lower
        ):
            if re.search(r"\brequires?\b|\bmust\b|\bneeded\b", lower):
                result["docker_supported"] = True
            elif result["docker_supported"] is None:
                result["docker_supported"] = True
            _evidence(result, "docker_supported", line_number, line)

        if "pip install" in lower or "pip3 install" in lower:
            result["package_manager"] = "pip"
            _evidence(result, "package_manager", line_number, line)
        elif "conda install" in lower or "conda env" in lower:
            result["package_manager"] = "conda"
            _evidence(result, "package_manager", line_number, line)

        if hard and not recommended and not tested:
            if lower.startswith(("requires ", "required ", "must ", "need ")):
                if not any(
                    token in lower
                    for token in ("python", "cuda", "gpu", "ram", "memory", "docker")
                ):
                    result["special_requirements"].append(line)
                    _evidence(result, "special_requirements", line_number, line)

    return result
