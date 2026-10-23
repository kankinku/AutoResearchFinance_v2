"""One-time explicitly authorized NEW Quant OAuth identity; no old identity rotation.

Fresh registration is independent of preserved research G452/G552. Never
prints keys/tokens and never overwrites a partially existing Quant identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.quant_public_url import _MOON_URL, _validate_base


class ProvisionBlocked(ValueError):
    """Refuse implicit issuance or overwrite of old auth / research records."""


def _create_new_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def provision_fresh_identity(root: Path, moon_notes: Path, *, authorized: bool) -> dict[str, Any]:
    if authorized is not True:
        raise ProvisionBlocked("EXPLICIT_NEW_OAUTH_APPROVAL_REQUIRED")
    state = root.resolve() / "state/moon-http"
    oauth = state / "oauth"
    research = state / "research"
    db = research / "oauth/quant-oauth.sqlite"
    key = oauth / "approval-key"
    pin = oauth / "public-base-url"
    marker = oauth / "new-registration-approved.json"
    # Fail closed on *any* legacy or partial identity and research system.
    if any(p.is_symlink() or p.exists() for p in (key, pin, db, marker)):
        raise ProvisionBlocked("EXISTING_OR_PARTIAL_OAUTH_IDENTITY: no overwrite")
    if research.exists() and any(research.iterdir()):
        raise ProvisionBlocked("EXISTING_RESEARCH_STATE: refusing reset")
    if oauth.exists() and any(oauth.iterdir()):
        raise ProvisionBlocked("EXISTING_OR_PARTIAL_OAUTH_DIR: no overwrite")
    hosts = set(_MOON_URL.findall(moon_notes.read_text(encoding="utf-8")))
    if len(hosts) != 1:
        raise ProvisionBlocked("MOON_PUBLIC_HOST_UNVERIFIED")
    issuer = _validate_base(next(iter(hosts)) + "/quant")
    # Research checkpoint DBs are not inspected or touched by this routine.
    oauth.mkdir(mode=0o700, parents=True, exist_ok=True)
    (research / "oauth").mkdir(mode=0o700, parents=True, exist_ok=True)
    key_bytes = (secrets.token_urlsafe(48) + "\n").encode("ascii")
    pin_bytes = (issuer + "\n").encode("ascii")
    _create_new_file(key, key_bytes)
    _create_new_file(pin, pin_bytes)
    # SQLite ex-nihilo, empty DCR clients and grants: user must consent in app.
    with sqlite3.connect(db.resolve()) as conn:
        conn.executescript(
            "CREATE TABLE clients (id TEXT PRIMARY KEY, data TEXT NOT NULL);"
            "CREATE TABLE grants (digest TEXT PRIMARY KEY, kind TEXT NOT NULL,"
            " client_id TEXT NOT NULL, payload TEXT NOT NULL, expires REAL NOT NULL);"
        )
    db.chmod(0o600)
    evidence = {
        "schema": "approved-fresh-quant-oauth-v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "key_digest": hashlib.sha256(key_bytes).hexdigest(),
        "pin_digest": hashlib.sha256(pin_bytes).hexdigest(),
        "original_reused": False,
    }
    _create_new_file(marker, (json.dumps(evidence, sort_keys=True) + "\n").encode())
    return {
        "status": "FRESH_OAUTH_PROVISIONED_PENDING_CLIENT_APPROVAL",
        "issuer": issuer,
        "client_count": 0,
        "reused_original_credentials": False,
        "research_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explicit one-time new Quant OAuth setup, never replacement"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--moon-notes", type=Path, default=Path("/shared/AGENTS.md"))
    parser.add_argument("--authorize-new-identity", action="store_true")
    args = parser.parse_args()
    try:
        result = provision_fresh_identity(
            args.root, args.moon_notes, authorized=args.authorize_new_identity
        )
    except (ProvisionBlocked, OSError, sqlite3.Error, ValueError) as error:
        print("FRESH_OAUTH_PROVISION_BLOCKED: " + type(error).__name__)
        return 78
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
