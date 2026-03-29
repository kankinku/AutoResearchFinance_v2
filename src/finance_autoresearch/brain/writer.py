from __future__ import annotations

from pathlib import Path

from finance_autoresearch.localization import DEFAULT_LOCALIZER, OutputLocalizer

from .models import BrainMap, BrainNote
from .templates import render_map, render_note


class BrainWriter:
    def __init__(
        self,
        *,
        root: Path | str,
        localizer: OutputLocalizer | None = None,
    ) -> None:
        self._root = Path(root)
        self._localizer = localizer or DEFAULT_LOCALIZER

    @property
    def root(self) -> Path:
        return self._root

    def write_note(self, note: BrainNote) -> Path:
        target_path = (self._root / note.relative_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() and not self._can_overwrite(target_path):
            return target_path
        target_path.write_text(render_note(note), encoding="utf-8")
        return target_path

    def write_map(self, note: BrainMap) -> Path:
        target_path = (self._root / note.relative_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(render_map(note, localizer=self._localizer), encoding="utf-8")
        return target_path

    def _can_overwrite(self, target_path: Path) -> bool:
        text = target_path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            return True
        frontmatter_end = text.find("\n---\n", 4)
        if frontmatter_end < 0:
            return True
        frontmatter = text[4:frontmatter_end]
        for line in frontmatter.splitlines():
            stripped = line.strip().lower()
            if stripped == "generated: false":
                return False
        return True
