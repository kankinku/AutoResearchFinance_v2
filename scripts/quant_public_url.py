"""Persist and validate Quant MCP's Moon Funnel OAuth issuer identity.

A different URL would invalidate registered OAuth resource/issuer assumptions.
An existing OAuth database must never be paired with an implicitly new URL.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

_MOON_URL = re.compile(r"https://[a-zA-Z0-9.-]+\.ts\.net")


def _validate_base(base: str) -> str:
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or not parsed.hostname.endswith(".ts.net")
        or parsed.port is not None
        or parsed.path != "/quant"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or base != f"https://{parsed.hostname}/quant"
    ):
        raise ValueError("Quant MCP public URL must be an exact HTTPS *.ts.net/quant base")
    return base


def pinned_public_base(pin: Path, moon_notes: Path, oauth_db: Path) -> str:
    """Bootstrap only before OAuth exists; otherwise require an existing stable pin."""
    hosts = set(_MOON_URL.findall(moon_notes.read_text(encoding="utf-8")))
    if len(hosts) != 1:
        raise ValueError("Moon host must be unambiguous; public URL unchanged")
    discovered = _validate_base(next(iter(hosts)) + "/quant")
    if pin.is_symlink():
        raise ValueError("Quant MCP URL pin must not be a symlink")
    if pin.exists():
        if pin.stat().st_mode & 0o077:
            raise ValueError("Quant MCP URL pin permissions are too broad")
        stored = _validate_base(pin.read_text(encoding="utf-8").strip())
    else:
        if oauth_db.exists():
            raise ValueError("Quant MCP URL pin is missing while existing OAuth state is present")
        pin.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(pin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(discovered + "\n")
        stored = discovered
    if discovered != stored:
        raise ValueError("Moon URL changed: refusing to silently change Quant OAuth issuer")
    return stored


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify pinned Quant MCP OAuth public URL")
    parser.add_argument("--pin", type=Path, required=True)
    parser.add_argument("--moon-notes", type=Path, default=Path("/shared/AGENTS.md"))
    parser.add_argument("--oauth-db", type=Path, required=True)
    options = parser.parse_args()
    print(pinned_public_base(options.pin, options.moon_notes, options.oauth_db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
