"""Full historical issuer-cash schedule is separate from PIT verification."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine import issuer_distribution_reference_v2 as reference
from research.indicator_engine.issuer_distribution_reference_v2 import (
    verify_qqq_issuer_distribution_reference_v2,
)


def _pair(days, amounts):
    provenance = MarketSourceProvenance(
        source_id="tiingo", retrieved_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        revision_policy="latest", universe_policy="single_symbol",
        corporate_action_policy="raw", corporate_action_reference=None,
        includes_delisted=False,
    )
    original = []
    adjusted = []
    factor = .9
    for d, amount in zip(days, amounts, strict=True):
        day = datetime.fromisoformat(d + "T00:00:00+00:00")
        factor *= 1 + amount / 100
        original.append(Bar(day, "QQQ", 100, 101, 99, 100, 1000))
        adjusted.append(Bar(day, "QQQ", 100*factor, 101*factor, 99*factor, 100*factor, 1000))
    return (
        MarketDataSet("v2", DataZone.DEVELOPMENT, tuple(original), provenance=provenance),
        MarketDataSet(
            "v2", DataZone.DEVELOPMENT, tuple(adjusted),
            provenance=replace(provenance, corporate_action_policy="total_return_adjusted"),
        ),
    )


def test_full_reference_has_25_issuer_rows_including_special_and_last_2025():
    rows = reference.load_qqq_issuer_reference_v2()
    assert len(rows) == 25
    assert rows["2023-12-27"]["kind"] == "SPECIAL_CASH"
    assert rows["2023-12-27"]["cash_usd_per_share"] == .21584
    assert rows["2025-09-22"]["cash_usd_per_share"] == .69395
    assert rows["2025-12-22"]["cash_usd_per_share"] == .79408


def test_special_dividend_is_classified_and_issuer_matched_not_pit():
    raw, adj = _pair(
        ["2023-12-26", "2023-12-27", "2023-12-28"], [0, .21584, 0]
    )
    result = verify_qqq_issuer_distribution_reference_v2(raw, adj)
    assert result.status == "MATCHED_REFERENCE_CASH_EVENTS"
    assert result.reference_events_in_window == result.matched_events == 1
    assert result.unreferenced_candidate_events == 0
    assert result.matched_special_cash_events == 1
    assert result.full_reference_window_covered is False
    assert result.point_in_time_price_verified is False
    assert result.all_corporate_actions_verified is False
    assert result.broker_executable is False


def test_unlisted_factor_jump_and_incorrect_cash_fail_closed():
    raw, adj = _pair(
        ["2025-03-21", "2025-03-24", "2025-03-25"], [0, .71571, .12]
    )
    good = verify_qqq_issuer_distribution_reference_v2(raw, adj)
    assert good.status == "UNREFERENCED_ADJUSTMENT_EVENTS"
    assert good.matched_events == 1
    assert good.unreferenced_candidate_events == 1
    assert good.unreferenced_candidate_dates == ("2025-03-25",)
    corrupted = list(adj.bars)
    corrupted[1] = replace(
        corrupted[1], open=corrupted[1].open*1.02,
        high=corrupted[1].high*1.02, low=corrupted[1].low*1.02,
        close=corrupted[1].close*1.02,
    )
    report = verify_qqq_issuer_distribution_reference_v2(
        raw, replace(adj, bars=tuple(corrupted))
    )
    assert report.status == "ISSUER_CASH_AMOUNT_MISMATCH"


def test_expected_issuer_event_missing_from_observations_and_cross_vendor_denial():
    raw, adj = _pair(
        ["2025-03-21", "2025-03-25"], [0, 0]
    )
    report = verify_qqq_issuer_distribution_reference_v2(raw, adj)
    assert report.status == "ISSUER_REFERENCE_DATE_MISSING"
    assert report.missing_reference_dates == ("2025-03-24",)
    assert verify_qqq_issuer_distribution_reference_v2(
        raw, replace(adj, provenance=replace(adj.provenance, source_id="another"))
    ).status == "NOT_COMPARABLE"


def test_v2_reference_corruption_stops_verification(tmp_path: Path, monkeypatch):
    raw, adj = _pair(
        ["2023-12-26", "2023-12-27"], [0, .21584]
    )
    fake = tmp_path / "reference.json"
    fake.write_text("{}")
    monkeypatch.setattr(reference, "_REFERENCE", fake)
    with pytest.raises(ValueError, match="integrity"):
        verify_qqq_issuer_distribution_reference_v2(raw, adj)
