"""Pure in-process intent adapters for externally authored GPT plans.

There is no embedded HTTP LLM client, Codex subprocess, or model credential.
The only production research director is the authenticated ChatGPT MCP caller.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

IntentTransport = Callable[[dict[str, Any]], Mapping[str, Any]]


class GPTIntentProvider:
    """Development injection adapter. Does not call a model or a network service."""

    def __init__(self, transport: IntentTransport) -> None:
        self._transport = transport

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        payload = self._transport(dict(context))
        if not isinstance(payload, Mapping):
            raise ValueError("GPT supplied intent must be an object")
        return dict(payload)


# Backwards import compatibility for deterministic tests only; no Codex runner.
CodexIntentProvider = GPTIntentProvider


class OfflineProvider:
    """Deterministic local test provider; never sends requests outside the process."""

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        frontier = context.get("frontier", [])
        parent_ids = tuple(
            item if isinstance(item, str) else str(item.get("id", "")) for item in frontier
        )
        parent_ids = tuple(item for item in parent_ids if item)
        payload: dict[str, Any] = {
            "mode": "structure",
            "parent_ids": parent_ids,
            "operations": (),
            "rationale": "offline deterministic exploration",
        }
        catalog = context.get("feature_catalog", [])
        if catalog and isinstance(catalog[0], dict):
            feature = catalog[0]
            name = str(feature.get("name", ""))
            inputs = tuple(str(value) for value in feature.get("inputs", ()))
            if name and inputs:
                calculator = str(feature.get("calculator", "expression"))
                lookback = int(feature.get("lookback", 1))
                payload["feature_proposal"] = {
                    "name": name,
                    "family": str(feature.get("family", "custom")),
                    "inputs": inputs,
                    "calculator": calculator,
                    "lookback": lookback,
                    "formula": f"{calculator}({inputs[0]}, {lookback})",
                    "justification": "offline catalog feature selection",
                }
        return payload


class ConfiguredJSONProvider:
    """Retired remote LLM provider. Kept only to reject old imports explicitly."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Embedded/remote LLM providers are removed; use ChatGPT MCP")

    def propose(self, _context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Embedded/remote LLM providers are removed")
