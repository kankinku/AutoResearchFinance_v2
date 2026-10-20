"""BOSWaves Trend Target Ribbon — causal indicator semantic port (Pine v6).

Copyright (c) BOSWaves, MPL-2.0: https://mozilla.org/MPL/2.0/
Independent Python adaptation of original trend, ribbon, target and visual
position logic. It is an indicator, not a strategy: no broker fills/orders,
and no claim of TradingView plot/alert parity or PIT/OOS profitability.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from math import exp, isfinite, sqrt


@dataclass(frozen=True)
class RibbonParams:
    alma_length: int = 34
    alma_offset: float = 0.85
    alma_sigma: float = 6.0
    deviation_length: int = 34
    deviation_multiplier: float = 0.65
    slope_length: int = 3
    slope_threshold: float = 0.08
    atr_length: int = 14
    structure_lookback: int = 12
    min_stop_atr: float = 0.75
    max_stop_atr: float = 3.0
    target_count: int = 4
    zone_pct: float = 0.06
    approach_r: float = 0.65
    projection_bars: int = 30
    keep_positions: int = 4

    def validate(self) -> None:
        if (
            min(self.alma_length, self.deviation_length, self.atr_length) < 5
            or not 1 <= self.slope_length <= 10
            or not 3 <= self.structure_lookback <= 50
            or not 2 <= self.target_count <= 4
            or not 1 <= self.keep_positions <= 5
            or not 10 <= self.projection_bars <= 100
            or not 0 <= self.alma_offset <= 1
            or self.alma_sigma <= 0
            or not 0.1 <= self.deviation_multiplier <= 3
            or not 0 <= self.slope_threshold <= 1
            or not 0.25 <= self.min_stop_atr <= 3
            or not 1 <= self.max_stop_atr <= 8
            or self.min_stop_atr > self.max_stop_atr
            or not 0.01 <= self.zone_pct <= 0.20
            or not 0.1 <= self.approach_r <= 1.5
        ):
            raise ValueError("BOSWaves Pine parameter bounds violated")
        if any(type(v) is bool or (isinstance(v, float) and not isfinite(v))
               for v in vars(self).values()):
            raise ValueError("nonfinite or boolean parameter")


@dataclass(frozen=True)
class RibbonBar:
    bar: int
    alma: float | None
    deviation: float | None
    atr: float | None
    slope: float | None
    trend: int
    flip: int
    conviction: float | None
    ribbon_edge: float | None
    ribbon_mid: float | None
    render_gap_on_flip: bool
    active_position_id: int | None
    stopped_now: bool
    newly_hit_targets: tuple[int, ...]


@dataclass(frozen=True)
class VisualPosition:
    position_id: int
    direction: int
    entry_bar: int
    entry_price: float
    stop_price: float
    risk_distance: float
    targets: tuple[float, ...]
    target_hit: tuple[bool, ...]
    end_bar: int | None
    end_reason: str | None
    zone_half_width: float
    projected_through_bar: int


@dataclass(frozen=True)
class RibbonResult:
    bars: tuple[RibbonBar, ...]
    visual_positions: tuple[VisualPosition, ...]
    source_kind: str = "PINE_V6_INDICATOR_SEMANTIC_ADAPTER"
    execution_semantics: str = "NO_ORDERS_NO_BACKTEST_NO_BROKER_EXECUTION"
    source_license: str = "MPL-2.0"
    tradingview_parity: str = "NOT_VERIFIED"


def compute_ribbon(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    *,
    params: RibbonParams | None = None,
    source: Sequence[float] | None = None,
) -> RibbonResult:
    """Compute causal close-bar signals and *visual* stop/target states.

    A flip is generated at the confirming close; the associated visual entry
    is the close, NOT an executable next-open fill. Stops are not triggered on
    an entry bar (Pine bar_index > entryBar). On a bar touching both an existing
    stop and target, the original renderer processes the stop first.
    """
    if params is None:
        params = RibbonParams()
    params.validate()
    n = len(close)
    if n != len(high) or n != len(low) or (source is not None and n != len(source)):
        raise ValueError("all signal input arrays must align")
    src = close if source is None else source
    if any(
        not all(isfinite(float(v)) for v in row)
        or row[0] < row[1]
        or not row[1] <= row[2] <= row[0]
        for row in zip(high, low, close, strict=True)
    ):
        raise ValueError("invalid OHLC bar")
    if any(not isfinite(float(v)) for v in src):
        raise ValueError("invalid source prices")

    length = params.alma_length
    center = params.alma_offset * (length - 1)
    width = length / params.alma_sigma
    weights = [exp(-((j - center) ** 2) / (2 * width * width))
               for j in range(length)]
    weight_total = sum(weights)
    true_ranges: list[float] = []
    atrs: list[float | None] = []
    almas: list[float | None] = []
    bars: list[RibbonBar] = []
    positions: list[VisualPosition] = []
    active: VisualPosition | None = None
    trend = 0

    for i in range(n):
        previous_close = close[i - 1] if i else close[i]
        tr = max(
            high[i] - low[i],
            abs(high[i] - previous_close),
            abs(low[i] - previous_close),
        )
        true_ranges.append(tr)
        if i == params.atr_length - 1:
            atr = sum(true_ranges[-params.atr_length:]) / params.atr_length
        elif i >= params.atr_length and atrs[-1] is not None:
            atr = (atrs[-1] * (params.atr_length - 1) + tr) / params.atr_length
        else:
            atr = None
        atrs.append(atr)

        if i >= length - 1:
            data = src[i - length + 1:i + 1]
            alma = sum(v * w for v, w in zip(data, weights, strict=True)) / weight_total
        else:
            alma = None
        almas.append(alma)

        if i >= params.deviation_length - 1:
            window = src[i - params.deviation_length + 1:i + 1]
            mean = sum(window) / len(window)
            deviation = sqrt(sum((x - mean) ** 2 for x in window) / len(window))
        else:
            deviation = None

        past_alma = almas[i - params.slope_length] if i >= params.slope_length else None
        slope = (
            (alma - past_alma) / atr if atr > 0 else 0.0
        ) if alma is not None and past_alma is not None and atr is not None else None
        flip = 0
        if slope is not None and deviation is not None and alma is not None:
            if (trend != 1 and slope > params.slope_threshold
                    and close[i] > alma + deviation * params.deviation_multiplier):
                trend, flip = 1, 1
            elif (trend != -1 and slope < -params.slope_threshold
                  and close[i] < alma - deviation * params.deviation_multiplier):
                trend, flip = -1, -1

        if (alma is None or atr is None or deviation is None or slope is None):
            conviction = edge = mid = None
        else:
            distance = abs(close[i] - alma) / atr if atr > 0 else 0.0
            conviction = max(0.0, min(1.0, abs(slope) * 2 + distance * 0.35))
            edge = (alma - deviation * 0.55 if trend == 1
                    else alma + deviation * 0.55 if trend == -1 else alma)
            mid = (alma + edge) / 2

        if flip:
            if active is not None and active.end_reason is None:
                active = replace(
                    active, end_bar=i, end_reason="REVERSED",
                    projected_through_bar=i,
                )
                positions[-1] = active
            # Pine ta.lowest/highest(..., lookback)[1] is na before
            # the full historical window exists. Do not shorten the
            # requested window and accidentally tighten the visual stop.
            structure = None
            if i >= params.structure_lookback:
                start = i - params.structure_lookback
                structure = (
                    min(low[start:i]) if flip == 1
                    else max(high[start:i])
                )
            raw_risk = (
                close[i] - structure if flip == 1 else structure - close[i]
            ) if structure is not None else None
            if atr is not None:
                low_risk = atr * params.min_stop_atr
                high_risk = atr * params.max_stop_atr
                risk = max(low_risk, min(high_risk, raw_risk if raw_risk is not None else low_risk))
                if risk > 0:
                    active = VisualPosition(
                        position_id=(positions[-1].position_id + 1 if positions else 1),
                        direction=flip,
                        entry_bar=i,
                        entry_price=close[i],
                        stop_price=close[i] - flip * risk,
                        risk_distance=risk,
                        targets=tuple(
                            close[i] + flip * risk * j
                            for j in range(1, params.target_count + 1)
                        ),
                        target_hit=(False,) * params.target_count,
                        end_bar=None,
                        end_reason=None,
                        zone_half_width=risk * params.zone_pct,
                        projected_through_bar=i + params.projection_bars,
                    )
                    positions.append(active)
                else:
                    active = None
            else:
                active = None

        stopped_now = False
        newly_hit: list[int] = []
        if active is not None and active.end_reason is None:
            # Pine only delays the stop check; visual targetHit updates
            # already run on the confirming flip bar.
            stopped_now = i > active.entry_bar and (
                (low[i] <= active.stop_price) if active.direction == 1
                else (high[i] >= active.stop_price)
            )
            if stopped_now:
                active = replace(
                    active, end_bar=i, end_reason="STOP_VISUAL",
                    projected_through_bar=i,
                )
                positions[-1] = active
            else:
                hit = list(active.target_hit)
                for j, target in enumerate(active.targets):
                    touched = (
                        high[i] >= target if active.direction == 1
                        else low[i] <= target
                    )
                    if touched and not hit[j]:
                        hit[j] = True
                        newly_hit.append(j + 1)
                active = replace(
                    active, target_hit=tuple(hit),
                    projected_through_bar=i + params.projection_bars,
                )
                positions[-1] = active
        bars.append(RibbonBar(
            i, alma, deviation, atr, slope, trend, flip, conviction,
            edge, mid, flip != 0,
            active.position_id if active is not None and active.end_reason is None else None,
            stopped_now, tuple(newly_hit),
        ))
    return RibbonResult(tuple(bars), tuple(positions[-params.keep_positions:]))
