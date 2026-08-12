from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


README_FILES = ("README.md", "README.rst", "README.txt", "README")

ENTRYPOINT_TYPES = {
    "train.py": "training",
    "main.py": "application",
    "demo.py": "demo",
    "infer.py": "inference",
    "inference.py": "inference",
    "predict.py": "inference",
    "tools/train.py": "training",
    "tools/test.py": "evaluation",
}

COMMON_ENTRYPOINTS = tuple(ENTRYPOINT_TYPES)

_README_COMMAND_PATTERN = re.compile(
    r"\b(?:python(?:3(?:\.\d+)*)?|py)\s+"
    r"(?:-[A-Za-z]+\s+)*(?:\.[\\/])?"
    r"(?P<entrypoint>tools[\\/](?:train|test)\.py|"
    r"train\.py|main\.py|demo\.py|infer\.py|inference\.py|predict\.py)"
    r"(?=\s|$|`)",
    re.IGNORECASE,
)


def _unknown_evidence(reason: str) -> dict[str, str]:
    return {"source": "unknown", "reason": reason}


@dataclass(frozen=True)
class EntrypointDetection:
    entrypoint: str = "unknown"
    entrypoint_type: str = "unknown"
    confidence: str = "unknown"
    evidence: dict[str, str] = field(
        default_factory=lambda: _unknown_evidence(
            "No common entrypoint file or explicit README command was found"
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_entrypoint(
    repository_path: str | Path,
    readme_text: str | None = None,
) -> EntrypointDetection:
    """Detect a likely repository entrypoint without executing repository code."""
    root = Path(repository_path)
    if not root.is_dir():
        return EntrypointDetection(
            evidence=_unknown_evidence("Repository path is not a directory")
        )

    readme_source = "README"
    if readme_text is None:
        readme_text, readme_source = _read_readme(root)

    readme_match = _README_COMMAND_PATTERN.search(readme_text or "")
    if readme_match:
        entrypoint = readme_match.group("entrypoint").replace("\\", "/").lower()
        exists = (root / Path(entrypoint)).is_file()
        reason = (
            "README contains an explicit Python command for an existing common entrypoint"
            if exists
            else "README contains an explicit Python command, but the expected file was not found"
        )
        return EntrypointDetection(
            entrypoint=entrypoint,
            entrypoint_type=ENTRYPOINT_TYPES[entrypoint],
            confidence="high" if exists else "medium",
            evidence={
                "source": readme_source,
                "reason": reason,
                "command": _extract_command(readme_text or "", readme_match.start()),
            },
        )

    for entrypoint in COMMON_ENTRYPOINTS:
        if (root / Path(entrypoint)).is_file():
            return EntrypointDetection(
                entrypoint=entrypoint,
                entrypoint_type=ENTRYPOINT_TYPES[entrypoint],
                confidence="high",
                evidence={
                    "source": entrypoint,
                    "reason": "Common entrypoint file exists",
                },
            )

    return EntrypointDetection()


def _read_readme(root: Path) -> tuple[str, str]:
    for name in README_FILES:
        path = root / name
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8", errors="replace"), name
            except OSError:
                return "", name
    return "", "README"


def _extract_command(readme_text: str, command_start: int) -> str:
    remainder = readme_text[command_start:]
    command = re.split(r"[`\r\n]", remainder, maxsplit=1)[0]
    return command.strip()
