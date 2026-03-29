from __future__ import annotations

from typing import Any

from finance_autoresearch.localization import DEFAULT_LOCALIZER, OutputLocalizer

from .models import BrainMap, BrainNote


def render_note(note: BrainNote) -> str:
    frontmatter = _render_frontmatter(note.frontmatter)
    body = note.body.rstrip()
    return f"---\n{frontmatter}---\n\n{body}\n"


def render_map(note: BrainMap, *, localizer: OutputLocalizer | None = None) -> str:
    resolved_localizer = localizer or DEFAULT_LOCALIZER
    lines: list[str] = [f"# {note.title}", ""]
    for section_title, items in note.sections:
        lines.append(f"## {section_title}")
        lines.append("")
        if items:
            lines.extend(f"- [[{item}]]" for item in items)
        else:
            lines.append(f"- {resolved_localizer.docs('brain.map.empty')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_frontmatter(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in payload.items():
        lines.extend(_render_frontmatter_value(key, value))
    return "\n".join(lines) + "\n"


def _render_frontmatter_value(key: str, value: Any) -> list[str]:
    if isinstance(value, bool):
        return [f"{key}: {'true' if value else 'false'}"]
    if value is None:
        return [f"{key}: null"]
    if isinstance(value, (int, float)):
        return [f"{key}: {value}"]
    if isinstance(value, (list, tuple)):
        lines = [f"{key}:"]
        for item in value:
            lines.append(f"  - {_format_scalar(item)}")
        if len(lines) == 1:
            lines.append("  -")
        return lines
    return [f"{key}: {_format_scalar(value)}"]


def _format_scalar(value: Any) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
