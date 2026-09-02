from __future__ import annotations

import json

import pytest

from research.llm.codex_schema import research_intent_schema
from research.llm.director import ResearchDirector
from research.llm.provider import CodexIntentProvider


def _valid_intent() -> dict[str, object]:
    return {
        "mode": "structure",
        "parent_ids": ["champion-1"],
        "operations": [],
        "rationale": "test a momentum interaction",
    }


def test_research_intent_schema_is_strict_and_rejects_code_changes() -> None:
    schema = research_intent_schema()

    assert schema["additionalProperties"] is False
    assert "python_patch" in schema["properties"]
    assert "evaluator_change" in schema["properties"]
    with pytest.raises(ValueError):
        provider = CodexIntentProvider(
            lambda _: {**_valid_intent(), "python_patch": "x"}
        )
        ResearchDirector(provider).propose({})


def test_codex_intent_provider_returns_mapping_without_mutating_context() -> None:
    context: dict[str, object] = {"generation": 4, "feature_catalog": [{"name": "vix"}]}
    provider = CodexIntentProvider(lambda received: _valid_intent())

    payload = provider.propose(context)

    assert payload == _valid_intent()
    assert context == {"generation": 4, "feature_catalog": [{"name": "vix"}]}


def test_research_intent_schema_serializes_as_json() -> None:
    assert json.loads(json.dumps(research_intent_schema()))["type"] == "object"
