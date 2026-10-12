"""Stable public resource identity must survive code updates and OAuth restarts."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quant_public_url import pinned_public_base

BASE = "https://project-moon.taild689f9.ts.net/quant"


def test_url_pin_created_once_and_reused(tmp_path: Path) -> None:
    notes = tmp_path / "AGENTS.md"
    notes.write_text("Public base URL: https://project-moon.taild689f9.ts.net\n")
    pin = tmp_path / "oauth" / "public-base-url"
    oauth = tmp_path / "research" / "oauth" / "quant-oauth.sqlite"
    assert pinned_public_base(pin, notes, oauth) == BASE
    assert pin.read_text().strip() == BASE
    assert pin.stat().st_mode & 0o077 == 0
    oauth.parent.mkdir(parents=True)
    oauth.write_bytes(b"existing persistent OAuth DB")
    assert pinned_public_base(pin, notes, oauth) == BASE


def test_url_drift_refused_without_overwriting_pin(tmp_path: Path) -> None:
    notes = tmp_path / "AGENTS.md"
    notes.write_text("Public base URL: https://project-moon.taild689f9.ts.net\n")
    pin = tmp_path / "oauth" / "public-base-url"
    oauth = tmp_path / "quant-oauth.sqlite"
    pinned_public_base(pin, notes, oauth)
    notes.write_text("Public base URL: https://new-host.taild689f9.ts.net\n")
    with pytest.raises(ValueError, match="changed"):
        pinned_public_base(pin, notes, oauth)
    assert pin.read_text().strip() == BASE


def test_missing_pin_with_existing_oauth_state_fails_closed(tmp_path: Path) -> None:
    notes = tmp_path / "AGENTS.md"
    notes.write_text("https://project-moon.taild689f9.ts.net")
    pin = tmp_path / "oauth" / "public-base-url"
    oauth = tmp_path / "oauth" / "quant-oauth.sqlite"
    oauth.parent.mkdir()
    oauth.write_bytes(b"state")
    with pytest.raises(ValueError, match="pin is missing"):
        pinned_public_base(pin, notes, oauth)
    assert not pin.exists()


def test_invalid_or_symlink_pin_is_rejected(tmp_path: Path) -> None:
    notes = tmp_path / "AGENTS.md"
    notes.write_text("https://project-moon.taild689f9.ts.net")
    pin = tmp_path / "oauth" / "public-base-url"
    pin.parent.mkdir()
    pin.symlink_to(notes)
    with pytest.raises(ValueError, match="symlink"):
        pinned_public_base(pin, notes, tmp_path / "missing")
