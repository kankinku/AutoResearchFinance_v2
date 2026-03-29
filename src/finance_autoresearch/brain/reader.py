from __future__ import annotations

import hashlib
import re
from pathlib import Path

from finance_autoresearch.research.models import KnowledgeSnippet

from .models import ParsedBrainNote


WIKILINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


class BrainReader:
    def __init__(self, *, root: Path | str) -> None:
        self._root = Path(root)

    def list_notes(self) -> list[ParsedBrainNote]:
        if not self._root.exists():
            return []
        notes: list[ParsedBrainNote] = []
        for path in sorted(self._root.rglob("*.md")):
            notes.append(self.read_note(path))
        return notes

    def read_note(self, path: Path | str) -> ParsedBrainNote:
        resolved_path = Path(path)
        if not resolved_path.is_absolute():
            resolved_path = (self._root / resolved_path).resolve()
        text = resolved_path.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text)
        title = _extract_title(body, fallback=resolved_path.stem)
        tags = tuple(str(item) for item in frontmatter.get("tags", []) if str(item).strip())
        links = tuple(dict.fromkeys(WIKILINK_PATTERN.findall(body)))
        generated = bool(frontmatter.get("generated", True))
        return ParsedBrainNote(
            note_type=str(frontmatter.get("note_type", "note")),
            title=title,
            relative_path=resolved_path.relative_to(self._root),
            frontmatter=frontmatter,
            body=body,
            tags=tags,
            links=links,
            generated=generated,
        )

    def select_related_snippets(
        self,
        *,
        terms: set[str],
        max_notes: int,
        preferred_paths: tuple[str, ...] = (),
        manual_notes_mode: str = "reference_only",
    ) -> list[KnowledgeSnippet]:
        snippets: list[KnowledgeSnippet] = []
        preferred = {path.replace("\\", "/").lower() for path in preferred_paths}
        for note in self.list_notes():
            parts = {part.lower() for part in note.relative_path.parts}
            if "00 inbox" in parts or "manual" in parts:
                continue
            if not note.generated and not _manual_note_is_retrievable(
                note=note,
                manual_notes_mode=manual_notes_mode,
            ):
                continue
            lower_title = note.title.lower()
            lower_body = note.body.lower()
            lower_tags = " ".join((note.note_type, *(item.lower() for item in note.tags)))
            match_count = sum(
                lower_title.count(term) + lower_body.count(term) + lower_tags.count(term)
                for term in terms
            )
            if match_count <= 0:
                continue
            source_path = (self._root / note.relative_path).as_posix()
            tags = tuple(dict.fromkeys(("brain-note", note.note_type, *note.tags)))
            score = float(match_count) + (2.0 if note.generated else 0.5)
            if note.relative_path.as_posix().lower() in preferred:
                score += 3.0
            snippets.append(
                KnowledgeSnippet(
                    source_id=source_path,
                    title=note.title,
                    source_path=source_path,
                    sha256=hashlib.sha256(note.body.encode("utf-8")).hexdigest(),
                    excerpt=_excerpt_for_terms(note.body, terms),
                    tags=tags,
                    relevance_reason="Matched linked second-brain notes.",
                    score=score,
                )
            )
        snippets.sort(key=lambda item: (-item.score, item.source_path))
        return snippets[:max_notes]


def _manual_note_is_retrievable(
    *,
    note: ParsedBrainNote,
    manual_notes_mode: str,
) -> bool:
    if manual_notes_mode != "reference_only":
        return False
    parts = note.relative_path.parts
    if not parts:
        return False
    top_level = parts[0]
    if top_level == "00 Inbox":
        return False
    return top_level in {
        "01 Iterations",
        "02 Experiments",
        "03 Lessons",
        "04 Failures",
        "05 Indicators",
        "06 Regimes",
        "07 Markets",
        "08 Families",
        "09 Strategies",
        "10 Baselines",
        "90 Maps",
    }


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    return _parse_frontmatter(text[4:end]), text[end + 5 :]


def _parse_frontmatter(text: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.endswith(":") and not line.startswith("  - "):
            key = line[:-1].strip()
            index += 1
            items: list[str] = []
            while index < len(lines) and lines[index].startswith("  - "):
                items.append(_parse_scalar(lines[index][4:]))
                index += 1
            payload[key] = items
            continue
        if ":" in line:
            key, raw_value = line.split(":", 1)
            payload[key.strip()] = _parse_scalar(raw_value.strip())
        index += 1
    return payload


def _parse_scalar(value: str) -> object:
    stripped = value.strip()
    if not stripped or stripped == "-":
        return ""
    if stripped == "true":
        return True
    if stripped == "false":
        return False
    if stripped == "null":
        return None
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    try:
        return int(stripped)
    except ValueError:
        try:
            return float(stripped)
        except ValueError:
            return stripped


def _extract_title(body: str, *, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return fallback.replace("-", " ").replace("_", " ").title()


def _excerpt_for_terms(body: str, terms: set[str], max_chars: int = 480) -> str:
    compact = " ".join(line.strip() for line in body.splitlines() if line.strip())
    lowered = compact.lower()
    for term in sorted(terms):
        index = lowered.find(term)
        if index >= 0:
            start = max(index - (max_chars // 3), 0)
            end = min(start + max_chars, len(compact))
            return compact[start:end].strip()
    return compact[:max_chars].strip()
