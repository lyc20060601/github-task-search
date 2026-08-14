"""Conflict models for static project environment requirements."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .evidence import Evidence
from .project_requirements import ProjectRequirements


ConflictStatus = Literal["resolved", "unresolved"]
CandidateScope = Literal[
    "explicit_requirement",
    "dependency_constraint",
    "docker_environment",
    "recommendation",
    "tested_environment",
    "support_statement",
]


class RequirementCandidate(BaseModel):
    value: Any
    source_file: str
    scope: CandidateScope
    evidence: list[Evidence] = Field(default_factory=list)


class RequirementConflict(BaseModel):
    field: str
    status: ConflictStatus
    selected_value: Any = None
    candidates: list[RequirementCandidate] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    reason: str


class ProjectRequirementAnalysis(BaseModel):
    requirements: ProjectRequirements
    conflicts: list[RequirementConflict] = Field(default_factory=list)
