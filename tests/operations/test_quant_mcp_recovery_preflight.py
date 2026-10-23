"""Existing-identity recovery must refuse bootstrapping new Quant OAuth."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.quant_mcp_recovery_preflight import check_recovery


def _setup(tmp_path: Path):
    root = tmp_path / "project"
    runner = root / "scripts/run_quant_moon_http.sh"
    runner.parent.mkdir(parents=True)
    runner.write_text("# existing service", encoding="utf-8")
    source = root / "deployment/moon/quant-mcp.supervisor.conf"
    source.parent.mkdir(parents=True)
    source.write_text(
        f"[program:quant-mcp]\ncommand=/bin/bash {runner}\ndirectory={root}\n", encoding="utf-8"
    )
    supervisor = f"[include]\nfiles={source}\n"
    nginx = "location = /quant/mcp { proxy_pass http://127.0.0.1:8787/mcp/; }"
    state = root / "state/moon-http"
    (state / "oauth").mkdir(parents=True)
    (state / "research/oauth").mkdir(parents=True)
    key = state / "oauth/approval-key"
    pin = state / "oauth/public-base-url"
    key.write_text("example-existing-secret")
    pin.write_text("https://existing-host.ts.net/quant\n")
    key.chmod(0o600)
    pin.chmod(0o600)
    db = state / "research/oauth/quant-oauth.sqlite"
    with sqlite3.connect(db) as handle:
        handle.execute("CREATE TABLE clients (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        handle.execute(
            "CREATE TABLE grants (digest TEXT PRIMARY KEY, kind TEXT NOT NULL, "
            "client_id TEXT NOT NULL, payload TEXT NOT NULL, expires REAL NOT NULL)"
        )
        handle.execute("INSERT INTO clients VALUES ('existing','{}')")
    return root, supervisor, nginx


def test_good_existing_identity_does_not_mutate_files(tmp_path: Path):
    root, supervisor, nginx = _setup(tmp_path)
    key = root / "state/moon-http/oauth/approval-key"
    before = key.read_bytes()
    outcome = check_recovery(
        root, supervisor_text=supervisor, nginx_text=nginx, listener_ready=True
    )
    assert outcome["status"] == "PRECHECK_PASS_NOT_AUTHENTICATED"
    assert outcome["blockers"] == []
    assert outcome["credentials_rotated"] is False
    assert key.read_bytes() == before


def test_missing_credentials_remain_missing(tmp_path: Path):
    root, supervisor, nginx = _setup(tmp_path)
    state = root / "state/moon-http"
    (state / "oauth/approval-key").unlink()
    (state / "oauth/public-base-url").unlink()
    (state / "research/oauth/quant-oauth.sqlite").unlink()
    outcome = check_recovery(
        root, supervisor_text=supervisor, nginx_text=nginx, listener_ready=False
    )
    assert outcome["status"] == "BLOCKED_PRESERVE_OAUTH"
    assert "OAUTH_APPROVAL_KEY_MISSING" in outcome["blockers"]
    assert "OAUTH_PUBLIC_URL_PIN_MISSING" in outcome["blockers"]
    assert "OAUTH_DATABASE_MISSING" in outcome["blockers"]
    assert "MCP_LISTENER_DOWN" in outcome["blockers"]
    assert not (state / "oauth/approval-key").exists()
    assert not (state / "research/oauth/quant-oauth.sqlite").exists()


def test_stale_runtime_paths_and_absent_nginx_route_fail_closed(tmp_path: Path):
    root, supervisor, nginx = _setup(tmp_path)
    stale = tmp_path / "old-missing-repo"
    old_service = root / "deployment/moon/quant-mcp.supervisor.conf"
    old_service.write_text(
        "[program:quant-mcp]\n"
        f"command=/bin/bash {stale}/scripts/run_quant_moon_http.sh\n"
        f"directory={stale}\n"
    )
    result = check_recovery(
        root,
        supervisor_text=supervisor,
        nginx_text="location = /mcp { proxy_pass http://127.0.0.1:3000; }",
        listener_ready=False,
    )
    assert "SUPERVISOR_QUANT_COMMAND_STALE" in result["blockers"]
    assert "SUPERVISOR_QUANT_DIRECTORY_STALE" in result["blockers"]
    assert "NGINX_QUANT_MCP_ROUTE_MISSING" in result["blockers"]
    assert result["status"] == "BLOCKED_PRESERVE_OAUTH"


def test_missing_supervisor_include_does_not_create_config(tmp_path: Path):
    root, _, nginx = _setup(tmp_path)
    missing = tmp_path / "missing.conf"
    result = check_recovery(
        root,
        supervisor_text=f"[include]\nfiles={missing}\n",
        nginx_text=nginx,
        listener_ready=True,
    )
    assert "SUPERVISOR_INCLUDE_MISSING" in result["blockers"]
    assert not missing.exists()


def test_broken_sqlite_existing_auth_fails_closed(tmp_path: Path):
    root, supervisor, nginx = _setup(tmp_path)
    db = root / "state/moon-http/research/oauth/quant-oauth.sqlite"
    db.write_text("not a sqlite database")
    result = check_recovery(root, supervisor_text=supervisor, nginx_text=nginx, listener_ready=True)
    assert "OAUTH_DATABASE_INVALID" in result["blockers"]


def test_current_supervisor_dashboard_only_is_not_false_positive(tmp_path: Path):
    root, _, nginx = _setup(tmp_path)
    included = root / "deployment/moon/quant-mcp.supervisor.conf"
    included.write_text(
        "# original OAuth absent; dashboard-only intentional\n"
        "[program:fresh-quant-dashboard]\ncommand=/bin/echo safe\n"
    )
    result = check_recovery(
        root,
        supervisor_text=f"[include]\nfiles={included}\n",
        nginx_text=nginx,
        listener_ready=False,
    )
    assert "SUPERVISOR_QUANT_PROGRAM_MISSING" in result["blockers"]


def test_checked_in_restore_template_points_to_existing_runner():
    root = Path(__file__).resolve().parents[2]
    template = (root / "deployment/moon/quant-mcp.supervisor.conf").read_text()
    runner = root / "scripts/run_quant_moon_http.sh"
    assert f"command=/bin/bash {runner}" in template
    assert f"directory={root}" in template
    assert runner.is_file()
    assert "user-explicitly-provisioned NEW identity" in template
    assert "Never generate credentials from a supervisor startup" in template


def test_direct_script_and_module_entrypoints_remain_compatible(tmp_path: Path):
    import json
    import subprocess
    import sys

    root, supervisor, _ = _setup(tmp_path)
    # Make the CLI test independent of a currently running host service.
    # A missing approval key must fail closed even when 8787 is listening.
    (root / "state/moon-http/oauth/approval-key").unlink()
    config = tmp_path / "supervisor.conf"
    config.write_text(supervisor)
    project = Path(__file__).resolve().parents[2]
    script = project / "scripts/quant_mcp_recovery_preflight.py"
    for args in (
        [sys.executable, str(script)],
        [sys.executable, "-m", "scripts.quant_mcp_recovery_preflight"],
    ):
        completed = subprocess.run(
            args + ["--root", str(root), "--active-supervisor", str(config)],
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        assert completed.returncode == 2
        report = json.loads(completed.stdout)
        assert report["status"] == "BLOCKED_PRESERVE_OAUTH"
        assert report["authenticated_mcp_verified"] is False
        assert "OAUTH_APPROVAL_KEY_MISSING" in report["blockers"]
        assert "Traceback" not in completed.stderr
