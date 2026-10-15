"""P0 chronological holdout evaluation: past-only indicators, zero training PnL."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.data.contracts import DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine.algorithm_plan import compile_algorithm_plan
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.forward_window import evaluate_chronological_window
from research.indicator_engine.strategy_adapter import evaluate_compiled_development
from tests.research.test_academic_algorithm_plan import _catalog, _market, _plan


def _split():
    all_data = _market()
    return (
        MarketDataSet(all_data.version, all_data.zone, all_data.bars[:450]),
        MarketDataSet(all_data.version, all_data.zone, all_data.bars[450:]),
    )


def test_history_warms_up_but_cannot_trade_or_inflate_forward_result(tmp_path: Path):
    catalog = _catalog(tmp_path)
    history, forward = _split()
    report = evaluate_chronological_window(catalog, _plan(), history, forward)
    assert report.status == "NON_PIT_CHRONOLOGICAL_RESEARCH_ONLY"
    assert report.warmup_bars == 300
    assert report.holdout_bars == 200
    assert report.training_hash == history.dataset_hash
    assert report.holdout_hash == forward.dataset_hash
    assert report.first_holdout_equity == report.initial_cash == 10_000.0
    assert report.final_equity == pytest.approx(10000 * (1 + report.total_return))
    assert report.first_execution_time is None or report.first_execution_time > report.holdout_start
    assert report.paid_costs >= 0
    assert report.point_in_time_independently_verified is False
    assert report.independent_oos_approved is False
    assert report.validation_decision == "NOT_VALIDATED"
    assert type(report.descriptive_gate_met) is bool
    assert report.candidate_promotable is False
    assert report.broker_executable is False
    assert evaluate_chronological_window(catalog, _plan(), history, forward) == report


def test_changing_far_past_price_cannot_add_prestart_profit(tmp_path: Path):
    catalog = _catalog(tmp_path)
    history, forward = _split()
    base = evaluate_chronological_window(catalog, _plan(), history, forward)
    # An event beyond the 300-bar past-only lookback should not affect
    # the concatenated window or the forward portfolio whatsoever.
    altered = list(history.bars)
    old = altered[0]
    altered[0] = replace(old, open=old.open * 1.02, high=old.high * 1.05)
    changed = MarketDataSet(history.version, history.zone, tuple(altered))
    got = evaluate_chronological_window(catalog, _plan(), changed, forward)
    assert got.training_hash != base.training_hash
    assert got.holdout_hash == base.holdout_hash
    assert got.total_return == base.total_return
    assert got.first_holdout_equity == base.first_holdout_equity
    assert got.evaluation_hash != base.evaluation_hash


def test_forward_future_bar_cannot_change_earlier_completed_window(tmp_path: Path):
    catalog = _catalog(tmp_path)
    history, forward = _split()
    shorter = MarketDataSet(forward.version, forward.zone, forward.bars[:120])
    before = evaluate_chronological_window(catalog, _plan(), history, shorter)
    # The first 120 forward bars and training history are unchanged.
    # Suffix bars cannot affect their known-at-the-time fills or equity.
    longer = evaluate_chronological_window(catalog, _plan(), history, forward)
    assert shorter.bars == forward.bars[:120]
    assert before.initial_cash == longer.initial_cash
    assert before.first_holdout_equity == longer.first_holdout_equity
    assert before.holdout_start == longer.holdout_start
    # Independently compile the two causal signal streams and compare every
    # already-known completed bar and every historical forward equity mark.
    prefix = history.bars[-300:]
    early = MarketDataSet("academic-forward-window-v1", DataZone.DEVELOPMENT,
                          (*prefix, *shorter.bars))
    full = MarketDataSet("academic-forward-window-v1", DataZone.DEVELOPMENT,
                         (*prefix, *forward.bars))
    early_plan = compile_algorithm_plan(catalog, _plan(), early)
    full_plan = compile_algorithm_plan(catalog, _plan(), full)
    for key in early_plan.compiled.feature_values:
        assert early_plan.compiled.feature_values[key] == (
            full_plan.compiled.feature_values[key][:len(early.bars)]
        )
    a = evaluate_compiled_development(
        early_plan.compiled, early, signal_start_at=shorter.bars[0].timestamp
    )
    b = evaluate_compiled_development(
        full_plan.compiled, full, signal_start_at=forward.bars[0].timestamp
    )
    assert a.equity_curve == b.equity_curve[:len(a.equity_curve)]
    assert a.trades == tuple(
        fill for fill in b.trades
        if fill.timestamp <= shorter.bars[-1].timestamp.isoformat()
    )


@pytest.mark.parametrize("bad_case", [
    "overlap", "sealed_train", "sealed_forward", "other_symbol", "short_history",
    "missing_history", "missing_forward", "bad_warmup", "bad_cash",
])
def test_reject_invalid_boundary_or_pseudo_oos(tmp_path: Path, bad_case: str):
    catalog = _catalog(tmp_path)
    history, forward = _split()
    kwargs = {}
    if bad_case == "overlap":
        forward = MarketDataSet(forward.version, forward.zone, (*history.bars[-2:], *forward.bars))
    elif bad_case == "sealed_train":
        history = MarketDataSet(history.version, DataZone.SEALED_OOS, history.bars)
    elif bad_case == "sealed_forward":
        forward = MarketDataSet(forward.version, DataZone.SEALED_OOS, forward.bars)
    elif bad_case == "other_symbol":
        forward = MarketDataSet(forward.version, forward.zone, tuple(
            replace(b, symbol="SPY") for b in forward.bars
        ))
    elif bad_case == "short_history":
        history = MarketDataSet(history.version, history.zone, history.bars[-5:])
    elif bad_case == "missing_history":
        history = MarketDataSet(history.version, history.zone, ())
    elif bad_case == "missing_forward":
        forward = MarketDataSet(forward.version, forward.zone, forward.bars[:1])
    elif bad_case == "bad_warmup":
        kwargs["max_warmup_bars"] = 0
    elif bad_case == "bad_cash":
        kwargs["initial_cash"] = -1
    with pytest.raises(ResearchCatalogError):
        evaluate_chronological_window(catalog, _plan(), history, forward, **kwargs)


def test_forward_report_future_data_cannot_be_forged_as_verified(tmp_path: Path):
    catalog = _catalog(tmp_path)
    history, forward = _split()
    result = evaluate_chronological_window(catalog, _plan(), history, forward)
    assert result.independent_oos_approved is False
    assert result.broker_executable is False
    assert result.candidate_promotable is False


def test_boundary_first_bar_cannot_fill_pending_signal_from_history(tmp_path: Path):
    catalog = _catalog(tmp_path)
    history, forward = _split()
    # A high momentum signal at the history end must not place a buy on
    # the first forward opening bar: the first permissible *decision*
    # occurs at the first forward completed close.
    result = evaluate_chronological_window(catalog, _plan(), history, forward)
    first_close = forward.bars[0].timestamp.isoformat()
    assert result.first_execution_time is None or result.first_execution_time > first_close



def test_reject_mixed_price_adjustments_and_mixed_lineage(tmp_path: Path):
    catalog = _catalog(tmp_path)
    history, forward = _split()
    source = MarketSourceProvenance(
        source_id="research_fixture", retrieved_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        revision_policy="latest", universe_policy="single_symbol",
        corporate_action_policy="raw", corporate_action_reference=None,
        includes_delisted=False,
    )
    raw_history = replace(history, provenance=source)
    with pytest.raises(ResearchCatalogError, match="lineage"):
        evaluate_chronological_window(catalog, _plan(), raw_history, forward)
    with pytest.raises(ResearchCatalogError, match="adjustment"):
        evaluate_chronological_window(
            catalog, _plan(), raw_history,
            replace(forward, provenance=replace(source,
                corporate_action_policy="total_return_adjusted")),
        )
    with pytest.raises(ResearchCatalogError, match="vendor"):
        evaluate_chronological_window(
            catalog, _plan(), raw_history,
            replace(forward, provenance=replace(source, source_id="different_vendor")),
        )
    correct = evaluate_chronological_window(
        catalog, _plan(), raw_history, replace(forward, provenance=source)
    )
    assert correct.training_hash == raw_history.dataset_hash
    assert correct.point_in_time_independently_verified is False
