"""Shaakuni v1.4 order-block semantics, no lookahead, no fake trading."""
from datetime import datetime, timedelta, timezone

import pytest

from research.pine_import.shaakuni_order_blocks import (
    ShaakuniParams,
    compute_shaakuni,
    session_at,
)


def _bull_fixture():
    times = [datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
             for i in range(22)]
    opened = [100.0] * 22
    close = [100.0] * 22
    high = [101.0] * 22
    low = [99.0] * 22
    high[12] = 110.0  # swing high, far enough before confirmed breakout
    opened[18], close[18], high[18], low[18] = 101, 100, 102, 96
    opened[19], close[19], high[19], low[19] = 103, 108, 109, 103
    opened[20], close[20], high[20], low[20] = 111, 112, 113, 110
    opened[21], close[21], high[21], low[21] = 100, 100, 101, 98
    return times, opened, high, low, close


def test_bullish_original_swing_impulse_fresh_and_later_mitigation():
    t, o, h, low_values, c = _bull_fixture()
    study = compute_shaakuni(t, o, h, low_values, c)
    assert study.bars[20].created_ids == (1,)
    assert study.bars[20].mitigated_ids == ()
    assert study.bars[20].fresh_bull == 1
    assert study.bars[21].created_ids == ()
    assert study.bars[21].mitigated_ids == (1,)
    assert study.bars[21].fresh_bull == 0
    zone = study.retained_blocks[0]
    assert zone.side == "BULL"
    assert zone.source_bar == 18
    assert zone.confirmed_bar == 20
    assert zone.top == 102.0 and zone.bottom == 96.0
    assert zone.mitigated_bar == 21
    assert study.broker_executable is False
    assert study.original_live_panel_parity is False
    assert study.source_license == "MPL-2.0"


def test_mirrored_bearish_source_and_mitigation():
    t, o, h, low_values, c = _bull_fixture()
    bear = compute_shaakuni(
        t, [220 - x for x in o], [220 - x for x in low_values],
        [220 - x for x in h], [220 - x for x in c],
    )
    assert bear.bars[20].created_ids == (1,)
    assert bear.bars[21].mitigated_ids == (1,)
    zone = bear.retained_blocks[0]
    assert zone.side == "BEAR"
    assert zone.top == 124
    assert zone.bottom == 118
    assert zone.source_bar == 18


def test_prefix_causality_and_no_creation_when_display_disabled():
    t, o, h, low_values, c = _bull_fixture()
    full = compute_shaakuni(t, o, h, low_values, c)
    for n in (12, 19, 21):
        partial = compute_shaakuni(t[:n], o[:n], h[:n], low_values[:n], c[:n])
        assert partial.bars == full.bars[:n]
    off = compute_shaakuni(
        t, o, h, low_values, c,
        ShaakuniParams(show_order_blocks=False),
    )
    assert not off.retained_blocks
    assert all(not x.created_ids for x in off.bars)


def test_reject_invalid_data_and_boundaries():
    t, o, h, low_values, c = _bull_fixture()
    with pytest.raises(ValueError):
        compute_shaakuni(t, o, h[:-1], low_values, c)
    with pytest.raises(ValueError):
        compute_shaakuni(t, o, h, low_values, c[:-1] + [float("nan")])
    with pytest.raises(ValueError):
        compute_shaakuni(t[:-1] + [t[-2]], o, h, low_values, c)
    with pytest.raises(ValueError):
        compute_shaakuni(
            t, o, h, low_values, c,
            ShaakuniParams(swing_lookback=2),
        )


def test_ny_clock_reproduces_fixed_session_boundaries_not_live_timenow():
    t = datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc)
    assert session_at(t) == "New York"
    assert session_at(t, "Manual UTC-5 (EST)") == "-"
    assert session_at(datetime(2026, 7, 1, 2, 0, tzinfo=timezone.utc)) == "Asian"
    assert session_at(datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)) == "London"
    with pytest.raises(ValueError):
        session_at(datetime(2026, 7, 1))


def test_completed_zone_ages_out_without_erasing_original_signal():
    t, o, h, low_values, c = _bull_fixture()
    for i in range(22, 190):
        t.append(t[0] + timedelta(hours=i))
        o.append(100.0)
        h.append(101.0)
        low_values.append(99.0)
        c.append(100.0)
    report = compute_shaakuni(
        t, o, h, low_values, c,
        ShaakuniParams(zone_lookback=30),
    )
    assert report.bars[20].created_bull_ids == (1,)
    assert report.bars[20].created_bear_ids == ()
    assert report.bars[21].mitigated_ids == (1,)
    assert all(block.block_id != 1 for block in report.retained_blocks)
    assert report.bars[20].created_bull_ids == (1,)
