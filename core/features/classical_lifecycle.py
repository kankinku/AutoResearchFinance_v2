"""A7 research-only classical chart geometry and causal neckline confirmation.

Price/geometry threshold choices are independent heuristics, not trade advice.
A confirmed pivot shape is only a CANDIDATE. CONFIRMED requires a subsequent
completed bar *close* crossing its projected neckline. No backdated events.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from core.features.causal_pivots import (
    CausalSwingConfig,
    CausalSwingTracker,
    ConfirmedPivot,
    valid_candle,
)

CLASSICAL_PATTERNS = (
    "double_top",
    "double_bottom",
    "head_shoulders",
    "inverse_head_shoulders",
)

LifecycleStage = Literal["CANDIDATE", "CONFIRMED", "INVALIDATED", "EXPIRED"]


@dataclass(frozen=True)
class ClassicalCandidate:
    pattern_id: str
    name: str
    direction: int
    known_at: int
    last_pivot_index: int
    pivots: tuple[ConfirmedPivot, ...]
    invalidation_price: float
    neckline_left_index: int
    neckline_left_value: float
    neckline_right_index: int
    neckline_right_value: float

    def neckline_at(self, index: int) -> float:
        if self.neckline_right_index == self.neckline_left_index:
            return self.neckline_right_value
        fraction = (index - self.neckline_left_index) / (
            self.neckline_right_index - self.neckline_left_index
        )
        return self.neckline_left_value + fraction * (
            self.neckline_right_value - self.neckline_left_value
        )


@dataclass(frozen=True)
class ClassicalEvent:
    event_id: str
    pattern_id: str
    name: str
    stage: LifecycleStage
    direction: int
    known_at: int
    eligible_on_next_bar: int
    neckline: float
    invalidation_price: float
    last_pivot_index: int
    reason: str


def assess_classical_candidate(
    pivots: Sequence[ConfirmedPivot],
    name: str,
    *,
    decision_at: int | None = None,
) -> ClassicalCandidate | None:
    """Validate candidate geometry only; no assertion of breakout here."""
    if name not in CLASSICAL_PATTERNS:
        raise ValueError("unknown classical pattern")
    size = 3 if name in ("double_top", "double_bottom") else 5
    if len(pivots) != size:
        return None
    if any(not isfinite(float(p.value)) for p in pivots):
        return None
    if any(
        a.index >= b.index or a.known_at > b.known_at
        for a, b in zip(pivots, pivots[1:], strict=False)
    ):
        return None
    observed = max(p.known_at for p in pivots)
    if decision_at is not None and observed > decision_at:
        return None
    start_high = name in ("double_top", "head_shoulders")
    for i, point in enumerate(pivots):
        expected = "high" if (i % 2 == 0) == start_high else "low"
        if point.kind != expected:
            return None
    prices = tuple(p.value for p in pivots)
    down = start_high
    direction = -1 if down else 1
    if size == 3:
        a, neck, last = prices
        denom = max(abs(a), abs(last), 1.0)
        if abs(a - last) / denom > 0.035:
            return None
        depth = (min(a, last) - neck if down else neck - max(a, last)) / denom
        if depth < 0.025:
            return None
        invalidation = max(a, last) if down else min(a, last)
        left = right = pivots[1]
    else:
        left_shoulder, left_neck, head, right_neck, right_shoulder = prices
        denom = max(abs(left_shoulder), abs(right_shoulder), 1.0)
        if abs(left_shoulder - right_shoulder) / denom > 0.05:
            return None
        prominence = (
            head - max(left_shoulder, right_shoulder)
            if down
            else min(left_shoulder, right_shoulder) - head
        ) / denom
        if prominence <= 0.03:
            return None
        if down:
            if not (
                left_neck < min(left_shoulder, head) and right_neck < min(head, right_shoulder)
            ):
                return None
        elif not (left_neck > max(left_shoulder, head) and right_neck > max(head, right_shoulder)):
            return None
        if abs(left_neck - right_neck) / max(abs(left_neck), abs(right_neck), 1.0) > 0.06:
            return None
        invalidation = (
            max(left_shoulder, head, right_shoulder)
            if down
            else min(left_shoulder, head, right_shoulder)
        )
        left, right = pivots[1], pivots[3]
    return ClassicalCandidate(
        pattern_id=f"classical-v1:{name}:{','.join(str(p.index) for p in pivots)}",
        name=name,
        direction=direction,
        known_at=observed,
        last_pivot_index=pivots[-1].index,
        pivots=tuple(pivots),
        invalidation_price=invalidation,
        neckline_left_index=left.index,
        neckline_left_value=left.value,
        neckline_right_index=right.index,
        neckline_right_value=right.value,
    )


class ClassicalLifecycle:
    """One-pattern, append-only research event state machine; no order code."""

    def __init__(self, name: str, max_confirmation_bars: int = 40) -> None:
        if name not in CLASSICAL_PATTERNS:
            raise ValueError("unregistered classical pattern")
        if not 1 <= max_confirmation_bars <= 252:
            raise ValueError("max_confirmation_bars out of range")
        self.name = name
        self.max_confirmation_bars = max_confirmation_bars
        self._history: list[ClassicalEvent] = []
        self._seen: set[str] = set()
        self.active: ClassicalCandidate | None = None
        self._last_bar: int | None = None

    @property
    def events(self) -> tuple[ClassicalEvent, ...]:
        return tuple(self._history)

    def _publish(
        self, stage: LifecycleStage, t: int, candidate: ClassicalCandidate, reason: str
    ) -> ClassicalEvent:
        evt = ClassicalEvent(
            event_id=f"{candidate.pattern_id}:{stage}:{t}",
            pattern_id=candidate.pattern_id,
            name=self.name,
            stage=stage,
            direction=candidate.direction,
            known_at=t,
            eligible_on_next_bar=t + 1,
            neckline=candidate.neckline_at(t),
            invalidation_price=candidate.invalidation_price,
            last_pivot_index=candidate.last_pivot_index,
            reason=reason,
        )
        self._history.append(evt)
        return evt

    def update(
        self,
        t: int,
        high: float | None,
        low: float | None,
        close: float | None,
        pivots: Sequence[ConfirmedPivot] = (),
    ) -> ClassicalEvent | None:
        """Called once after full bar t close; rejects missing or skipped bars."""
        if self._last_bar is not None and t != self._last_bar + 1:
            raise ValueError("non-sequential observed OHLC bar")
        self._last_bar = t
        ok = valid_candle(high, low, close)
        if self.active is not None:
            active = self.active
            if not ok:
                self.active = None
                return self._publish("INVALIDATED", t, active, "INVALID_BAR")
            assert high is not None and low is not None and close is not None
            # If both neckline breaks and price exceeds invalidation within
            # the same bar, conservatively invalidate rather than assume a fill.
            invalidated = (
                float(high) > active.invalidation_price
                if active.direction == -1
                else float(low) < active.invalidation_price
            )
            if invalidated:
                self.active = None
                return self._publish("INVALIDATED", t, active, "PRICE_INVALIDATION")
            neckline = active.neckline_at(t)
            crossed = float(close) < neckline if active.direction == -1 else float(close) > neckline
            if t > active.known_at and crossed:
                self.active = None
                return self._publish("CONFIRMED", t, active, "NECKLINE_CLOSE_BREAK")
            if t - active.known_at >= self.max_confirmation_bars:
                self.active = None
                return self._publish("EXPIRED", t, active, "CONFIRMATION_TIMEOUT")
        if not ok or self.active is not None:
            return None
        count = 3 if self.name in ("double_top", "double_bottom") else 5
        tail = tuple(pivots[-count:])
        if len(tail) != count or tail[-1].known_at != t:
            return None
        candidate = assess_classical_candidate(tail, self.name, decision_at=t)
        if candidate is None or candidate.pattern_id in self._seen:
            return None
        self._seen.add(candidate.pattern_id)
        self.active = candidate
        return self._publish("CANDIDATE", t, candidate, "PIVOT_SHAPE_ONLY")


def replay_classical_lifecycle(
    candidate: ClassicalCandidate,
    candles: Mapping[str, Sequence[float | None]],
    *,
    max_confirmation_bars: int = 40,
) -> tuple[ClassicalEvent, ...]:
    """Synthetic prefix replay: publish a known candidate on its known_at only."""
    high, low, close = (candles[k] for k in ("high", "low", "close"))
    if len(high) != len(low) or len(high) != len(close):
        raise ValueError("unaligned OHLC")
    tracker = ClassicalLifecycle(candidate.name, max_confirmation_bars)
    for t in range(len(close)):
        observed = candidate.pivots if t == candidate.known_at else ()
        tracker.update(t, high[t], low[t], close[t], observed)
    return tracker.events


def calculate_classical_events(
    inputs: Mapping[str, Sequence[float | None]],
    name: str,
    *,
    confirmation_bars: int = 2,
    lookback: int = 160,
    minimum_swing: float = 0.015,
    max_confirmation_bars: int = 40,
) -> tuple[ClassicalEvent, ...]:
    """End-to-end research-only scan using only confirmed causal swing pivots."""
    c = CausalSwingTracker(
        CausalSwingConfig(
            confirmation_bars=confirmation_bars,
            lookback=lookback,
            minimum_swing=minimum_swing,
        )
    )
    tracker = ClassicalLifecycle(name, max_confirmation_bars)
    high, low, close = (inputs[k] for k in ("high", "low", "close"))
    if len(high) != len(low) or len(high) != len(close):
        raise ValueError("unaligned OHLC")
    for t, (h, low_value, price) in enumerate(zip(high, low, close, strict=True)):
        swing = c.update(t, h, low_value, price)
        pivots = c.pivots if swing is not None and swing.kind == "APPEND" else ()
        tracker.update(t, h, low_value, price, pivots)
    return tracker.events
