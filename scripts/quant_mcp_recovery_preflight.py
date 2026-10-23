"""Read-only Quant MCP recovery diagnostic: refuse OAuth re-bootstrap.

No secrets are printed, created, restored or modified. The diagnostic checks
the *active* Supervisor and nginx wiring against the chosen worktree, not
whether the deployment templates merely exist in Git.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sqlite3
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _valid_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.endswith(".ts.net")
        and parsed.path == "/quant"
        and parsed.port is None
        and parsed.query == ""
        and parsed.fragment == ""
        and parsed.username is None
        and parsed.password is None
        and value == f"https://{parsed.hostname}/quant"
    )


def _include_paths(text: str) -> list[Path]:
    match = re.search(r"(?m)^\s*files\s*=\s*([^\n#]+)", text)
    if match is None:
        return []
    return [Path(piece) for piece in match.group(1).split()]


def check_recovery(
    project_root: Path,
    *,
    supervisor_text: str,
    nginx_text: str,
    listener_ready: bool,
) -> dict[str, Any]:
    """Evaluate persisted identity and live routing without changing anything."""
    root = project_root.resolve()
    problems: list[str] = []
    sources = _include_paths(supervisor_text)
    if not sources:
        problems.append("SUPERVISOR_INCLUDE_MISSING")
    included = False
    for path in sources:
        if not path.is_file():
            problems.append("SUPERVISOR_INCLUDE_MISSING")
            continue
        content = path.read_text(encoding="utf-8")
        if "[program:quant-mcp]" not in content:
            continue
        included = True
        command_match = re.search(r"(?m)^\s*command\s*=\s*/bin/bash\s+(\S+)", content)
        directory_match = re.search(r"(?m)^\s*directory\s*=\s*(\S+)", content)
        expected_script = root / "scripts/run_quant_moon_http.sh"
        if (
            command_match is None
            or Path(command_match.group(1)).resolve() != expected_script
            or not expected_script.is_file()
        ):
            problems.append("SUPERVISOR_QUANT_COMMAND_STALE")
        if directory_match is None or Path(directory_match.group(1)).resolve() != root:
            problems.append("SUPERVISOR_QUANT_DIRECTORY_STALE")
    if not included:
        problems.append("SUPERVISOR_QUANT_PROGRAM_MISSING")
    if (
        "location = /quant/mcp" not in nginx_text
        or "proxy_pass http://127.0.0.1:8787/mcp/" not in nginx_text
    ):
        problems.append("NGINX_QUANT_MCP_ROUTE_MISSING")
    if listener_ready is not True:
        problems.append("MCP_LISTENER_DOWN")

    state = root / "state/moon-http"
    key = state / "oauth/approval-key"
    pin = state / "oauth/public-base-url"
    db_file = state / "research/oauth/quant-oauth.sqlite"
    if key.is_symlink() or not key.is_file() or not key.stat().st_size:
        problems.append("OAUTH_APPROVAL_KEY_MISSING")
    if pin.is_symlink() or not pin.is_file() or not pin.stat().st_size:
        problems.append("OAUTH_PUBLIC_URL_PIN_MISSING")
    else:
        try:
            if not _valid_url(pin.read_text(encoding="utf-8").strip()):
                problems.append("OAUTH_PUBLIC_URL_PIN_INVALID")
        except (OSError, ValueError, UnicodeError):
            problems.append("OAUTH_PUBLIC_URL_PIN_INVALID")
    if db_file.is_symlink() or not db_file.is_file() or not db_file.stat().st_size:
        problems.append("OAUTH_DATABASE_MISSING")
    else:
        try:
            with sqlite3.connect(db_file.resolve().as_uri() + "?mode=ro", uri=True) as db:
                integrity = db.execute("PRAGMA integrity_check").fetchone()
                clients = db.execute("SELECT count(*) FROM clients").fetchone()
                if integrity is None or integrity[0] != "ok" or clients is None or clients[0] < 1:
                    problems.append("OAUTH_DATABASE_INVALID")
        except (sqlite3.Error, OSError):
            problems.append("OAUTH_DATABASE_INVALID")
    blockers = sorted(set(problems))
    return {
        "status": "BLOCKED_PRESERVE_OAUTH" if blockers else "PRECHECK_PASS_NOT_AUTHENTICATED",
        "blockers": blockers,
        "credentials_rotated": False,
        "authentication_reset_performed": False,
        "authenticated_mcp_verified": False,
        "server_restarted": False,
        "orders_enabled_by_preflight": False,
    }


def _read_live_nginx() -> str:
    try:
        result = subprocess.run(
            ["/usr/sbin/nginx", "-T"],
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _loopback_listener() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8787), timeout=0.7):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only existing Quant MCP OAuth and routing preflight"
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--active-supervisor",
        type=Path,
        default=Path("/etc/supervisor/conf.d/workmachine.conf"),
    )
    args = parser.parse_args()
    try:
        supervisor = args.active_supervisor.read_text(encoding="utf-8")
    except OSError:
        supervisor = ""
    result = check_recovery(
        args.root,
        supervisor_text=supervisor,
        nginx_text=_read_live_nginx(),
        listener_ready=_loopback_listener(),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PRECHECK_PASS_NOT_AUTHENTICATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
