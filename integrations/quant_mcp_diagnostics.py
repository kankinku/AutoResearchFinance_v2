"""Privacy-preserving MCP request diagnostics (never log tokens or arguments)."""

from __future__ import annotations

import json
import os
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID: ContextVar[str] = ContextVar("quant_mcp_request_id", default="-")
_ROUTES = {
    "/mcp": "mcp",
    "/authorize": "oauth_authorize",
    "/token": "oauth_token",
    "/register": "oauth_register",
    "/consent": "oauth_consent",
    "/.well-known/oauth-authorization-server": "oauth_metadata",
    "/.well-known/oauth-protected-resource/quant/mcp": "resource_metadata",
}


class MCPAuditLog:
    """Rotating JSONL log containing only predefined safe metadata fields."""

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "logs" / "mcp-events.jsonl"
        self.lock = Lock()

    def emit(
        self,
        event: str,
        *,
        route: str | None = None,
        http_status: int | None = None,
        tool: str | None = None,
        result: str | None = None,
        error_code: str | None = None,
        count: int | None = None,
        elapsed_ms: int | None = None,
    ) -> None:
        record: dict[str, str | int] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "request_id": _REQUEST_ID.get(),
            "event": event,
        }
        for key, value in {
            "route": route,
            "http_status": http_status,
            "tool": tool,
            "result": result,
            "error_code": error_code,
            "count": count,
            "elapsed_ms": elapsed_ms,
        }.items():
            if value is not None:
                record[key] = value
        line = (json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            with self.lock:
                self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                if self.path.exists() and self.path.stat().st_size > 4 * 1024 * 1024:
                    self.path.replace(self.path.with_suffix(".jsonl.1"))
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "ab") as output:
                    output.write(line)
        except OSError:
            # Diagnostics must never interrupt the MCP request.
            pass


class MCPRequestDiagnostics:
    """Track HTTP status by allowlisted endpoint, never inspect bodies or headers."""

    def __init__(self, app: ASGIApp, audit: MCPAuditLog) -> None:
        self.app = app
        self.audit = audit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        route = _ROUTES.get(scope.get("path", "").rstrip("/"), "other")
        token = _REQUEST_ID.set(uuid4().hex)
        started = time.monotonic()

        async def audited_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.audit.emit(
                    "http_response",
                    route=route,
                    http_status=message["status"],
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
            await send(message)

        try:
            await self.app(scope, receive, audited_send)
        except Exception as exc:
            self.audit.emit("http_exception", route=route, error_code=type(exc).__name__)
            raise
        finally:
            _REQUEST_ID.reset(token)
