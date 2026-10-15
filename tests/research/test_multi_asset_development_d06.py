"""D06 cross-symbol sessions, as-of cutoffs, immutable StrategyIR comparisons."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.data.contracts import DataZone, MarketDataSet
from research.indicator_engine.algorithm_plan import compile_algorithm_plan
from research.indicator_engine.multi_asset_development import (
    MultiAssetResearchError,
    align_parallel_market,
    compile_parallel_plan,
    evaluate_parallel_plan,
)
from tests.research.test_academic_algorithm_plan import _catalog, _market, _plan


def _market_pair(*, n: int = 650, late_spy: bool = True) -> MarketDataSet:
    """Two synthetic ETF histories, US exchange session closes, NOT PIT quotes."""
    base = _market().bars[:n]
    ny = ZoneInfo("America/New_York")
    start = date(2020, 1, 2)
    sessions: list[date] = []
    day = start
    while len(sessions) < n:
        if day.weekday() < 5:
            sessions.append(day)
        day += timedelta(days=1)
    qqq = []
    spy = []
    for session, sample in zip(sessions, base, strict=True):
        close = datetime.combine(session, datetime.min.time(), tzinfo=ny).replace(hour=16)
        later = close + timedelta(minutes=3 if late_spy else 0)
        qqq.append(replace(sample, timestamp=close, symbol="QQQ"))
        spy.append(replace(
            sample, timestamp=later, symbol="SPY",
            open=sample.open * 0.8, high=sample.high * 0.8,
            low=sample.low * 0.8, close=sample.close * 0.8,
        ))
    return MarketDataSet(
        "synthetic_qqq_spy_d06", DataZone.DEVELOPMENT, (*qqq, *spy),
    )


def test_pair_aligns_same_nyse_sessions_without_forward_fill() -> None:
    market = _market_pair()
    a = align_parallel_market(market, symbols=("SPY", "QQQ"))
    assert a.symbols == ("QQQ", "SPY")
    assert len(a.session_dates) == 650
    assert a.input_dataset_hash == market.dataset_hash
    assert len(a.symbol_datasets) == 2
    assert a.symbol_datasets[0][1].bars[0].symbol == "QQQ"
    assert a.symbol_datasets[1][1].bars[0].symbol == "SPY"
    assert a.decision_known_at_utc[0] == market.bars[650].timestamp.astimezone(timezone.utc)
    assert a.execution_next_open_at_utc[0] is not None
    assert a.decision_known_at_utc[0] < a.execution_next_open_at_utc[0]
    assert a.execution_next_open_at_utc[-1] is None
    assert a.sealed_oos_approved is False
    assert a.broker_executable is False
    assert a == align_parallel_market(market, symbols=("QQQ", "SPY"))


def test_parallel_verified_plan_runs_per_symbol_strategy_ir(tmp_path: Path) -> None:
    market = _market_pair()
    catalog, plan = _catalog(tmp_path), _plan()
    compiled = compile_parallel_plan(catalog, plan, market)
    assert compiled.alignment.symbols == ("QQQ", "SPY")
    assert compiled.plan_hash == compiled.compiled_by_symbol[0][1].plan_hash
    assert compiled.compiled_by_symbol[0][1].compiled.strategy.family == "academic_algorithm_plan"
    report = evaluate_parallel_plan(catalog, compiled, market)
    assert report.status == "MULTI_ASSET_DEVELOPMENT_COMPARISON_ONLY"
    assert report.study_dataset_hash == market.dataset_hash
    assert len(report.symbol_results) == 2
    assert all(x.trades_count >= 0 and x.strategy_hash for x in report.symbol_results)
    assert all(x.initial_cash == 10_000 for x in report.symbol_results)
    assert report.portfolio_pnl_approved is False
    assert report.broker_executable is False
    assert report == evaluate_parallel_plan(catalog, compiled, market)
    per_qqq = MarketDataSet(
        market.version + ":QQQ", market.zone, market.bars[:650]
    )
    checked = compile_algorithm_plan(catalog, plan, per_qqq)
    assert (checked.compiled.strategy_hash ==
            compiled.compiled_by_symbol[0][1].compiled.strategy_hash)


def test_missing_asset_session_rejected_without_lookahead(tmp_path: Path) -> None:
    market = _market_pair()
    absent = tuple(b for i, b in enumerate(market.bars) if i != 650 + 240)
    damaged = replace(market, bars=absent)
    with pytest.raises(MultiAssetResearchError, match="missing|session|alignment"):
        align_parallel_market(damaged)
    with pytest.raises(MultiAssetResearchError, match="missing|session|alignment"):
        compile_parallel_plan(_catalog(tmp_path), _plan(), damaged)


def test_duplicate_local_session_disallowed() -> None:
    market = _market_pair(n=40)
    repeated = replace(
        market.bars[40], timestamp=market.bars[40].timestamp + timedelta(minutes=10),
    )
    altered = replace(market, bars=tuple(sorted(
        (*market.bars, repeated), key=lambda x: (x.symbol, x.timestamp),
    )))
    with pytest.raises(MultiAssetResearchError, match="duplicate|session"):
        align_parallel_market(altered)


def test_session_cutoff_denies_preclose_and_overnight_data() -> None:
    market = _market_pair(n=40)
    early = replace(market.bars[0], timestamp=market.bars[0].timestamp - timedelta(hours=4))
    bad = replace(market, bars=tuple(sorted(
        (early, *market.bars[1:]), key=lambda b: (b.symbol, b.timestamp),
    )))
    with pytest.raises(MultiAssetResearchError, match="close|completion"):
        align_parallel_market(bad)


def test_only_development_and_two_to_eight_us_daily_symbols() -> None:
    market = _market_pair(n=40)
    for bad in (
        replace(market, zone=DataZone.SEALED_OOS),
        replace(market, zone=DataZone.VALIDATION),
        replace(market, timeframe="1h"),
        replace(market, calendar="continuous"),
        replace(market, bars=market.bars[:40]),
    ):
        with pytest.raises(MultiAssetResearchError):
            align_parallel_market(bad)
    with pytest.raises(MultiAssetResearchError, match="symbols"):
        align_parallel_market(market, symbols=("QQQ", "IWM"))


def test_pair_input_tamper_after_compile_fails_closed(tmp_path: Path) -> None:
    market = _market_pair()
    catalog = _catalog(tmp_path)
    compiled = compile_parallel_plan(catalog, _plan(), market)
    altered = list(market.bars)
    altered[450] = replace(altered[450], close=altered[450].close * 1.01)
    # keep OHLC bound legal by increasing high if needed
    altered[450] = replace(
        altered[450], high=max(altered[450].high, altered[450].close),
    )
    with pytest.raises(MultiAssetResearchError, match="hash|identity|changed"):
        evaluate_parallel_plan(catalog, compiled, replace(market, bars=tuple(altered)))
    with pytest.raises(MultiAssetResearchError, match="alignment|hash"):
        evaluate_parallel_plan(catalog, replace(
            compiled, alignment=replace(compiled.alignment, alignment_hash="0" * 64),
        ), market)


def test_independent_per_symbol_causal_features_are_immutable(tmp_path: Path) -> None:
    market = _market_pair()
    catalog = _catalog(tmp_path)
    original = compile_parallel_plan(catalog, _plan(), market)
    updated = list(market.bars)
    last = updated[-1]
    updated[-1] = replace(last, close=last.close * 1.03,
                          high=max(last.high, last.close * 1.03))
    adjusted = compile_parallel_plan(catalog, _plan(), replace(market, bars=tuple(updated)))
    old_qqq = original.compiled_by_symbol[0][1].compiled.feature_values
    new_qqq = adjusted.compiled_by_symbol[0][1].compiled.feature_values
    assert old_qqq == new_qqq
    for key, before in original.compiled_by_symbol[1][1].compiled.feature_values.items():
        after = adjusted.compiled_by_symbol[1][1].compiled.feature_values[key]
        assert before[:-1] == after[:-1]


def test_no_fabricated_nyse_history_or_results_from_metadata_only() -> None:
    # No synthetic prices may be generated by production coordinator.
    with pytest.raises((TypeError, MultiAssetResearchError, ValueError)):
        align_parallel_market(None)  # type: ignore[arg-type]


def test_cli_offline_multi_symbol_research_and_sealed_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json
    import sys

    from core.data.parquet import ParquetDataProvider
    from research.indicator_engine.cli import main

    catalog = _catalog(tmp_path)
    market = _market_pair()
    file = tmp_path / "market.parquet"
    plan_file = tmp_path / "plan.json"
    ParquetDataProvider.write(file, market)
    plan_file.write_text(_plan().model_dump_json(), encoding="utf-8")
    base = [
        "indicator-research", "--database", str(catalog.database),
        "preview-parallel-algorithm", "--market-parquet", str(file),
        "--plan-json-file", str(plan_file),
    ]
    monkeypatch.setattr(sys, "argv", base)
    assert main() == 0
    reply = json.loads(capsys.readouterr().out)
    assert reply["status"] == "MULTI_ASSET_DEVELOPMENT_COMPARISON_ONLY"
    assert reply["portfolio_pnl_approved"] is False
    assert reply["broker_executable"] is False
    assert len(reply["result"]["symbol_results"]) == 2

    ParquetDataProvider.write(file, replace(market, zone=DataZone.SEALED_OOS))
    assert main() == 2
    denied = json.loads(capsys.readouterr().out)
    assert denied["status"] == "PARALLEL_RESEARCH_REJECTED"
    assert denied["orders_enabled"] is False
