"""The exact 34+6 source output set must be executable, causal and unchanged."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from research.llm.inherited_feature_compiler import _new_feature_vector
from scripts.v3_audit_82_formula_overlap import get_source_output
from scripts.v3_audit_335_features import synthetic
from strategy_ir.schema import FeatureRef

COHORT = Path("core/features/bulk40_manifest.json")
AUDIT = Path("docs/operations/quant-v3-82-formula-overlap-audit-20261029.json")
PRIOR_COUNT = 447  # A10: 435 legacy + 12 causal chart
NEW_COUNT = 40


def selected() -> list[dict[str, object]]:
    return json.loads(COHORT.read_text())["entries"]


def test_source_cohort_exact_34_plus_6_from_formula_audit() -> None:
    source = json.loads(AUDIT.read_text())["items"]
    selected_source = {
        row["candidate"]: row
        for row in source
        if row["formula_disposition"]
        in (
            "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
            "UNREPRESENTED_FORMULA",
        )
    }
    cohort = selected()
    specs = {s.name: s for s in research_feature_specs()}
    assert len(specs) == PRIOR_COUNT + NEW_COUNT == 487
    assert len(cohort) == len({str(r["name"]) for r in cohort}) == NEW_COUNT
    assert len(selected_source) == NEW_COUNT
    assert {str(r["audit_candidate"]) for r in cohort} == set(selected_source)
    assert (
        sum(r["formula_disposition"] == "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY" for r in cohort)
        == 34
    )
    assert sum(r["formula_disposition"] == "UNREPRESENTED_FORMULA" for r in cohort) == 6
    assert all(r["name"] in specs for r in cohort)
    for row in cohort:
        spec = specs[row["name"]]
        assert spec.status == "REGISTERED"
        assert spec.source_licenses == ("MIT",)
        assert spec.calculator == "pandas_ta_pinned"
        assert spec.inputs == tuple(row["inputs"])
        assert spec.parameters["source_name"] == row["source"]
        assert spec.parameters["output_index"] == row["output_index"]


def test_all_40_compute_and_replay_with_multicutoff_lookahead_gate() -> None:
    raw, market = synthetic(480)
    specs = {s.name: s for s in research_feature_specs()}
    names = {str(row["name"]) for row in selected()}
    current: dict[tuple[float | None, ...], str] = {}
    for spec in specs.values():
        if spec.name in names or spec.data_contract != "scalar" or not set(spec.inputs) <= set(raw):
            continue
        values = calculate_feature(spec, {key: raw[key] for key in spec.inputs})
        fingerprint = tuple(None if v is None else round(v, 7) for v in values)
        current[fingerprint] = spec.name
    for row in selected():
        spec = specs[row["name"]]
        subset = {key: raw[key] for key in spec.inputs}
        values = calculate_feature(spec, subset)
        assert len(values) == 480
        assert all(value is None or math.isfinite(value) for value in values)
        assert len({round(value, 7) for value in values if value is not None}) > 1
        for cutoff in (140, 280, 420, 479):
            earlier = calculate_feature(
                spec, {key: series[:cutoff] for key, series in subset.items()}
            )
            assert values[:cutoff] == earlier, (spec.name, cutoff)
        inherited = _new_feature_vector(
            FeatureRef(feature_id=spec.name, lookback=spec.lookback, inputs=spec.inputs),
            market,
        )
        assert inherited == values, spec.name
        source_output = get_source_output(
            {
                "source": row["source"],
                "category": row["category"],
                "index": row["output_index"],
            },
            raw,
        )
        oracle = np.asarray([np.nan if v is None else v for v in values])
        assert np.allclose(source_output, oracle, rtol=1e-9, atol=1e-7, equal_nan=True), spec.name
        fingerprint = tuple(None if v is None else round(v, 7) for v in values)
        assert fingerprint not in current, (
            spec.name,
            current.get(fingerprint),
        )
        current[fingerprint] = spec.name


@pytest.mark.parametrize(
    "name",
    [
        "pta_drawdown_out0",
        "pta_drawdown_out1",
        "pta_drawdown_out2",
        "pta_midpoint_out0",
        "pta_wcp_out0",
        "pta_adosc_out0",
    ],
)
def test_all_6_missing_formulas_have_live_scalar_calculator(name: str) -> None:
    raw, market = synthetic(480)
    spec = next(x for x in research_feature_specs() if x.name == name)
    vals = calculate_feature(spec, {field: raw[field] for field in spec.inputs})
    ref = FeatureRef(feature_id=name, lookback=spec.lookback, inputs=spec.inputs)
    assert len(vals) == 480
    assert vals == _new_feature_vector(ref, market)
    assert any(v is not None for v in vals)
