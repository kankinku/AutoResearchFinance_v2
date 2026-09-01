from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any, cast

JSONTransport = Callable[[str, dict[str, object], dict[str, str]], str]
IntentTransport = Callable[[dict[str, Any]], Mapping[str, Any]]


class CodexIntentProvider:
    """Adapter for a Codex-backed proposer with a local JSON contract."""

    def __init__(self, transport: IntentTransport) -> None:
        self._transport = transport

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        payload = self._transport(dict(context))
        if not isinstance(payload, Mapping):
            raise ValueError("Codex provider response must be a mapping")
        return dict(payload)


class OfflineProvider:
    """Deterministic provider used for local development and replay tests."""

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        frontier = context.get("frontier", [])
        parent_ids = tuple(
            item if isinstance(item, str) else str(item.get("id", ""))
            for item in frontier
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
    """Optional live provider; secrets are used only in request headers."""

    def __init__(
        self,
        endpoint: str,
        *,
        api_key: str | None = None,
        transport: JSONTransport | None = None,
    ) -> None:
        if not endpoint or not endpoint.startswith(("https://", "http://")):
            raise ValueError("endpoint must be an HTTP URL")
        self.endpoint = endpoint
        self._api_key = api_key or os.environ.get("QUANT_LLM_API_KEY")
        self._transport = transport or _http_transport

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        response = self._transport(self.endpoint, dict(context), headers)
        try:
            payload = json.loads(response)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("LLM provider response must be a mapping")
        return payload


def _http_transport(endpoint: str, body: dict[str, object], headers: dict[str, str]) -> str:
    from urllib.request import Request, urlopen

    request = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - endpoint is explicit config
        return cast(str, response.read().decode("utf-8"))
