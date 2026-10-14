"""Predefined faster time-series horizons stay verified and train-only."""
from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.reentry_challengers import (
    REENTRY_CANDIDATES,
    register_reentry_challengers,
)
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import (
    calculate_signal,
    verify_signal_on_synthetic_prices,
)
from research.indicator_engine.walkforward import run_development_walkforward


def _catalog(tmp_path):
    db = ResearchCatalog(tmp_path / "catalog.sqlite")
    seed_approved_references(db)
    for name in ("previous_range_breakout", "time_series_momentum", "sma_direction"):
        signal = db.get_indicator(name)
        db.verify_and_register(name, verify_signal_on_synthetic_prices(signal))
    return db


def _market(n=695):
    start = datetime(2020, 1, 2, tzinfo=timezone.utc)
    bars = tuple(
        Bar(start + timedelta(days=i), "QQQ", price, price + 1.0,
            price - 1.0, price, 1000)
        for i in range(n)
        for price in (100.0 + i * 0.07 + (i % 17) * 0.19,)
    )
    return MarketDataSet("research", DataZone.DEVELOPMENT, bars)


def test_reentry_registration_is_opt_in_still_proposed_and_idempotent(tmp_path):
    db = _catalog(tmp_path)
    before = len(db.list_indicators())
    register_reentry_challengers(db)
    register_reentry_challengers(db)
    assert len(db.list_indicators()) == before + 3
    for entry, regime in REENTRY_CANDIDATES:
        for name in (entry, regime):
            candidate = db.get_indicator(name)
            if name.endswith("_63") or name.endswith("_126") or name.endswith("_10"):
                assert candidate.status == "PROPOSED"
                assert candidate.paper_doi in {
                    "10.1016/j.jfineco.2011.11.003",
                    "10.1111/j.1540-6261.1992.tb04681.x",
                }
                assert verify_signal_on_synthetic_prices(candidate).passed


def test_shorter_lookback_changes_earliest_signal_but_no_future_peek(tmp_path):
    db = _catalog(tmp_path)
    register_reentry_challengers(db)
    raw = {"close": tuple(100 + i * 0.11 for i in range(300))}
    for name, length in (("time_series_momentum_63", 63),
                         ("time_series_momentum_126", 126)):
        indicator = db.get_indicator(name)
        value = calculate_signal(indicator, raw)
        assert all(v is None for v in value[:length])
        assert value[length] == 1.0
        for cutoff in (length + 3, 190):
            assert calculate_signal(indicator, {"close": raw["close"][:cutoff]}) == value[:cutoff]


def test_fast_candidate_requires_explicit_verification_no_automatic_promotion(tmp_path):
    db = _catalog(tmp_path)
    with pytest.raises(ResearchCatalogError):
        run_development_walkforward(db, _market(), train_bars=400,
                                    test_bars=100, min_final_test_bars=90,
                                    include_fast_reentry_challengers=True)
    register_reentry_challengers(db)
    with pytest.raises(ResearchCatalogError, match="VERIFIED"):
        run_development_walkforward(db, _market(), train_bars=400,
                                    test_bars=100, min_final_test_bars=90,
                                    include_fast_reentry_challengers=True)
    for new_id in ("time_series_momentum_63", "time_series_momentum_126",
                   "sma_direction_10"):
        candidate = db.get_indicator(new_id)
        db.verify_and_register(new_id, verify_signal_on_synthetic_prices(candidate))
    full = run_development_walkforward(db, _market(), train_bars=400,
                                       test_bars=100, min_final_test_bars=90,
                                       include_fast_reentry_challengers=True,
                                       include_passive_challenger=True)
    assert len(full.folds) == 3
    assert all({"time_series_momentum_63", "time_series_momentum_126"} <=
               dict(f.training_final_equities).keys() for f in full.folds)
    assert not full.candidate_promotable and not full.out_of_sample_approved
    for fold in full.folds:
        assert fold.first_trade_time is None or fold.first_trade_time >= fold.test_start


def test_tail_extension_does_not_change_past_training_choices(tmp_path):
    db = _catalog(tmp_path)
    register_reentry_challengers(db)
    for new_id in ("time_series_momentum_63", "time_series_momentum_126",
                   "sma_direction_10"):
        cand = db.get_indicator(new_id)
        db.verify_and_register(new_id, verify_signal_on_synthetic_prices(cand))
    a = run_development_walkforward(db, _market(600), train_bars=400,
                                    test_bars=100, min_final_test_bars=100,
                                    include_fast_reentry_challengers=True)
    b = run_development_walkforward(db, _market(695), train_bars=400,
                                    test_bars=100, min_final_test_bars=90,
                                    include_fast_reentry_challengers=True)
    assert a.folds == b.folds[:2]


def test_reentry_seed_rejects_mismatched_predeclared_period_and_preserves_verified(tmp_path):
    db = _catalog(tmp_path)
    before = db.get_indicator("time_series_momentum")
    conflict = before.model_copy(update={
        "signal_id": "time_series_momentum_63", "lookback": 21,
        "status": "PROPOSED",
    })
    db.add_indicator(conflict)
    with pytest.raises(ResearchCatalogError, match="preregistration"):
        register_reentry_challengers(db)
    assert db.get_indicator("time_series_momentum_63") == conflict

    safe = ResearchCatalog(tmp_path / "safe.sqlite")
    seed_approved_references(safe)
    register_reentry_challengers(safe)
    proposed = safe.get_indicator("time_series_momentum_63")
    safe.verify_and_register(proposed.signal_id, verify_signal_on_synthetic_prices(proposed))
    register_reentry_challengers(safe)
    assert safe.get_indicator("time_series_momentum_63").status == "VERIFIED"


def test_fast_options_do_not_change_legacy_default(tmp_path):
    db = _catalog(tmp_path)
    market = _market()
    baseline = run_development_walkforward(db, market, train_bars=400,
                                           test_bars=100, min_final_test_bars=90)
    register_reentry_challengers(db)
    for key in ("time_series_momentum_63", "time_series_momentum_126",
                "sma_direction_10"):
        item = db.get_indicator(key)
        db.verify_and_register(key, verify_signal_on_synthetic_prices(item))
    assert run_development_walkforward(db, market, train_bars=400,
                                        test_bars=100, min_final_test_bars=90) == baseline
