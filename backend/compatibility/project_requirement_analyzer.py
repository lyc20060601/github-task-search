"""Aggregate static environment parsers into ProjectRequirements."""

from __future__ import annotations

import re
from typing import Any

from .conda_parser import parse_conda_environment
from .dependency_parser import parse_python_dependencies
from .docker_environment_parser import parse_docker_environment
from .evidence import Evidence, make_evidence
from .project_requirements import ProjectRequirements
from .readme_requirement_parser import parse_readme_requirements
from .requirement_conflicts import (
    ProjectRequirementAnalysis,
    RequirementCandidate,
    RequirementConflict,
)


README_FILES = ("README.md", "README", "README.rst")


def _readme_text(repository_environment: dict[str, Any]) -> str:
    files = repository_environment.get("files", {})
    if not isinstance(files, dict):
        return ""
    for filename in README_FILES:
        file_data = files.get(filename)
        if isinstance(file_data, dict) and isinstance(file_data.get("content"), str):
            return file_data["content"]
    return ""


def _first_value(results: list[dict[str, Any]], field: str) -> Any:
    for result in results:
        value = result.get(field)
        if value is not None and value != "unknown":
            return value
    return None


def _merge_os(*results: dict[str, Any]) -> list[str]:
    merged: list[str] = []
    for result in results:
        values = result.get("supported_os", [])
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str) and value not in merged:
                merged.append(value)
    return merged


def _merge_strings(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, str) and item not in merged:
                merged.append(item)
    return merged


def _merge_evidence(*results: dict[str, Any]) -> list[Evidence]:
    merged: list[Evidence] = []
    seen: set[tuple[Any, ...]] = set()
    for result in results:
        evidence_items = result.get("evidence", [])
        if not isinstance(evidence_items, list):
            continue
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            try:
                evidence = Evidence.model_validate(item)
            except (TypeError, ValueError):
                continue
            key = (
                evidence.field,
                evidence.source_file,
                evidence.raw_text,
                evidence.location,
            )
            if key not in seen:
                seen.add(key)
                merged.append(evidence)
    return merged


def analyze_project_requirements(
    repository_environment: dict[str, Any],
) -> ProjectRequirements:
    """Run all static parsers and conservatively aggregate their results."""

    dependencies = parse_python_dependencies(repository_environment)
    conda = parse_conda_environment(repository_environment)
    docker = parse_docker_environment(repository_environment)
    readme = parse_readme_requirements(_readme_text(repository_environment))

    # Structured manifests take precedence for software versions. README and
    # Docker only fill fields that those manifests did not provide.
    software_results = [dependencies, conda, readme, docker]

    # Hardware minima and required/optional state come only from README's
    # explicit-language parser. Images and framework dependencies are not
    # sufficient evidence for a hardware requirement.
    return ProjectRequirements(
        supported_os=_merge_os(readme, docker),
        preferred_os=_first_value([readme, docker], "preferred_os"),
        python_min_version=_first_value(software_results, "python_min_version"),
        python_max_version=_first_value(software_results, "python_max_version"),
        python_exact_version=_first_value(software_results, "python_exact_version"),
        framework=_first_value(software_results, "framework"),
        framework_version=_first_value(software_results, "framework_version"),
        cuda_required=readme.get("cuda_required"),
        cuda_version=_first_value([conda, readme, docker], "cuda_version"),
        gpu_required=readme.get("gpu_required"),
        gpu_vendor=readme.get("gpu_vendor"),
        minimum_gpu_memory_gb=readme.get("minimum_gpu_memory_gb"),
        minimum_ram_gb=readme.get("minimum_ram_gb"),
        docker_supported=_first_value([docker, readme], "docker_supported"),
        package_manager=_first_value([dependencies, conda, readme], "package_manager"),
        special_requirements=_merge_strings(readme.get("special_requirements")),
        evidence=_merge_evidence(dependencies, conda, docker, readme),
    )


def _evidence_for_field(result: dict[str, Any], field: str) -> list[Evidence]:
    values: list[Evidence] = []
    for item in result.get("evidence", []):
        if not isinstance(item, dict) or item.get("field") != field:
            continue
        try:
            values.append(Evidence.model_validate(item))
        except (TypeError, ValueError):
            continue
    return values


def _scope_for_result(result: dict[str, Any], field: str) -> str:
    source = ";".join(
        evidence.source_file for evidence in _evidence_for_field(result, field)
    )
    if source == "README.md":
        return "explicit_requirement"
    if source in {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
        return "docker_environment"
    if source.endswith(":pip") or source in {
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Pipfile",
        ".python-version",
        "runtime.txt",
        "environment.yml",
        "environment.yaml",
    }:
        return "dependency_constraint"
    return "support_statement"


def _readme_scope(result: dict[str, Any], field: str) -> str:
    hints = result.get("soft_hints", [])
    evidence = _evidence_for_field(result, field)
    evidence_lines = {
        int(evidence_item.location.split()[-1])
        for evidence_item in evidence
        if evidence_item.location and evidence_item.location.startswith("line ")
    }
    for hint in hints:
        if hint.get("line") in evidence_lines:
            kind = hint.get("kind")
            if kind == "recommended":
                return "recommendation"
            if kind == "tested":
                return "tested_environment"
            if kind == "supported":
                return "support_statement"
    return "explicit_requirement"


def _soft_readme_candidate(
    result: dict[str, Any], field: str, pattern: str
) -> list[RequirementCandidate]:
    candidates: list[RequirementCandidate] = []
    for hint in result.get("soft_hints", []):
        if not isinstance(hint, dict) or not isinstance(hint.get("text"), str):
            continue
        match = re.search(pattern, hint["text"], re.IGNORECASE)
        if match is None:
            continue
        value = match.group("version")
        evidence = make_evidence(
            field=field,
            value=value,
            source_file="README.md",
            raw_text=hint["text"],
            evidence_type=hint.get("kind", "supported"),
            confidence="medium",
            location=f"line {hint.get('line')}",
            reason=f"README {hint.get('kind', 'soft')} environment statement",
        )
        if evidence is None:
            continue
        scope = {
            "recommended": "recommendation",
            "tested": "tested_environment",
            "supported": "support_statement",
        }.get(hint.get("kind"), "support_statement")
        candidates.append(
            RequirementCandidate(
                value=value,
                source_file="README.md",
                scope=scope,
                evidence=[Evidence.model_validate(evidence)],
            )
        )
    return candidates


def _candidate(
    value: Any, result: dict[str, Any], field: str, *, readme: bool = False
) -> RequirementCandidate | None:
    if value is None or value == "unknown":
        return None
    evidence = _evidence_for_field(result, field)
    if not evidence:
        return None
    scope = _readme_scope(result, field) if readme else _scope_for_result(result, field)
    return RequirementCandidate(
        value=value,
        source_file=evidence[0].source_file,
        scope=scope,
        evidence=evidence,
    )


def _version_tuple(value: str) -> tuple[int, ...] | None:
    import re

    match = re.search(r"\d+(?:\.\d+){0,3}", value)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def _python_candidate_compatible(value: str, candidate: str) -> bool | None:
    requested = _version_tuple(value)
    actual = _version_tuple(candidate)
    if requested is None or actual is None:
        return None
    if value.startswith((">=", ">", "~=")):
        return actual >= requested
    if value.startswith(("<=", "<")):
        return actual <= requested
    return actual == requested


def _resolve_candidates(
    field: str, candidates: list[RequirementCandidate]
) -> RequirementConflict | None:
    if len(candidates) < 2:
        return None
    values = {str(candidate.value) for candidate in candidates}
    if len(values) == 1:
        return None

    hard = [
        candidate
        for candidate in candidates
        if candidate.scope in {"explicit_requirement", "dependency_constraint"}
    ]
    soft = [candidate for candidate in candidates if candidate not in hard]

    if field == "python_version" and hard:
        hard_values = [str(candidate.value) for candidate in hard]
        compatible = all(
            _python_candidate_compatible(hard_values[0], value) is True
            or _python_candidate_compatible(value, hard_values[0]) is True
            for value in hard_values[1:]
        )
        if compatible and not soft:
            return None
        if compatible and soft and all(
            candidate.scope == "docker_environment"
            and _python_candidate_compatible(hard_values[0], str(candidate.value)) is True
            for candidate in soft
        ):
            return None
        if compatible:
            selected = hard[0].value
            status: str = "resolved"
        else:
            selected = None
            status = "unresolved"
    elif hard:
        selected = hard[0].value if len({str(item.value) for item in hard}) == 1 else None
        if selected is not None and not soft:
            return None
        status = "resolved" if selected is not None else "unresolved"
    else:
        selected = None
        status = "unresolved"

    return RequirementConflict(
        field=field,
        status=status,
        selected_value=selected,
        candidates=candidates,
        evidence=[evidence for candidate in candidates for evidence in candidate.evidence],
        reason=(
            "Structured/explicit requirements are compatible; softer environment "
            "evidence was retained."
            if status == "resolved"
            else "Conflicting authoritative requirements were retained without selecting one."
        ),
    )


def analyze_project_requirements_with_conflicts(
    repository_environment: dict[str, Any],
) -> ProjectRequirementAnalysis:
    """Return requirements plus explicit conflicts between source categories."""

    dependencies = parse_python_dependencies(repository_environment)
    conda = parse_conda_environment(repository_environment)
    docker = parse_docker_environment(repository_environment)
    readme = parse_readme_requirements(_readme_text(repository_environment))
    requirements = analyze_project_requirements(repository_environment)
    conflicts: list[RequirementConflict] = []

    python_candidates: list[RequirementCandidate] = []
    for result in (dependencies, conda, readme, docker):
        if result is readme:
            value = None
            if readme.get("python_exact_version"):
                value = readme["python_exact_version"]
            elif readme.get("python_min_version"):
                value = f">={readme['python_min_version']}"
            elif readme.get("python_max_version"):
                value = f"<={readme['python_max_version']}"
            candidate = _candidate(value, result, "python_exact_version", readme=True) or _candidate(value, result, "python_min_version", readme=True)
        elif result is dependencies:
            value = None
            if dependencies.get("python_exact_version"):
                value = dependencies["python_exact_version"]
            elif dependencies.get("python_min_version"):
                value = f">={dependencies['python_min_version']}"
            candidate = _candidate(value, result, "python_exact_version") or _candidate(value, result, "python_requirement")
        elif result is conda:
            value = conda.get("python_exact_version") or (
                f">={conda['python_min_version']}" if conda.get("python_min_version") else None
            )
            candidate = _candidate(value, result, "python_exact_version") or _candidate(value, result, "python_min_version")
        else:
            candidate = _candidate(docker.get("python_version"), docker, "Python version is present in the image tag")
        if candidate is not None:
            python_candidates.append(candidate)
    python_candidates.extend(
        _soft_readme_candidate(
            readme,
            "python_version",
            r"python(?:\s+version)?\s*(?:=|==|is\s+)?(?P<version>\d+(?:\.\d+){0,3})",
        )
    )
    python_conflict = _resolve_candidates("python_version", python_candidates)
    if python_conflict:
        conflicts.append(python_conflict)
        if python_conflict.status == "unresolved":
            requirements.python_min_version = None
            requirements.python_max_version = None
            requirements.python_exact_version = None

    cuda_candidates: list[RequirementCandidate] = []
    for result, value, readme_flag in (
        (conda, conda.get("cuda_version"), False),
        (docker, docker.get("cuda_version"), False),
        (readme, readme.get("cuda_version"), True),
    ):
        candidate = _candidate(value, result, "cuda_version", readme=readme_flag)
        if candidate is not None:
            cuda_candidates.append(candidate)
    cuda_candidates.extend(
        _soft_readme_candidate(
            readme,
            "cuda_version",
            r"cuda(?:\s+version)?\s*(?:=|is\s+)?(?P<version>\d+(?:\.\d+){0,3})",
        )
    )
    cuda_conflict = _resolve_candidates("cuda_version", cuda_candidates)
    if cuda_conflict:
        conflicts.append(cuda_conflict)
        if cuda_conflict.status == "unresolved":
            requirements.cuda_version = None

    return ProjectRequirementAnalysis(requirements=requirements, conflicts=conflicts)
