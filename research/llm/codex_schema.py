from __future__ import annotations

from typing import Any

from research.llm.director import ResearchIntent


def research_intent_schema() -> dict[str, Any]:
    """Return the strict JSON Schema shared by Codex and local validation."""
    return ResearchIntent.model_json_schema()
