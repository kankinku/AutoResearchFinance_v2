"""Issuer-sourced dividends are spot checks, not historical PIT certificates."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine import issuer_distributions as issuer
from research.indicator_engine.issuer_distributions import (
    compare_issuer_qqq_cash_to_price_adjustments,
)


def _pair():
    # Two historical official issuer cash ex-dates, with one preceding trading
    # day for each. Synthetic Tiingo-like factors are generated independently.
    source = MarketSourceProvenance(
        source_id="tiingo",
        retrieved_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        revision_policy="latest",
        universe_policy="single_symbol",
        corporate_action_policy="raw",
        corporate_action_reference=None,
        includes_delisted=False,
    )
    amounts = {
        "2025-03-21": 0.0, "2025-03-24": .71571,
        "2025-06-20": 0.0, "2025-06-23": .59111,
    }
    factor = .97
    raw = []
    adjusted = []
    for d, cash in amounts.items():
        if cash:
            factor *= 1 + cash / 100.0
        stamp = datetime.fromisoformat(d + "T00:00:00+00:00")
        raw.append(Bar(stamp, "QQQ", 100., 101., 99., 100., 1000.))
        adjusted.append(Bar(stamp, "QQQ", 100*factor, 101*factor, 99*factor,
                            100*factor, 1000.))
    original = MarketDataSet("unit", DataZone.DEVELOPMENT, tuple(raw), provenance=source)
    adjusted_set = MarketDataSet(
        "unit", DataZone.DEVELOPMENT, tuple(adjusted),
        provenance=replace(source, corporate_action_policy="total_return_adjusted",
                           corporate_action_reference="https://www.tiingo.com/documentation/end-of-day"),
    )
    return original, adjusted_set


def test_selected_issuer_cash_events_exact_and_non_pit():
    raw, adj = _pair()
    r = compare_issuer_qqq_cash_to_price_adjustments(raw, adj)
    assert r.status == "PARTIAL_ISSUER_DISTRIBUTIONS_MATCH"
    assert r.checked_events == r.matched_events == 2
    assert [day for day, _ in r.implied_cash_events] == ["2025-03-24", "2025-06-23"]
    assert [amount for _, amount in r.implied_cash_events] == pytest.approx([.71571, .59111])
    assert r.distribution_coverage == "SELECTED_CHECKPOINTS_ONLY"
    assert not r.point_in_time_price_verified
    assert not r.all_corporate_actions_verified
    assert not r.broker_executable
    assert compare_issuer_qqq_cash_to_price_adjustments(raw, adj) == r


def test_false_factor_and_missing_dividend_day_report_mismatch():
    raw, adj = _pair()
    altered = list(adj.bars)
    changed = altered[1]
    altered[1] = replace(changed, open=changed.open*1.03, high=changed.high*1.03,
                          low=changed.low*1.03, close=changed.close*1.03)
    tampered = replace(adj, bars=tuple(altered))
    result = compare_issuer_qqq_cash_to_price_adjustments(raw, tampered)
    assert result.status == "ISSUER_DISTRIBUTION_MISMATCH"
    assert "2025-03-24" in result.amount_mismatches
    assert result.matched_events == 1

    missing = (raw.bars[0], *raw.bars[2:])
    missing_adj = (adj.bars[0], *adj.bars[2:])
    absent = compare_issuer_qqq_cash_to_price_adjustments(
        replace(raw, bars=tuple(missing)), replace(adj, bars=tuple(missing_adj))
    )
    assert absent.status == "ISSUER_DISTRIBUTION_MISMATCH"
    assert absent.missing_events == ("2025-03-24",)


def test_ineligible_cross_vendor_or_missing_reference_cannot_be_certified():
    raw, adj = _pair()
    p = replace(adj.provenance, source_id="other_vendor")
    changed_vendor = compare_issuer_qqq_cash_to_price_adjustments(
        raw, replace(adj, provenance=p)
    )
    assert changed_vendor.status == "NOT_COMPARABLE"
    other = replace(raw, bars=tuple(replace(x, symbol="SPY") for x in raw.bars))
    assert compare_issuer_qqq_cash_to_price_adjustments(other, adj).status == "NOT_COMPARABLE"
    assert compare_issuer_qqq_cash_to_price_adjustments(raw, raw).status == "NOT_COMPARABLE"
    assert compare_issuer_qqq_cash_to_price_adjustments(
        replace(raw, bars=raw.bars[:2]), replace(adj, bars=adj.bars[:2])
    ).checked_events == 1


def test_issuer_source_tamper_fails_closed(tmp_path: Path, monkeypatch):
    raw, adj = _pair()
    bogus = tmp_path / "bogus.json"
    bogus.write_text('{"schema":"issuer_qqq_distributions_v1"}')
    monkeypatch.setattr(issuer, "_REFERENCE", bogus)
    with pytest.raises(ValueError, match="integrity mismatch"):
        compare_issuer_qqq_cash_to_price_adjustments(raw, adj)
