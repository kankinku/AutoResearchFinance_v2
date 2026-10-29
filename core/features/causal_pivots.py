"""Research-only deterministic pivot/swing tracker with explicit knowledge time.

Only confirmed pivots are output. A candidate observed at i is eligible at
the close of i+confirmation_bars. The public event log is append-only:
a later, more extreme same-kind pivot REPLACES the *current state* but never
erases a previously published observation. Baseline percent mode preserves
the legacy chart_geometry feature values (see frozen pre-A4 oracle).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Literal

SwingMode = Literal["percent", "absolute", "atr"]
EventKind = Literal["APPEND", "REPLACE", "RESET"]


@dataclass(frozen=True)
class ConfirmedPivot:
    index: int
    value: float
    kind: str
    known_at: int


@dataclass(frozen=True)
class ProvisionalPivot:
    """Visible swing *candidate*, never a confirmed decision signal."""

    index: int
    value: float
    kind: str
    observed_at: int
    stage: Literal["DEVELOPING"] = "DEVELOPING"
    known_at: None = None


@dataclass(frozen=True)
class CausalSwingConfig:
    confirmation_bars: int = 2
    lookback: int = 160
    minimum_swing: float = 0.015
    mode: SwingMode = "percent"
    atr_period: int = 14

    def __post_init__(self) -> None:
        if self.mode not in ("percent", "absolute", "atr"):
            raise ValueError("unsupported swing threshold mode")
        if not (1 <= self.confirmation_bars <= 6 and 32 <= self.lookback <= 252):
            raise ValueError("out-of-range confirmation or lookback")
        if not isfinite(self.minimum_swing) or self.minimum_swing <= 0:
            raise ValueError("minimum_swing must be finite and positive")
        if self.mode == "percent" and self.minimum_swing > 0.25:
            raise ValueError("percent minimum_swing exceeds legacy contract")
        if not 2 <= self.atr_period <= 100:
            raise ValueError("bounded ATR period required")


@dataclass(frozen=True)
class PivotDecision:
    event_id: str
    kind: EventKind
    known_at: int
    pivot: ConfirmedPivot | None
    previous: ConfirmedPivot | None


@dataclass(frozen=True)
class _Candle:
    index: int
    high: float | None
    low: float | None
    close: float | None


def valid_candle(high: float | None, low: float | None, close: float | None) -> bool:
    """Identical validation contract to pre-A4 chart_patterns._valid_candle."""
    if high is None or low is None or close is None:
        return False
    h, low_value, c = float(high), float(low), float(close)
    return all(isfinite(v) for v in (h, low_value, c)) and h >= max(low_value, c) and low_value <= c


class CausalSwingTracker:
    """Bounded active history, immutable events, sequential confirmed observations."""

    def __init__(self, config: CausalSwingConfig) -> None:
        self.config = config
        self._window: deque[_Candle] = deque(maxlen=2 * config.confirmation_bars + 1)
        self._pivots: list[ConfirmedPivot] = []
        self._events: list[PivotDecision] = []
        self._atr_ranges: deque[float] = deque(maxlen=config.atr_period)
        self._previous_close: float | None = None
        self._next_index = 0
        self.last_decision: PivotDecision | None = None

    @property
    def pivots(self) -> tuple[ConfirmedPivot, ...]:
        return tuple(self._pivots)

    @property
    def events(self) -> tuple[PivotDecision, ...]:
        return tuple(self._events)

    @property
    def window(self) -> tuple[_Candle, ...]:
        return tuple(self._window)

    @property
    def provisional(self) -> ProvisionalPivot | None:
        """Last-bar candidate based only on bars already seen, never tradable."""
        c = self.config.confirmation_bars
        if len(self._window) < c + 1:
            return None
        recent = tuple(self._window)[-(c + 1) :]
        if not all(valid_candle(b.high, b.low, b.close) for b in recent):
            return None
        highs = [float(b.high) for b in recent if b.high is not None]
        lows = [float(b.low) for b in recent if b.low is not None]
        high_candidate = highs[-1] == max(highs) and highs.count(highs[-1]) == 1
        low_candidate = lows[-1] == min(lows) and lows.count(lows[-1]) == 1
        if high_candidate == low_candidate:
            return None
        bar = recent[-1]
        return ProvisionalPivot(
            index=bar.index,
            value=highs[-1] if high_candidate else lows[-1],
            kind="high" if high_candidate else "low",
            observed_at=bar.index,
        )

    def _event(
        self,
        kind: EventKind,
        at: int,
        pivot: ConfirmedPivot | None,
        previous: ConfirmedPivot | None,
    ) -> PivotDecision:
        event = PivotDecision(
            event_id=f"causal-pivot-v1:{at}:{kind}:{pivot.index if pivot else 'reset'}",
            kind=kind,
            known_at=at,
            pivot=pivot,
            previous=previous,
        )
        self._events.append(event)
        self.last_decision = event
        return event

    def _minimum_delta(self, prior: float) -> float | None:
        if self.config.mode == "percent":
            return self.config.minimum_swing * max(abs(prior), 1e-9)
        if self.config.mode == "absolute":
            return self.config.minimum_swing
        if len(self._atr_ranges) < self.config.atr_period:
            return None
        atr = sum(self._atr_ranges) / len(self._atr_ranges)
        return self.config.minimum_swing * atr

    def update(
        self,
        index: int,
        high: float | None,
        low: float | None,
        close: float | None,
    ) -> PivotDecision | None:
        """Observe one complete bar; never infer a pivot on a future bar."""
        if index != self._next_index:
            raise ValueError("a bar must be ingested exactly once and in order")
        self._next_index += 1
        candle = _Candle(index, high, low, close)
        self._window.append(candle)
        if valid_candle(high, low, close):
            assert high is not None and low is not None and close is not None
            true_range = float(high) - float(low)
            if self._previous_close is not None:
                true_range = max(
                    true_range,
                    abs(float(high) - self._previous_close),
                    abs(float(low) - self._previous_close),
                )
            self._atr_ranges.append(true_range)
            self._previous_close = float(close)
        else:
            self._previous_close = None
            self._atr_ranges.clear()

        c = self.config.confirmation_bars
        if len(self._window) < 2 * c + 1:
            return None
        if not all(valid_candle(b.high, b.low, b.close) for b in self._window):
            if self._pivots:
                previous = self._pivots[-1]
                self._pivots.clear()
                return self._event("RESET", index, None, previous)
            self._pivots.clear()
            return None
        highs = [float(b.high) for b in self._window if b.high is not None]
        lows = [float(b.low) for b in self._window if b.low is not None]
        is_high = highs[c] == max(highs) and highs.count(highs[c]) == 1
        is_low = lows[c] == min(lows) and lows.count(lows[c]) == 1
        if is_high == is_low:
            return None

        kind = "high" if is_high else "low"
        current_value = highs[c] if is_high else lows[c]
        pivot = ConfirmedPivot(self._window[c].index, current_value, kind, index)
        self._pivots = [p for p in self._pivots if p.index >= index - self.config.lookback]
        if self._pivots and self._pivots[-1].kind == kind:
            previous = self._pivots[-1]
            more_extreme = (
                current_value > previous.value if is_high else current_value < previous.value
            )
            if more_extreme:
                self._pivots[-1] = pivot
                return self._event("REPLACE", index, pivot, previous)
            return None
        if self._pivots:
            minimum = self._minimum_delta(self._pivots[-1].value)
            if minimum is None or abs(current_value - self._pivots[-1].value) < minimum:
                return None
        self._pivots.append(pivot)
        return self._event("APPEND", index, pivot, None)


class MultiScaleSwingTracker:
    """Multiple causal trackers share observations, never their pivot state."""

    def __init__(self, configurations: Mapping[str, CausalSwingConfig]) -> None:
        if not configurations or any(not key.strip() for key in configurations):
            raise ValueError("at least one named scale is required")
        self.trackers = {key: CausalSwingTracker(config) for key, config in configurations.items()}

    def update(
        self,
        index: int,
        high: float | None,
        low: float | None,
        close: float | None,
    ) -> dict[str, PivotDecision | None]:
        return {
            key: tracker.update(index, high, low, close) for key, tracker in self.trackers.items()
        }
