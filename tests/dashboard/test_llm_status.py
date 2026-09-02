from __future__ import annotations

import json
from pathlib import Path

from dashboard.service import DashboardService
from dashboard.state import DashboardStateReader


def test_dashboard_reads_codex_status_without_prompt_or_credentials(tmp_path: Path) -> None:
    path = tmp_path / "llm"
    path.mkdir()
    (path / "status.json").write_text(
        json.dumps(
            {
                "provider": "codex_exec",
                "status": "ONLINE",
                "last_result": "VALIDATED",
                "last_call_at": "2026-09-01T12:00:00+00:00",
                "prompt": "do not expose",
                "OPENAI_API_KEY": "placeholder",
            }
        ),
        encoding="utf-8",
    )

    snapshot = DashboardStateReader(tmp_path).read()

    assert snapshot.llm.provider == "codex_exec"
    assert snapshot.llm.status == "ONLINE"
    assert snapshot.llm.last_result == "VALIDATED"
    assert not hasattr(snapshot.llm, "prompt")


def test_dashboard_service_refreshes_llm_status_beyond_cached_snapshot(tmp_path: Path) -> None:
    service = DashboardService(tmp_path)
    service.refresh()
    llm_path = tmp_path / "llm" / "status.json"
    llm_path.parent.mkdir(exist_ok=True)
    llm_path.write_text(
        json.dumps(
            {
                "provider": "codex_desktop",
                "status": "ONLINE",
                "last_result": "MCP_CONNECTED",
            }
        ),
        encoding="utf-8",
    )

    assert service.snapshot().llm.last_result == "MCP_CONNECTED"
