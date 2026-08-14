"""Normalize explicit project requirements without compatibility inference."""

from __future__ import annotations

import re
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, Field

from .project_requirements import ProjectRequirements


_VERSION = r"\d+(?:\.\d+){1,2}"
_OPERATOR = r"~=|==|>=|<=|>|<"


class NormalizedValue(BaseModel):
    """One original value and its conservative normalized representation."""

    raw: Any = None
    normalized: Any = None


class NormalizedProjectRequirements(BaseModel):
    """Original requirements plus normalized values for comparable fields."""

    raw: ProjectRequirements
    normalized: dict[str, Any] = Field(default_factory=dict)


def _canonical_version(value: str) -> str | None:
    try:
        return str(Version(value))
    except InvalidVersion:
        return None


def _valid_specifier(value: str) -> str | None:
    try:
        SpecifierSet(value)
    except InvalidSpecifier:
        return None
    return value


def _normalize_version_expression(
    raw: Any,
    *,
    prefix: str | None = None,
    default_operator: str = "==",
) -> NormalizedValue:
    result = NormalizedValue(raw=raw)
    if raw is None or not isinstance(raw, (str, int, float)):
        return result

    text = str(raw).strip()
    if not text or text.casefold() in {"unknown", "null", "none"}:
        return result

    if prefix:
        text = re.sub(rf"^{prefix}\s*", "", text, flags=re.IGNORECASE).strip()

    range_match = re.fullmatch(rf"({_VERSION})\s*[-–]\s*({_VERSION})", text)
    if range_match:
        minimum = _canonical_version(range_match.group(1))
        maximum = _canonical_version(range_match.group(2))
        if minimum is None or maximum is None or Version(minimum) > Version(maximum):
            return result
        result.normalized = f">={minimum},<={maximum}"
        return result

    plus_match = re.fullmatch(rf"({_VERSION})\s*\+", text)
    if plus_match:
        version = _canonical_version(plus_match.group(1))
        result.normalized = _valid_specifier(f">={version}") if version else None
        return result

    operator_match = re.fullmatch(rf"({_OPERATOR})\s*({_VERSION})", text)
    if operator_match:
        version = _canonical_version(operator_match.group(2))
        expression = f"{operator_match.group(1)}{version}" if version else ""
        result.normalized = _valid_specifier(expression) if expression else None
        return result

    bare_match = re.fullmatch(rf"({_VERSION})", text)
    if bare_match:
        version = _canonical_version(bare_match.group(1))
        expression = f"{default_operator}{version}" if version else ""
        result.normalized = _valid_specifier(expression) if expression else None
    return result


def normalize_python_version(
    raw: Any, *, default_operator: str = "=="
) -> NormalizedValue:
    """Normalize an explicit Python version or version constraint."""

    return _normalize_version_expression(
        raw,
        prefix=r"python",
        default_operator=default_operator,
    )


def normalize_cuda_version(
    raw: Any, *, default_operator: str = "=="
) -> NormalizedValue:
    """Normalize an explicit CUDA version without driver compatibility inference."""

    result = NormalizedValue(raw=raw)
    if isinstance(raw, str):
        compact = raw.strip().casefold()
        wheel_tag = re.fullmatch(r"cu(\d{2})(\d)", compact)
        if wheel_tag:
            version = f"{int(wheel_tag.group(1))}.{int(wheel_tag.group(2))}"
            result.normalized = f"=={version}"
            return result

    return _normalize_version_expression(
        raw,
        prefix=r"cuda",
        default_operator=default_operator,
    )


def normalize_capacity(
    raw: Any, *, default_operator: str | None = None
) -> NormalizedValue:
    """Normalize an explicitly GB-denominated RAM or GPU-memory value."""

    result = NormalizedValue(raw=raw)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if raw >= 0:
            result.normalized = {
                "gigabytes": float(raw),
                "operator": default_operator,
            }
        return result
    if not isinstance(raw, str):
        return result

    text = " ".join(raw.strip().split())
    if not text or text.casefold() in {"unknown", "null", "none"}:
        return result

    label = r"(?:vram|gpu\s+memory|ram|memory)"
    number = r"(?P<number>\d+(?:\.\d+)?)"
    unit = r"(?:gb|g)"
    leading = re.fullmatch(
        rf"(?P<minimum>>=|at\s+least)?\s*{number}\s*{unit}\s*{label}",
        text,
        flags=re.IGNORECASE,
    )
    trailing = re.fullmatch(
        rf"{label}\s*(?P<minimum>>=|at\s+least)?\s*{number}\s*{unit}",
        text,
        flags=re.IGNORECASE,
    )
    match = leading or trailing
    if not match:
        return result

    operator = ">=" if match.group("minimum") else default_operator
    result.normalized = {
        "gigabytes": float(match.group("number")),
        "operator": operator,
    }
    return result


def normalize_os_requirement(raw: Any) -> NormalizedValue:
    """Normalize explicitly named supported operating systems and releases."""

    result = NormalizedValue(raw=raw)
    if not isinstance(raw, str):
        return result

    text = " ".join(raw.strip().split())
    windows = re.fullmatch(r"windows(?:\s+(10|11))?", text, flags=re.IGNORECASE)
    if windows:
        result.normalized = {
            "family": "Windows",
            "version": windows.group(1),
            "distribution": None,
        }
        return result

    if re.fullmatch(r"linux", text, flags=re.IGNORECASE):
        result.normalized = {
            "family": "Linux",
            "version": None,
            "distribution": None,
        }
        return result

    ubuntu = re.fullmatch(
        r"ubuntu(?:\s+(\d{2}\.\d{2})(?:\s+lts)?)?",
        text,
        flags=re.IGNORECASE,
    )
    if ubuntu:
        result.normalized = {
            "family": "Linux",
            "version": ubuntu.group(1),
            "distribution": "Ubuntu",
        }
        return result

    macos = re.fullmatch(r"(?:macos|mac\s+os)", text, flags=re.IGNORECASE)
    if macos:
        result.normalized = {
            "family": "macOS",
            "version": None,
            "distribution": None,
        }
    return result


def _dump(result: NormalizedValue) -> dict[str, Any]:
    return result.model_dump()


def normalize_project_requirements(
    requirements: ProjectRequirements,
) -> NormalizedProjectRequirements:
    """Normalize comparable ProjectRequirements fields without mutating the input."""

    supported_os = None
    if requirements.supported_os is not None:
        supported_os = [
            _dump(normalize_os_requirement(value)) for value in requirements.supported_os
        ]

    normalized = {
        "supported_os": supported_os,
        "preferred_os": _dump(normalize_os_requirement(requirements.preferred_os)),
        "python_min_version": _dump(
            normalize_python_version(requirements.python_min_version, default_operator=">=")
        ),
        "python_max_version": _dump(
            normalize_python_version(requirements.python_max_version, default_operator="<=")
        ),
        "python_exact_version": _dump(
            normalize_python_version(requirements.python_exact_version, default_operator="==")
        ),
        "cuda_version": _dump(normalize_cuda_version(requirements.cuda_version)),
        "minimum_gpu_memory_gb": _dump(
            normalize_capacity(requirements.minimum_gpu_memory_gb, default_operator=">=")
        ),
        "minimum_ram_gb": _dump(
            normalize_capacity(requirements.minimum_ram_gb, default_operator=">=")
        ),
    }
    return NormalizedProjectRequirements(raw=requirements, normalized=normalized)
