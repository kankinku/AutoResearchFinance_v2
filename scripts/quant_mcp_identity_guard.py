"""Reject Quant MCP startup unless its *existing* OAuth identity is intact.

This never creates or modifies credentials, SQLite files, pins, or public URL.
It is a local bootstrap guard, not a claim of successful external OAuth login.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import stat
from pathlib import Path
from urllib.parse import urlsplit


def check_existing_identity(project_root: Path) -> tuple[str, ...]:
    state = project_root / "state/moon-http"
    key = state / "oauth/approval-key"
    pin = state / "oauth/public-base-url"
    database = state / "research/oauth/quant-oauth.sqlite"
    fresh_marker = state / "oauth/new-registration-approved.json"
    missing: list[str] = []
    for name, path in (
        ("APPROVAL_KEY_MISSING", key),
        ("PUBLIC_URL_PIN_MISSING", pin),
        ("OAUTH_DATABASE_MISSING", database),
    ):
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            missing.append(name)
    if missing:
        return tuple(missing)
    # Do not reveal the key or URL in messages or output.
    if key.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO) or pin.stat().st_mode & (
        stat.S_IRWXG | stat.S_IRWXO
    ):
        missing.append("OAUTH_IDENTITY_PERMISSIONS_INVALID")
    try:
        value = pin.read_text(encoding="utf-8").strip()
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or not parsed.hostname.endswith(".ts.net")
            or parsed.path != "/quant"
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or value != f"https://{parsed.hostname}/quant"
        ):
            missing.append("PUBLIC_URL_PIN_INVALID")
    except (OSError, UnicodeError, ValueError):
        missing.append("PUBLIC_URL_PIN_INVALID")

    authorized_fresh = False
    if fresh_marker.exists() or fresh_marker.is_symlink():
        if fresh_marker.is_symlink() or not fresh_marker.is_file():
            missing.append("NEW_REGISTRATION_MARKER_MISMATCH")
        else:
            try:
                document = json.loads(fresh_marker.read_text(encoding="utf-8"))
                marker_valid = (
                    fresh_marker.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO) == 0
                    and document.get("schema") == "approved-fresh-quant-oauth-v1"
                    and document.get("original_reused") is False
                    and document.get("key_digest") == hashlib.sha256(key.read_bytes()).hexdigest()
                    and document.get("pin_digest") == hashlib.sha256(pin.read_bytes()).hexdigest()
                )
                if marker_valid:
                    authorized_fresh = True
                else:
                    missing.append("NEW_REGISTRATION_MARKER_MISMATCH")
            except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
                missing.append("NEW_REGISTRATION_MARKER_MISMATCH")
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            integrity = db.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                missing.append("OAUTH_DATABASE_INVALID")
            tables = {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if not {"clients", "grants"}.issubset(tables):
                missing.append("OAUTH_DATABASE_SCHEMA_INVALID")
            else:
                clients = {row[1] for row in db.execute("PRAGMA table_info(clients)")}
                grants = {row[1] for row in db.execute("PRAGMA table_info(grants)")}
                if not {"id", "data"}.issubset(clients) or not {
                    "digest",
                    "kind",
                    "client_id",
                    "payload",
                    "expires",
                }.issubset(grants):
                    missing.append("OAUTH_DATABASE_SCHEMA_INVALID")
                elif (
                    db.execute("SELECT COUNT(*) FROM clients").fetchone()[0] < 1
                    and not authorized_fresh
                ):
                    missing.append("OAUTH_REGISTERED_CLIENTS_MISSING")
    except (OSError, sqlite3.Error):
        missing.append("OAUTH_DATABASE_INVALID")
    return tuple(sorted(set(missing)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only guard against reinitializing original Quant OAuth."
    )
    parser.add_argument("--root", type=Path, required=True)
    opts = parser.parse_args()
    problems = check_existing_identity(opts.root)
    if problems:
        print("BLOCKED_EXISTING_QUANT_OAUTH: " + ",".join(problems))
        return 78
    print("EXISTING_QUANT_OAUTH_PREFLIGHT_PASS_NOT_AUTHENTICATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
