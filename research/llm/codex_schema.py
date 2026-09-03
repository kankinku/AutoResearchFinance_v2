from __future__ import annotations

from typing import Any

from research.llm.director import ResearchIntent


def research_intent_schema() -> dict[str, Any]:
    """Return the strict JSON Schema shared by Codex and local validation."""
    schema = ResearchIntent.model_json_schema()
    _make_strict(schema)
    return schema


def _make_strict(node: object) -> None:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["required"] = list(properties)
            node["additionalProperties"] = False
            for child in properties.values():
                _make_strict(child)
        elif node.get("type") == "object":
            node["additionalProperties"] = False
            node.setdefault("properties", {})
            node.setdefault("required", [])
        for key in ("items", "anyOf", "oneOf", "allOf"):
            child = node.get(key)
            if isinstance(child, list):
                for item in child:
                    _make_strict(item)
            else:
                _make_strict(child)
        definitions = node.get("$defs")
        if isinstance(definitions, dict):
            for definition in definitions.values():
                _make_strict(definition)
    elif isinstance(node, list):
        for item in node:
            _make_strict(item)
