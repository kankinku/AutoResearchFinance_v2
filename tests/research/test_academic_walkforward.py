"""Training-only selection and no-pretest-fill research walk-forward acceptance."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices
from research.indicator_engine.walkforward import run_development_walkforward


def _catalog(tmp_path: Path) -> ResearchCatalog:
    db = ResearchCatalog(tmp_path / "papers.sqlite")
    seed_approved_references(db)
    for key in ("sma_direction", "time_series_momentum", "previous_range_breakout"):
        item = db.get_indicator(key)
        db.verify_and_register(key, verify_signal_on_synthetic_prices(item))
    return db


def _market(n: int = 700, *, zone: DataZone = DataZone.DEVELOPMENT) -> MarketDataSet:
    start = datetime(2020, 1, 2, tzinfo=timezone.utc)
    bars = []
    for i in range(n):
        # Sawtooth noise and trending periods; enough signal for both formulas.
        price = 125.0 + i * 0.08 + (i % 19) * 0.2
        bars.append(Bar(start + timedelta(days=i), "QQQ", price,
                        price + 0.7, price - 0.7, price, 1000))
    return MarketDataSet("test-development", zone, tuple(bars))


def test_train_only_three_folds_never_trade_in_training_and_never_seal(tmp_path: Path):
    db = _catalog(tmp_path)
    market = _market(695)
    report = run_development_walkforward(db, market, train_bars=400,
                                         test_bars=100, min_final_test_bars=90)
    assert [(f.train_end_index, f.test_end_index) for f in report.folds] == [
        (400, 500), (500, 600), (600, 695)
    ]
    assert report.status == "NON_PIT_ROLLING_RESEARCH_ONLY"
    assert not report.out_of_sample_approved and not report.candidate_promotable
    assert not report.benchmark_independently_verified
    assert report.compounded_test_final_equity > 0
    for fold in report.folds:
        assert fold.selected_entry in {"time_series_momentum", "previous_range_breakout"}
        assert fold.train_cutoff < fold.test_start
        assert fold.first_trade_time is None or fold.first_trade_time > fold.test_start
        assert fold.training_choice_hash
        assert fold.selected_hypothesis_hash
        assert fold.training_final_equities
        assert fold.test_final_equity > 0
    assert run_development_walkforward(db, market, train_bars=400,
           test_bars=100, min_final_test_bars=90) == report


def test_forward_tail_changes_no_past_fold_choices(tmp_path: Path):
    db = _catalog(tmp_path)
    initial = _market(600)
    extended = _market(695)
    a = run_development_walkforward(db, initial, train_bars=400,
                                    test_bars=100, min_final_test_bars=100)
    b = run_development_walkforward(db, extended, train_bars=400,
                                    test_bars=100, min_final_test_bars=90)
    assert a.folds[0] == b.folds[0]
    assert a.folds[1] == b.folds[1]


def test_rejects_sealed_unverified_and_weak_sample(tmp_path: Path):
    db = _catalog(tmp_path)
    with pytest.raises(ResearchCatalogError, match="development"):
        run_development_walkforward(db, _market(zone=DataZone.SEALED_OOS),
                                    train_bars=400, test_bars=100)
    with pytest.raises(ResearchCatalogError, match="fold"):
        run_development_walkforward(db, _market(350), train_bars=400, test_bars=100)
    proposed = ResearchCatalog(tmp_path / "unverified.sqlite")
    seed_approved_references(proposed)
    with pytest.raises(ResearchCatalogError, match="VERIFIED"):
        run_development_walkforward(proposed, _market(), train_bars=400, test_bars=100)


def test_training_only_passive_hurdle_replaces_losing_entry_with_baseline(tmp_path: Path):
    db = _catalog(tmp_path)
    market = _market(695)
    report = run_development_walkforward(
        db, market, train_bars=400, test_bars=100,
        min_final_test_bars=90, include_passive_challenger=True,
    )
    assert report.status == "NON_PIT_ROLLING_RESEARCH_ONLY"
    assert not report.candidate_promotable and not report.out_of_sample_approved
    assert any(f.selected_entry == "buy_and_hold" for f in report.folds)
    for fold in report.folds:
        assert "buy_and_hold" in dict(fold.training_final_equities)
        assert fold.training_choice_hash
        if fold.selected_entry == "buy_and_hold":
            assert fold.test_final_equity == pytest.approx(fold.test_buyhold_price_only_equity)
            assert fold.first_trade_time == fold.test_start
            assert fold.trade_count == 1
    assert report.report_hash == run_development_walkforward(
        db, market, train_bars=400, test_bars=100,
        min_final_test_bars=90, include_passive_challenger=True,
    ).report_hash


def test_passive_hurdle_does_not_consult_later_fold_to_select_earlier(tmp_path: Path):
    db = _catalog(tmp_path)
    early = run_development_walkforward(
        db, _market(600), train_bars=400, test_bars=100,
        min_final_test_bars=100, include_passive_challenger=True,
    )
    longer = run_development_walkforward(
        db, _market(695), train_bars=400, test_bars=100,
        min_final_test_bars=90, include_passive_challenger=True,
    )
    assert early.folds == longer.folds[:2]
    assert all(not f.status.endswith("APPROVED") for f in longer.folds)


def test_passive_hurdle_keeps_flat_strategy_when_training_market_declines(tmp_path: Path):
    db = _catalog(tmp_path)
    start = datetime(2020, 1, 2, tzinfo=timezone.utc)
    bars = tuple(
        Bar(start + timedelta(days=i), "QQQ", price,
            price + 0.5, price - 0.5, price, 1000)
        for i in range(550)
        for price in (100.0 - i * 0.09,)
    )
    market = MarketDataSet("falling-training", DataZone.DEVELOPMENT, bars)
    report = run_development_walkforward(
        db, market, train_bars=400, test_bars=100,
        min_final_test_bars=50, include_passive_challenger=True,
    )
    assert len(report.folds) == 2
    assert report.folds[0].selected_entry != "buy_and_hold"
    assert dict(report.folds[0].training_final_equities)["buy_and_hold"] < 10_000
    assert not report.candidate_promotable
