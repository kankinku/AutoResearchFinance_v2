"""User-opted new Quant identity: only once, no old OAuth overwrite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.provision_quant_fresh_oauth import ProvisionBlocked, provision_fresh_identity
from scripts.quant_mcp_identity_guard import check_existing_identity


def _notes(tmp_path: Path) -> Path:
    notes = tmp_path / "notes.md"
    notes.write_text("Public base URL: https://project-moon.example.ts.net\n", encoding="utf-8")
    return notes


def test_fresh_opt_in_identity_bootstraps_empty_oauth_registration_once(tmp_path: Path):
    root = tmp_path / "quant"
    notes = _notes(tmp_path)
    result = provision_fresh_identity(root, notes, authorized=True)
    assert result["status"] == "FRESH_OAUTH_PROVISIONED_PENDING_CLIENT_APPROVAL"
    assert result["client_count"] == 0
    assert result["reused_original_credentials"] is False
    assert result["issuer"] == "https://project-moon.example.ts.net/quant"
    state = root / "state/moon-http"
    key = state / "oauth/approval-key"
    pin = state / "oauth/public-base-url"
    db = state / "research/oauth/quant-oauth.sqlite"
    marker = state / "oauth/new-registration-approved.json"
    assert key.stat().st_mode & 0o077 == 0
    assert pin.stat().st_mode & 0o077 == 0
    assert marker.stat().st_mode & 0o077 == 0
    assert pin.read_text().strip() == result["issuer"]
    assert len(key.read_text().strip()) >= 40
    with sqlite3.connect(db) as handle:
        assert handle.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert handle.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 0
    assert check_existing_identity(root) == ()
    assert "approval-key" not in json.dumps(result)

    previous = (key.read_bytes(), pin.read_bytes(), marker.read_bytes(), db.read_bytes())
    with pytest.raises(ProvisionBlocked, match="EXISTING|PARTIAL"):
        provision_fresh_identity(root, notes, authorized=True)
    assert previous == (key.read_bytes(), pin.read_bytes(), marker.read_bytes(), db.read_bytes())


def test_no_authorization_never_creates_identity(tmp_path: Path):
    root = tmp_path / "quant"
    with pytest.raises(ProvisionBlocked, match="EXPLICIT"):
        provision_fresh_identity(root, _notes(tmp_path), authorized=False)
    assert not (root / "state/moon-http/oauth").exists()


def test_partial_previous_identity_is_never_replaced(tmp_path: Path):
    root = tmp_path / "quant"
    oauth = root / "state/moon-http/oauth"
    oauth.mkdir(parents=True)
    saved = oauth / "approval-key"
    saved.write_text("original-do-not-rotate")
    with pytest.raises(ProvisionBlocked, match="EXISTING|PARTIAL"):
        provision_fresh_identity(root, _notes(tmp_path), authorized=True)
    assert saved.read_text() == "original-do-not-rotate"


def test_research_state_existing_is_not_reset(tmp_path: Path):
    root = tmp_path / "quant"
    research = root / "state/moon-http/research/system"
    research.mkdir(parents=True)
    data = research / "important.sqlite"
    data.write_bytes(b"immutable state")
    with pytest.raises(ProvisionBlocked, match="EXISTING"):
        provision_fresh_identity(root, _notes(tmp_path), authorized=True)
    assert data.read_bytes() == b"immutable state"


def test_new_registration_marker_cannot_authorize_unrelated_key(tmp_path: Path):
    root = tmp_path / "quant"
    provision_fresh_identity(root, _notes(tmp_path), authorized=True)
    key = root / "state/moon-http/oauth/approval-key"
    key.write_text("z" * 80)
    key.chmod(0o600)
    assert "NEW_REGISTRATION_MARKER_MISMATCH" in check_existing_identity(root)


def test_marker_is_required_when_oauth_client_db_empty(tmp_path: Path):
    root = tmp_path / "quant"
    provision_fresh_identity(root, _notes(tmp_path), authorized=True)
    (root / "state/moon-http/oauth/new-registration-approved.json").unlink()
    assert "OAUTH_REGISTERED_CLIENTS_MISSING" in check_existing_identity(root)
