"""Opt-in, non-executable Pine feature replay contract tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.pine_import.boswaves_bridge import prepare_boswaves_development_replay


def _market():
    bars = []
    for i in range(110):
        price = 100 + 0.45 * i if i < 60 else 127 - 0.8 * (i - 60)
        bars.append(Bar(
            datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            "QQQ", price, price + 1, price - 1, price, 5000.0,
        ))
    return MarketDataSet("boswaves-port-research", DataZone.DEVELOPMENT, tuple(bars))


def test_causal_replay_bounded_and_not_registered_or_executable():
    market = _market()
    replay = prepare_boswaves_development_replay(market)
    assert replay == prepare_boswaves_development_replay(market)
    assert replay.status == "DEVELOPMENT_ONLY"
    assert replay.dataset_hash == market.dataset_hash
    assert len(replay.signals) == 4
    assert replay.signals[0][0] == "pine.boswaves.bull_flip"
    assert replay.signals[1][0] == "pine.boswaves.bear_flip"
    assert replay.in_operational_feature_registry is False
    assert replay.tradingview_parity_verified is False
    assert replay.broker_executable is False
    assert replay.strategy_execution_equivalent is False
    assert replay.execution_not_before[:-1] == replay.timestamps[1:]
    assert replay.execution_not_before[-1] is None
    assert all(len(series) == len(market.bars) for _, series in replay.signals)
    assert any(x == 1.0 for x in dict(replay.signals)["pine.boswaves.bull_flip"])
    assert any(x == 1.0 for x in dict(replay.signals)["pine.boswaves.bear_flip"])


def test_bars_with_future_change_do_not_change_previous_feature_values():
    original = _market()
    replay = prepare_boswaves_development_replay(original)
    changed = replace(
        original,
        bars=original.bars[:-1] + (
            replace(
                original.bars[-1],
                high=200.0,
                low=40.0,
                close=80.0,
                open=80.0,
            ),
        ),
    )
    changed_replay = prepare_boswaves_development_replay(changed)
    for (_, a), (_, b) in zip(replay.signals, changed_replay.signals):
        assert a[:-1] == b[:-1]


def test_reject_sealed_data():
    market = _market()
    with pytest.raises(ValueError):
        prepare_boswaves_development_replay(
            replace(market, zone=DataZone.SEALED_OOS)
        )
