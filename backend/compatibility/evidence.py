"""Structured, bounded, and secret-safe evidence records."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


MAX_RAW_TEXT_LENGTH = 512
EvidenceConfidence = Literal["high", "medium", "low", "unknown"]
EvidenceType = Literal[
    "explicit",
    "dependency",
    "inferred",
    "tested",
    "recommended",
    "supported",
    "unknown",
]

_SENSITIVE_TEXT = re.compile(
    r"(?:GITHUB_TOKEN|LLM_API_KEY|Authorization\s*:|Bearer\s+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?P<key>GITHUB_TOKEN|LLM_API_KEY)\s*=\s*[^\s]+",
    re.IGNORECASE,
)
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{1,2})")


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        value = _SECRET_ASSIGNMENT.sub(r"\g<key>=[REDACTED]", value)
        return _SENSITIVE_TEXT.sub("[REDACTED]", value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    return value


class Evidence(BaseModel):
    """A bounded explanation for one extracted project requirement."""

    field: str
    value: Any = None
    source_file: str
    raw_text: str = Field(max_length=MAX_RAW_TEXT_LENGTH)
    reason: str = "Explicit evidence for the extracted field"
    confidence: EvidenceConfidence = "high"
    evidence_type: EvidenceType = "explicit"
    location: str | None = None

    @field_validator("source_file")
    @classmethod
    def validate_source_file(cls, value: str) -> str:
        normalized = value.strip().replace("\\", "/")
        if (
            not normalized
            or _ABSOLUTE_PATH.match(value)
            or any(part == ".env" for part in normalized.split("/"))
        ):
            raise ValueError("source_file must be a repository-relative path")
        if any(part == ".." for part in normalized.split("/")):
            raise ValueError("source_file must not escape the repository")
        return normalized

    @field_validator("raw_text", mode="before")
    @classmethod
    def bound_raw_text(cls, value: Any) -> str:
        text = str(value)
        return _redact(text)[:MAX_RAW_TEXT_LENGTH]

    @field_validator("value", mode="before")
    @classmethod
    def redact_value(cls, value: Any) -> Any:
        return _redact(value)

    def model_dump_safe(self) -> dict[str, Any]:
        return self.model_dump()


class EvidenceRecord(dict[str, Any]):
    """JSON-compatible record with backward-compatible subset equality."""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            return all(self.get(key) == value for key, value in other.items())
        return super().__eq__(other)


def make_evidence(
    *,
    field: str,
    value: Any,
    source_file: str,
    raw_text: str,
    reason: str | None = None,
    confidence: EvidenceConfidence = "high",
    evidence_type: EvidenceType = "explicit",
    location: str | None = None,
) -> dict[str, Any] | None:
    """Build a safe serializable evidence record, skipping invalid sources."""

    try:
        model = Evidence(
            field=field,
            value=value,
            source_file=source_file,
            raw_text=raw_text,
            reason=reason or f"Explicit evidence for {field}",
            confidence=confidence,
            evidence_type=evidence_type,
            location=location,
        )
        record = EvidenceRecord(model.model_dump_safe())
        # Preserve the keys emitted by the pre-Evidence parsers.
        record["source"] = record["source_file"]
        record["text"] = record["raw_text"]
        return record
    except (TypeError, ValueError):
        return None


def evidence_contains_secret(evidence: Evidence | dict[str, Any]) -> bool:
    """Return whether a serialized record contains a known secret marker."""

    payload = evidence.model_dump() if isinstance(evidence, Evidence) else evidence
    serialized = json.dumps(payload, ensure_ascii=False)
    return bool(_SENSITIVE_TEXT.search(serialized) or ".env" in serialized)
