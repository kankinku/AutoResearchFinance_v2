"""A9 partial synthetic audit: reproducibility, positive/negative oracle, regime limits."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.features.registry import research_feature_specs
from research.chart_pattern_bridge import (
    calculate_chart_research,
    chart_research_feature_specs,
)
from scripts.v3_chart_a9_phase1_audit import (
    RANGE_NAMES,
    goldens,
    run_audit,
    synthetic_scenarios,
)


def test_a9_evidence_is_a_partial_not_market_release_gate() -> None:
    file = Path("docs/operations/quant-v3-chart-A9-phase1-synthetic-audit-20261029.json")
    report = json.loads(file.read_text())
    assert report["scope"] == "SYNTHETIC_ONLY_PHASE1_NOT_COMPLETE_A9"
    assert report["registered_default"] == 447  # frozen A9-phase1 artifact
    assert len(research_feature_specs()) == 487
    assert report["registered_research_opt_in"] == 491
    assert report["research_scalar_channels"] == 44
    assert report["pattern_families"] == 12
    assert report["scenarios"] == list(RANGE_NAMES)
    assert report["summary"]["scalar_vectors_evaluated"] == 264
    assert report["summary"]["prefix_checks"] == 1056
    assert report["summary"]["prefix_mismatches"] == 0
    assert report["summary"]["nonfinite_values"] == 0
    assert report["market_precision"] is None
    assert report["market_recall"] is None
    assert report["net_profit"] is None
    assert report["validation_layers"]["protected_2026_OOS"] == "NOT_ACCESSED"


def test_a9_golden_cases_are_explicit_and_all_pass() -> None:
    named = goldens()
    assert len(named["harmonic_positive"]) == len(named["harmonic_negative"]) == 4
    assert len(named["classical_positive"]) == len(named["classical_negative"]) == 4
    assert len(named["elliott_structure_positive"]) == 5
    assert all(named["elliott_structure_positive"].values())
    assert named["elliott_structure_negative"]["impulse_wave3_shortest"] == "INVALIDATED"


def test_price_scenario_reproducibility_and_volumes_not_masquerading_as_inputs() -> None:
    first = synthetic_scenarios(96)
    second = synthetic_scenarios(96)
    assert first == second
    assert all(len(data["close"]) == 96 for data in first.values())
    quiet = first["quiet_low_liquidity"]
    assert all(v == 10.0 for v in quiet["volume"])
    assert all(v == 1000.0 for v in first["shock"]["volume"])
    source = {k: quiet[k] for k in ("high", "low", "close")}
    same_ohlc_other_volume = {**source, "volume": (10000.0,) * 96}
    detect = calculate_chart_research("double_top", "detected", source)
    # The standalone A8 API deliberately rejects volume rather than pretending
    # volume changes can be inferred as an effect on price-action output.
    with pytest.raises(ValueError):
        calculate_chart_research("double_top", "detected", same_ohlc_other_volume)
    assert len(detect) == 96 and all(math.isfinite(x) for x in detect)


@pytest.mark.parametrize("regime", RANGE_NAMES)  # type: ignore[untyped-decorator]
def test_all_research_scalar_channels_finite_and_prefix_stable(regime: str) -> None:
    data = synthetic_scenarios(112)[regime]
    inputs = {key: data[key] for key in ("high", "low", "close")}
    for spec in chart_research_feature_specs():
        name = str(spec.parameters["pattern_name"])
        channel = str(spec.parameters["channel"])
        observed = calculate_chart_research(name, channel, inputs)
        assert len(observed) == 112
        assert all(math.isfinite(v) for v in observed)
        for cutoff in (32, 78, 112):
            part = {key: vec[:cutoff] for key, vec in inputs.items()}
            assert calculate_chart_research(name, channel, part) == observed[:cutoff]


def test_synthetic_phase_audit_recomputes_without_writing_to_source() -> None:
    a = run_audit(n=72, save=False)
    b = run_audit(n=72, save=False)
    assert a["registered_default"] == b["registered_default"] == 487
    assert a["summary"]["prefix_mismatches"] == b["summary"]["prefix_mismatches"] == 0
    assert a["summary"]["scalar_vectors_evaluated"] == 264
    assert b["summary"]["scalar_vectors_evaluated"] == 264
    assert [x["hash"] for x in a["scalar_rows"]] == [x["hash"] for x in b["scalar_rows"]]
