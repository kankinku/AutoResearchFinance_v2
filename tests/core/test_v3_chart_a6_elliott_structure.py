"""A6 structural Elliott: chronological inner subwaves or no verified labels."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.features.causal_pivots import ConfirmedPivot
from core.features.elliott_structure import (
    WaveHypothesisStream,
    analyze_abc,
    analyze_combination,
    analyze_impulse,
)


def pivots(values: list[float]) -> tuple[ConfirmedPivot, ...]:
    return tuple(
        ConfirmedPivot(i * 20, float(value), "low" if i % 2 == 0 else "high", i * 20 + 2)
        for i, value in enumerate(values)
    )


def nested(start: ConfirmedPivot, end: ConfirmedPivot, legs: int) -> tuple[ConfirmedPivot, ...]:
    assert legs in (3, 5)
    weights = (0.30, -0.08, 0.34, -0.08, 0.52) if legs == 5 else (0.55, -0.15, 0.60)
    idx = [start.index] + [start.index + i * 3 for i in range(1, legs)] + [end.index]
    result = [start]
    price = start.value
    for i, weight in enumerate(weights):
        price += (end.value - start.value) * weight
        if i == legs - 1:
            result.append(end)
        else:
            result.append(
                ConfirmedPivot(
                    idx[i + 1],
                    round(price, 8),
                    "high" if weight * (end.value - start.value) > 0 else "low",
                    idx[i + 1] + 1,
                )
            )
    return tuple(result)


def subdivisions(
    points: tuple[ConfirmedPivot, ...], counts: tuple[int, ...]
) -> tuple[tuple[ConfirmedPivot, ...], ...]:
    return tuple(nested(points[i], points[i + 1], count) for i, count in enumerate(counts))


def test_impulse_progress_states_wave1_to_5() -> None:
    p = pivots([100, 110, 105, 122, 115, 130])
    for n in range(1, 6):
        result = analyze_impulse(p[: n + 1], decision_at=p[n].known_at)
        assert result.wave_number == n
        assert result.direction == 1
        assert result.stage == ("CONFIRMED" if n == 5 else "DEVELOPING")
        assert result.known_at == p[n].known_at
        assert not result.structurally_verified
        assert result.alternative_counts and len(result.alternative_counts) <= 3
        assert result.eligible_on_next_bar == p[n].known_at + 1


def test_bearish_impulse_mirror_and_wave3_shortest_and_overlap() -> None:
    up = pivots([100, 110, 105, 122, 115, 130])
    mirrored = tuple(ConfirmedPivot(q.index, 250 - q.value, q.kind, q.known_at) for q in up)
    x = analyze_impulse(mirrored)
    assert x.stage == "CONFIRMED" and x.direction == -1
    assert analyze_impulse(pivots([100, 110, 105, 111, 109, 128])).stage == "INVALIDATED"
    assert "WAVE3_SHORTEST" in analyze_impulse(pivots([100, 110, 105, 111, 109, 128])).violations
    assert "WAVE4_OVERLAPS_1" in analyze_impulse(pivots([100, 110, 105, 122, 108, 131])).violations
    assert "WAVE2_RETRACE_ORIGIN" in analyze_impulse(pivots([100, 110, 98])).violations


def test_impulse_5_3_5_3_5_nested_requirements_and_no_future_labels() -> None:
    p = pivots([100, 110, 105, 122, 115, 130])
    good = subdivisions(p, (5, 3, 5, 3, 5))
    result = analyze_impulse(p, subwaves=good)
    assert result.stage == "CONFIRMED" and result.structurally_verified
    incorrect = subdivisions(p, (3, 3, 5, 3, 5))
    bad = analyze_impulse(p, subwaves=incorrect)
    assert bad.stage == "INVALIDATED" and "SUBWAVE_TOPOLOGY" in bad.violations
    future = list(list(v) for v in good)
    child = future[2][2]
    future[2][2] = ConfirmedPivot(child.index, child.value, child.kind, p[-1].known_at + 1)
    late = analyze_impulse(p, subwaves=tuple(tuple(x) for x in future))
    assert late.stage == "INVALIDATED" and "SUBWAVE_NOT_KNOWN" in late.violations


def test_abc_zigzag_vs_flat_requires_inner_counts() -> None:
    zig = pivots([100, 110, 105, 116])
    zag = analyze_abc(zig, subdivisions(zig, (5, 3, 5)))
    assert zag.stage == "CONFIRMED" and zag.subtype == "ZIGZAG"
    assert zag.structurally_verified
    lacking = analyze_abc(zig)
    assert lacking.stage == "DEVELOPING" and not lacking.structurally_verified
    assert lacking.subtype == "OUTER_ONLY"
    flat = pivots([100, 110, 100.8, 111.5])
    flat_result = analyze_abc(flat, subdivisions(flat, (3, 3, 5)))
    assert flat_result.stage == "CONFIRMED" and flat_result.subtype == "FLAT"
    wrong = analyze_abc(zig, subdivisions(zig, (3, 3, 5)))
    assert wrong.stage == "INVALIDATED"
    assert "ABC_FAMILY_RATIO" in wrong.violations
    assert analyze_abc(flat, subdivisions(flat, (5, 3, 5))).stage == "INVALIDATED"


def test_wxy_wxyxz_nested_groups_and_connectors() -> None:
    p = pivots([100, 110, 105, 116, 106, 111, 99, 110, 105, 116, 106, 111, 99, 110, 105, 116])
    kinds = (5, 3, 5)
    units = tuple(subdivisions(p[3 * i : 3 * i + 4], kinds) for i in range(5))
    wxy = analyze_combination(p[:10], units[:3], count=3)
    assert wxy.stage == "CONFIRMED" and wxy.subtype == "W-X-Y"
    assert wxy.structurally_verified
    wxyxz = analyze_combination(p, units, count=5)
    assert wxyxz.stage == "CONFIRMED" and wxyxz.subtype == "W-X-Y-X-Z"
    missing = analyze_combination(p[:10], units[:2], count=3)
    assert missing.stage == "DEVELOPING" and not missing.structurally_verified
    wrong = analyze_combination(p[:10], (units[0], units[0], units[2]), count=3)
    assert wrong.stage == "INVALIDATED" and "CONNECTOR_MISMATCH" in wrong.violations


def test_known_at_causality_and_stream_immutable_history() -> None:
    p = pivots([100, 110, 105, 122, 115, 130])
    with pytest.raises(ValueError):
        analyze_impulse(p[:4], decision_at=p[3].known_at - 1)
    stream = WaveHypothesisStream(max_alternatives=3)
    history = []
    for point in p:
        result = stream.ingest(point)
        history.append(result)
        assert stream.history == tuple(history)
        assert all(x.known_at <= point.known_at for x in stream.history)
        assert all(len(x.alternative_counts) <= 3 for x in stream.history)
    assert stream.history[-1].stage == "CONFIRMED"
    with pytest.raises(ValueError):
        stream.ingest(p[-1])
    bad = ConfirmedPivot(140, 113, "low", 142)
    stream.ingest(bad)
    assert stream.history[-1].known_at == bad.known_at


def test_a6_machine_readable_gate_and_catalog_unchanged() -> None:
    evidence = json.loads(
        Path("docs/operations/quant-v3-chart-A6-elliott-acceptance-20261029.json").read_text()
    )
    assert evidence["feature_count"] == 447
    assert evidence["new_scalar_features"] == 0
    assert evidence["experimental_structure_api_only"]
    assert evidence["verified_subwave_topologies"] == {
        "impulse": "5-3-5-3-5",
        "zigzag": "5-3-5",
        "flat": "3-3-5",
    }
    assert evidence["causal_gate"]["timestamp_violations"] == 0
    assert evidence["causal_gate"]["prefix_mismatches"] == 0
    assert evidence["causal_gate"]["checkpoints"] >= 4608


def test_multiscale_fine_pivots_must_have_matching_observed_endpoints() -> None:
    from core.features.elliott_structure import analyze_multiscale_impulse, derive_subwaves

    outer = pivots([100, 110, 105, 122, 115, 130])
    inner = subdivisions(outer, (5, 3, 5, 3, 5))
    fine = tuple(p for leg in inner for p in leg[:-1]) + (inner[-1][-1],)
    aligned = derive_subwaves(outer, fine, (5, 3, 5, 3, 5))
    assert aligned == inner
    assert analyze_multiscale_impulse(outer, fine).structurally_verified
    # Remove a fast-scale turning point: do not hallucinate its missing subwave.
    omitted = tuple(p for p in fine if p.index != inner[2][2].index)
    inferred = analyze_multiscale_impulse(outer, omitted)
    assert inferred.stage == "CONFIRMED"
    assert not inferred.structurally_verified
    early = tuple(p for p in fine if p.known_at <= outer[-2].known_at)
    assert not analyze_multiscale_impulse(outer, early).structurally_verified


def test_multiscale_zigzag_flat_types_are_not_guessed_without_subwaves() -> None:
    from core.features.elliott_structure import analyze_multiscale_abc

    zig = pivots([100, 110, 105, 116])
    nested_zig = subdivisions(zig, (5, 3, 5))
    fine = tuple(p for leg in nested_zig for p in leg[:-1]) + (nested_zig[-1][-1],)
    assert analyze_multiscale_abc(zig, fine).subtype == "ZIGZAG"
    assert analyze_multiscale_abc(zig, fine).structurally_verified
    assert analyze_multiscale_abc(zig, fine[:6]).subtype == "OUTER_ONLY"
    flat = pivots([100, 110, 100.8, 111.5])
    children = subdivisions(flat, (3, 3, 5))
    fine_flat = tuple(p for leg in children for p in leg[:-1]) + (children[-1][-1],)
    assert analyze_multiscale_abc(flat, fine_flat).subtype == "FLAT"
    assert analyze_multiscale_abc(flat, fine_flat).structurally_verified
