from __future__ import annotations

import pytest

from core.features.calculators import FeatureCalculationError, calculate_feature
from core.features.contracts import FeatureSpec


def _spec(calculator: str, lookback: int = 3, inputs: tuple[str, ...] = ("close",)) -> FeatureSpec:
    return FeatureSpec(
        name=calculator,
        family="test",
        inputs=inputs,
        lookback=lookback,
        formula=f"{calculator}({', '.join(inputs)})",
        calculator=calculator,
    )


def test_calculate_feature_supports_sma_and_returns() -> None:
    values = calculate_feature(_spec("sma"), {"close": (1.0, 2.0, 3.0, 4.0)})
    returns = calculate_feature(
        _spec("returns", lookback=1), {"close": (100.0, 110.0, 99.0, 99.0)}
    )

    assert values == (None, None, 2.0, 3.0)
    assert returns[0] is None
    assert returns[1] == pytest.approx(0.1)
    assert returns[2] == pytest.approx(-0.1)
    assert returns[3] == pytest.approx(0.0)


def test_calculate_feature_supports_cross_asset_spread_and_correlation() -> None:
    spread = calculate_feature(
        _spec("spread", inputs=("target.close", "VIX.close")),
        {"target.close": (10.0, 12.0, 15.0), "VIX.close": (2.0, 3.0, 5.0)},
    )
    correlation = calculate_feature(
        _spec("rolling_correlation", inputs=("target.close", "SPY.close")),
        {"target.close": (1.0, 2.0, 3.0), "SPY.close": (2.0, 4.0, 6.0)},
    )

    assert spread == (8.0, 9.0, 10.0)
    assert correlation[0] is None and correlation[1] is None
    assert correlation[2] == pytest.approx(1.0)


def test_calculate_feature_rejects_missing_inputs_and_unknown_calculators() -> None:
    with pytest.raises(FeatureCalculationError, match="missing input"):
        calculate_feature(_spec("sma"), {"other": (1.0, 2.0, 3.0)})
    with pytest.raises(FeatureCalculationError, match="unsupported calculator"):
        calculate_feature(_spec("not_real"), {"close": (1.0, 2.0, 3.0)})


def test_calculate_feature_supports_bollinger_volume_and_52_week_features() -> None:
    middle = calculate_feature(
        _spec("bollinger", inputs=("close",)),
        {"close": (1.0, 2.0, 3.0)},
    )
    volume = calculate_feature(
        _spec("volume_breakout", lookback=2, inputs=("volume",)),
        {"volume": (100.0, 100.0, 200.0)},
    )
    high = calculate_feature(
        _spec("52_week_high", lookback=2),
        {"close": (10.0, 12.0, 11.0)},
    )

    assert middle[-1] == pytest.approx(2.0)
    assert volume[0] is None and volume[1] == pytest.approx(1.0)
    assert volume[2] == pytest.approx(2.0)
    assert high == (None, 1.0, pytest.approx(11.0 / 12.0))


def test_calculate_feature_supports_macd_atr_and_regime_features() -> None:
    macd = calculate_feature(
        _spec("macd", lookback=3), {"close": (1.0, 2.0, 3.0, 4.0, 5.0)}
    )
    atr = calculate_feature(
        _spec("atr", lookback=2, inputs=("high", "low", "close")),
        {
            "high": (11.0, 13.0, 14.0),
            "low": (9.0, 10.0, 12.0),
            "close": (10.0, 12.0, 13.0),
        },
    )
    regime = calculate_feature(
        _spec("regime_filter", lookback=3),
        {"close": (1.0, 2.0, 3.0, 4.0, 5.0)},
    )

    assert macd[-1] is not None
    assert atr[0] is None and atr[1] == pytest.approx(2.5)
    assert regime[-1] is not None
