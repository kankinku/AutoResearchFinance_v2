"""Moon-style approval-key OAuth 2.1 for ChatGPT's Quant research MCP.

Separate issuer, audience and credential database; never reuse Moon's tokens.
All OAuth grants use short-lived PKCE authorization codes and persisted access
and rotating refresh tokens. No implicit anonymous MCP permissions.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode, urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

_SCOPE = "mcp:tools"


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _secret() -> str:
    return secrets.token_urlsafe(32)


def _redirect_allowed(value: str) -> bool:
    u = urlparse(value)
    return (
        u.scheme == "https"
        or (u.scheme == "http" and u.hostname in {"localhost", "127.0.0.1", "::1"})
    ) and not (u.username or u.password or u.fragment)


@dataclass(frozen=True)
class _Pending:
    client_id: str
    params: AuthorizationParams
    expires: float


class QuantOAuthProvider:
    """OAuth DCR, PKCE, refresh-rotation and Moon-equivalent approval flow."""

    def __init__(self, *, state_dir: Path, public_base: str, approval_key: str) -> None:
        if len(approval_key) < 32:
            raise ValueError("QUANT_MCP_OAUTH_APPROVAL_KEY must have at least 32 characters")
        base = public_base.rstrip("/")
        parsed = urlparse(base)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "public OAuth base URL must be absolute HTTPS without credentials or query"
            )
        self.public_base = base
        self.resource = base + "/mcp"
        self.approval_key = approval_key
        self._pending: dict[str, _Pending] = {}
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db_path = state_dir / "quant-oauth.sqlite"
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS clients (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS grants (
                    digest TEXT PRIMARY KEY, kind TEXT NOT NULL, client_id TEXT NOT NULL,
                    payload TEXT NOT NULL, expires REAL NOT NULL
                );
            """)
        self.db_path.chmod(0o600)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def _store_grant(
        self, value: str, kind: str, client_id: str, data: dict[str, Any], ttl: int
    ) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO grants VALUES(?,?,?,?,?)",
                (_hash(value), kind, client_id, json.dumps(data), time.time() + ttl),
            )

    def _get_grant(self, value: str, kind: str, client_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT payload,expires FROM grants WHERE digest=? AND kind=? AND client_id=?",
                (_hash(value), kind, client_id),
            ).fetchone()
        if row is None or row["expires"] < time.time():
            return None
        return cast(dict[str, Any], json.loads(row["payload"]))

    def _consume(self, value: str, kind: str, client_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload,expires FROM grants WHERE digest=? AND kind=? AND client_id=?",
                (_hash(value), kind, client_id),
            ).fetchone()
            if row is None or row["expires"] < time.time():
                return None
            db.execute("DELETE FROM grants WHERE digest=?", (_hash(value),))
        return cast(dict[str, Any], json.loads(row["payload"]))

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._db() as db:
            row = db.execute("SELECT data FROM clients WHERE id=?", (client_id,)).fetchone()
        return OAuthClientInformationFull.model_validate_json(row["data"]) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if (
            not client_info.redirect_uris
            or not all(_redirect_allowed(str(uri)) for uri in client_info.redirect_uris)
            or client_info.token_endpoint_auth_method not in {"none", "client_secret_post", None}
            or (client_info.scope and not set(client_info.scope.split()) <= {_SCOPE})
            or (
                client_info.token_endpoint_auth_method == "client_secret_post"
                and not client_info.client_secret
            )
        ):
            raise ValueError("unapproved OAuth client metadata")
        with self._db() as db:
            db.execute(
                "INSERT INTO clients VALUES(?,?)",
                (client_info.client_id, client_info.model_dump_json()),
            )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if params.resource != self.resource:
            raise ValueError("OAuth resource must match the Quant MCP audience")
        if not set(params.scopes or [_SCOPE]) <= {_SCOPE}:
            raise ValueError("unrecognized OAuth scope")
        if str(params.redirect_uri) not in [str(u) for u in (client.redirect_uris or [])]:
            raise ValueError("unregistered OAuth redirect URI")
        nonce = _secret()
        self._pending[nonce] = _Pending(client.client_id, params, time.time() + 300)
        return self.public_base + "/consent?" + urlencode({"request": nonce})

    async def consent(self, request: Request) -> Response:
        if request.method == "GET":
            nonce = request.query_params.get("request", "")
        else:
            form = await request.form()
            nonce = str(form.get("request", ""))
        record = self._pending.get(nonce)
        if not record or record.expires < time.time():
            return Response("Expired authorization request", status_code=400)
        headers = {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": (
                "default-src 'none'; form-action 'self'; "
                "style-src 'unsafe-inline'; frame-ancestors 'none'"
            ),
        }
        if request.method == "GET":
            import html

            return HTMLResponse(
                "<!doctype html><html><head><title>Quant MCP authorization</title></head><body>"
                "<h2>Authorize Quant Autoresearch MCP</h2>"
                "<p>Enter the private Quant approval key.</p>"
                f'<form method="POST" action="{html.escape(self.public_base)}/consent">'
                f'<input type="hidden" name="request" value="{html.escape(nonce)}">'
                '<input type="password" name="access_key" autocomplete="off" required>'
                '<button type="submit">Authorize</button></form></body></html>',
                headers=headers,
            )
        if not compare_digest(str(form.get("access_key", "")), self.approval_key):
            return Response("Invalid approval key", status_code=401, headers=headers)
        del self._pending[nonce]
        code = _secret()
        params = record.params
        self._store_grant(
            code,
            "code",
            record.client_id,
            {
                "scopes": params.scopes or [_SCOPE],
                "code_challenge": params.code_challenge,
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                "resource": params.resource,
            },
            300,
        )
        from urllib.parse import parse_qsl, urlunparse

        target = urlparse(str(params.redirect_uri))
        query = dict(parse_qsl(target.query))
        query["code"] = code
        if params.state is not None:
            query["state"] = params.state
        return RedirectResponse(
            urlunparse(target._replace(query=urlencode(query))), status_code=303, headers=headers
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        data = self._get_grant(authorization_code, "code", client.client_id)
        if data is None:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=data["scopes"],
            expires_at=time.time() + 300,
            client_id=client.client_id,
            code_challenge=data["code_challenge"],
            redirect_uri=AnyUrl(data["redirect_uri"]),
            redirect_uri_provided_explicitly=data["redirect_uri_provided_explicitly"],
            resource=data["resource"],
        )

    def _issue_tokens(self, client_id: str, scopes: list[str]) -> OAuthToken:
        access, refresh = _secret(), _secret()
        payload = {"scopes": scopes, "resource": self.resource}
        self._store_grant(access, "access", client_id, payload, 3600)
        self._store_grant(refresh, "refresh", client_id, payload, 30 * 24 * 3600)
        return OAuthToken(
            access_token=access, refresh_token=refresh, expires_in=3600, scope=" ".join(scopes)
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        data = self._consume(authorization_code.code, "code", client.client_id)
        if data is None or data["resource"] != self.resource:
            raise ValueError("invalid or expired authorization code")
        return self._issue_tokens(client.client_id, data["scopes"])

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        data = self._get_grant(refresh_token, "refresh", client.client_id)
        if data is None:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=data["scopes"],
            expires_at=int(time.time() + 3600),
            resource=data["resource"],
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        if not set(scopes) <= set(refresh_token.scopes):
            raise ValueError("cannot escalate refresh scope")
        data = self._consume(refresh_token.token, "refresh", client.client_id)
        if data is None or data["resource"] != self.resource:
            raise ValueError("invalid refresh token")
        return self._issue_tokens(client.client_id, scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        with self._db() as db:
            row = db.execute(
                "SELECT client_id,payload,expires FROM grants WHERE digest=? AND kind='access'",
                (_hash(token),),
            ).fetchone()
        if row is None or row["expires"] < time.time():
            return None
        data = json.loads(row["payload"])
        if data["resource"] != self.resource:
            return None
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=data["scopes"],
            expires_at=int(row["expires"]),
            resource=self.resource,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        return await self.load_access_token(token)

    async def exchange_identity_assertion(
        self, client: OAuthClientInformationFull, params: Any
    ) -> OAuthToken:
        """Machine-to-machine identity assertions are not authorized."""
        raise NotImplementedError("identity assertion grant is disabled")

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        with self._db() as db:
            db.execute("DELETE FROM grants WHERE digest=?", (_hash(token.token),))
