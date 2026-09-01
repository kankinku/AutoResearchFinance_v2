from __future__ import annotations

import json

import pytest

from research.llm.provider import ConfiguredJSONProvider


def test_configured_provider_sends_context_and_returns_json_without_secret() -> None:
    calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

    def transport(endpoint: str, body: dict[str, object], headers: dict[str, str]) -> str:
        calls.append((endpoint, body, headers))
        return json.dumps(
            {"mode": "structure", "parent_ids": ["p1"], "rationale": "explore"}
        )

    provider = ConfiguredJSONProvider("https://llm.invalid", api_key="secret", transport=transport)
    result = provider.propose({"generation": 2})

    assert result["parent_ids"] == ["p1"]
    assert calls[0][0] == "https://llm.invalid"
    assert calls[0][1] == {"generation": 2}
    assert calls[0][2]["Authorization"] == "Bearer secret"
    assert "secret" not in json.dumps(result)


def test_configured_provider_requires_endpoint_and_mapping_response() -> None:
    with pytest.raises(ValueError, match="endpoint"):
        ConfiguredJSONProvider("")

    def bad_transport(endpoint: str, body: dict[str, object], headers: dict[str, str]) -> str:
        return "[]"

    provider = ConfiguredJSONProvider("https://llm.invalid", transport=bad_transport)
    with pytest.raises(ValueError, match="mapping"):
        provider.propose({})
