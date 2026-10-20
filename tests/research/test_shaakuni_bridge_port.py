"""Shaakuni study bridge: immutable as-of signals, no automatic execution."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.pine_import.shaakuni_bridge import prepare_shaakuni_development_replay
from research.pine_import.shaakuni_order_blocks import ShaakuniParams


def _qqq():
    bars = []
    for i in range(120):
        price = 100 + i * 0.12 if i < 65 else 107.8 - (i-65) * 0.17
        bars.append(Bar(
            datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            "QQQ", price, price + 1.0, price - 1.0, price, 5000.0,
        ))
    return MarketDataSet("shaakuni-study", DataZone.DEVELOPMENT, tuple(bars))


def test_replay_signal_contract_and_no_order_permissions():
    market = _qqq()
    a = prepare_shaakuni_development_replay(market)
    b = prepare_shaakuni_development_replay(market)
    assert a == b
    assert a.dataset_hash == market.dataset_hash
    assert a.execution_not_before[:-1] == a.timestamps[1:]
    assert a.execution_not_before[-1] is None
    assert a.source_license == "MPL-2.0"
    assert not a.in_operational_feature_registry
    assert not a.strategy_ir_compatible
    assert not a.broker_executable
    assert not a.independent_oos_approved
    assert not a.tradingview_parity_verified
    by_key = dict(a.signals)
    assert len(by_key) == 9
    assert len(set(by_key)) == 9
    assert all(len(v) == len(market.bars) for v in by_key.values())
    assert any(p is None for p in by_key["pine.shaakuni.pdh"])
    assert any(p is not None for p in by_key["pine.shaakuni.pdl"])


def test_mutating_future_bar_cannot_change_previous_signals():
    market = _qqq()
    previous = prepare_shaakuni_development_replay(market)
    final_bar = market.bars[-1]
    changed = replace(
        market,
        bars=market.bars[:-1] + (
            replace(final_bar, open=95.0, high=101.0, low=90.0, close=96.0),
        ),
    )
    current = prepare_shaakuni_development_replay(changed)
    for (label1, values1), (label2, values2) in zip(previous.signals, current.signals):
        assert label1 == label2
        assert values1[:-1] == values2[:-1]


def test_bad_market_zone_and_timeframe_fail_closed():
    market = _qqq()
    with pytest.raises(ValueError):
        prepare_shaakuni_development_replay(replace(market, zone=DataZone.SEALED_OOS))
    with pytest.raises(ValueError):
        prepare_shaakuni_development_replay(replace(market, timeframe="15m"))
    with pytest.raises(ValueError):
        prepare_shaakuni_development_replay(
            market, params=ShaakuniParams(swing_lookback=51),
        )
