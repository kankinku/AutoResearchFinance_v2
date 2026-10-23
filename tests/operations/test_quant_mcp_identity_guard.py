"""Read-only prestart verification of ORIGINAL Quant OAuth state."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.quant_mcp_identity_guard import check_existing_identity


def _oauth_fixture(tmp_path: Path):
    root = tmp_path / "quant"
    state = root / "state/moon-http"
    (state / "oauth").mkdir(parents=True)
    (state / "research/oauth").mkdir(parents=True)
    key = state / "oauth/approval-key"
    pin = state / "oauth/public-base-url"
    db = state / "research/oauth/quant-oauth.sqlite"
    key.write_text("example-persisted-key", encoding="utf-8")
    pin.write_text("https://persistent-issuer.ts.net/quant\n", encoding="utf-8")
    key.chmod(0o600)
    pin.chmod(0o600)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE clients (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE grants (digest TEXT PRIMARY KEY, kind TEXT NOT NULL, "
            "client_id TEXT NOT NULL, payload TEXT NOT NULL, expires REAL NOT NULL)"
        )
        conn.execute("INSERT INTO clients VALUES (?, ?)", ("persisted-id", "{}"))
    return root, key, pin, db


def test_verified_existing_issuer_client_store_is_read_only(tmp_path: Path):
    root, key, pin, db = _oauth_fixture(tmp_path)
    original = (key.read_bytes(), pin.read_bytes(), db.stat().st_size)
    assert check_existing_identity(root) == ()
    assert original == (key.read_bytes(), pin.read_bytes(), db.stat().st_size)


def test_missing_or_empty_triplet_blocks_and_does_not_create(tmp_path: Path):
    root = tmp_path / "no-identity"
    result = check_existing_identity(root)
    assert set(result) == {
        "APPROVAL_KEY_MISSING",
        "PUBLIC_URL_PIN_MISSING",
        "OAUTH_DATABASE_MISSING",
    }
    assert not (root / "state/moon-http").exists()


def test_bad_schema_or_no_registered_clients_blocks(tmp_path: Path):
    root, _, _, db = _oauth_fixture(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM clients")
    assert "OAUTH_REGISTERED_CLIENTS_MISSING" in check_existing_identity(root)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE grants")
    assert "OAUTH_DATABASE_SCHEMA_INVALID" in check_existing_identity(root)


def test_invalid_pin_permissions_or_linked_key_blocks(tmp_path: Path):
    root, key, pin, _ = _oauth_fixture(tmp_path)
    pin.chmod(0o644)
    assert "OAUTH_IDENTITY_PERMISSIONS_INVALID" in check_existing_identity(root)
    pin.chmod(0o600)
    pin.write_text("https://different-host.com/quant\n")
    assert "PUBLIC_URL_PIN_INVALID" in check_existing_identity(root)
    pin.write_text("https://persistent-issuer.ts.net/quant\n")
    linked = tmp_path / "original"
    linked.write_bytes(key.read_bytes())
    key.unlink()
    key.symlink_to(linked)
    assert "APPROVAL_KEY_MISSING" in check_existing_identity(root)


def test_sqlite_corruption_fails_closed(tmp_path: Path):
    root, _, _, db = _oauth_fixture(tmp_path)
    db.write_bytes(b"corrupt and not sqlite")
    assert "OAUTH_DATABASE_INVALID" in check_existing_identity(root)
