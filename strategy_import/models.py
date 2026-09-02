from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AnalysisStatus(str, Enum):
    NORMALIZED = "NORMALIZED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class AnalysisResult:
    status: AnalysisStatus
    source_hash: str
    source_type: str
    strategy: Any | None = None
    profile: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative_path: Path
    content: str
    source_hash: str


@dataclass(frozen=True)
class GitHubSource:
    repository_url: str
    ref: str


@dataclass(frozen=True)
class DuplicateResult:
    kind: str
    duplicate_of: str | None = None
