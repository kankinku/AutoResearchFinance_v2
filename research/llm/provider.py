from __future__ import annotations

from typing import Any


class OfflineProvider:
    """Deterministic provider used for local development and replay tests."""

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        frontier = context.get("frontier", [])
        parent_ids = tuple(
            item if isinstance(item, str) else str(item.get("id", ""))
            for item in frontier
        )
        parent_ids = tuple(item for item in parent_ids if item)
        return {
            "mode": "structure",
            "parent_ids": parent_ids,
            "operations": (),
            "rationale": "offline deterministic exploration",
        }
