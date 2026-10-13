"""Small, whitelisted causal reference implementations for academic signal candidates.

Outputs at index t use bars <= t only. Trade decisions must execute no sooner
than bar t+1. These calculators do not provide multi-asset or sealed OOS data.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import fmean

from core.integrity.hashes import content_hash
from research.indicator_engine.models import IndicatorCandidate, VerificationResult

Numbers = Mapping[str, Sequence[float]]


def _series(candidate: IndicatorCandidate, raw: Numbers) -> dict[str, tuple[float, ...]]:
    fields = set(candidate.required_fields)
    if not fields <= raw.keys():
        raise ValueError("missing required OHLC field")
    size = len(raw[candidate.required_fields[0]])
    if size == 0 or size > 1_000_000:
        raise ValueError("empty or unbounded input data")
    values: dict[str, tuple[float, ...]] = {}
    for field in candidate.required_fields:
        series = tuple(float(item) for item in raw[field])
        if len(series) != size or any(not math.isfinite(x) or x <= 0 for x in series):
            raise ValueError("missing, unequal, nonfinite or nonpositive OHLC observation")
        values[field] = series
    if "high" in values and "low" in values:
        if any(h < low for h, low in zip(values["high"], values["low"], strict=True)):
            raise ValueError("high must be greater than or equal to low")
    if "high" in values and "close" in values:
        if any(h < c for h, c in zip(values["high"], values["close"], strict=True)):
            raise ValueError("high must include close")
    if "high" in values and "open" in values:
        if any(h < o for h, o in zip(values["high"], values["open"], strict=True)):
            raise ValueError("high must include open")
    if "low" in values and "close" in values:
        if any(low > c for low, c in zip(values["low"], values["close"], strict=True)):
            raise ValueError("low must include close")
    if "low" in values and "open" in values:
        if any(low > o for low, o in zip(values["low"], values["open"], strict=True)):
            raise ValueError("low must include open")
    return values


def calculate_signal(candidate: IndicatorCandidate, inputs: Numbers) -> tuple[float | None, ...]:
    """Evaluate a research-only signal from historical completed bars."""
    if candidate.scope != "single_asset":
        raise ValueError("cross-sectional research requires PIT multi-asset universe")
    values = _series(candidate, inputs)
    size = len(next(iter(values.values())))
    output: list[float | None] = [None] * size
    n = candidate.lookback
    kind = candidate.calculator
    if kind == "sma_direction":
        close = values["close"]
        for i in range(n - 1, size):
            output[i] = float(close[i] > fmean(close[i - n + 1 : i + 1]))
    elif kind == "time_series_momentum":
        close = values["close"]
        for i in range(n, size):
            output[i] = float(close[i] / close[i - n] - 1 > 0)
    elif kind == "previous_range_breakout":
        close, high = values["close"], values["high"]
        for i in range(n, size):
            output[i] = float(close[i] > max(high[i - n : i]))
    elif kind == "garman_klass_variance":
        opened, high, low, close = (values["open"], values["high"], values["low"], values["close"])
        coefficient = 2 * math.log(2) - 1
        components: list[float] = []
        for i in range(size):
            day_var = 0.5 * math.log(high[i] / low[i]) ** 2 - (
                coefficient * math.log(close[i] / opened[i]) ** 2
            )
            components.append(max(0.0, day_var))
            if i >= n - 1:
                output[i] = fmean(components[i - n + 1 : i + 1])
    else:
        raise ValueError("unsupported research signal")
    return tuple(output)


def _synthetic_prices() -> dict[str, tuple[float, ...]]:
    # At least 500 completed bars so long-lookback formulas actually calculate.
    close = tuple(10.0 + i * 0.02 + (i % 11) * 0.13 for i in range(530))
    return {
        "open": close,
        "high": tuple(x + 1 for x in close),
        "low": tuple(x - 1 for x in close),
        "close": close,
    }


def _reference_check(
    signal: IndicatorCandidate, obs: Numbers, actual: tuple[float | None, ...]
) -> bool:
    n = signal.lookback
    close = obs["close"]
    kind = signal.calculator
    if kind == "sma_direction":
        expected = tuple(
            None if t < n - 1 else float(n * close[t] > sum(close[t - n + 1 : t + 1]))
            for t in range(len(close))
        )
    elif kind == "time_series_momentum":
        expected = tuple(
            None if t < n else float(close[t] > close[t - n]) for t in range(len(close))
        )
    elif kind == "previous_range_breakout":
        high = obs["high"]
        expected = tuple(
            None if t < n else float(all(close[t] > high[k] for k in range(t - n, t)))
            for t in range(len(close))
        )
    elif kind == "garman_klass_variance":
        highs, lows, opens = obs["high"], obs["low"], obs["open"]
        components = [
            max(
                0.0,
                (math.log(highs[t]) - math.log(lows[t])) ** 2 / 2
                - (2 * math.log(2) - 1) * (math.log(close[t]) - math.log(opens[t])) ** 2,
            )
            for t in range(len(close))
        ]
        expected = tuple(
            None if t < n - 1 else sum(components[t - n + 1 : t + 1]) / n for t in range(len(close))
        )
    else:
        return False
    return all(
        (lhs is None and rhs is None)
        or (lhs is not None and rhs is not None and math.isclose(lhs, rhs, abs_tol=1e-12))
        for lhs, rhs in zip(actual, expected, strict=True)
    )


def verify_signal_on_synthetic_prices(candidate: IndicatorCandidate) -> VerificationResult:
    """Independent reference and prefix-extension checks; no remote or broker IO."""
    signal_hash = content_hash(candidate.model_dump(mode="json", exclude={"status"}))
    if candidate.scope != "single_asset":
        return VerificationResult(
            signal_hash=signal_hash,
            passed=False,
            math_reference=False,
            causal_prefix=False,
            missing_data=False,
            deterministic=False,
            bounded=True,
            error="PIT cross-sectional universe and independent baseline unavailable",
        )
    obs = _synthetic_prices()
    flags: dict[str, bool] = dict(
        math_reference=False,
        causal_prefix=False,
        missing_data=False,
        deterministic=False,
        bounded=False,
    )
    try:
        output = calculate_signal(candidate, obs)
        flags["math_reference"] = any(value is not None for value in output) and _reference_check(
            candidate, obs, output
        )
        flags["causal_prefix"] = all(
            calculate_signal(candidate, {k: v[:t] for k, v in obs.items()}) == output[:t]
            for t in range(1, len(output) + 1)
        )
        flags["deterministic"] = calculate_signal(candidate, obs) == output
        try:
            calculate_signal(
                candidate, {k: v[:-1] for k, v in obs.items() if k != candidate.required_fields[0]}
            )
        except ValueError:
            flags["missing_data"] = True
        flags["bounded"] = candidate.lookback <= 500 and len(obs["close"]) < 1_000_000
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        return VerificationResult(
            signal_hash=signal_hash,
            passed=False,
            math_reference=flags["math_reference"],
            causal_prefix=flags["causal_prefix"],
            missing_data=flags["missing_data"],
            deterministic=flags["deterministic"],
            bounded=flags["bounded"],
            error=type(exc).__name__,
        )
    return VerificationResult(
        signal_hash=signal_hash,
        passed=all(flags.values()),
        math_reference=flags["math_reference"],
        causal_prefix=flags["causal_prefix"],
        missing_data=flags["missing_data"],
        deterministic=flags["deterministic"],
        bounded=flags["bounded"],
    )
