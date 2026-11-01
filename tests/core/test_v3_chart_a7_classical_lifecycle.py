"""A7 classical geometry vs actionable neckline breakout, no repaint."""

from __future__ import annotations

import math

import pytest

from core.features.causal_pivots import ConfirmedPivot
from core.features.chart_patterns import classical_shape
from core.features.classical_lifecycle import (
    ClassicalLifecycle,
    assess_classical_candidate,
    replay_classical_lifecycle,
)


def points(values: tuple[float, ...], *, start_high: bool) -> tuple[ConfirmedPivot, ...]:
    return tuple(
        ConfirmedPivot(
            index=i * 5,
            value=price,
            kind="high" if ((i % 2 == 0) == start_high) else "low",
            known_at=i * 5 + 2,
        )
        for i, price in enumerate(values)
    )


SHAPES = {
    "double_top": points((110.0, 95.0, 111.0), start_high=True),
    "double_bottom": points((90.0, 110.0, 91.0), start_high=False),
    "head_shoulders": points((110.0, 100.0, 122.0, 101.0, 111.0), start_high=True),
    "inverse_head_shoulders": points((90.0, 100.0, 78.0, 99.0, 89.0), start_high=False),
}


@pytest.mark.parametrize("name", tuple(SHAPES))  # type: ignore[untyped-decorator]
def test_all_four_shapes_are_candidates_not_confirmed(name: str) -> None:
    result = assess_classical_candidate(SHAPES[name], name)
    assert result is not None
    assert result.name == name
    assert result.known_at == SHAPES[name][-1].known_at
    assert result.direction == (1 if name in ("double_bottom", "inverse_head_shoulders") else -1)
    assert result.pattern_id
    assert result.invalidation_price is not None
    assert result.neckline_at(result.known_at) > 0


def test_inverse_head_equal_or_shallower_is_rejected_without_false_signal() -> None:
    equal = points((100.0, 110.0, 100.0, 110.0, 100.0), start_high=False)
    shallower = points((100.0, 110.0, 101.0, 110.0, 100.0), start_high=False)
    for fixture in (equal, shallower):
        assert assess_classical_candidate(fixture, "inverse_head_shoulders") is None
        assert classical_shape(fixture, "inverse_head_shoulders") == 0
    valid = SHAPES["inverse_head_shoulders"]
    assert classical_shape(valid, "inverse_head_shoulders") == 1


def test_true_head_and_shoulders_mirrors_to_inverse_with_same_geometry() -> None:
    original = SHAPES["head_shoulders"]
    reflection = tuple(
        ConfirmedPivot(q.index, 200 - q.value, "low" if q.kind == "high" else "high", q.known_at)
        for q in original
    )
    inv = assess_classical_candidate(reflection, "inverse_head_shoulders")
    assert inv is not None and inv.direction == 1
    assert classical_shape(reflection, "inverse_head_shoulders") == 1


@pytest.mark.parametrize("name", tuple(SHAPES))  # type: ignore[untyped-decorator]
def test_only_next_bar_close_after_candidate_confirms_neckline(name: str) -> None:
    shape = SHAPES[name]
    state = ClassicalLifecycle(name, max_confirmation_bars=8)
    idx = shape[-1].known_at
    neck = assess_classical_candidate(shape, name)
    assert neck is not None
    # Candidate has a completed pivot but no confirmed neckline break yet.
    first = state.update(
        idx,
        neck.invalidation_price - 1 if neck.direction == -1 else neck.neckline_at(idx) + 1,
        neck.neckline_at(idx) - 1 if neck.direction == -1 else neck.invalidation_price + 1,
        neck.neckline_at(idx),
        shape,
    )
    assert first is not None and first.stage == "CANDIDATE"
    assert first.known_at == idx and first.eligible_on_next_bar == idx + 1
    assert state.events == (first,)
    # A legal next-bar *close* through neckline now confirms; shape isn't enough.
    breakout = neck.neckline_at(idx + 1) + 2 * neck.direction
    second = state.update(
        idx + 1,
        max(breakout + 1, neck.neckline_at(idx + 1) + 1),
        min(breakout - 1, neck.neckline_at(idx + 1) - 1),
        breakout,
        shape,
    )
    assert second is not None and second.stage == "CONFIRMED"
    assert second.known_at == idx + 1
    assert second.direction == neck.direction
    assert second.eligible_on_next_bar == idx + 2
    assert list(state.events) == [first, second]


def test_same_bar_invalid_and_breakout_must_choose_invalidation() -> None:
    shape = SHAPES["double_top"]
    engine = ClassicalLifecycle("double_top")
    at = shape[-1].known_at
    candidate = assess_classical_candidate(shape, "double_top")
    assert candidate is not None
    engine.update(at, 110.0, 95.0, 101.0, shape)
    result = engine.update(at + 1, 120.0, 90.0, 94.0, shape)
    assert result is not None and result.stage == "INVALIDATED"
    assert result.reason == "PRICE_INVALIDATION"
    assert all(e.stage != "CONFIRMED" for e in engine.events)


def test_invalidated_and_expired_events_preserve_old_candidate() -> None:
    shape = SHAPES["head_shoulders"]
    state = ClassicalLifecycle("head_shoulders", max_confirmation_bars=3)
    at = shape[-1].known_at
    first = state.update(at, 111.0, 102.0, 106.0, shape)
    assert first is not None and first.stage == "CANDIDATE"
    for t in (at + 1, at + 2):
        assert state.update(t, 111.0, 102.0, 106.0, shape) is None
    last = state.update(at + 3, 111.0, 102.0, 106.0, shape)
    assert last is not None and last.stage == "EXPIRED"
    assert list(state.events) == [first, last]
    assert state.active is None


def test_invalid_candle_cannot_complete_breakout() -> None:
    shape = SHAPES["double_top"]
    state = ClassicalLifecycle("double_top")
    at = shape[-1].known_at
    state.update(at, 111.0, 95.0, 100.0, shape)
    ended = state.update(at + 1, math.nan, 93.0, 94.0, shape)
    assert ended is not None and ended.stage == "INVALIDATED"
    assert ended.reason == "INVALID_BAR"


def test_frozen_history_and_prefix_replay_for_all_four_patterns() -> None:
    for name, shape in SHAPES.items():
        cand = assess_classical_candidate(shape, name)
        assert cand is not None
        n = shape[-1].known_at
        t = list(range(n + 7))
        candles = {"high": [110.0] * len(t), "low": [90.0] * len(t), "close": [100.0] * len(t)}
        events = replay_classical_lifecycle(cand, candles)
        for cutoff in range(n, len(t) + 1):
            prefix = {k: v[:cutoff] for k, v in candles.items()}
            assert replay_classical_lifecycle(cand, prefix) == tuple(
                event for event in events if event.known_at < cutoff
            )


def test_unverified_lookahead_shape_and_order_rejected() -> None:
    x = SHAPES["double_top"]
    assert assess_classical_candidate(x, "double_bottom") is None
    assert assess_classical_candidate(x, "double_top", decision_at=x[-1].known_at - 1) is None
    with pytest.raises(ValueError):
        ClassicalLifecycle("unregistered_pattern")


def interpolate_ohlc(anchors: tuple[float, ...]) -> dict[str, tuple[float, ...]]:
    """Complete synthetic OHLC bars; unique turning points five bars apart."""
    values: list[float] = []
    for start, end in zip(anchors[:-1], anchors[1:], strict=False):
        values.extend(start + (end - start) * step / 5 for step in range(5))
    values.append(anchors[-1])
    return {name: tuple(values) for name in ("high", "low", "close")}


EXAMPLES = {
    "double_top": (100.0, 110.0, 95.0, 111.0, 96.0, 90.0),
    "double_bottom": (100.0, 90.0, 105.0, 89.0, 104.0, 110.0),
    "head_shoulders": (100.0, 110.0, 100.0, 122.0, 101.0, 111.0, 99.0, 90.0),
    "inverse_head_shoulders": (100.0, 90.0, 100.0, 78.0, 99.0, 89.0, 101.0, 110.0),
}


@pytest.mark.parametrize("name", tuple(EXAMPLES))  # type: ignore[untyped-decorator]
def test_full_ohlc_pipeline_candidate_then_breakout_and_all_prefixes(name: str) -> None:
    from core.features.classical_lifecycle import calculate_classical_events

    data = interpolate_ohlc(EXAMPLES[name])
    full = calculate_classical_events(data, name)
    assert [event.stage for event in full] == ["CANDIDATE", "CONFIRMED"]
    first, confirmed = full
    assert confirmed.known_at > first.known_at
    assert confirmed.reason == "NECKLINE_CLOSE_BREAK"
    assert first.eligible_on_next_bar == first.known_at + 1
    assert confirmed.eligible_on_next_bar == confirmed.known_at + 1
    assert confirmed.pattern_id == first.pattern_id
    for cutoff in range(1, len(data["close"]) + 1):
        partial = {key: values[:cutoff] for key, values in data.items()}
        assert calculate_classical_events(partial, name) == tuple(
            e for e in full if e.known_at < cutoff
        ), (name, cutoff)


def test_a7_only_whitelisted_legacy_inverse_output_may_change() -> None:
    import json
    from pathlib import Path

    frozen = json.loads(
        Path("tests/core/fixtures/v3_chart_pre_a4_baseline_20261029.json").read_text()
    )
    corrected = json.loads(
        Path("tests/core/fixtures/v3_chart_a7_inverse_corrected_baseline_20261029.json").read_text()
    )
    assert corrected["baseline"] == frozen["schema"]
    assert corrected["changed_only"] == "inverse_head_shoulders"
    assert len(corrected["differences"]) == 4
    assert all(x["pattern"] == "inverse_head_shoulders" for x in corrected["differences"])


def test_a7_acceptance_evidence_is_reproducible() -> None:
    import json
    from pathlib import Path

    a7 = json.loads(
        Path("docs/operations/quant-v3-chart-A7-classical-acceptance-20261029.json").read_text()
    )
    assert a7["registered_feature_count"] == 447
    assert a7["versioned_scalar_diff"]["unchanged_against_A4_original"] == 44
    assert a7["versioned_scalar_diff"]["approved_inverse_HS_corrections"] == 4
    assert a7["versioned_scalar_diff"]["non_whitelisted_changes"] == 0
    assert a7["prefix_gate"]["event_history_changes"] == 0
    assert all(
        row["neckline_break_confirmed_at"] > row["candidate_at"] for row in a7["pattern_evidence"]
    )
