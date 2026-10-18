"""Live Moon dashboard must have an immutable, localhost-only auto-start launcher."""

import re
import subprocess
from pathlib import Path


def test_academic_monitor_launch_is_pinned_and_supervised() -> None:
    root = Path(__file__).resolve().parents[2]
    runner = (root / "scripts/run_quant_academic_monitor.sh").read_text()
    supervisor = (root / "deployment/moon/quant-mcp.supervisor.conf").read_text()
    assert "[program:quant-academic-monitor]" in supervisor
    assert "autostart=true" in supervisor
    assert "autorestart=true" in supervisor
    assert "/scripts/run_quant_academic_monitor.sh" in supervisor
    assert re.search(r"^EXPECTED_SHA=[a-f0-9]{40}$", runner, re.MULTILINE)
    assert "git -C \"$SOURCE_ROOT\" rev-parse HEAD" in runner
    assert "git -C \"$SOURCE_ROOT\" status --porcelain" in runner
    assert "--checkpoint-dir \"$CHECKPOINT_DIR\" --host 127.0.0.1 --port 8085" in runner


def test_running_dashboard_pin_resolves_to_clean_source() -> None:
    root = Path(__file__).resolve().parents[2]
    runner = (root / "scripts/run_quant_academic_monitor.sh").read_text()
    source = re.search(r'^SOURCE_ROOT=(/[^\n]+)$', runner, re.MULTILINE)
    pin = re.search(r'^EXPECTED_SHA=([a-f0-9]{40})$', runner, re.MULTILINE)
    assert source is not None and pin is not None
    source_root = Path(source.group(1))
    assert (source_root / "dashboard/academic_run.py").is_file()
    actual_sha = subprocess.check_output(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True
    ).strip()
    assert actual_sha == pin.group(1), "supervised runner points at a stale source SHA"
    assert not subprocess.check_output(
        ["git", "-C", str(source_root), "status", "--porcelain"], text=True
    ).strip()
