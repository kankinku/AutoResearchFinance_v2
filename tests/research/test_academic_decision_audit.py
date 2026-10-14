"""Decision → next-open execution → realized PnL, with no invented cause."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.decision_audit import audit_compiled_academic_decisions
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices
from research.indicator_engine.strategy_adapter import compile_research_hypothesis


def _fixture(tmp_path: Path, *, sealed: bool = False, change_last: bool = False):
    catalog = ResearchCatalog(tmp_path / ("study_chg.sqlite" if change_last else "study.sqlite"))
    seed_approved_references(catalog)
    for name in ("previous_range_breakout", "sma_direction"):
        candidate = catalog.get_indicator(name)
        catalog.verify_and_register(name, verify_signal_on_synthetic_prices(candidate))
    source = []
    for i in range(185):
        if i < 60:
            price = 100.0 + i * 0.5
        elif i < 97:
            price = 129.5 - (i - 59) * 0.85
        elif i < 154:
            price = 98.05 + (i - 96) * 0.86
        else:
            price = 147.07 - (i - 153) * 0.76
        if i == 184 and change_last:
            price *= 1.2
        source.append(Bar(datetime(2020, 1, 1, tzinfo=timezone.utc)
                          + timedelta(days=i), "QQQ", price, price + 0.1,
                          price - 0.1, price, 10_000.0))
    market = MarketDataSet("trace-test", DataZone.SEALED_OOS if sealed
                           else DataZone.DEVELOPMENT, tuple(source))
    hypothesis = compose_hypotheses(
        catalog, signal_ids=("previous_range_breakout", "sma_direction")
    )[0]
    return market, compile_research_hypothesis(catalog, hypothesis, market)


def test_real_canonical_fills_have_prior_close_signal_snapshots(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    report = audit_compiled_academic_decisions(compiled, market)
    assert report.evaluation.trades_count >= 3
    assert len(report.decisions) == len(market.bars)
    assert len(report.fills) == report.evaluation.trades_count
    assert report.round_trips
    assert report.status == "RESEARCH_DECISION_AUDIT_ONLY"
    assert not report.candidate_promotable and not report.point_in_time_verified
    by_id = {decision.decision_id: decision for decision in report.decisions}
    assert any(decision.action == "FILTERED_REGIME" for decision in report.decisions)
    assert any(decision.action == "NO_ENTRY_SIGNAL" for decision in report.decisions)
    for j, record in enumerate(report.fills):
        assert record.fill_id.endswith(f"-{j:06d}")
        assert record.trade_id
        decision = by_id[record.decision_id]
        assert decision.signal_time < record.execution_time
        assert decision.earliest_execution == record.execution_time
        assert decision.entry_signal is not None
        assert decision.regime_signal is not None
        assert record.price == market.bars[record.bar_index].open
        assert record.trade == report.evaluation.trades[j]
        if record.side == "buy":
            assert decision.action == "REQUEST_ENTRY"
            assert decision.entry_signal > 0 and decision.regime_signal > 0
        else:
            assert decision.action == "REQUEST_EXIT"
            assert decision.entry_signal <= 0
    for closed in report.round_trips:
        assert closed.net_pnl == pytest.approx(
            closed.exit_fill.trade.notional - closed.exit_fill.trade.cost
            - closed.entry_fill.trade.notional - closed.entry_fill.trade.cost
        )
        assert closed.entry_fill.trade_id == closed.exit_fill.trade_id
        assert closed.entry_fill.execution_time < closed.exit_fill.execution_time
    assert report.trace_hash == audit_compiled_academic_decisions(compiled, market).trace_hash
    assert report.llm_packet["causal_claim"] == "NOT_ESTABLISHED"
    assert isinstance(report.llm_packet["loss_examples"], list)
    assert report.llm_packet["hypotheses_tested"] == 0
    metrics = report.llm_packet["metrics"]
    assert metrics["total_return"] == pytest.approx(
        report.evaluation.final_equity / report.evaluation.initial_cash - 1
    )
    assert metrics["trade_count"] == len(report.round_trips)
    assert metrics["max_drawdown"] >= 0
    samples = report.llm_packet["execution_samples"]
    assert samples[0]["indicator_values"]
    assert samples[0]["signal_time"] < samples[0]["execution_time"]
    assert samples[0]["decision_action"] in {"REQUEST_ENTRY", "REQUEST_EXIT"}


def test_trace_future_candle_cannot_change_past_decisions(tmp_path: Path):
    a_market, a_compiled = _fixture(tmp_path)
    b_market, b_compiled = _fixture(tmp_path, change_last=True)
    a = audit_compiled_academic_decisions(a_compiled, a_market)
    b = audit_compiled_academic_decisions(b_compiled, b_market)
    assert a.trace_hash != b.trace_hash
    before = [(r.action, r.entry_signal, r.regime_signal) for r in a.decisions[:-1]]
    after = [(r.action, r.entry_signal, r.regime_signal) for r in b.decisions[:-1]]
    assert before == after


def test_reject_sealed_dataset_and_tampered_replay(tmp_path: Path):
    development, compiled = _fixture(tmp_path)
    sealed = MarketDataSet(development.version, DataZone.SEALED_OOS, development.bars)
    with pytest.raises(ResearchCatalogError, match="development"):
        audit_compiled_academic_decisions(compiled, sealed)
    forged = replace(compiled, strategy_hash="f" * 64)
    with pytest.raises(ResearchCatalogError, match="hash"):
        audit_compiled_academic_decisions(forged, development)
    corrupt = replace(compiled, feature_values={**compiled.feature_values,
                      "previous_range_breakout": tuple(1.0 for _ in development.bars)})
    with pytest.raises(ResearchCatalogError, match="feature mismatch"):
        audit_compiled_academic_decisions(corrupt, development)


def test_no_pending_fill_on_last_bar_and_warmup_explicit(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    bundle = audit_compiled_academic_decisions(compiled, market)
    assert bundle.decisions[0].action == "WARMUP"
    assert bundle.decisions[-1].earliest_execution is None
    assert bundle.decisions[-1].fill_id is None
    for event in bundle.decisions:
        if event.fill_id is not None:
            assert any(f.fill_id == event.fill_id for f in bundle.fills)
