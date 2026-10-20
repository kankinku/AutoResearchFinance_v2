"""Pine component composition is typed research, not broker/StrategyIR promotion."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.expression_ir import ExpressionError
from research.pine_import.expression_study import (
    PINE_RESEARCH_SOURCES,
    compose_pine_research_expression,
)


def _market() -> MarketDataSet:
    bars = []
    for i in range(140):
        price = (
            100.0 + i * 0.4 if i < 75
            else 130.0 - (i - 75) * 0.7
        )
        bars.append(Bar(
            datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            "QQQ", price, price + 1.0, price - 1.0, price, 5000.0,
        ))
    return MarketDataSet("pine-typed-composition", DataZone.DEVELOPMENT, tuple(bars))


def _expression():
    return {
        "op": "and",
        "args": [
            {
                "op": "gt",
                "args": [
                    {"op": "source", "name": "boswaves_trend"},
                    {"op": "const", "value": 0.0},
                ],
            },
            {
                "op": "gt",
                "args": [
                    {"op": "source", "name": "shaakuni_fresh_bull_ob_count"},
                    {"op": "const", "value": 0.0},
                ],
            },
        ],
    }


def test_two_independent_pine_sources_can_be_composed_without_new_evaluator():
    market = _market()
    a = compose_pine_research_expression(market, _expression())
    b = compose_pine_research_expression(market, _expression())
    assert a == b
    assert a.market_hash == market.dataset_hash
    assert a.algorithm_hash
    assert a.evidence_hash
    assert len(a.signals) == len(market.bars)
    assert set(a.source_replays) == {"boswaves", "shaakuni"}
    assert set(PINE_RESEARCH_SOURCES) == {
        "boswaves_trend", "boswaves_bull_flip", "boswaves_bear_flip",
        "boswaves_conviction", "shaakuni_bull_ob_confirmed",
        "shaakuni_bear_ob_confirmed", "shaakuni_fresh_bull_ob_count",
        "shaakuni_fresh_bear_ob_count",
    }
    assert not a.operationally_registered
    assert not a.tradingview_parity_verified
    assert not a.broker_executable
    assert not a.out_of_sample_approved
    assert a.next_bar_timestamps[:-1] == a.timestamps[1:]
    assert a.next_bar_timestamps[-1] is None
    assert all(v is None or type(v) is bool for v in a.signals)


def test_latest_candle_does_not_rewrite_earlier_composed_signals():
    market = _market()
    a = compose_pine_research_expression(market, _expression())
    final = market.bars[-1]
    modified = replace(
        market,
        bars=market.bars[:-1] + (
            replace(final, open=98.0, high=102.0, low=92.0, close=100.0),
        ),
    )
    b = compose_pine_research_expression(modified, _expression())
    assert a.signals[:-1] == b.signals[:-1]
    assert a.market_hash != b.market_hash
    assert a.evidence_hash != b.evidence_hash


def test_sealed_market_and_unreviewed_source_fail_closed():
    market = _market()
    with pytest.raises(ValueError):
        compose_pine_research_expression(
            replace(market, zone=DataZone.SEALED_OOS), _expression()
        )
    with pytest.raises(ExpressionError):
        compose_pine_research_expression(
            market,
            {"op": "gt", "args": [
                {"op": "source", "name": "pine_raw_unapproved"},
                {"op": "const", "value": 0.0},
            ]},
        )
    with pytest.raises(ValueError):
        compose_pine_research_expression(
            market, {"op": "source", "name": "boswaves_trend"}
        )


def test_can_mutate_formula_without_modifying_original_indicator():
    market = _market()
    changed = {
        "op": "or",
        "args": [
            _expression(),
            {
                "op": "gt",
                "args": [
                    {"op": "source", "name": "boswaves_conviction"},
                    {"op": "const", "value": 0.95},
                ],
            },
        ],
    }
    a = compose_pine_research_expression(market, _expression())
    b = compose_pine_research_expression(market, changed)
    assert a.algorithm_hash != b.algorithm_hash
    assert a.market_hash == b.market_hash
    assert a.source_replays == b.source_replays
