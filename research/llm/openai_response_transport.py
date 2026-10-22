"""Optional external OpenAI Responses transport for operator-invoked research.

Requires OPENAI_API_KEY and explicit model selection. Never stores credentials;
never spawns background jobs, uses tools, streams data into broker execution or
claims that a model has produced a profitable strategy.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx


class RemoteModelError(RuntimeError):
    """Transport unavailable, incomplete or refused response; safe to retry explicitly."""


class OpenAIResponsesResearcher:
    ENDPOINT = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self._api_key:
            raise RemoteModelError("OPENAI_API_KEY is required for actual model research")
        if (
            not isinstance(model, str)
            or not 1 <= len(model) <= 80
            or not all(c.isascii() and (c.isalnum() or c in "-._") for c in model)
        ):
            raise RemoteModelError("explicit valid model ID is required")
        if not 5 <= timeout <= 300:
            raise RemoteModelError("model request timeout outside reviewed range")
        self._transport = transport
        self._timeout = timeout

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(context, dict):
            raise RemoteModelError("structured research context required")
        contract = context.get("output_contract")
        stage = (
            "InheritedResearchIntent"
            if contract == "InheritedResearchIntent"
            else "AlgorithmPlan"
            if contract == "AlgorithmPlan"
            else "DiagnosticResponse"
            if context.get("schema") == "research-diagnostic-context-v1"
            else "INVALID"
        )
        if stage == "INVALID":
            raise RemoteModelError("unrecognized research response contract")
        instructions = (
            "You are a research-only trading ALGORITHM DESIGNER, not an order agent. "
            "Return exactly ONE JSON object matching the context's output contract. "
            "Use ONLY the verified indicator IDs and typed operations already supplied. "
            "Treat backtest data and past results as observations, NOT proof of causality. "
            "Do not use sealed OOS, invent trade IDs, claim actual profits, or output Python. "
            "Every different generation must explore a genuinely distinct entry/regime "
            "signal and its next diagnostic must cite authentic observed IDs. "
            "When an exploration direction is provided, weigh it against the "
            "measured evidence and avoid repeating identical strategies. "
            "In inherited mode use only the pinned inherited_parent_strategy_id, "
            "using a supported structure/parameter/mixed mode and one to six "
            "verified typed operations. Treat a "
            "rejected risk candidate as evidence to consider a new hypothesis; "
            "never relax risk limits or repeat identical failed operations. "
            f"Requested JSON object contract: {stage}."
        )
        # The diagnostic context is evidence-bound and must remain byte-for-byte
        # unchanged for local hash checking. Send the response schema outside
        # that context; do not mutate context_hash or the archived trace.
        from research.indicator_engine.algorithm_plan import AlgorithmPlan
        from research.llm.diagnostic_research import DiagnosticResponse
        from research.llm.director import ResearchIntent

        expected_schema = (
            ResearchIntent.model_json_schema()
            if stage == "InheritedResearchIntent"
            else AlgorithmPlan.model_json_schema()
            if stage == "AlgorithmPlan"
            else DiagnosticResponse.model_json_schema()
        )
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": json.dumps(
                {
                    "evidence_context": context,
                    "required_output_json_schema": expected_schema,
                },
                sort_keys=True,
                ensure_ascii=False,
            ),
            "text": {"format": {"type": "json_object"}},
            "max_output_tokens": 6000,
            "store": False,
        }
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                response = client.post(
                    self.ENDPOINT,
                    headers={"Authorization": "Bearer " + self._api_key},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise RemoteModelError("external model HTTP transport failed") from exc
        if response.status_code != 200:
            # Never echo remote body: may contain model input or secrets.
            raise RemoteModelError(f"external model rejected request HTTP {response.status_code}")
        try:
            body = response.json()
            if body.get("status") != "completed":
                raise RemoteModelError("remote model result incomplete or refused")
            chunks = [
                item["text"]
                for outer in body["output"]
                if outer.get("type") == "message"
                for item in outer.get("content", [])
                if item.get("type") == "output_text"
            ]
            if len(chunks) != 1:
                raise RemoteModelError("expected exactly one structured model output")
            parsed = json.loads(chunks[0])
            if not isinstance(parsed, dict):
                raise RemoteModelError("model output must be JSON object")
            return parsed
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            raise RemoteModelError("invalid model JSON response") from exc
