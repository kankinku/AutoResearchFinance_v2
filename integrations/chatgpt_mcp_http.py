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
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

from integrations.chatgpt_mcp_sdk import create_chatgpt_sdk_adapter


class _AuthenticatedMCP:
    """Protect GET, POST and DELETE; do not leak token or request payload."""

    def __init__(self, app: ASGIApp, *, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        supplied = (
            authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        )
        if not compare_digest(supplied, self.token):
            await Response("Unauthorized", status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def require_access_token(token: str | None) -> str:
    if not isinstance(token, str) or len(token) < 32 or token.isspace():
        raise ValueError("MCP HTTP token must contain at least 32 characters")
    return token


def create_http_app(
    *,
    project_root: Path,
    state_dir: Path,
    token: str,
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"),
) -> Starlette:
    """Build the official SDK HTTP ASGI app; never start it implicitly."""
    secret = require_access_token(token)
    adapter = create_chatgpt_sdk_adapter(project_root=project_root, state_dir=state_dir)
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

    app = Starlette(routes=[Mount("/mcp", app=session_manager.handle_request)], lifespan=lifespan)
    app.add_middleware(_AuthenticatedMCP, token=secret)
    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authenticated local MCP HTTP endpoint")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--allowed-host", action="append", dest="allowed_hosts")
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("public interface binding is prohibited; use a trusted TLS gateway")
    if not 1 <= args.port <= 65535:
        raise ValueError("invalid MCP HTTP port")
    token = require_access_token(os.environ.get("QUANT_MCP_HTTP_TOKEN"))
    hosts = tuple(args.allowed_hosts or ("127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"))
    app = create_http_app(
        project_root=args.project_root,
        state_dir=args.state_dir,
        token=token,
        allowed_hosts=hosts,
    )
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
