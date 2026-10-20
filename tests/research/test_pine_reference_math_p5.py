"""Independent numeric witnesses for Pine v6-derived calculation contracts.

These are reference-formula tests on synthetic bars. They are NOT extracted
TradingView reference bar-by-bar exports or a broker emulator parity verdict.
"""
from math import exp
from statistics import pstdev

import pytest

from research.pine_import.boswaves_ribbon import RibbonParams, compute_ribbon
from research.pine_import.shaakuni_order_blocks import (
    ShaakuniParams,
    compute_shaakuni,
)


def _values():
    close = [
        100.0 + 0.31 * i + (3.2 if i >= 45 else 0.0) -
        (8.5 if i >= 79 else 0.0)
        for i in range(130)
    ]
    return [x + 1 for x in close], [x - 1 for x in close], close


def _wilder_tr(high, low, close, periods):
    ranges = []
    result = []
    for idx, (hi, lo, closing) in enumerate(zip(high, low, close, strict=True)):
        before = closing if idx == 0 else close[idx - 1]
        ranges.append(max(hi - lo, abs(hi - before), abs(lo - before)))
        if idx < periods - 1:
            result.append(None)
        elif idx == periods - 1:
            result.append(sum(ranges) / periods)
        else:
            result.append((result[-1] * (periods - 1) + ranges[-1]) / periods)
    return result


def test_boswaves_reference_formula_alma_stdev_and_wilder_atr():
    high, low, close = _values()
    params = RibbonParams(
        alma_length=14, alma_sigma=4.0, alma_offset=0.6,
        deviation_length=16, atr_length=12,
    )
    source = [v + 0.37 for v in close]
    out = compute_ribbon(high, low, close, params=params, source=source)
    expected_atr = _wilder_tr(high, low, close, 12)
    # Independent cross-check of exact source formulas, not approximate S7 PnL.
    for idx, row in enumerate(out.bars):
        assert row.atr == pytest.approx(expected_atr[idx])
        if idx < params.alma_length - 1:
            assert row.alma is None
        else:
            prior = source[idx - 13:idx + 1]
            center = 0.6 * 13
            width = 14 / 4.0
            weights = [
                exp(-0.5 * ((j - center) / width) ** 2)
                for j in range(14)
            ]
            expected_alma = sum(
                value * weight for value, weight in zip(prior, weights, strict=True)
            ) / sum(weights)
            assert row.alma == pytest.approx(expected_alma, abs=1e-10)
        if idx < 15:
            assert row.deviation is None
        else:
            assert row.deviation == pytest.approx(pstdev(source[idx - 15:idx + 1]))


def test_shaakuni_reference_wilder_atr_matches_independent_formula():
    from datetime import datetime, timedelta, timezone

    high, low, close = _values()
    stamps = [
        datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
        for i in range(len(close))
    ]
    out = compute_shaakuni(
        stamps,
        close,
        high,
        low,
        close,
        ShaakuniParams(),
    )
    ref = _wilder_tr(high, low, close, 14)
    assert [item.atr for item in out.bars] == pytest.approx(ref, nan_ok=True)
