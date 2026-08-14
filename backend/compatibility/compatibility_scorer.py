"""Weighted local-machine compatibility scoring, separate from runtime scoring."""

from __future__ import annotations

from collections.abc import Iterable

from .compatibility_advisor import generate_compatibility_advice
from .compatibility_models import CompatibilityCheck, CompatibilityResult


COMPONENT_WEIGHTS: dict[str, float] = {
    "python": 18.0,
    "os": 15.0,
    "ram": 12.0,
    "gpu": 18.0,
    "gpu_memory": 12.0,
    "cuda": 18.0,
    "docker": 7.0,
}

STATUS_FACTORS: dict[str, float] = {
    "compatible": 1.0,
    "partial": 0.6,
    "incompatible": 0.0,
    "unknown": 0.5,
}

# These caps prevent a weighted total from hiding an explicit hard failure.
INCOMPATIBILITY_CAPS: dict[str, float] = {
    "gpu": 30.0,
    "cuda": 30.0,
    "python": 45.0,
    "os": 45.0,
    "gpu_memory": 50.0,
    "ram": 55.0,
    "docker": 45.0,
}


def _overall_status(checks: list[CompatibilityCheck]) -> str:
    statuses = {check.status for check in checks}
    if "incompatible" in statuses:
        return "incompatible"
    if "partial" in statuses:
        return "partial"
    if "unknown" in statuses or not checks:
        return "unknown"
    return "compatible"


def score_compatibility(
    checks: Iterable[CompatibilityCheck],
) -> CompatibilityResult:
    """Score how well project requirements match the backend host, from 0 to 100."""

    provided_checks = list(checks)
    checks_by_component = {
        check.component: check
        for check in provided_checks
        if check.component in COMPONENT_WEIGHTS
    }

    weighted_score = 0.0
    known_weight = 0.0
    incompatible_checks: list[CompatibilityCheck] = []

    for component, weight in COMPONENT_WEIGHTS.items():
        check = checks_by_component.get(component)
        status = check.status if check is not None else "unknown"
        weighted_score += weight * STATUS_FACTORS[status]
        if status != "unknown":
            known_weight += weight
        if status == "incompatible" and check is not None:
            incompatible_checks.append(check)

    if incompatible_checks:
        failure_cap = min(
            INCOMPATIBILITY_CAPS[check.component]
            for check in incompatible_checks
        )
        weighted_score = min(weighted_score, failure_cap)

    score = round(max(0.0, min(100.0, weighted_score)), 1)
    known_coverage = round(known_weight, 1)

    advice = generate_compatibility_advice(provided_checks)
    warnings = list(advice.warnings)
    if known_coverage < 100.0:
        warnings.append(
            f"Known requirement coverage is {known_coverage:g}%; unknown checks "
            "use a neutral contribution and do not count as compatible."
        )

    effective_checks = [
        checks_by_component[component]
        for component in COMPONENT_WEIGHTS
        if component in checks_by_component
    ]
    overall_status = _overall_status(effective_checks)
    if (
        overall_status == "compatible"
        and len(checks_by_component) < len(COMPONENT_WEIGHTS)
    ):
        overall_status = "unknown"
    return CompatibilityResult(
        overall_status=overall_status,
        compatibility_score=score,
        checks=provided_checks,
        warnings=warnings,
        issues=advice.issues,
        suggestions=advice.suggestions,
    )
