import json

from compatibility.conda_parser import parse_conda_environment
from compatibility.docker_environment_parser import parse_docker_environment
from compatibility.evidence import (
    MAX_RAW_TEXT_LENGTH,
    Evidence,
    evidence_contains_secret,
    make_evidence,
)
from compatibility.readme_requirement_parser import parse_readme_requirements
from compatibility.dependency_parser import parse_python_dependencies


def _fetched(**files: str) -> dict[str, object]:
    return {
        "files": {
            name: {"content": content, "size": len(content), "truncated": False}
            for name, content in files.items()
        }
    }


def test_evidence_has_structured_fields_and_bounded_text() -> None:
    evidence = Evidence(
        field="cuda_version",
        value="11.8",
        source_file="environment.yml",
        raw_text="x" * (MAX_RAW_TEXT_LENGTH + 100),
    )

    assert evidence.source_file == "environment.yml"
    assert len(evidence.raw_text) == MAX_RAW_TEXT_LENGTH
    assert evidence.confidence == "high"
    assert evidence.evidence_type == "explicit"


def test_make_evidence_accepts_null_and_unknown_values() -> None:
    null_value = make_evidence(
        field="minimum_ram_gb",
        value=None,
        source_file="README.md",
        raw_text="not specified",
        confidence="unknown",
        evidence_type="unknown",
    )
    unknown_value = make_evidence(
        field="framework",
        value="unknown",
        source_file="README.md",
        raw_text="framework not stated",
        confidence="unknown",
        evidence_type="unknown",
    )

    assert null_value is not None and null_value["value"] is None
    assert unknown_value is not None and unknown_value["value"] == "unknown"


def test_dependency_parser_emits_requirements_evidence() -> None:
    result = parse_python_dependencies(
        _fetched(**{"requirements.txt": "torch==2.4.0\n"})
    )

    evidence = result["evidence"]
    assert any(
        item.get("source_file") == "requirements.txt"
        and item.get("raw_text") == "torch==2.4.0"
        for item in evidence
    )


def test_conda_parser_emits_environment_evidence() -> None:
    result = parse_conda_environment(
        _fetched(**{"environment.yml": "dependencies:\n  - cudatoolkit=11.8\n"})
    )

    assert any(
        item.get("source_file") == "environment.yml"
        and item.get("raw_text") == "cudatoolkit=11.8"
        for item in result["evidence"]
    )


def test_docker_parser_emits_dockerfile_evidence() -> None:
    result = parse_docker_environment(
        _fetched(**{"Dockerfile": "FROM nvidia/cuda:11.8.0-runtime\n"})
    )

    assert any(
        item.get("source_file") == "Dockerfile"
        and "11.8.0" in item.get("raw_text", "")
        for item in result["evidence"]
    )


def test_readme_parser_emits_readme_evidence() -> None:
    result = parse_readme_requirements("Requires at least 16GB RAM.\n")

    assert any(
        item.get("source_file") == "README.md"
        and item.get("raw_text") == "Requires at least 16GB RAM."
        for item in result["evidence"]
    )


def test_sensitive_values_are_redacted_and_not_serialized() -> None:
    evidence = make_evidence(
        field="token_check",
        value="github_pat_secretvalue",
        source_file="README.md",
        raw_text="GITHUB_TOKEN=secret Authorization: Bearer secret sk-abcdefghijklmnop",
    )

    assert evidence is not None
    serialized = json.dumps(evidence)
    assert "secretvalue" not in serialized
    assert "Bearer secret" not in serialized
    assert "sk-abcdefghijklmnop" not in serialized
    assert not evidence_contains_secret(evidence)


def test_local_sensitive_paths_are_rejected() -> None:
    assert (
        make_evidence(
            field="x",
            value=1,
            source_file="C:/Users/example/.env",
            raw_text="x",
        )
        is None
    )
