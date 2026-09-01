from __future__ import annotations

import math

import pytest

from core.features.calculators import calculate_feature
from core.features.contracts import FeatureSpec

CLOSE = tuple(float(value) for value in (10, 11, 12, 11, 13, 14, 13, 15, 16, 15, 17, 18))
HIGH = tuple(value + 1.0 for value in CLOSE)
LOW = tuple(value - 1.0 for value in CLOSE)
VOLUME = tuple(
    float(value) for value in (100, 120, 90, 130, 150, 140, 160, 180, 170, 190, 200, 210)
)
INPUTS = {"close": CLOSE, "high": HIGH, "low": LOW, "volume": VOLUME}


def _spec(
    calculator: str,
    inputs: tuple[str, ...] = ("close",),
    parameters: dict[str, int | float | str | bool] | None = None,
) -> FeatureSpec:
    return FeatureSpec(
        name=calculator,
        family="test",
        inputs=inputs,
        calculator=calculator,
        lookback=3,
        parameters=parameters or {},
        formula=f"{calculator}({', '.join(inputs)})",
    )


@pytest.mark.parametrize(
    ("calculator", "inputs"),
    [
        ("wma", ("close",)),
        ("hma", ("close",)),
        ("dema", ("close",)),
        ("tema", ("close",)),
        ("kama", ("close",)),
        ("wilder", ("close",)),
        ("stochastic", ("high", "low", "close")),
        ("williams_r", ("high", "low", "close")),
        ("cci", ("high", "low", "close")),
        ("trix", ("close",)),
        ("tsi", ("close",)),
        ("vortex", ("high", "low", "close")),
        ("aroon", ("high", "low")),
        ("supertrend", ("high", "low", "close")),
        ("ichimoku", ("high", "low", "close")),
        ("parabolic_sar", ("high", "low")),
        ("true_range", ("high", "low", "close")),
        ("bollinger_bandwidth", ("close",)),
        ("bollinger_percent_b", ("close",)),
        ("keltner", ("high", "low", "close")),
        ("donchian", ("high", "low")),
        ("normalized_atr", ("high", "low", "close")),
        ("ulcer_index", ("close",)),
        ("obv", ("close", "volume")),
        ("vwap", ("high", "low", "close", "volume")),
        ("adl", ("high", "low", "close", "volume")),
        ("cmf", ("high", "low", "close", "volume")),
        ("mfi", ("high", "low", "close", "volume")),
        ("force_index", ("close", "volume")),
        ("pvt", ("close", "volume")),
        ("fisher", ("high", "low")),
        ("dpo", ("close",)),
        ("zscore", ("close",)),
        ("hurst", ("close",)),
        ("entropy", ("close",)),
        ("log_returns", ("close",)),
        ("cusum", ("close",)),
        ("tma", ("close",)),
        ("vidya", ("close",)),
        ("cmo", ("close",)),
        ("vwma", ("close", "volume")),
        ("mcginley", ("close",)),
        ("zero_lag_ema", ("close",)),
        ("fama", ("close",)),
        ("stoch_rsi", ("close",)),
        ("rvi", ("close",)),
        ("rsx", ("close",)),
        ("ultimate_oscillator", ("high", "low", "close")),
        ("dti", ("close",)),
        ("laguerre_rsi", ("close",)),
        ("smi", ("high", "low", "close")),
        ("macd_signal", ("close",)),
        ("macd_histogram", ("close",)),
        ("historical_volatility", ("close",)),
        ("volatility_ratio", ("close",)),
        ("atr_percent", ("high", "low", "close")),
        ("mass_index", ("high", "low")),
        ("garman_klass", ("open", "high", "low", "close")),
        ("parkinson", ("high", "low")),
        ("range_volatility", ("high", "low")),
        ("volume_oscillator", ("volume",)),
        ("volume_roc", ("volume",)),
        ("volume_delta", ("close", "volume")),
        ("smoothed_obv", ("close", "volume")),
        ("pvi", ("close", "volume")),
        ("nvi", ("close", "volume")),
        ("pivot_points", ("high", "low", "close")),
        ("zigzag", ("close",)),
        ("heikin_ashi", ("open", "high", "low", "close")),
        ("renko", ("close",)),
        ("engulfing", ("open", "high", "low", "close")),
        ("doji", ("open", "high", "low", "close")),
        ("hammer", ("open", "high", "low", "close")),
        ("inside_bar", ("high", "low")),
        ("outside_bar", ("high", "low")),
        ("higher_high_lower_low", ("high", "low")),
        ("fractal", ("high", "low")),
        ("fractal_dimension", ("close",)),
        ("kalman_slope", ("close",)),
        ("minmax_scale", ("close",)),
        ("robust_scale", ("close",)),
        ("rolling_skewness", ("close",)),
        ("rolling_kurtosis", ("close",)),
        ("mad", ("close",)),
        ("percentile_rank", ("close",)),
    ],
)
def test_imported_calculator_returns_finite_input_length_series(
    calculator: str, inputs: tuple[str, ...]
) -> None:
    result = calculate_feature(_spec(calculator, inputs), {**INPUTS, "open": CLOSE})

    assert len(result) == len(CLOSE)
    assert all(value is None or math.isfinite(value) for value in result)


def test_imported_calculators_support_explicit_parameters() -> None:
    percent_b = calculate_feature(
        _spec("bollinger_percent_b", parameters={"deviations": 2.0}), INPUTS
    )
    atr_percent = calculate_feature(
        _spec("normalized_atr", inputs=("high", "low", "close")), INPUTS
    )

    assert percent_b[-1] is not None
    assert atr_percent[-1] is not None


def test_new_calculators_reject_missing_declared_inputs() -> None:
    with pytest.raises(ValueError, match="missing input"):
        calculate_feature(_spec("mfi", ("high", "low", "close", "volume")), {"close": CLOSE})
