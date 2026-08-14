"""Deterministic compatibility checks for local and project environments."""

from __future__ import annotations

import re
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .compatibility_models import CompatibilityCheck
from .evidence import Evidence
from .models import MachineProfile
from .project_requirements import ProjectRequirements
from .requirement_normalizer import (
    normalize_cuda_version,
    normalize_os_requirement,
    normalize_python_version,
)


_UNKNOWN_VALUES = {"", "unknown", "null", "none"}
_DOCKER_REQUIRED = re.compile(
    r"\b(?:docker\s+(?:is\s+)?(?:required|mandatory)|"
    r"requires?\s+docker|must\s+(?:use|have|install)\s+docker|"
    r"docker[-\s]+only)\b",
    re.IGNORECASE,
)
_EXCLUSIVE_OS = re.compile(
    r"\b(?:only|exclusively)\b|(?:仅支持|只支持)",
    re.IGNORECASE,
)


def _is_declared(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in _UNKNOWN_VALUES
    return True


def _python_evidence(requirements: ProjectRequirements) -> list[Evidence | str]:
    relevant: list[Evidence | str] = []
    for item in requirements.evidence or []:
        if isinstance(item, Evidence):
            if item.field.startswith("python"):
                relevant.append(item)
        else:
            relevant.append(item)
    return relevant


def _requirement_display(requirements: ProjectRequirements) -> str | None:
    values = [
        requirements.python_exact_version,
        requirements.python_min_version,
        requirements.python_max_version,
    ]
    declared = [str(value).strip() for value in values if _is_declared(value)]
    return ",".join(declared) or None


def _python_specifier(
    requirements: ProjectRequirements,
) -> tuple[SpecifierSet | None, str | None]:
    expressions: list[str] = []
    fields = (
        (requirements.python_exact_version, "=="),
        (requirements.python_min_version, ">="),
        (requirements.python_max_version, "<="),
    )
    for raw, default_operator in fields:
        if not _is_declared(raw):
            continue
        normalized = normalize_python_version(
            raw,
            default_operator=default_operator,
        ).normalized
        if normalized is None:
            return None, _requirement_display(requirements)
        expressions.append(normalized)

    if not expressions:
        return None, None

    display = ",".join(expressions)
    try:
        return SpecifierSet(display), display
    except InvalidSpecifier:
        return None, _requirement_display(requirements)


def check_python_compatibility(
    machine_profile: MachineProfile,
    project_requirements: ProjectRequirements,
) -> CompatibilityCheck:
    """Compare only the local Python version with explicit project constraints."""

    specifier, required_value = _python_specifier(project_requirements)
    evidence = _python_evidence(project_requirements)
    local_version = machine_profile.python_version

    if required_value is None:
        return CompatibilityCheck(
            component="python",
            local_value=local_version,
            required_value=None,
            status="unknown",
            reason=(
                f"Local Python version is {local_version or 'unknown'}. "
                "The project does not declare a Python version requirement, "
                "so compatibility is unknown."
            ),
            evidence=evidence,
        )

    if machine_profile.python_available is False:
        return CompatibilityCheck(
            component="python",
            local_value="unavailable",
            required_value=required_value,
            status="incompatible",
            reason=(
                f"Local Python is not available. Project requires {required_value}, "
                "so the requirement cannot be satisfied."
            ),
            evidence=evidence,
        )

    if specifier is None:
        return CompatibilityCheck(
            component="python",
            local_value=local_version,
            required_value=required_value,
            status="unknown",
            reason=(
                f"Local Python version is {local_version or 'unknown'}. "
                f"Project requirement '{required_value}' cannot be parsed reliably, "
                "so compatibility is unknown."
            ),
            evidence=evidence,
        )

    if machine_profile.python_available is not True:
        return CompatibilityCheck(
            component="python",
            local_value=local_version,
            required_value=required_value,
            status="unknown",
            reason=(
                "Local Python availability cannot be determined. "
                f"Project requires {required_value}, so compatibility is unknown."
            ),
            evidence=evidence,
        )

    if not _is_declared(local_version):
        version_problem = (
            "cannot be determined"
            if local_version is None
            else f"'{local_version}' cannot be parsed reliably"
        )
        return CompatibilityCheck(
            component="python",
            local_value=local_version,
            required_value=required_value,
            status="unknown",
            reason=(
                f"Local Python is available, but its version {version_problem}. "
                f"Project requires {required_value}, so compatibility is unknown."
            ),
            evidence=evidence,
        )

    try:
        parsed_local = Version(str(local_version).strip())
    except InvalidVersion:
        return CompatibilityCheck(
            component="python",
            local_value=local_version,
            required_value=required_value,
            status="unknown",
            reason=(
                f"Local Python version '{local_version}' cannot be parsed reliably. "
                f"Project requires {required_value}, so compatibility is unknown."
            ),
            evidence=evidence,
        )

    compatible = specifier.contains(parsed_local, prereleases=True)
    status = "compatible" if compatible else "incompatible"
    relation = "satisfies" if compatible else "does not satisfy"
    return CompatibilityCheck(
        component="python",
        local_value=local_version,
        required_value=required_value,
        status=status,
        reason=(
            f"Local Python version {local_version} {relation} "
            f"project requirement {required_value}."
        ),
        evidence=evidence,
    )


def _os_evidence(requirements: ProjectRequirements) -> list[Evidence | str]:
    relevant: list[Evidence | str] = []
    for item in requirements.evidence or []:
        if isinstance(item, Evidence):
            if item.field in {"supported_os", "preferred_os"}:
                relevant.append(item)
        else:
            relevant.append(item)
    return relevant


def _normalize_os(value: Any) -> dict[str, Any] | None:
    if not _is_declared(value):
        return None
    text = str(value).strip()
    normalized = normalize_os_requirement(text).normalized
    if normalized is not None:
        return normalized

    without_exclusive = _EXCLUSIVE_OS.sub("", text).strip(" .,:;-()")
    normalized = normalize_os_requirement(without_exclusive).normalized
    if normalized is not None:
        return normalized

    if text.casefold() == "darwin":
        return {"family": "macOS", "version": None, "distribution": None}
    return None


def _local_os(machine: MachineProfile) -> tuple[str | None, dict[str, Any] | None]:
    name = machine.os_name.strip() if _is_declared(machine.os_name) else None
    version = machine.os_version.strip() if _is_declared(machine.os_version) else None
    display = " ".join(part for part in (name, version) if part) or None

    normalized = _normalize_os(name)
    version_normalized = _normalize_os(version)
    if version_normalized is not None:
        if normalized is None or version_normalized["family"] == normalized["family"]:
            normalized = version_normalized
    return display, normalized


def _has_exclusive_os_requirement(requirements: ProjectRequirements) -> bool:
    texts = [str(value) for value in requirements.supported_os or []]
    texts.extend(requirements.special_requirements or [])
    for item in requirements.evidence or []:
        if isinstance(item, Evidence) and item.field in {"supported_os", "preferred_os"}:
            texts.append(item.raw_text)
    return any(_EXCLUSIVE_OS.search(text) for text in texts)


def _os_matches(local: dict[str, Any], required: dict[str, Any]) -> bool:
    return local["family"] == required["family"]


def check_os_compatibility(
    machine_profile: MachineProfile,
    project_requirements: ProjectRequirements,
) -> CompatibilityCheck:
    """Compare only the local OS with explicitly declared project OS support."""

    supported_raw = list(project_requirements.supported_os or [])
    preferred_raw = (
        project_requirements.preferred_os
        if _is_declared(project_requirements.preferred_os)
        else None
    )
    required_value = {
        "supported_os": supported_raw,
        "preferred_os": preferred_raw,
    }
    evidence = _os_evidence(project_requirements)
    local_display, local_normalized = _local_os(machine_profile)

    if not supported_raw:
        return CompatibilityCheck(
            component="os",
            local_value=local_display,
            required_value=required_value,
            status="unknown",
            reason=(
                f"Local OS is {local_display or 'unknown'}. The project does not "
                "declare supported operating systems, so compatibility is unknown."
            ),
            evidence=evidence,
        )

    supported_normalized = [
        normalized
        for value in supported_raw
        if (normalized := _normalize_os(value)) is not None
    ]
    supported_display = ", ".join(str(value) for value in supported_raw)
    if local_normalized is None or not supported_normalized:
        return CompatibilityCheck(
            component="os",
            local_value=local_display,
            required_value=required_value,
            status="unknown",
            reason=(
                f"Local OS is {local_display or 'unknown'} and project support is "
                f"{supported_display}. One or both values cannot be normalized "
                "reliably, so compatibility is unknown."
            ),
            evidence=evidence,
        )

    if any(_os_matches(local_normalized, item) for item in supported_normalized):
        preferred = _normalize_os(preferred_raw)
        preference_note = ""
        if preferred_raw and (
            preferred is None
            or not _os_matches(local_normalized, preferred)
            or (
                preferred.get("distribution")
                and preferred.get("distribution")
                != local_normalized.get("distribution")
            )
        ):
            preference_note = (
                f" The project preferred environment is {preferred_raw}, which "
                "differs from the detected local environment."
            )
        return CompatibilityCheck(
            component="os",
            local_value=local_display,
            required_value=required_value,
            status="compatible",
            reason=(
                f"Local OS {local_display} belongs to the explicitly supported "
                f"set: {supported_display}.{preference_note}"
            ),
            evidence=evidence,
        )

    if _has_exclusive_os_requirement(project_requirements):
        return CompatibilityCheck(
            component="os",
            local_value=local_display,
            required_value=required_value,
            status="incompatible",
            reason=(
                f"Local OS {local_display} is outside the project's explicit "
                f"{supported_display}-only requirement."
            ),
            evidence=evidence,
        )

    return CompatibilityCheck(
        component="os",
        local_value=local_display,
        required_value=required_value,
        status="partial",
        reason=(
            f"Local OS {local_display} is not listed in project support "
            f"({supported_display}), but the available evidence does not explicitly "
            "exclude it. Compatibility is therefore partial."
        ),
        evidence=evidence,
    )


def _ram_evidence(requirements: ProjectRequirements) -> list[Evidence | str]:
    relevant: list[Evidence | str] = []
    for item in requirements.evidence or []:
        if isinstance(item, Evidence):
            if item.field == "minimum_ram_gb":
                relevant.append(item)
        else:
            relevant.append(item)
    return relevant


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if parsed > 0 else None


def check_ram_compatibility(
    machine_profile: MachineProfile,
    project_requirements: ProjectRequirements,
) -> CompatibilityCheck:
    """Compare only total local RAM with an explicit minimum RAM requirement."""

    raw_required = project_requirements.minimum_ram_gb
    required = _positive_number(raw_required)
    local = _positive_number(machine_profile.memory_total_gb)
    evidence = _ram_evidence(project_requirements)

    if required is None:
        return CompatibilityCheck(
            component="ram",
            local_value=local,
            required_value=raw_required,
            status="unknown",
            reason=(
                f"Local RAM is {local if local is not None else 'unknown'} GB. "
                "The project does not declare a numeric minimum RAM requirement, "
                "so compatibility is unknown."
            ),
            evidence=evidence,
        )

    if local is None:
        return CompatibilityCheck(
            component="ram",
            local_value=machine_profile.memory_total_gb,
            required_value=required,
            status="unknown",
            reason=(
                "Local RAM cannot be determined. "
                f"The project requires at least {required:g} GB RAM, "
                "so compatibility is unknown."
            ),
            evidence=evidence,
        )

    tolerance = max(0.25, required * 0.01)
    compatible = local + tolerance >= required
    if compatible:
        tolerance_note = (
            " The small difference is within the display tolerance."
            if local < required
            else ""
        )
        return CompatibilityCheck(
            component="ram",
            local_value=local,
            required_value=required,
            status="compatible",
            reason=(
                f"Local RAM is {local:g} GB and the project minimum is "
                f"{required:g} GB; the minimum is satisfied.{tolerance_note}"
            ),
            evidence=evidence,
        )

    return CompatibilityCheck(
        component="ram",
        local_value=local,
        required_value=required,
        status="incompatible",
        reason=(
            f"Local RAM is {local:g} GB, which is below the project minimum "
            f"of {required:g} GB even after allowing {tolerance:g} GB for "
            "display differences."
        ),
        evidence=evidence,
    )


def _gpu_evidence(
    requirements: ProjectRequirements, fields: set[str]
) -> list[Evidence | str]:
    relevant: list[Evidence | str] = []
    for item in requirements.evidence or []:
        if isinstance(item, Evidence):
            if item.field in fields:
                relevant.append(item)
        else:
            relevant.append(item)
    return relevant


def _gpu_local_value(machine: MachineProfile) -> dict[str, Any]:
    return {
        "gpu_vendor": machine.gpu_vendor,
        "gpu_name": machine.gpu_name,
        "nvidia_gpu_available": machine.nvidia_gpu_available,
    }


def _gpu_detected(machine: MachineProfile) -> bool | None:
    if _is_declared(machine.gpu_vendor) or _is_declared(machine.gpu_name):
        return True
    if machine.nvidia_gpu_available is True:
        return True
    if machine.nvidia_gpu_available is False:
        return False
    return None


def check_gpu_compatibility(
    machine_profile: MachineProfile,
    project_requirements: ProjectRequirements,
) -> CompatibilityCheck:
    """Compare only GPU presence and an explicit GPU-vendor requirement."""

    required = project_requirements.gpu_required
    required_vendor = (
        str(project_requirements.gpu_vendor).strip()
        if _is_declared(project_requirements.gpu_vendor)
        else None
    )
    local_value = _gpu_local_value(machine_profile)
    required_value = {
        "gpu_required": required,
        "gpu_vendor": required_vendor,
    }
    evidence = _gpu_evidence(project_requirements, {"gpu_required", "gpu_vendor"})

    if required is False:
        return CompatibilityCheck(
            component="gpu",
            local_value=local_value,
            required_value=required_value,
            status="compatible",
            reason=(
                "The project does not require a GPU, so an absent or unidentified "
                "local GPU does not make the environment incompatible."
            ),
            evidence=evidence,
        )

    if required is not True:
        return CompatibilityCheck(
            component="gpu",
            local_value=local_value,
            required_value=required_value,
            status="unknown",
            reason=(
                f"Project GPU requirement is {required or 'unknown'}. "
                "GPU compatibility cannot be determined."
            ),
            evidence=evidence,
        )

    detected = _gpu_detected(machine_profile)
    if detected is False:
        return CompatibilityCheck(
            component="gpu",
            local_value=local_value,
            required_value=required_value,
            status="incompatible",
            reason=(
                "The project requires a GPU, but the machine reports no recognizable "
                "GPU, so the requirement is not satisfied."
            ),
            evidence=evidence,
        )
    if detected is None:
        return CompatibilityCheck(
            component="gpu",
            local_value=local_value,
            required_value=required_value,
            status="unknown",
            reason=(
                "The project requires a GPU, but local GPU presence cannot be "
                "determined reliably."
            ),
            evidence=evidence,
        )

    local_vendor = (
        str(machine_profile.gpu_vendor).strip()
        if _is_declared(machine_profile.gpu_vendor)
        else None
    )
    local_name = machine_profile.gpu_name or "unnamed GPU"
    if required_vendor:
        if local_vendor is None:
            return CompatibilityCheck(
                component="gpu",
                local_value=local_value,
                required_value=required_value,
                status="unknown",
                reason=(
                    f"A local GPU ({local_name}) is detected, but its vendor cannot "
                    f"be confirmed against the required vendor {required_vendor}."
                ),
                evidence=evidence,
            )
        if local_vendor.casefold() != required_vendor.casefold():
            return CompatibilityCheck(
                component="gpu",
                local_value=local_value,
                required_value=required_value,
                status="incompatible",
                reason=(
                    f"Local GPU {local_name} uses vendor {local_vendor}, while the "
                    f"project explicitly requires {required_vendor}."
                ),
                evidence=evidence,
            )

    vendor_note = f" from {local_vendor}" if local_vendor else ""
    return CompatibilityCheck(
        component="gpu",
        local_value=local_value,
        required_value=required_value,
        status="compatible",
        reason=(
            f"Local GPU {local_name}{vendor_note} is detected and satisfies the "
            f"project GPU requirement{f' for {required_vendor}' if required_vendor else ''}."
        ),
        evidence=evidence,
    )


def check_gpu_memory_compatibility(
    machine_profile: MachineProfile,
    project_requirements: ProjectRequirements,
) -> CompatibilityCheck:
    """Compare only detected GPU memory with an explicit minimum VRAM value."""

    raw_required = project_requirements.minimum_gpu_memory_gb
    required = _positive_number(raw_required)
    local = _positive_number(machine_profile.gpu_memory_gb)
    evidence = _gpu_evidence(project_requirements, {"minimum_gpu_memory_gb"})

    if required is None:
        return CompatibilityCheck(
            component="gpu_memory",
            local_value=local,
            required_value=raw_required,
            status="unknown",
            reason=(
                f"Detected GPU memory is {local if local is not None else 'unknown'} "
                "GB. The project does not declare a numeric minimum GPU-memory "
                "requirement, so compatibility is unknown."
            ),
            evidence=evidence,
        )

    if local is None:
        return CompatibilityCheck(
            component="gpu_memory",
            local_value=machine_profile.gpu_memory_gb,
            required_value=required,
            status="unknown",
            reason=(
                "Local GPU memory cannot be determined from machine detection. "
                f"The project requires at least {required:g} GB GPU memory, so "
                "compatibility is unknown."
            ),
            evidence=evidence,
        )

    tolerance = max(0.25, required * 0.01)
    compatible = local + tolerance >= required
    status = "compatible" if compatible else "incompatible"
    relation = "satisfies" if compatible else "is below"
    return CompatibilityCheck(
        component="gpu_memory",
        local_value=local,
        required_value=required,
        status=status,
        reason=(
            f"Detected GPU memory is {local:g} GB, which {relation} the project "
            f"minimum of {required:g} GB."
        ),
        evidence=evidence,
    )


def check_cuda_compatibility(
    machine_profile: MachineProfile,
    project_requirements: ProjectRequirements,
) -> CompatibilityCheck:
    """Compare only explicit CUDA availability and version information."""

    required = project_requirements.cuda_required
    raw_required_version = project_requirements.cuda_version
    local_value = {
        "nvidia_gpu_available": machine_profile.nvidia_gpu_available,
        "cuda_available": machine_profile.cuda_available,
        "cuda_version": machine_profile.cuda_version,
    }
    required_value = {
        "cuda_required": required,
        "cuda_version": raw_required_version,
    }
    evidence = _gpu_evidence(project_requirements, {"cuda_required", "cuda_version"})

    if required is False:
        return CompatibilityCheck(
            component="cuda",
            local_value=local_value,
            required_value=required_value,
            status="compatible",
            reason=(
                "The project does not require CUDA, so missing local CUDA does not "
                "make the environment incompatible."
            ),
            evidence=evidence,
        )

    if required is not True:
        return CompatibilityCheck(
            component="cuda",
            local_value=local_value,
            required_value=required_value,
            status="unknown",
            reason=(
                f"Project CUDA requirement is {required or 'unknown'}. "
                "CUDA compatibility cannot be determined."
            ),
            evidence=evidence,
        )

    if machine_profile.cuda_available is False:
        return CompatibilityCheck(
            component="cuda",
            local_value=local_value,
            required_value=required_value,
            status="incompatible",
            reason=(
                "The project requires CUDA, but CUDA is explicitly not available "
                "on the local machine."
            ),
            evidence=evidence,
        )

    if machine_profile.cuda_available is not True:
        return CompatibilityCheck(
            component="cuda",
            local_value=local_value,
            required_value=required_value,
            status="unknown",
            reason=(
                "The project requires CUDA, but local CUDA availability cannot be "
                "determined."
            ),
            evidence=evidence,
        )

    normalized_required = normalize_cuda_version(raw_required_version).normalized
    if normalized_required is None:
        return CompatibilityCheck(
            component="cuda",
            local_value=local_value,
            required_value=required_value,
            status="unknown",
            reason=(
                "CUDA is available locally, but the project does not declare a "
                "comparable CUDA version, so version compatibility is unknown."
            ),
            evidence=evidence,
        )
    required_value["cuda_version"] = normalized_required

    if not _is_declared(machine_profile.cuda_version):
        return CompatibilityCheck(
            component="cuda",
            local_value=local_value,
            required_value=required_value,
            status="unknown",
            reason=(
                "Local CUDA is available, but its version cannot be determined. "
                f"The project requires {normalized_required}."
            ),
            evidence=evidence,
        )

    try:
        local_version = Version(str(machine_profile.cuda_version).strip())
        specifier = SpecifierSet(normalized_required)
    except (InvalidVersion, InvalidSpecifier):
        return CompatibilityCheck(
            component="cuda",
            local_value=local_value,
            required_value=required_value,
            status="unknown",
            reason=(
                f"Local CUDA version '{machine_profile.cuda_version}' or project "
                f"requirement '{normalized_required}' cannot be parsed reliably."
            ),
            evidence=evidence,
        )

    compatible = specifier.contains(local_version, prereleases=True)
    status = "compatible" if compatible else "incompatible"
    relation = "satisfies" if compatible else "does not satisfy"
    return CompatibilityCheck(
        component="cuda",
        local_value=local_value,
        required_value=required_value,
        status=status,
        reason=(
            f"Local CUDA version {machine_profile.cuda_version} {relation} "
            f"project requirement {normalized_required}. This comparison does not "
            "infer driver, toolkit, runtime, or framework-wheel compatibility."
        ),
        evidence=evidence,
    )


def _docker_evidence(requirements: ProjectRequirements) -> list[Evidence | str]:
    relevant: list[Evidence | str] = []
    for item in requirements.evidence or []:
        if isinstance(item, Evidence):
            if item.field in {
                "docker_supported",
                "docker_required",
                "special_requirements",
            }:
                relevant.append(item)
        else:
            relevant.append(item)
    return relevant


def _docker_is_explicitly_required(requirements: ProjectRequirements) -> bool:
    texts = list(requirements.special_requirements or [])
    for item in requirements.evidence or []:
        if isinstance(item, Evidence) and item.field in {
            "docker_supported",
            "docker_required",
            "special_requirements",
        }:
            texts.append(item.raw_text)
    return any(_DOCKER_REQUIRED.search(text) for text in texts)


def check_docker_compatibility(
    machine_profile: MachineProfile,
    project_requirements: ProjectRequirements,
) -> CompatibilityCheck:
    """Compare Docker availability without treating optional support as required."""

    supported = project_requirements.docker_supported
    required = _docker_is_explicitly_required(project_requirements)
    local = machine_profile.docker_available
    required_value = {
        "docker_supported": supported,
        "docker_required": required,
    }
    evidence = _docker_evidence(project_requirements)

    if required:
        if local is True:
            status = "compatible"
            reason = (
                "The project explicitly requires Docker, and Docker is available "
                "on the local machine."
            )
        elif local is False:
            status = "incompatible"
            reason = (
                "The project explicitly requires Docker, but Docker is not "
                "available on the local machine."
            )
        else:
            status = "unknown"
            reason = (
                "The project explicitly requires Docker, but local Docker "
                "availability cannot be determined."
            )
        return CompatibilityCheck(
            component="docker",
            local_value=local,
            required_value=required_value,
            status=status,
            reason=reason,
            evidence=evidence,
        )

    if supported is True:
        if local is True:
            status = "compatible"
            reason = (
                "The project provides an optional Docker deployment path, and "
                "Docker is available locally."
            )
        elif local is False:
            status = "partial"
            reason = (
                "The project provides Docker support, but Docker is unavailable "
                "locally. Docker support alone is not a hard requirement, so "
                "this is partial rather than incompatible."
            )
        else:
            status = "unknown"
            reason = (
                "The project provides optional Docker support, but local Docker "
                "availability cannot be determined."
            )
        return CompatibilityCheck(
            component="docker",
            local_value=local,
            required_value=required_value,
            status=status,
            reason=reason,
            evidence=evidence,
        )

    return CompatibilityCheck(
        component="docker",
        local_value=local,
        required_value=required_value,
        status="unknown",
        reason=(
            "The project does not declare Docker support or a Docker requirement, "
            "so Docker compatibility is unknown."
        ),
        evidence=evidence,
    )
