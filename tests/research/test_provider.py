"""Local LLM providers are decommissioned in favor of the GPT MCP boundary."""

from __future__ import annotations

import pytest

from research.llm.provider import ConfiguredJSONProvider, GPTIntentProvider


def test_old_remote_llm_provider_is_unavailable() -> None:
    with pytest.raises(RuntimeError, match="removed"):
        ConfiguredJSONProvider("https://llm.invalid", api_key="not-used")


def test_gpt_intent_provider_is_only_an_inprocess_adapter() -> None:
    seen: list[dict[str, object]] = []

    def proposal(context: dict[str, object]) -> dict[str, object]:
        seen.append(context)
        return {
            "mode": "structure",
            "parent_ids": ["parent"],
            "operations": [],
            "rationale": "GPT hypothesis",
        }

    adapter = GPTIntentProvider(proposal)
    result = adapter.propose({"generation": 1})
    assert result["rationale"] == "GPT hypothesis"
    assert seen == [{"generation": 1}]
