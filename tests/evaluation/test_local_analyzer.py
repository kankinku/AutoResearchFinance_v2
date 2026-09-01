from __future__ import annotations

from evaluation.local_analyzer import summarize_results
from evaluation.selector import FunnelResult


def test_local_analyzer_returns_compact_counts_and_evidence_status() -> None:
    summary = summarize_results(
        (
            FunnelResult("a", "trend", "SURVIVOR", 0.8, ()),
            FunnelResult("b", "trend", "REJECT", 0.1, ()),
            FunnelResult("c", "breakout", "NEAR_MISS", 0.4, ()),
        )
    )

    assert summary["tested"] == 3
    assert summary["counts"] == {"NEAR_MISS": 1, "REJECT": 1, "SURVIVOR": 1}
    assert summary["evidence"] == "INSUFFICIENT_EVIDENCE"
    assert summary["champion"]["candidate_hash"] == "a"
