from __future__ import annotations

from collections import defaultdict

from finance_autoresearch.localization import DEFAULT_LOCALIZER, OutputLocalizer
from finance_autoresearch.state.models import BrainNoteRecord

from .models import BrainMap


MAP_DEFINITIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Active Experiments", "90 Maps/Active Experiments.md", ("experiment", "iteration")),
    ("Failure Atlas", "90 Maps/Failure Atlas.md", ("failure",)),
    ("Indicator Playbook", "90 Maps/Indicator Playbook.md", ("indicator",)),
    ("Regime Playbook", "90 Maps/Regime Playbook.md", ("regime",)),
    ("Family Memory", "90 Maps/Family Memory.md", ("family",)),
    ("Strategy Evolution", "90 Maps/Strategy Evolution.md", ("strategy", "baseline")),
)


class BrainIndexer:
    def __init__(self, *, localizer: OutputLocalizer | None = None) -> None:
        self._localizer = localizer or DEFAULT_LOCALIZER

    def build_maps(self, notes: list[BrainNoteRecord]) -> list[BrainMap]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for note in notes:
            if note.note_type == "map":
                continue
            grouped[note.note_type].append(note.path[:-3] if note.path.endswith(".md") else note.path)

        maps: list[BrainMap] = []
        for title, relative_path, note_types in MAP_DEFINITIONS:
            sections: list[tuple[str, tuple[str, ...]]] = []
            for note_type in note_types:
                section_title = self._localizer.docs(f"brain.map.section.{note_type}")
                items = tuple(sorted(dict.fromkeys(grouped.get(note_type, []))))
                sections.append((section_title, items))
            maps.append(
                BrainMap(
                    title=self._map_title(title),
                    relative_path=relative_path,
                    sections=tuple(sections),
                )
            )
        return maps

    def _map_title(self, title: str) -> str:
        key = title.lower().replace(" ", "_")
        return self._localizer.docs(f"brain.map.{key}")
