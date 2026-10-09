"""No unauthenticated externally reachable MCP transports."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from integrations.chatgpt_mcp_http import create_http_app, require_access_token

TOKEN = "a" * 48


def test_http_boot_requires_strong_token() -> None:
    for token in (None, "", "short"):
        with pytest.raises(ValueError, match="token"):
            require_access_token(token)
    assert require_access_token(TOKEN) == TOKEN


def test_http_mcp_denies_unauthenticated_requests_and_accepts_sdk_initialize(
    tmp_path: Path,
) -> None:
    app = create_http_app(project_root=tmp_path, state_dir=tmp_path / "state", token=TOKEN)

    async def check() -> None:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
                follow_redirects=True,
            ) as client:
                message = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "external-gpt-test", "version": "1"},
                    },
                }
                for headers in ({}, {"authorization": "Bearer invalid"}):
                    response = await client.post("/mcp", json=message, headers=headers)
                    assert response.status_code == 401
                response = await client.post(
                    "/mcp",
                    json=message,
                    headers={
                        "authorization": f"Bearer {TOKEN}",
                        "accept": "application/json, text/event-stream",
                    },
                )
                assert response.status_code == 200, response.text
                assert response.json()["result"]["serverInfo"]["name"] == "quant-autoresearch"
                assert TOKEN not in response.text
                for name, parameters in (
                    ("tools/list", {}),
                    ("tools/call", {"name": "get_research_brief", "arguments": {}}),
                ):
                    rpc = await client.post(
                        "/mcp",
                        json={"jsonrpc": "2.0", "id": 2, "method": name, "params": parameters},
                        headers={
                            "authorization": f"Bearer {TOKEN}",
                            "accept": "application/json, text/event-stream",
                            "mcp-protocol-version": "2025-11-25",
                        },
                    )
                    assert rpc.status_code == 200, rpc.text
                    if name == "tools/list":
                        assert any(
                            item["name"] == "run_research_step"
                            for item in rpc.json()["result"]["tools"]
                        )
                    else:
                        import json

                        brief = json.loads(rpc.json()["result"]["content"][0]["text"])
                        assert brief["llm_controller"] == "external_mcp_client"
                        assert brief["_contract"]["orders_enabled"] is False

    asyncio.run(check())
