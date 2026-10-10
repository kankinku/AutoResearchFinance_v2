"""Authenticated, opt-in Streamable HTTP transport for an external MCP client.

This transport is deliberately separate from the canonical stdio entrypoint.
It binds to loopback by default and requires a secret supplied at launch.
"""

from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from hmac import compare_digest
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.auth.routes import (
    MetadataHandler,
    build_metadata,
    cors_middleware,
    create_auth_routes,
    create_protected_resource_routes,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from integrations.chatgpt_mcp_sdk import create_chatgpt_sdk_adapter
from integrations.quant_mcp_diagnostics import MCPAuditLog, MCPRequestDiagnostics
from integrations.quant_oauth import QuantOAuthProvider


class _AuthenticatedMCP:
    """Protect GET, POST and DELETE; do not leak token or request payload."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        token: str | None,
        oauth: QuantOAuthProvider | None = None,
    ) -> None:
        self.app = app
        self.token = token
        self.oauth = oauth

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path", "").rstrip("/") != "/mcp":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        match = authorization.lower().startswith("bearer ")
        supplied = authorization[7:].strip() if match else ""
        authorized = bool(self.token and compare_digest(supplied, self.token))
        if not authorized and supplied and self.oauth:
            verified = await self.oauth.verify_token(supplied)
            authorized = bool(
                verified
                and verified.resource == self.oauth.resource
                and "mcp:tools" in verified.scopes
            )
        if not authorized:
            headers_out: dict[str, str] = {}
            if self.oauth:
                from urllib.parse import urlparse

                resource = urlparse(self.oauth.resource)
                resource_metadata = (
                    f"{resource.scheme}://{resource.netloc}"
                    f"/.well-known/oauth-protected-resource{resource.path}"
                )
                headers_out["WWW-Authenticate"] = (
                    'Bearer realm="quant-autoresearch", error="invalid_token", '
                    f'scope="mcp:tools", resource_metadata="{resource_metadata}"'
                )
            else:
                headers_out["WWW-Authenticate"] = 'Bearer realm="quant-autoresearch"'
            await Response("Unauthorized", status_code=401, headers=headers_out)(
                scope, receive, send
            )
            return
        await self.app(scope, receive, send)


class _OAuthToolSchemaResponse:
    """Preserve tool securitySchemes through pinned MCP SDK 2.2 serialization.

    The installed SDK's ListToolsResult serializer drops Tool subclass fields,
    so add tool-level metadata only to complete, nonstreaming JSON tools/list
    replies from the external OAuth endpoint. Never modify tool results.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "").rstrip("/") != "/mcp":
            await self.app(scope, receive, send)
            return
        start: Message | None = None

        async def send_filtered(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
                return
            if message["type"] == "http.response.body" and start is not None:
                raw = message.get("body", b"")
                headers = dict(start.get("headers", []))
                if (
                    not message.get("more_body")
                    and start.get("status") == 200
                    and b"application/json" in headers.get(b"content-type", b"")
                    and len(raw) <= 512_000
                ):
                    import json

                    try:
                        payload = json.loads(raw)
                    except (ValueError, TypeError):
                        payload = None
                    result = payload.get("result") if isinstance(payload, dict) else None
                    tools = result.get("tools") if isinstance(result, dict) else None
                    if (
                        isinstance(tools, list)
                        and tools
                        and all(isinstance(tool, dict) and "name" in tool for tool in tools)
                    ):
                        for tool in tools:
                            tool["securitySchemes"] = [{"type": "oauth2", "scopes": ["mcp:tools"]}]
                        raw = json.dumps(payload, separators=(",", ":")).encode()
                        headers[b"content-length"] = str(len(raw)).encode()
                        start = {**start, "headers": list(headers.items())}
                await send(start)
                start = None
                await send({**message, "body": raw})
                return
            if start is not None:
                await send(start)
                start = None
            await send(message)

        await self.app(scope, receive, send_filtered)


def require_access_token(token: str | None) -> str:
    if not isinstance(token, str) or len(token) < 32 or token.isspace():
        raise ValueError("MCP HTTP token must contain at least 32 characters")
    return token


def create_http_app(
    *,
    project_root: Path,
    state_dir: Path,
    token: str | None = None,
    oauth: QuantOAuthProvider | None = None,
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"),
) -> Starlette:
    """Build the official SDK HTTP ASGI app; never start it implicitly."""
    if token is None and oauth is None:
        raise ValueError("at least one MCP authentication method is required")
    secret = require_access_token(token) if token is not None else None
    audit = MCPAuditLog(state_dir) if oauth is not None else None
    adapter = create_chatgpt_sdk_adapter(
        project_root=project_root,
        state_dir=state_dir,
        require_oauth=oauth is not None,
        audit=audit,
    )
    session_manager = StreamableHTTPSessionManager(
        adapter.server,
        json_response=True,
        stateless=True,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(allowed_hosts),
            allowed_origins=[],
        ),
    )

    @asynccontextmanager
    async def lifespan(_: Starlette) -> Any:
        async with session_manager.run():
            yield

    routes: list[BaseRoute] = [Mount("/mcp", app=session_manager.handle_request)]
    if oauth is not None:
        issuer, resource = AnyHttpUrl(oauth.public_base), AnyHttpUrl(oauth.resource)
        registration = ClientRegistrationOptions(
            enabled=True, valid_scopes=["mcp:tools"], default_scopes=["mcp:tools"]
        )
        auth_routes = create_auth_routes(oauth, issuer, client_registration_options=registration)
        metadata = build_metadata(issuer, None, registration, RevocationOptions())
        # SDK 2.2.0 incorrectly advertises only confidential clients here.
        # The Quant provider supports public PKCE and secret_post, not secret_basic.
        metadata.token_endpoint_auth_methods_supported = ["none", "client_secret_post"]
        auth_routes[0] = Route(
            "/.well-known/oauth-authorization-server",
            endpoint=cors_middleware(MetadataHandler(metadata).handle, ["GET", "OPTIONS"]),
            methods=["GET", "OPTIONS"],
        )
        routes.extend(auth_routes)
        routes.extend(
            create_protected_resource_routes(
                resource,
                [issuer],
                scopes_supported=["mcp:tools"],
                resource_name="Quant Autoresearch",
            )
        )
        routes.append(Route("/consent", oauth.consent, methods=["GET", "POST"]))
    app = Starlette(routes=routes, lifespan=lifespan)
    if oauth is not None:
        app.add_middleware(_OAuthToolSchemaResponse)
    app.add_middleware(_AuthenticatedMCP, token=secret, oauth=oauth)
    if audit is not None:
        app.add_middleware(MCPRequestDiagnostics, audit=audit)
    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authenticated local MCP HTTP endpoint")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--allowed-host", action="append", dest="allowed_hosts")
    parser.add_argument(
        "--public-url", help="fixed public HTTPS URL with /quant path; activates Moon-style OAuth"
    )
    parser.add_argument(
        "--approval-key-file",
        type=Path,
        help="private file containing a separate Quant OAuth approval key",
    )
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("public interface binding is prohibited; use a trusted TLS gateway")
    if not 1 <= args.port <= 65535:
        raise ValueError("invalid MCP HTTP port")
    token = os.environ.get("QUANT_MCP_HTTP_TOKEN") or None
    oauth = None
    if args.public_url:
        if not args.approval_key_file:
            raise ValueError("Quant OAuth --approval-key-file is required with --public-url")
        key_file = args.approval_key_file.resolve()
        if key_file.stat().st_mode & 0o077:
            raise ValueError("Quant OAuth approval key file must not be readable by others")
        oauth = QuantOAuthProvider(
            state_dir=args.state_dir.resolve() / "oauth",
            public_base=args.public_url,
            approval_key=key_file.read_text(encoding="utf-8").strip(),
        )
    from urllib.parse import urlparse

    public_host = urlparse(args.public_url).hostname if args.public_url else None
    hosts = tuple(
        args.allowed_hosts
        or (
            "127.0.0.1",
            "127.0.0.1:*",
            "localhost",
            "localhost:*",
            *((public_host,) if public_host else ()),
        )
    )
    app = create_http_app(
        project_root=args.project_root,
        state_dir=args.state_dir,
        token=token,
        oauth=oauth,
        allowed_hosts=hosts,
    )
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
