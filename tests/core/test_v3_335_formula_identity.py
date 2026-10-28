"""Mathematical identity checks uncovered by the 335-wide execution audit."""

from __future__ import annotations

import math

import pytest

from core.features.calculators import _ema, _rsi, calculate_feature
from core.features.registry import research_feature_specs


def _spec(name: str, period: int):
    origin = next(s for s in research_feature_specs() if s.name == name)
    return origin.model_copy(update={"lookback": period})


def test_vidya_is_variable_index_dynamic_average_not_rsi() -> None:
    close = tuple(100.0 + 0.9 * j + 4.2 * math.sin(j / 2.4) for j in range(80))
    output = calculate_feature(_spec("vidya", 10), {"close": close})
    assert output[:9] == (None,) * 9
    assert output[9] == pytest.approx(sum(close[:10]) / 10)
    assert output[-1] is not None
    assert 100 < output[-1] < close[-1]
    assert output != _rsi(close, 10)
    assert output != _ema(close, 10)


def test_vidya_flat_price_is_constant() -> None:
    output = calculate_feature(_spec("vidya", 5), {"close": (100.0,) * 25})
    assert output[:4] == (None,) * 4
    assert output[4:] == (100.0,) * 21


def test_connors_rsi_combines_price_streak_and_return_percent_rank() -> None:
    close = tuple(100.0 + 2.0 * math.sin(j / 4) + j * 0.02 + (j % 5 == 0) * 0.8 for j in range(110))
    output = calculate_feature(_spec("connors_rsi", 14), {"close": close})
    assert output[:14] == (None,) * 14
    assert all(v is None or 0 <= v <= 100 for v in output)
    assert output[35] is not None
    assert output != _rsi(close, 3)
    shortened = calculate_feature(_spec("connors_rsi", 14), {"close": close[:-1]})
    assert output[:-1] == shortened
