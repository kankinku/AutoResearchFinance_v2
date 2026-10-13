"""Live Moon-style OAuth approval + PKCE + fixed URL/resource scope (ASGI)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from integrations.chatgpt_mcp_http import create_http_app
from integrations.quant_oauth import QuantOAuthProvider

PUBLIC = "https://project-moon.example.ts.net/quant"
KEY = "a" * 64


def test_moon_oauth_registration_approval_pkce_and_scope(tmp_path: Path) -> None:
    oauth = QuantOAuthProvider(
        state_dir=tmp_path / "private-oauth", public_base=PUBLIC, approval_key=KEY
    )
    app = create_http_app(project_root=tmp_path, state_dir=tmp_path / "research", oauth=oauth)

    async def verify() -> None:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "ChatGPT test", "version": "1"},
                    },
                }
                headers = {"accept": "application/json, text/event-stream"}
                denied = await client.post("/mcp", json=payload, headers=headers)
                assert denied.status_code == 401
                assert f"{PUBLIC}/mcp" not in denied.text
                assert (
                    "/.well-known/oauth-protected-resource/quant/mcp"
                    in denied.headers["www-authenticate"]
                )

                resource = await client.get("/.well-known/oauth-protected-resource/quant/mcp")
                assert resource.status_code == 200, resource.text
                assert resource.json()["resource"] == f"{PUBLIC}/mcp"
                assert str(resource.json()["authorization_servers"][0]).rstrip("/") == PUBLIC
                meta = await client.get("/.well-known/oauth-authorization-server")
                assert meta.status_code == 200, meta.text
                assert meta.json()["token_endpoint"].startswith(PUBLIC)
                assert meta.json()["token_endpoint_auth_methods_supported"] == [
                    "none",
                    "client_secret_post",
                ]
                assert (
                    "client_secret_basic"
                    not in meta.json()["token_endpoint_auth_methods_supported"]
                )
                redirect = "https://chatgpt.com/connector_platform_oauth_redirect"
                registered = await client.post(
                    "/register",
                    json={
                        "client_name": "GPT Quant MCP Test",
                        "redirect_uris": [redirect],
                        "token_endpoint_auth_method": "none",
                        "grant_types": ["authorization_code", "refresh_token"],
                        "response_types": ["code"],
                        "scope": "mcp:tools",
                    },
                )
                assert registered.status_code == 201, registered.text
                client_id = registered.json()["client_id"]
                verifier = "z" * 64
                challenge = (
                    base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                    .decode()
                    .rstrip("=")
                )
                auth = await client.get(
                    "/authorize",
                    params={
                        "response_type": "code",
                        "client_id": client_id,
                        "redirect_uri": redirect,
                        "state": "confident-state",
                        "code_challenge": challenge,
                        "code_challenge_method": "S256",
                        "scope": "mcp:tools",
                        "resource": f"{PUBLIC}/mcp",
                    },
                )
                assert auth.status_code == 302, auth.text
                consent_url = auth.headers["location"]
                assert consent_url.startswith(PUBLIC + "/consent?")
                nonce = parse_qs(urlparse(consent_url).query)["request"][0]
                page = await client.get("/consent", params={"request": nonce})
                assert page.status_code == 200
                assert "access_key" in page.text
                rejected = await client.post(
                    "/consent", data={"request": nonce, "access_key": "incorrect"}
                )
                assert rejected.status_code == 401
                approved = await client.post("/consent", data={"request": nonce, "access_key": KEY})
                assert approved.status_code == 303
                query = parse_qs(urlparse(approved.headers["location"]).query)
                assert query["state"] == ["confident-state"]
                code = query["code"][0]
                token = await client.post(
                    "/token",
                    data={
                        "grant_type": "authorization_code",
                        "client_id": client_id,
                        "code": code,
                        "redirect_uri": redirect,
                        "code_verifier": verifier,
                        "resource": f"{PUBLIC}/mcp",
                    },
                )
                assert token.status_code == 200, token.text
                access = token.json()["access_token"]
                refresh = token.json()["refresh_token"]
                assert KEY not in token.text
                authorized = await client.post(
                    "/mcp",
                    follow_redirects=True,
                    json=payload,
                    headers={**headers, "authorization": f"Bearer {access}"},
                )
                assert authorized.status_code == 200, authorized.text
                assert authorized.json()["result"]["serverInfo"]["name"] == "quant-autoresearch"
                listed = await client.post(
                    "/mcp",
                    follow_redirects=True,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                    headers={
                        **headers,
                        "authorization": f"Bearer {access}",
                        "mcp-protocol-version": "2025-11-25",
                    },
                )
                assert listed.status_code == 200, listed.text
                assert all(
                    tool["securitySchemes"] == [{"type": "oauth2", "scopes": ["mcp:tools"]}]
                    for tool in listed.json()["result"]["tools"]
                )
                called = await client.post(
                    "/mcp",
                    follow_redirects=True,
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "get_workspace_status", "arguments": {}},
                    },
                    headers={**headers, "authorization": f"Bearer {access}"},
                )
                assert called.status_code == 200
                assert called.json()["result"]["isError"] is False
                unknown = await client.post(
                    "/mcp",
                    follow_redirects=True,
                    json={
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {
                            "name": "nonexistent_tool",
                            "arguments": {"canary": "DONT_LOG_THIS_SECRET"},
                        },
                    },
                    headers={**headers, "authorization": f"Bearer {access}"},
                )
                assert unknown.status_code == 200
                assert unknown.json()["result"]["isError"] is True
                audit_file = tmp_path / "research" / "logs" / "mcp-events.jsonl"
                audit_data = audit_file.read_text(encoding="utf-8")
                records = [json.loads(line) for line in audit_data.splitlines()]
                assert any(r["event"] == "tools_list" and r["count"] == 24 for r in records)
                assert any(
                    r["event"] == "tool_call"
                    and r["tool"] == "get_workspace_status"
                    and r["result"] == "OK"
                    for r in records
                )
                assert any(
                    r["event"] == "http_response"
                    and r["route"] == "mcp"
                    and r["http_status"] == 401
                    for r in records
                )
                assert any(
                    r["event"] == "tool_call"
                    and r["tool"] == "unknown"
                    and r["error_code"] == "UNKNOWN_TOOL"
                    for r in records
                )
                assert any(
                    r["event"] == "http_response"
                    and r["route"] == "oauth_consent"
                    and r["http_status"] == 401
                    for r in records
                )
                assert "DONT_LOG_THIS_SECRET" not in audit_data
                assert access not in audit_data and KEY not in audit_data
                assert audit_file.stat().st_mode & 0o077 == 0
                replay = await client.post(
                    "/token",
                    data={
                        "grant_type": "authorization_code",
                        "client_id": client_id,
                        "code": code,
                        "redirect_uri": redirect,
                        "code_verifier": verifier,
                        "resource": f"{PUBLIC}/mcp",
                    },
                )
                assert replay.status_code != 200
                renewed = await client.post(
                    "/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "refresh_token": refresh,
                        "scope": "mcp:tools",
                        "resource": f"{PUBLIC}/mcp",
                    },
                )
                assert renewed.status_code == 200, renewed.text
                assert renewed.json()["refresh_token"] != refresh
                reused = await client.post(
                    "/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "refresh_token": refresh,
                        "scope": "mcp:tools",
                        "resource": f"{PUBLIC}/mcp",
                    },
                )
                assert reused.status_code != 200
                assert oauth.db_path.stat().st_mode & 0o077 == 0

    asyncio.run(verify())
