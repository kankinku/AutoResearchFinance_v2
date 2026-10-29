"""A8 explicit-opt-in, causal chart/strategy research scalar and overlay bridge.

Not installed in the normal catalog or trading dashboard by default.
All supplied OHLC is development-only and sourced from one symbol.
A bar-close observation at t can first be consumed at t+1.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from math import isfinite
from pathlib import Path
from typing import Any, Literal, cast

from core.data.contracts import DataZone, MarketDataSet
from core.features.catalog import semantic_feature_id
from core.features.causal_pivots import CausalSwingConfig, CausalSwingTracker
from core.features.chart_patterns import PATTERNS, _recognize
from core.features.classical_lifecycle import CLASSICAL_PATTERNS, ClassicalLifecycle
from core.features.contracts import FeatureSpec
from core.features.harmonic_geometry import projected_reversal_zone
from core.integrity.hashes import content_hash

CLASSICAL_CHANNELS = (
    "detected",
    "stage",
    "quality",
    "neckline_distance",
    "distance_to_invalidation",
    "bars_since_confirmation",
)
HARMONIC_CHANNELS = ("detected", "stage", "distance_to_prz")
ELLIOTT_CHANNELS = ("detected", "stage")
RESEARCH_VERSION = "chart-research-a8-v1"
INPUTS = ("high", "low", "close")
_REPO = Path(__file__).resolve().parents[1]
_RESEARCH_FILES = (
    "research/chart_pattern_bridge.py",
    "core/features/classical_lifecycle.py",
    "core/features/harmonic_geometry.py",
    "core/features/elliott_structure.py",
    "core/features/causal_pivots.py",
    "core/features/chart_patterns.py",
)


def _source_hash() -> str:
    digest = hashlib.sha256()
    for name in _RESEARCH_FILES:
        digest.update(name.encode("utf-8"))
        digest.update((_REPO / name).read_bytes())
    return digest.hexdigest()


def chart_research_feature_specs() -> tuple[FeatureSpec, ...]:
    """44 distinct opt-in scalar outputs from 12 source pattern families."""
    implementation_hash = _source_hash()
    specs: list[FeatureSpec] = []
    for name in PATTERNS:
        channels = (
            CLASSICAL_CHANNELS
            if name in CLASSICAL_PATTERNS
            else HARMONIC_CHANNELS
            if name.startswith("harmonic_")
            else ELLIOTT_CHANNELS
        )
        for channel in channels:
            spec = FeatureSpec(
                name=f"chart_research_{name}_{channel}",
                family="chart_research",
                calculator="chart_research",
                inputs=INPUTS,
                lookback=160,
                lag_bars=0,
                parameters={
                    "pattern_name": name,
                    "channel": channel,
                    "confirmation_bars": 2,
                    "minimum_swing": 0.015,
                },
                timeframe="1d",
                version=RESEARCH_VERSION,
                status="REGISTERED",
                source_licenses=("original-research-only",),
                implementation_hash=implementation_hash,
                output_name=channel,
                formula=f"{RESEARCH_VERSION}({name},{channel},2,0.015)",
                data_contract="scalar",
                duplicate_group=f"chart-research-{name}",
            )
            specs.append(spec.model_copy(update={"canonical_id": semantic_feature_id(spec)}))
    return tuple(sorted(specs, key=lambda item: item.name))


def validate_optin_parameters(parameters: Mapping[str, object]) -> tuple[str, str]:
    if set(parameters) != {"pattern_name", "channel", "confirmation_bars", "minimum_swing"}:
        raise ValueError("A8 research features forbid unreviewed parameter overrides")
    pattern = parameters["pattern_name"]
    channel = parameters["channel"]
    if not isinstance(pattern, str) or pattern not in PATTERNS:
        raise ValueError("unknown A8 chart family")
    channels = (
        CLASSICAL_CHANNELS
        if pattern in CLASSICAL_PATTERNS
        else HARMONIC_CHANNELS
        if pattern.startswith("harmonic_")
        else ELLIOTT_CHANNELS
    )
    if not isinstance(channel, str) or channel not in channels:
        raise ValueError("unsupported A8 scalar channel")
    if type(parameters["confirmation_bars"]) is not int or parameters["confirmation_bars"] != 2:
        raise ValueError("non-versioned confirmation delay override")
    if (
        type(parameters["minimum_swing"]) not in (float, int)
        or float(cast(float | int, parameters["minimum_swing"])) != 0.015
    ):
        raise ValueError("non-versioned swing threshold override")
    return pattern, channel


def _aligned(
    inputs: Mapping[str, Sequence[float | None]],
) -> tuple[
    Sequence[float | None],
    Sequence[float | None],
    Sequence[float | None],
]:
    if set(inputs) != set(INPUTS):
        raise ValueError("A8 chart research expects only same-symbol OHLC")
    high, low, close = (inputs[k] for k in INPUTS)
    if len(high) != len(low) or len(high) != len(close):
        raise ValueError("unaligned research OHLC")
    return high, low, close


def calculate_chart_research(
    pattern: str,
    channel: str,
    inputs: Mapping[str, Sequence[float | None]],
) -> tuple[float, ...]:
    """Produce one finite scalar per completed bar; no backfilling."""
    validate_optin_parameters(
        {
            "pattern_name": pattern,
            "channel": channel,
            "confirmation_bars": 2,
            "minimum_swing": 0.015,
        }
    )
    high, low, close = _aligned(inputs)
    tracker = CausalSwingTracker(CausalSwingConfig())
    n = len(close)
    output = [0.0] * n
    lifecycle = ClassicalLifecycle(pattern) if pattern in CLASSICAL_PATTERNS else None
    last_confirmation = -1

    for t in range(n):
        decision = tracker.update(t, high[t], low[t], close[t])
        if lifecycle is not None:
            event = lifecycle.update(
                t,
                high[t],
                low[t],
                close[t],
                tracker.pivots if decision is not None and decision.kind == "APPEND" else (),
            )
            if channel == "detected" and event is not None and event.stage == "CONFIRMED":
                output[t] = float(event.direction)
            elif channel == "stage" and event is not None:
                output[t] = {
                    "CANDIDATE": 1.0,
                    "CONFIRMED": 2.0,
                    "INVALIDATED": -1.0,
                    "EXPIRED": -2.0,
                }[event.stage]
            elif channel == "quality" and lifecycle.active is not None:
                active = lifecycle.active
                pivot_prices = [p.value for p in active.pivots]
                if len(pivot_prices) == 3:
                    prominence = abs(pivot_prices[0] - pivot_prices[1])
                else:
                    prominence = abs(pivot_prices[2] - (pivot_prices[0] + pivot_prices[-1]) / 2)
                output[t] = min(1.0, prominence / max(abs(pivot_prices[0]), 1e-9))
            elif channel in ("distance_to_invalidation", "neckline_distance"):
                candidate = lifecycle.active
                if (
                    candidate is not None
                    and close[t] is not None
                    and isfinite(float(cast(float, close[t])))
                ):
                    price = float(cast(float, close[t]))
                    if channel == "distance_to_invalidation":
                        output[t] = max(
                            0.0,
                            ((price - candidate.invalidation_price) * candidate.direction)
                            / max(abs(price), 1e-9),
                        )
                    else:
                        output[t] = (
                            (price - candidate.neckline_at(t)) * candidate.direction
                        ) / max(abs(price), 1e-9)
            if event is not None and event.stage == "CONFIRMED":
                last_confirmation = t
            if channel == "bars_since_confirmation":
                output[t] = float(t - last_confirmation) if last_confirmation >= 0 else -1.0
            continue

        if decision is not None and decision.kind == "APPEND":
            pulse = _recognize(pattern, tracker.pivots)
            if pulse:
                if channel == "detected":
                    output[t] = float(pulse)
                elif channel == "stage":
                    output[t] = 2.0
        if pattern.startswith("harmonic_"):
            if channel in ("stage", "distance_to_prz") and close[t] is not None:
                xabc = tracker.pivots[-4:]
                if len(xabc) == 4:
                    zone = projected_reversal_zone(xabc, pattern)
                    if zone is not None and all(isfinite(x) for x in zone):
                        if channel == "stage" and output[t] == 0.0:
                            output[t] = 1.0
                        if channel == "distance_to_prz":
                            price = float(cast(float, close[t]))
                            output[t] = (
                                min(abs(price - zone[0]), abs(price - zone[1]))
                                / max(abs(price), 1e-9)
                                if not zone[0] <= price <= zone[1]
                                else 0.0
                            )
        elif channel == "stage" and output[t] == 0.0:
            required = {
                "elliott_impulse_5": 6,
                "elliott_abc": 4,
                "elliott_wxy": 10,
                "elliott_wxyxz": 16,
            }[pattern]
            if 2 <= len(tracker.pivots) < required:
                output[t] = 1.0
    if not all(isfinite(x) for x in output):
        raise ValueError("A8 scalar output not finite")
    return tuple(output)


def _market_scope(market: MarketDataSet) -> None:
    if market.zone != DataZone.DEVELOPMENT or market.timeframe != "1d":
        raise PermissionError("A8 only accepts same-symbol DEVELOPMENT daily bars")
    if not market.bars or len({bar.symbol for bar in market.bars}) != 1:
        raise PermissionError("A8 requires a single symbol and nonempty data")
    if market.calendar != "us_equities":
        raise PermissionError("A8 requires standard US daily bar alignment")


def overlay_payload(
    market: MarketDataSet,
    *,
    patterns: tuple[str, ...],
    allow_research: bool = False,
    generation: str | None = None,
    date_window: tuple[int, int] | None = None,
    data_kind: Literal["SYNTHETIC", "RESEARCH_DEVELOPMENT"] = "RESEARCH_DEVELOPMENT",
) -> dict[str, Any]:
    """Read-only chart DTO; event appears on known_at, not underlying pivot_at."""
    if not allow_research:
        raise PermissionError("A8 overlays are opt-in only")
    if data_kind not in ("SYNTHETIC", "RESEARCH_DEVELOPMENT"):
        raise ValueError("unrecognized A8 data provenance label")
    _market_scope(market)
    if (
        not patterns
        or len(set(patterns)) != len(patterns)
        or any(p not in PATTERNS for p in patterns)
    ):
        raise ValueError("invalid overlay pattern selection")
    if generation is not None and re.fullmatch(r"G[0-9]{1,6}", generation) is None:
        raise ValueError("generation must be a bounded G-number")
    n = len(market.bars)
    start, end = date_window if date_window is not None else (0, n)
    if not 0 <= start <= end <= n:
        raise ValueError("invalid visible bar range")
    values = {field: tuple(float(getattr(bar, field)) for bar in market.bars) for field in INPUTS}
    from core.features.classical_lifecycle import calculate_classical_events

    events = []
    for name in patterns:
        if name in CLASSICAL_PATTERNS:
            for event in calculate_classical_events(values, name):
                if not start <= event.known_at < end:
                    continue
                events.append(
                    {
                        "name": name,
                        "stage": event.stage,
                        "direction": event.direction,
                        "event_at": event.known_at,
                        "known_at": event.known_at,
                        "last_pivot_index": event.last_pivot_index,
                        "eligible_from": event.eligible_on_next_bar,
                        "neckline": event.neckline,
                        "invalidation_price": event.invalidation_price,
                        "event_id": event.event_id,
                        "pattern_id": event.pattern_id,
                    }
                )
        else:
            stream = calculate_chart_research(name, "detected", values)
            for t, value in enumerate(stream):
                if value and start <= t < end:
                    events.append(
                        {
                            "name": name,
                            "stage": "OUTER_GEOMETRY",
                            "direction": int(value),
                            "event_at": t,
                            "known_at": t,
                            "eligible_from": t + 1,
                            "last_pivot_index": t,
                            "event_id": f"a8:{name}:detected:{t}",
                        }
                    )
    pivot_engine = CausalSwingTracker(CausalSwingConfig())
    pivots = []
    for t, bar in enumerate(market.bars):
        event = pivot_engine.update(t, bar.high, bar.low, bar.close)
        if event is not None and event.pivot is not None and start <= event.known_at < end:
            pivots.append(
                {
                    "event_id": event.event_id,
                    "kind": event.kind,
                    "type": event.pivot.kind,
                    "pivot_at": event.pivot.index,
                    "known_at": event.known_at,
                    "price": event.pivot.value,
                }
            )
    events.sort(key=lambda e: (e["event_at"], e["name"], e["event_id"]))
    base: dict[str, Any] = {
        "schema": "chart-research-overlay-a8-v1",
        "opt_in": True,
        "source": "DEVELOPMENT_ONLY",
        "data_kind": data_kind,
        "version": RESEARCH_VERSION,
        "symbol": market.bars[0].symbol,
        "generation": generation,
        "visible_window": [start, end],
        "dataset_hash": market.dataset_hash,
        "feature_source_hash": _source_hash(),
        "events": events,
        "pivots": pivots,
        "bar_times": [b.timestamp.isoformat() for b in market.bars[start:end]],
        "series": {
            "close": [b.close for b in market.bars[start:end]],
        },
        "execution_trades": [],
        "execution_trades_status": "NOT_AVAILABLE_NO_SIMULATED_FILLED_TRADES",
        "note": "Event at known_at; pivot shape may predate first knowable observation.",
    }
    base["overlay_hash"] = content_hash(base)
    return base
