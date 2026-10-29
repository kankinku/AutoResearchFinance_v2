"""A4 acceptance: causal, bounded, versioned pivots and zero drift in chart signals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from core.features.causal_pivots import (
    CausalSwingConfig,
    CausalSwingTracker,
    ConfirmedPivot,
    MultiScaleSwingTracker,
    PivotDecision,
    SwingMode,
)
from core.features.chart_patterns import PATTERNS, calculate_chart_pattern
from scripts.v3_chart_a2_a3_stream_audit import build_scenarios
from tests.core.test_v3_causal_chart_patterns import bars

BASELINE = Path("tests/core/fixtures/v3_chart_pre_a4_baseline_20261029.json")


@pytest.mark.parametrize("pattern", PATTERNS)  # type: ignore[untyped-decorator]
def test_existing_12_chart_outputs_identical_to_frozen_pre_a4_oracle(pattern: str) -> None:
    reference = json.loads(BASELINE.read_text())
    cases = build_scenarios(190)
    cases["trend_wave"] = {k: tuple(v) for k, v in bars(190).items()}
    for label, candles in cases.items():
        current = calculate_chart_pattern(candles, pattern)
        canonical = json.dumps(current, allow_nan=False, separators=(",", ":"))
        assert (
            hashlib.sha256(canonical.encode()).hexdigest()
            == reference["signals"][label][pattern]["sha256"]
        ), (pattern, label)
        assert sum(v != 0.0 for v in current) == reference["signals"][label][pattern]["nonzero"]


def test_tracker_append_replace_event_log_retains_prior_publications() -> None:
    tracker = CausalSwingTracker(CausalSwingConfig(confirmation_bars=2))
    high = (10, 11, 14, 11, 12, 11, 17, 12, 11)
    for i, h in enumerate(high):
        tracker.update(i, float(h), 8.0, 9.0)
    assert tuple(e.kind for e in tracker.events) == ("APPEND", "REPLACE")
    first, replacement = tracker.events
    assert first.pivot == ConfirmedPivot(2, 14, "high", 4)
    assert replacement.previous == first.pivot
    assert replacement.pivot == ConfirmedPivot(6, 17, "high", 8)
    assert first.known_at == 4 and replacement.known_at == 8
    assert first.event_id != replacement.event_id
    assert tracker.pivots == (replacement.pivot,)
    assert tracker.last_decision == replacement
    assert first in tracker.events  # replacement cannot erase the prior knowledge event


def test_ill_formed_candle_is_never_used_as_a_confirmed_pivot() -> None:
    tracker = CausalSwingTracker(CausalSwingConfig())
    high = (10, 11, 14, 11, 12, 11, 17, 12, 11)
    for i, h in enumerate(high):
        close = None if i == 6 else 9.0
        tracker.update(i, float(h), 8.0, close)
    assert any(e.kind == "RESET" for e in tracker.events)
    assert tracker.pivots == ()


def test_ties_and_flat_price_do_not_emit_synthetic_swings() -> None:
    tracker = CausalSwingTracker(CausalSwingConfig())
    for i in range(64):
        assert tracker.update(i, 100.0, 100.0, 100.0) is None
    assert tracker.pivots == ()
    assert tracker.events == ()


def test_threshold_modes_percent_absolute_and_atr_causal() -> None:
    highs = (10, 11, 16, 11, 10, 11, 11, 11, 10)
    lows = (4, 4, 4, 4, 4, 4, 0, 4, 4)
    expected = {
        "percent": 2,
        "absolute": 1,
        "atr": 2,
    }
    for mode, threshold in (("percent", 0.015), ("absolute", 20.0), ("atr", 1.0)):
        tracker = CausalSwingTracker(
            CausalSwingConfig(mode=cast(SwingMode, mode), minimum_swing=threshold, atr_period=3)
        )
        for t, (h, low) in enumerate(zip(highs, lows, strict=True)):
            tracker.update(t, float(h), float(low), 5.0)
        assert len([x for x in tracker.events if x.kind == "APPEND"]) == expected[mode], mode


def test_multiscale_uses_independent_stream_state() -> None:
    engine = MultiScaleSwingTracker(
        {
            "fast": CausalSwingConfig(confirmation_bars=1, minimum_swing=0.01),
            "slow": CausalSwingConfig(confirmation_bars=3, minimum_swing=0.05),
        }
    )
    high = tuple(110 + 11 * (1 if i % 9 == 4 else 0) for i in range(90))
    for i, h in enumerate(high):
        engine.update(i, float(h), 90.0, 100.0)
    assert engine.trackers["fast"].config.confirmation_bars == 1
    assert engine.trackers["slow"].config.confirmation_bars == 3
    assert engine.trackers["fast"].events != engine.trackers["slow"].events
    assert all(
        e.pivot is None or e.known_at - e.pivot.index == 1 for e in engine.trackers["fast"].events
    )
    assert all(
        e.pivot is None or e.known_at - e.pivot.index == 3 for e in engine.trackers["slow"].events
    )


def test_streaming_has_no_time_travel_and_bounded_active_history() -> None:
    candles = build_scenarios(420)["oscillating"]
    conf = CausalSwingConfig(confirmation_bars=2, lookback=32)
    tracker = CausalSwingTracker(conf)
    previous: tuple[PivotDecision, ...] = ()
    for i in range(420):
        tracker.update(i, candles["high"][i], candles["low"][i], candles["close"][i])
        assert len(tracker.window) <= 5
        assert all(p.known_at <= i and p.known_at == p.index + 2 for p in tracker.pivots)
        assert tuple(tracker.events[: len(previous)]) == previous
        previous = tracker.events
    assert all(x.pivot is None or x.pivot.known_at == x.known_at for x in tracker.events)
    assert all(x.event_id for x in tracker.events)


def test_bad_parameter_or_skipped_bar_rejected() -> None:
    with pytest.raises(ValueError):
        CausalSwingConfig(mode="wrong")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CausalSwingConfig(confirmation_bars=0)
    tracker = CausalSwingTracker(CausalSwingConfig())
    with pytest.raises(ValueError):
        tracker.update(1, 10.0, 8.0, 9.0)


def test_provisional_pivot_stays_unconfirmed_until_right_bars_close() -> None:
    tracker = CausalSwingTracker(CausalSwingConfig(confirmation_bars=2))
    high = (10.0, 11.0, 14.0, 11.0, 12.0)
    tracker.update(0, high[0], 8.0, 9.0)
    tracker.update(1, high[1], 8.0, 9.0)
    candidate = tracker.update(2, high[2], 8.0, 9.0)
    assert candidate is None
    developing = tracker.provisional
    assert developing is not None
    assert developing.index == 2 and developing.observed_at == 2
    assert developing.stage == "DEVELOPING" and developing.known_at is None
    assert tracker.pivots == ()
    assert tracker.events == ()
    tracker.update(3, high[3], 8.0, 9.0)
    result = tracker.update(4, high[4], 8.0, 9.0)
    assert result is not None and result.kind == "APPEND"
    assert result.known_at == 4
    assert result.pivot == ConfirmedPivot(2, 14.0, "high", 4)
