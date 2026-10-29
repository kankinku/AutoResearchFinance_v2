"""A2 original source rules and A3 full bar-by-bar causal feature evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.features.chart_patterns as patterns
from core.features.registry import research_feature_specs
from scripts.v3_chart_a2_a3_stream_audit import (
    A2_RULES,
    build_scenarios,
    reproduce,
    stream_prefix_gate,
)

A2 = Path("docs/operations/quant-v3-chart-A2-verified-ratio-rules-20261029.json")
A3 = Path("docs/operations/quant-v3-chart-A3-causal-stream-gate-20261029.json")


def test_a2_deep_rule_matrix_has_all_12_and_primary_source_links() -> None:
    evidence = json.loads(A2.read_text())
    by_name = {x["name"]: x for x in evidence["registered_rules"]}
    assert set(by_name) == set(patterns.PATTERNS) == set(A2_RULES)
    assert len(evidence["proposed_not_implemented"]) == 18
    assert all(x["source_urls"] and x["formula_deltas"] for x in by_name.values())
    assert all(
        x["commercial_license_verdict"] != "CLEARED"
        for x in by_name.values()
        if x["name"].startswith("harmonic_")
    )
    assert (
        by_name["harmonic_gartley"]["formula_deltas"]["cd_to_bc"]["status"] == "MISSING_SOURCE_GATE"
    )


def test_a3_evidence_covers_all_patterns_regimes_and_prefixes() -> None:
    evidence = json.loads(A3.read_text())
    assert len(evidence["regimes"]) >= 3
    assert set(evidence["pattern_names"]) == set(patterns.PATTERNS)
    assert all(set(x["patterns"]) == set(patterns.PATTERNS) for x in evidence["regimes"])
    assert evidence["summary"]["prefix_mismatches"] == 0
    assert evidence["summary"]["timestamp_violations"] == 0
    assert evidence["summary"]["runtime_errors"] == 0
    assert evidence["summary"]["checkpoints"] > 500


@pytest.mark.parametrize("pattern", patterns.PATTERNS)
def test_full_incremental_stream_equals_batch_for_each_pattern(pattern: str) -> None:
    cases = build_scenarios(112)
    assert cases
    for label, data in cases.items():
        result = stream_prefix_gate(pattern, data, confirmation_bars=2)
        assert result["prefix_mismatches"] == 0, (pattern, label)
        assert result["timestamp_violations"] == 0, (pattern, label)
        assert result["runtime_error"] is None, (pattern, label)


def test_a3_prefix_and_event_trace_over_one_bar_mutations(monkeypatch: pytest.MonkeyPatch) -> None:
    data = build_scenarios(175)["oscillating"]
    original = patterns._recognize
    observed: list[tuple[int, int]] = []

    def spy(name: str, pivots: list[patterns.ConfirmedPivot]) -> int:
        result = original(name, pivots)
        if result:
            last = pivots[-1]
            observed.append((last.index, last.known_at))
        return result

    monkeypatch.setattr(patterns, "_recognize", spy)
    values = patterns.calculate_chart_pattern(data, "elliott_abc", confirmation_bars=2)
    assert observed
    assert all(observed_index + 2 == known for observed_index, known in observed)
    assert all(values[known] != 0 for _, known in observed)
    assert all(values[t] == 0 for t in range(4))
    assert len(values) == 175
    # Historical t cannot change when only future close/high/low beyond t is changed.
    altered = {k: list(v) for k, v in data.items()}
    t = 80
    for j in range(t + 1, 175):
        altered["high"][j] = 800.0 + j
        altered["low"][j] = 5.0
        altered["close"][j] = 400.0 + j
    mutated = patterns.calculate_chart_pattern(altered, "elliott_abc")
    assert values[: t + 1] == mutated[: t + 1]


def test_feature_refs_remain_registered_without_any_new_live_order_paths() -> None:
    registered = {s.name: s for s in research_feature_specs()}
    assert len(registered) == 447
    for name in patterns.PATTERNS:
        spec = registered[f"chart_{name}"]
        assert spec.inputs == ("high", "low", "close")
        assert spec.data_contract == "scalar"
        assert spec.status == "REGISTERED"
        assert spec.parameters["confirmation_bars"] == 2
    assert reproduce(strict=False, short=True)["summary"]["prefix_mismatches"] == 0
