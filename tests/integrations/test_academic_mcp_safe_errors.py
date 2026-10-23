"""T4: model-facing academic repair reasons are safe, allowlisted, no leaked inputs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import types
from mcp.server import ServerRequestContext

from integrations.codex_mcp_sdk_server import SDKMCPServerAdapter
from research.llm.intent_bridge import IntentEligibilityError


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            IntentEligibilityError("private path: /var/lib/secret", code="INTENT_PATH_TARGET"),
            "INTENT_PATH_TARGET",
        ),
        (
            ValueError("UNCHANGED_CANONICAL_FILLS: candidate duplicates parent at /private/path"),
            "UNCHANGED_CANONICAL_FILLS",
        ),
        (
            ValueError("DUPLICATE_EFFECTIVE_INHERITED_SIGNALS: existing generation hash secret"),
            "DUPLICATE_EFFECTIVE_INHERITED_SIGNALS",
        ),
        (
            ValueError("P2_PRECOMMIT_RISK_REJECTED: parent/child detail"),
            "P2_PRECOMMIT_RISK_REJECTED",
        ),
        (
            ValueError("P3_SEMANTIC_PREFLIGHT_REJECTED: omitted details"),
            "P3_SEMANTIC_PREFLIGHT_REJECTED",
        ),
    ],
)
def test_safe_checkpoint_retry_reasons_do_not_echo_raw_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected: str,
) -> None:
    adapter = SDKMCPServerAdapter(state_dir=tmp_path / "state", project_root=tmp_path)

    def rejected(_name: str, _args: dict[str, object]) -> None:
        raise error

    monkeypatch.setattr(adapter.dispatcher, "_dispatch", rejected)

    async def run() -> None:
        request = types.CallToolRequestParams(
            name="submit_algorithm_plan",
            arguments={"session_id": "a" * 32, "checkpoint_token": "b" * 32, "plan": {}},
        )
        response = await adapter.call_tool(cast(ServerRequestContext[Any], None), request)
        assert response.is_error
        part = response.content[0]
        assert isinstance(part, types.TextContent)
        body = json.loads(part.text)
        assert body["error_code"] == expected
        assert body["orders_enabled"] is False
        assert body["retry_same_checkpoint"] is True
        assert "private" not in part.text
        assert "secret" not in part.text
        assert "/var/lib" not in part.text
        assert "b" * 32 not in part.text
        assert len(part.text) < 700

    asyncio.run(run())


def test_unknown_academic_exception_never_echoes_internal_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SDKMCPServerAdapter(state_dir=tmp_path / "state", project_root=tmp_path)

    def failure(_name: str, _args: dict[str, object]) -> None:
        raise ValueError("sensitive payload token=secret-database-row")

    monkeypatch.setattr(adapter.dispatcher, "_dispatch", failure)

    async def run() -> None:
        request = types.CallToolRequestParams(
            name="submit_algorithm_diagnosis",
            arguments={"session_id": "a" * 32, "checkpoint_token": "b" * 32, "diagnosis": {}},
        )
        response = await adapter.call_tool(cast(ServerRequestContext[Any], None), request)
        assert response.is_error
        body = json.loads(cast(types.TextContent, response.content[0]).text)
        assert body["error_code"] == "ACADEMIC_CHECKPOINT_REJECTED"
        assert "secret" not in json.dumps(body)
        assert body["retry_same_checkpoint"] is False

    asyncio.run(run())
