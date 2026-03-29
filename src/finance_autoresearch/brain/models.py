from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class BrainNote:
    note_type: str
    title: str
    relative_path: Path
    frontmatter: dict[str, Any]
    body: str
    generated: bool = True


@dataclass(slots=True, frozen=True)
class ParsedBrainNote:
    note_type: str
    title: str
    relative_path: Path
    frontmatter: dict[str, Any]
    body: str
    tags: tuple[str, ...] = ()
    links: tuple[str, ...] = ()
    generated: bool = True


@dataclass(slots=True, frozen=True)
class BrainMap:
    title: str
    relative_path: Path
    sections: tuple[tuple[str, tuple[str, ...]], ...] = field(default_factory=tuple)
