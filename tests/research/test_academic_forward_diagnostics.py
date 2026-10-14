"""Trade replay and missed-market exposure are independently reconciled."""

from datetime import datetime, timedelta, timezone
from math import log

import pytest

from core.backtest.engine import Trade
from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.forward_diagnostics import diagnose_forward_exposure


def _fixture(zone=DataZone.DEVELOPMENT):
    first = datetime(2023, 1, 2, tzinfo=timezone.utc)
    prices = (100.0, 110.0, 100.0, 120.0, 140.0, 130.0)
    return MarketDataSet("diagnostic", zone, tuple(
        Bar(first + timedelta(days=i), "QQQ", close, close + 1,
            close - 1, close, 1000) for i, close in enumerate(prices)
    ))


def test_cash_only_days_track_passive_returns_and_no_fictitious_alpha():
    report = diagnose_forward_exposure(_fixture(), (), start_index=0, end_index=6)
    assert report.exposed_sessions == 0
    assert report.cash_only_sessions == 6
    assert report.total_execution_cost == 0
    assert report.flat_market_log_return == pytest.approx(log(130/100))
    assert not report.candidate_promotable
    assert not report.point_in_time_verified


def test_replay_open_trades_counts_cash_days_and_costs():
    market = _fixture()
    transactions = (
        Trade(market.bars[1].timestamp.isoformat(), "buy", 110, 20, 2200, 1.50, "QQQ"),
        Trade(market.bars[4].timestamp.isoformat(), "sell", 140, 20, 2800, 1.80, "QQQ"),
    )
    report = diagnose_forward_exposure(market, transactions, start_index=0, end_index=6)
    assert report.exposed_sessions == 3
    assert report.cash_only_sessions == 3
    assert report.total_execution_cost == pytest.approx(3.3)
    assert report.flat_market_log_return == pytest.approx(log(130/120))
    assert report.exposed_market_log_return == pytest.approx(log(120/100))
    assert report.entry_count == report.exit_count == 1
    assert report.report_hash == diagnose_forward_exposure(
        market, transactions, start_index=0, end_index=6
    ).report_hash


def test_rejects_out_of_scope_and_impossible_or_tampered_ledger():
    market = _fixture()
    with pytest.raises(ResearchCatalogError, match="development"):
        diagnose_forward_exposure(_fixture(DataZone.SEALED_OOS), (),
                                 start_index=0, end_index=6)
    with pytest.raises(ResearchCatalogError, match="window"):
        diagnose_forward_exposure(market, (), start_index=1, end_index=7)
    with pytest.raises(ResearchCatalogError, match="sell"):
        diagnose_forward_exposure(market, (
            Trade(market.bars[0].timestamp.isoformat(), "sell", 100, 1, 100, 0.1, "QQQ"),
        ), start_index=0, end_index=6)
    with pytest.raises(ResearchCatalogError, match="timestamp"):
        diagnose_forward_exposure(market, (
            Trade("2022-12-20T00:00:00+00:00", "buy", 100, 1, 100, 0.1, "QQQ"),
        ), start_index=0, end_index=6)


def test_buy_and_hold_is_all_exposed_and_flat_return_zero():
    market = _fixture()
    tx = (Trade(market.bars[0].timestamp.isoformat(), "buy", 100, 10, 1000, 0.8, "QQQ"),)
    report = diagnose_forward_exposure(market, tx, start_index=0, end_index=6)
    assert report.exposed_sessions == 6
    assert report.cash_only_sessions == 0
    assert report.flat_market_log_return == 0
    assert report.exposed_market_log_return == pytest.approx(log(130/100))
