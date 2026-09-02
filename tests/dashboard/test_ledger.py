from __future__ import annotations

import json
from pathlib import Path

from dashboard.ledger import append_funnel_results
from dashboard.state import DashboardStateReader
from evaluation.selector import FunnelResult


def test_ledger_appends_sanitized_funnel_results_for_dashboard(tmp_path: Path) -> None:
    result = FunnelResult(
        "strategy-1",
        "macro",
        "SURVIVOR",
        0.8,
        (),
        full_total_return=0.2,
        full_max_drawdown=0.05,
    )

    append_funnel_results(
        tmp_path / "test-records.jsonl",
        generation=3,
        results=(result,),
        timestamp="2026-09-01T12:00:00+00:00",
    )

    payload = json.loads((tmp_path / "test-records.jsonl").read_text(encoding="utf-8"))
    snapshot = DashboardStateReader(tmp_path).read()
    assert payload["strategy_hash"] == "strategy-1"
    assert payload["total_return"] == 0.2
    assert snapshot.tests[0].run_id == "strategy-1-generation-3"
