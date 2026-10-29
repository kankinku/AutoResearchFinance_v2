"""A9 phase2: read-only non-PIT development evidence + adverse cases.

No 2026 OOS file is ever loaded. The named source is a locked 2020-25
DEVELOPMENT snapshot. Detection frequency is not labeled precision.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.data.contracts import DataZone
from core.features.registry import research_feature_specs
from research.chart_pattern_bridge import calculate_chart_research
from research.llm.inherited_feature_compiler import (
    InheritedFeatureBindingError,
    _new_feature_vector,
)
from scripts.v3_chart_a9_phase2_development import (
    CORP_EVENT_SPLIT_BAR,
    DATA_SHA256,
    load_development_market,
    metamorphic_probes,
    summarize_development,
)
from strategy_ir.schema import FeatureRef
from tests.core.test_v3_chart_a9_phase1_quality import synthetic_scenarios


def test_frozen_development_source_contract_and_provenance() -> None:
    market, identity = load_development_market()
    assert market.zone == DataZone.DEVELOPMENT
    assert len(market.bars) == 1508
    assert {bar.symbol for bar in market.bars} == {"QQQ"}
    assert identity["parquet_sha256"] == DATA_SHA256
    assert identity["provider_confirmed"] is False
    assert identity["pit_status"] == "NON_PIT_DEVELOPMENT_ONLY"
    assert identity["window"] == ["2020-01-02", "2025-12-31"]
    assert identity["source_row_count"] == 1508
    assert identity["protected_2026_OOS_accessed"] is False
    assert len({bar.timestamp for bar in market.bars}) == 1508
    assert all(b.high >= max(b.open, b.close) for b in market.bars)
    assert all(b.low <= min(b.open, b.close) for b in market.bars)


def test_real_development_ref_and_default_disabled_and_sealed_guard() -> None:
    market, _ = load_development_market()
    feature = "chart_research_double_top_detected"
    ref = FeatureRef(feature_id=feature, timeframe="1d", lag_bars=0)
    with pytest.raises(InheritedFeatureBindingError):
        _new_feature_vector(ref, market)
    allowed = _new_feature_vector(ref, market, allow_chart_research=True)
    direct = calculate_chart_research(
        "double_top",
        "detected",
        {k: tuple(getattr(b, k) for b in market.bars) for k in ("high", "low", "close")},
    )
    assert allowed == direct
    delayed = _new_feature_vector(
        FeatureRef(feature_id=feature, timeframe="1d", lag_bars=1),
        market,
        allow_chart_research=True,
    )
    assert delayed[0] is None and delayed[1:] == direct[:-1]
    assert len(research_feature_specs()) == 487
    assert len(research_feature_specs(chart_research_opt_in=True)) == 531


def test_real_development_pattern_summary_is_reproducible_and_nonclairvoyant() -> None:
    market, _ = load_development_market()
    first = summarize_development(market)
    second = summarize_development(market)
    # Runtime durations vary by host scheduling; measurement/provenance does not.
    nondeterministic = {"runtime_median_ms", "runtime_p95_ms"}
    assert {k: v for k, v in first.items() if k not in nondeterministic} == {
        k: v for k, v in second.items() if k not in nondeterministic
    }
    assert len(first["families"]) == 12
    assert len(first["channels"]) == 44
    assert first["prefix_mismatches"] == 0
    assert first["prefix_checks"] >= 44 * 3
    assert first["overlay_violations"] == 0
    assert all(row["event_count"] >= 0 and row["per_1000_bars"] >= 0 for row in first["families"])
    assert all(row["nonfinite"] == 0 for row in first["channels"])
    assert all(
        row["known_at"] >= row["last_pivot_index"] and row["eligible_from"] == row["known_at"] + 1
        for row in first["selected_event_evidence"]
    )


def test_metamorphic_missing_flat_split_price_scale_and_spike_are_classified() -> None:
    probes = metamorphic_probes()
    assert probes["split_bar"] == CORP_EVENT_SPLIT_BAR
    assert probes["flat_prices"]["detected_signals"] == 0
    assert probes["missing_bar"]["lookahead_errors"] == 0
    assert probes["tied_pivots"]["detected_signals"] == 0
    assert probes["scaled_prices"]["input_bar_count"] >= 100
    assert probes["split_like_adjustment"]["explicitly_non_pit"] is True
    assert probes["single_spike"]["finite_outputs"] is True
    assert probes["invalid_high_low"]["rejected"] is True


def test_real_data_audit_report_has_no_ground_truth_claims() -> None:
    file = Path("docs/operations/quant-v3-chart-A9-phase2-development-audit-20261029.json")
    report = json.loads(file.read_text())
    assert report["schema"] == "quant-v3-chart-A9-phase2-development-v1"
    assert report["scope"] == "READ_ONLY_NON_PIT_DEVELOPMENT_NO_OOS"
    assert report["input"]["source_row_count"] == 1508
    assert report["summary"]["channels_evaluated"] == 44
    assert report["summary"]["families_evaluated"] == 12
    assert report["summary"]["prefix_mismatches"] == 0
    assert report["summary"]["overlay_violations"] == 0
    assert report["real_market_precision"] is None
    assert report["real_market_recall"] is None
    assert report["profitability"] is None
    assert report["release_authorized"] is False
    assert report["protected_paths_modified"] is False
    assert report["sealed_2026_OOS_accessed"] is False


def test_quick_small_scenario_no_nonfinite_outputs_after_price_scale() -> None:
    sample = synthetic_scenarios(112)["oscillating"]
    original = {key: sample[key] for key in ("high", "low", "close")}
    scaled = {key: tuple(v * 2 for v in values) for key, values in original.items()}
    for pattern in ("double_top", "double_bottom", "harmonic_bat", "elliott_abc"):
        for channel in ("detected", "stage"):
            a = calculate_chart_research(pattern, channel, original)
            b = calculate_chart_research(pattern, channel, scaled)
            assert len(a) == len(b) == 112
            assert all(math.isfinite(v) for v in a + b)
            assert a == b, (pattern, channel)
