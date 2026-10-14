"""S6 vetted primitives: verified math, causal timing and session isolation."""
from pathlib import Path

import pytest

from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    audit_algorithm_plan,
    compile_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.s6_seed import S6_SIGNALS, seed_s6_references
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import calculate_signal, verify_signal_on_synthetic_prices
from tests.research.test_academic_algorithm_plan import _market, _plan


def _s6_catalog(tmp_path: Path):
    cat = ResearchCatalog(tmp_path / 's6.sqlite')
    seed_approved_references(cat)
    seed_s6_references(cat)
    for x in S6_SIGNALS:
        cat.verify_and_register(x.signal_id, verify_signal_on_synthetic_prices(x))
    return cat


def test_s6_four_reviewed_entry_primitives(tmp_path: Path):
    cat = _s6_catalog(tmp_path)
    assert len(S6_SIGNALS) == 4
    assert {x.signal_id for x in S6_SIGNALS} == {
        'sma_pullback_20', 'dual_sma_trend_50',
        'ema_direction_20', 'range_low_reclaim_20',
    }
    assert all(verify_signal_on_synthetic_prices(s).passed for s in S6_SIGNALS)
    assert all(cat.get_indicator(s.signal_id).status == 'VERIFIED' for s in S6_SIGNALS)
    seed_s6_references(cat)
    assert len(cat.list_indicators()) == 11
    assert len(cat.list_papers()) == 6  # no invented papers or DOI
    assert cat.get_indicator('cross_sectional_momentum').status == 'PROPOSED'


def test_formula_hand_check_and_causal_prefix_on_choppy_prices():
    sigs = {s.calculator: s for s in S6_SIGNALS}
    close = [100.0] * 55
    close[20] = 80.0
    close[21] = 110.0
    low = [x - 1 for x in close]
    low[22] = 60.0
    close[22] = 101.0
    obs = {'close': close, 'low': low}
    pullback = calculate_signal(sigs['sma_pullback'], obs)
    assert pullback[18] is None and pullback[20] == 1.0
    assert pullback[21] == 0.0
    reclaim = calculate_signal(sigs['range_low_reclaim'], obs)
    assert reclaim[19] is None and reclaim[22] == 1.0
    assert reclaim[21] == 0.0
    trend = calculate_signal(sigs['dual_sma_trend'], obs)
    assert all(x is None for x in trend[:49])
    assert trend[49] in (0.0, 1.0)
    ema = calculate_signal(sigs['ema_direction'], obs)
    assert ema[18] is None and ema[19] == 0.0 and ema[21] == 1.0
    for sig in sigs.values():
        values = calculate_signal(sig, obs)
        assert calculate_signal(sig, {k: v[:-1] for k, v in obs.items()}) == values[:-1]
        assert all(x in (None, 0.0, 1.0) for x in values)


def test_new_votes_work_via_original_backtest_and_typed_plan(tmp_path: Path):
    cat, data = _s6_catalog(tmp_path), _market()
    plain = _plan().model_dump(mode='json')
    plain['cases'][0]['votes'] = [
        {'indicator_id': 'ema_direction_20', 'weight': 0.4},
        {'indicator_id': 'dual_sma_trend_50', 'weight': 0.3},
        {'indicator_id': 'sma_pullback_20', 'weight': 0.3},
    ]
    plain['cases'][1]['votes'] = [
        {'indicator_id': 'range_low_reclaim_20', 'weight': 0.5},
        {'indicator_id': 'time_series_momentum', 'weight': 0.5},
    ]
    # Verify the older entry indicator needed for the second case too.
    old = cat.get_indicator('time_series_momentum')
    cat.verify_and_register(old.signal_id, verify_signal_on_synthetic_prices(old))
    gate = cat.get_indicator('parkinson_variance')
    cat.verify_and_register(gate.signal_id, verify_signal_on_synthetic_prices(gate))
    plan = AlgorithmPlan.model_validate(plain)
    compiled = compile_algorithm_plan(cat, plan, data)
    audit = audit_algorithm_plan(cat, compiled, data)
    assert len(audit.decisions) == len(data.bars)
    assert all(name in compiled.compiled.feature_values for name in (
        'ema_direction_20', 'dual_sma_trend_50', 'sma_pullback_20', 'range_low_reclaim_20'
    ))
    by_id = {decision.decision_id: decision for decision in audit.decisions}
    assert all(
        by_id[fill.decision_id].signal_time < fill.execution_time
        for fill in audit.fills
    )
    changed = compile_algorithm_plan(cat, plan, _market(change_last=True))
    for name in compiled.compiled.feature_values:
        assert (
            compiled.compiled.feature_values[name][:-1]
            == changed.compiled.feature_values[name][:-1]
        )


def test_old_catalog_and_s6_proposals_separate(tmp_path: Path):
    old = ResearchCatalog(tmp_path / 'old.sqlite')
    seed_approved_references(old)
    assert len(old.list_indicators()) == 7
    with pytest.raises(ResearchCatalogError, match='not found'):
        old.get_indicator('ema_direction_20')
    expanded = ResearchCatalog(tmp_path / 'expanded.sqlite')
    seed_approved_references(expanded)
    seed_s6_references(expanded)
    assert all(expanded.get_indicator(x.signal_id).status == 'PROPOSED' for x in S6_SIGNALS)
    assert not expanded.list_indicators(eligible_only=True)


def test_invalid_and_gapped_prices_fail_closed():
    sig = S6_SIGNALS[0]
    with pytest.raises(ValueError):
        sig.__class__.model_validate(sig.model_dump() | {'calculator': 'arbitrary_code'})
    with pytest.raises(ValueError):
        calculate_signal(sig, {'close': [99.0] * 30 + [float('nan')]})
