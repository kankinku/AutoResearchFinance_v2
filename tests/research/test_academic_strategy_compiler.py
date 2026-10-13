"""P0 research compiler acceptance: costed next-open fills; no PIT/real orders."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices
from research.indicator_engine.strategy_adapter import (
    compile_research_hypothesis,
    evaluate_compiled_development,
)


def fixtures(tmp_path: Path, *, risk: bool = False):
    db = ResearchCatalog(tmp_path / "papers.sqlite")
    seed_approved_references(db)
    names = ("previous_range_breakout", "sma_direction") + (("parkinson_variance",) if risk else ())
    for name in names:
        sig = db.get_indicator(name)
        db.verify_and_register(name, verify_signal_on_synthetic_prices(sig))
    hypothesis = next(
        h for h in compose_hypotheses(db, signal_ids=names) if len(h.signal_ids) == len(names)
    )
    bars = []
    t0 = datetime(2021, 1, 1, 21, tzinfo=timezone.utc)
    for i in range(100):
        close = 100.0 + (i * 2.0 if i < 50 else (100 - i) * 2.0)
        bars.append(Bar(t0 + timedelta(days=i), "QQQ", close, close + 1, close - 1, close, 1000))
    market = MarketDataSet("fixture", DataZone.DEVELOPMENT, tuple(bars))
    return db, hypothesis, market


def test_compiles_and_uses_costed_next_open_fills(tmp_path: Path) -> None:
    db, hypothesis, market = fixtures(tmp_path)
    compiled = compile_research_hypothesis(db, hypothesis, market)
    assert compiled.status == "DEVELOPMENT_ONLY"
    assert not compiled.broker_executable
    assert not compiled.sealed_oos_approved
    assert len(compiled.strategy.features) == 2
    assert compiled.strategy.entry.conditions[0].value == 0.5
    assert compiled.strategy.exit.conditions[0].op == "less_equal"
    first = evaluate_compiled_development(compiled, market)
    second = evaluate_compiled_development(compiled, market)
    assert first == second
    assert first.trades_count > 0
    assert first.total_paid_costs > 0
    assert first.status == "NON_PIT_DEVELOPMENT_RESULT"
    assert first.qqq_cagr_delta is None and first.pbo is None and first.dsr is None
    assert not first.candidate_promotable and not first.broker_executable
    for trade in first.trades:
        i = next(
            i for i, bar in enumerate(market.bars) if trade.timestamp == bar.timestamp.isoformat()
        )
        assert i > 0 and trade.price == pytest.approx(market.bars[i].open)
        if trade.side == "buy":
            vectors = dict(compiled.replay.signals)
            entry = hypothesis.signal_ids[hypothesis.roles.index("entry")]
            regime = hypothesis.signal_ids[hypothesis.roles.index("regime")]
            assert vectors[entry][i - 1] == 1.0
            assert vectors[regime][i - 1] == 1.0


def test_fails_closed_for_risk_overlay_oos_unverified_or_forged(tmp_path: Path) -> None:
    db, hypothesis, market = fixtures(tmp_path, risk=True)
    with pytest.raises(ResearchCatalogError, match="risk overlay"):
        compile_research_hypothesis(db, hypothesis, market)
    db, hypothesis, market = fixtures(tmp_path / "safe")
    with pytest.raises(ResearchCatalogError, match="non-development"):
        compile_research_hypothesis(
            db, hypothesis, MarketDataSet("sealed", DataZone.SEALED_OOS, market.bars)
        )
    with pytest.raises(ResearchCatalogError, match="forged"):
        compile_research_hypothesis(
            db, hypothesis.model_copy(update={"identity_hash": "0" * 64}), market
        )
    proposals = ResearchCatalog(tmp_path / "new.sqlite")
    seed_approved_references(proposals)
    with pytest.raises(ResearchCatalogError, match="unverified"):
        compile_research_hypothesis(proposals, hypothesis, market)


def test_compiled_results_bind_data_and_strategy_hash(tmp_path: Path) -> None:
    db, hypothesis, market = fixtures(tmp_path)
    compiled = compile_research_hypothesis(db, hypothesis, market)
    bars = list(market.bars)
    last = bars[-1]
    bars[-1] = Bar(last.timestamp, last.symbol, 250, 251, 249, 250, 1000)
    changed = MarketDataSet("fixture", DataZone.DEVELOPMENT, tuple(bars))
    with pytest.raises(ResearchCatalogError, match="data hash"):
        evaluate_compiled_development(compiled, changed)
    invalid = compiled.strategy.model_copy(update={"family": "mutated"})
    with pytest.raises(ResearchCatalogError, match="strategy hash"):
        evaluate_compiled_development(replace(compiled, strategy=invalid), market)


def test_mutated_replay_values_cannot_reach_backtest(tmp_path: Path) -> None:
    db, hypothesis, market = fixtures(tmp_path)
    compiled = compile_research_hypothesis(db, hypothesis, market)
    vectors = dict(compiled.replay.signals)
    first = hypothesis.signal_ids[0]
    changed = list(vectors[first])
    changed[25] = 1.0 if changed[25] != 1.0 else 0.0
    vectors[first] = tuple(changed)
    tampered_replay = replace(
        compiled.replay,
        signals=tuple((k, vectors[k]) for k, _ in compiled.replay.signals),
    )
    tampered_compiled = replace(compiled, replay=tampered_replay, feature_values=vectors)
    with pytest.raises(ResearchCatalogError, match="replay integrity"):
        evaluate_compiled_development(tampered_compiled, market)
