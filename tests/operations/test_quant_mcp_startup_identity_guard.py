"""Quant's *original* OAuth identity must never be bootstrapped by recovery."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / "scripts/run_quant_moon_http.sh"


def _copy_launcher(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "quant-runner"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    launcher = scripts / RUNNER.name
    launcher.write_bytes(RUNNER.read_bytes())
    return launcher, root


def _invoke(launcher: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        ["bash", str(launcher)],
        text=True,
        capture_output=True,
        timeout=5,
        env={**os.environ, **(env or {})},
        check=False,
    )


def test_no_existing_identity_refuses_start_without_creating_key_or_pin(tmp_path: Path):
    launcher, root = _copy_launcher(tmp_path)
    response = _invoke(launcher)
    assert response.returncode != 0
    assert "original" in response.stderr.lower()
    assert not (root / "state/moon-http/oauth/approval-key").exists()
    assert not (root / "state/moon-http/oauth/public-base-url").exists()
    assert not (root / "state/moon-http/research/oauth/quant-oauth.sqlite").exists()


def test_partial_original_identity_also_refuses_start_without_mutation(tmp_path: Path):
    launcher, root = _copy_launcher(tmp_path)
    identity = root / "state/moon-http"
    (identity / "research/oauth").mkdir(parents=True)
    db = identity / "research/oauth/quant-oauth.sqlite"
    db.write_bytes(b"existing-do-not-replace")
    response = _invoke(launcher)
    assert response.returncode != 0
    assert "original" in response.stderr.lower()
    assert db.read_bytes() == b"existing-do-not-replace"
    assert not (identity / "oauth/approval-key").exists()


def test_existing_triplet_can_reach_mock_transport_without_bootstrap(tmp_path: Path):
    launcher, root = _copy_launcher(tmp_path)
    identity = root / "state/moon-http"
    (identity / "oauth").mkdir(parents=True)
    (identity / "research/oauth").mkdir(parents=True)
    key = identity / "oauth/approval-key"
    pin = identity / "oauth/public-base-url"
    db = identity / "research/oauth/quant-oauth.sqlite"
    key.write_text("unchanged-existing-key", encoding="utf-8")
    pin.write_text("https://original-host.ts.net/quant\n", encoding="utf-8")
    db.write_bytes(b"unchanged-existing-database")
    interpreter = root / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *scripts.quant_mcp_identity_guard*) exit 0;;\n"
        "  *scripts.quant_public_url*) printf 'https://original-host.ts.net/quant\\n';;\n"
        "  *integrations.chatgpt_mcp_http*) printf 'MOCK_TRANSPORT_ONLY\\n';;\n"
        "  *) exit 13;;\n"
        "esac\n",
        encoding="utf-8",
    )
    interpreter.chmod(0o700)
    result = _invoke(launcher)
    assert result.returncode == 0
    assert "MOCK_TRANSPORT_ONLY" in result.stdout
    assert key.read_text() == "unchanged-existing-key"
    assert pin.read_text() == "https://original-host.ts.net/quant\n"
    assert db.read_bytes() == b"unchanged-existing-database"


def test_mismatched_requested_base_refuses_even_with_existing_identity(tmp_path: Path):
    launcher, root = _copy_launcher(tmp_path)
    identity = root / "state/moon-http"
    (identity / "oauth").mkdir(parents=True)
    (identity / "research/oauth").mkdir(parents=True)
    (identity / "oauth/approval-key").write_text("unchanged")
    (identity / "oauth/public-base-url").write_text("https://host.ts.net/quant\n")
    (identity / "research/oauth/quant-oauth.sqlite").write_text("existing")
    python = root / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nprintf 'https://host.ts.net/quant\\n'\n")
    python.chmod(0o700)
    response = _invoke(launcher, {"QUANT_MCP_PUBLIC_BASE": "https://other-host.ts.net/quant"})
    assert response.returncode != 0
    assert "conflicts" in response.stderr.lower()


def test_symlinked_identity_is_rejected_without_loading_target(tmp_path: Path):
    launcher, root = _copy_launcher(tmp_path)
    state = root / "state/moon-http"
    (state / "oauth").mkdir(parents=True)
    (state / "research/oauth").mkdir(parents=True)
    protected = tmp_path / "do-not-modify-existing-key"
    protected.write_text("original-approved-secret", encoding="utf-8")
    (state / "oauth/approval-key").symlink_to(protected)
    (state / "oauth/public-base-url").write_text(
        "https://original-host.ts.net/quant\n", encoding="utf-8"
    )
    (state / "research/oauth/quant-oauth.sqlite").write_bytes(b"existing-db")
    result = _invoke(launcher)
    assert result.returncode == 78
    assert protected.read_text(encoding="utf-8") == "original-approved-secret"
