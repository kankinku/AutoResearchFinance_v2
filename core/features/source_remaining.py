"""Causal scalar ports from pinned TA-Lib C and Stock Indicators C# sources."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import fmean

from core.features.contracts import FeatureSpec
from core.features.source_multi_backend import calculate_additional_source

Numbers = Sequence[float | None]
Data = Mapping[str, Numbers]
DEFINITIONS: tuple[tuple[str, str, tuple[str, ...], int, str], ...] = (
    ("talib_ibs", "momentum", ("high", "low", "close"), 2, "BSD-3-Clause"),
    ("talib_si", "price_action", ("open", "high", "low", "close"), 2, "BSD-3-Clause"),
    ("talib_asi", "price_action", ("open", "high", "low", "close"), 2, "BSD-3-Clause"),
    ("talib_frama", "trend", ("high", "low"), 20, "BSD-3-Clause"),
    ("stock_gator_upper", "momentum", ("high", "low"), 13, "Apache-2.0"),
    ("stock_gator_lower", "momentum", ("high", "low"), 13, "Apache-2.0"),
    ("stock_pmo", "momentum", ("close",), 35, "Apache-2.0"),
    ("stock_pmo_signal", "momentum", ("close",), 35, "Apache-2.0"),
    ("stock_roc_wb_upper", "volatility", ("close",), 20, "Apache-2.0"),
    ("stock_fcb_upper", "price_action", ("high", "low"), 2, "Apache-2.0"),
    ("stock_fcb_lower", "price_action", ("high", "low"), 2, "Apache-2.0"),
    ("stock_stddev_channel_upper_now", "trend", ("close",), 20, "Apache-2.0"),
    ("stock_stddev_channel_lower_now", "trend", ("close",), 20, "Apache-2.0"),
)
NAMES = frozenset(row[0] for row in DEFINITIONS)


def feature_specs() -> tuple[FeatureSpec, ...]:
    sources = {
        "BSD-3-Clause": "https://github.com/TA-Lib/ta-lib@4334163d3a1f5019aa9051342316b936a4dfb994",
        "Apache-2.0": "https://github.com/DaveSkender/Stock.Indicators@da428182d0e222339b662bc8ac645596102260bd",
    }
    return tuple(
        FeatureSpec(
            name=name,
            family=family,
            inputs=inputs,
            calculator="verified_remaining_formula",
            lookback=period,
            formula=f"{name}({', '.join(inputs)}, {period})",
            status="REGISTERED",
            duplicate_group=name,
            source_repositories=(sources[license_name],),
            source_licenses=(license_name,),
            data_contract="scalar",
        )
        for name, family, inputs, period, license_name in DEFINITIONS
    )


def _safe(values: Numbers, index: int) -> float | None:
    if index < 0 or index >= len(values):
        return None
    value = values[index]
    if value is None or not math.isfinite(float(value)):
        return None
    return float(value)


def _nonnull(value: float | None) -> float:
    if value is None:
        raise ValueError("missing output")
    return float(value)


def _span(values: Numbers, i: int, n: int) -> list[float] | None:
    if n < 1 or i < n - 1:
        return None
    data = [_safe(values, j) for j in range(i - n + 1, i + 1)]
    return None if any(v is None for v in data) else [float(v) for v in data if v is not None]


def _ema(data: Numbers, period: int, *, alpha: float | None = None) -> list[float | None]:
    alpha = 2 / (period + 1) if alpha is None else alpha
    current: float | None = None
    out: list[float | None] = [None] * len(data)
    for i, _ in enumerate(data):
        value = _safe(data, i)
        if value is None:
            current = None
            continue
        if current is None:
            window = _span(data, i, period)
            if window is not None:
                current = fmean(window)
        else:
            current = (1 - alpha) * current + alpha * value
        out[i] = current
    return out


def calculate_remaining(spec: FeatureSpec, raw: Data) -> tuple[float | None, ...]:
    name = spec.name
    if name not in NAMES or spec.calculator != "verified_remaining_formula":
        raise ValueError("unapproved feature")
    if not any(
        (k == name and inputs == spec.inputs and period == spec.lookback)
        for k, _, inputs, period, _ in DEFINITIONS
    ):
        raise ValueError("source signature mismatch")
    n = len(next(iter(raw.values())))
    if n > 1_000_000 or any(len(x) != n for x in raw.values()):
        raise ValueError("malformed alignment")
    output: list[float | None] = [None] * n
    hi = raw.get("high", ())
    lo = raw.get("low", ())
    op = raw.get("open", ())
    cl = raw.get("close", ())

    if name == "talib_ibs":
        for i in range(n):
            h, lval, c = _safe(hi, i), _safe(lo, i), _safe(cl, i)
            if None not in (h, lval, c):
                assert h is not None and lval is not None and c is not None
                output[i] = (c - lval) / (h - lval) if h > lval else 0.5
        return tuple(output)

    if name in ("talib_si", "talib_asi"):
        total = 0.0
        for i in range(1, n):
            earlier = [_safe(op, i - 1), _safe(cl, i - 1)]
            values = [_safe(series, i) for series in (op, hi, lo, cl)]
            if None in (*earlier, *values):
                total = 0.0
                continue
            prior_open, prior_close = (float(v) for v in earlier if v is not None)
            current_open, high, low, close = (float(v) for v in values if v is not None)
            body = close - current_open
            prior_body = prior_close - prior_open
            numerator = close - prior_close + 0.5 * body + 0.25 * prior_body
            up, down = abs(high - prior_close), abs(low - prior_close)
            movement = max(up, down)
            divisor = max(up - 0.5 * down, down - 0.5 * up, high - low)
            divisor += 0.25 * abs(prior_body)
            swing = 50 * numerator / divisor * (movement / 3.0) if divisor else 0.0
            total += swing
            output[i] = swing if name == "talib_si" else total
        return tuple(output)

    if name == "talib_frama":
        window = spec.lookback
        half = window // 2
        last: float | None = None
        for i in range(n):
            highs, lows = _span(hi, i, window), _span(lo, i, window)
            if highs is None or lows is None:
                continue
            price = (highs[-1] + lows[-1]) / 2
            last = price if last is None else last
            hi1, lo1 = max(highs[-half:]), min(lows[-half:])
            hi2, lo2 = max(highs[:-half]), min(lows[:-half])
            r1, r2 = hi1 - lo1, hi2 - lo2
            r = max(hi1, hi2) - min(lo1, lo2)
            if r > 0 and r1 > 0 and r2 > 0 and r1 + r2 > r:
                alpha = math.exp(-4.6 / math.log(2) * math.log((r1 + r2) / r))
                last = alpha * price + (1 - alpha) * last
            else:
                last = price
            output[i] = last
        return tuple(output)

    if name.startswith("stock_gator_"):
        jaw = calculate_additional_source("stock_alligator_jaw", raw, 13)
        teeth = calculate_additional_source("stock_alligator_teeth", raw, 8)
        lips = calculate_additional_source("stock_alligator_lips", raw, 5)
        for i in range(n):
            if name.endswith("upper"):
                if jaw[i] is not None and teeth[i] is not None:
                    output[i] = abs(_nonnull(jaw[i]) - _nonnull(teeth[i]))
            elif teeth[i] is not None and lips[i] is not None:
                output[i] = -abs(_nonnull(teeth[i]) - _nonnull(lips[i]))
        return tuple(output)

    if name.startswith("stock_fcb_"):
        # Source FCB is a delayed fractal confirmation, 2*span history.
        span = spec.lookback
        fractal_last: float | None = None
        for i in range(2 * span, n):
            fractal_values = hi if name.endswith("upper") else lo
            fractal_window = _span(fractal_values, i, 2 * span + 1)
            if fractal_window is not None:
                middle = fractal_window[span]
                others = fractal_window[:span] + fractal_window[span + 1 :]
                if name.endswith("upper") and middle > max(others):
                    fractal_last = middle
                elif name.endswith("lower") and middle < min(others):
                    fractal_last = middle
            output[i] = fractal_last
        return tuple(output)

    if name.startswith("stock_pmo"):
        roc: list[float | None] = [None] * n
        for i in range(1, n):
            previous, today = _safe(cl, i - 1), _safe(cl, i)
            if previous not in (None, 0) and today is not None:
                roc[i] = 100 * (today / float(previous) - 1)
        first = _ema(roc, 35, alpha=2 / 35)
        scaled = [None if v is None else v * 10 for v in first]
        double = _ema(scaled, 20, alpha=2 / 20)
        if name == "stock_pmo":
            return tuple(double)
        return tuple(_ema(double, 10))

    if name == "stock_roc_wb_upper":
        roc_band: list[float | None] = [None] * n
        for i in range(spec.lookback, n):
            current, previous = _safe(cl, i), _safe(cl, i - spec.lookback)
            if current is not None and previous not in (None, 0):
                roc_band[i] = 100 * (current / float(previous) - 1)
        for i in range(n):
            band_window = _span(roc_band, i, 5)
            if band_window is not None:
                output[i] = math.sqrt(fmean(v * v for v in band_window))
        return tuple(output)

    if name.startswith("stock_stddev_channel_"):
        # The original Stock Channels writes a completed regression backwards
        # over a span; the modified _now output never rewrites past observations.
        for i in range(n):
            reg_window = _span(cl, i, spec.lookback)
            if reg_window is None:
                continue
            k = len(reg_window)
            xm = (k - 1) / 2
            ym = fmean(reg_window)
            slope = sum((j - xm) * (v - ym) for j, v in enumerate(reg_window))
            slope /= sum((j - xm) ** 2 for j in range(k))
            center = ym + slope * xm
            std = math.sqrt(
                fmean((v - (ym + slope * (j - xm))) ** 2 for j, v in enumerate(reg_window))
            )
            output[i] = center + (2 if "upper" in name else -2) * std
        return tuple(output)
    raise ValueError("unknown remaining formula")
