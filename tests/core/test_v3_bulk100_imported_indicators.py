"""+100 distinct source-output cohort: execution, provenance and StrategyIR acceptance."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from research.llm.inherited_feature_compiler import _new_feature_vector
from scripts.v3_audit_335_features import synthetic
from strategy_ir.schema import FeatureRef

MANIFEST = Path("core/features/bulk100_manifest.json")


def test_bulk100_cohort_has_exactly_100_new_pinned_distinct_output_ids() -> None:
    manifest = json.loads(MANIFEST.read_text())
    names = [entry["name"] for entry in manifest["entries"]]
    specs = {spec.name: spec for spec in research_feature_specs()}
    assert len(specs) == 487  # baseline 435 + 12 chart patterns + 40 pinned outputs
    assert len(names) == len(set(names)) == 100
    assert sum(e["provider"] == "pta" for e in manifest["entries"]) == 43
    assert sum(e["provider"] == "ta" for e in manifest["entries"]) == 57
    assert set(names) <= specs.keys()
    assert all(specs[name].status == "REGISTERED" for name in names)
    assert all(specs[name].source_licenses == ("MIT",) for name in names)
    for entry in manifest["entries"]:
        spec = specs[entry["name"]]
        assert spec.data_contract == "scalar"
        assert spec.calculator in ("bukosabino_pinned", "pandas_ta_pinned")
        assert spec.source_repositories
    assert "MIT" in Path("ta/LICENSE").read_text()
    assert manifest["source_shas"]["bukosabino-ta"] in Path("ta/PINNED_SOURCE").read_text()


def test_all_100_source_outputs_are_real_causal_and_inherited_replay_compatible() -> None:
    raw, market = synthetic(480)
    specs = {spec.name: spec for spec in research_feature_specs()}
    manifest = json.loads(MANIFEST.read_text())
    unique_signatures: dict[tuple[float | None, ...], str] = {}
    for entry in manifest["entries"]:
        spec = specs[entry["name"]]
        subset = {key: raw[key] for key in spec.inputs}
        full = calculate_feature(spec, subset)
        past = calculate_feature(spec, {key: v[:-1] for key, v in subset.items()})
        ref = FeatureRef(feature_id=spec.name, lookback=spec.lookback, inputs=spec.inputs)
        inherited = _new_feature_vector(ref, market)
        assert len(full) == len(raw["close"]) == 480, spec.name
        assert full[:-1] == past, spec.name
        for cutoff in (140, 280, 420):
            smaller = calculate_feature(
                spec, {key: values[:cutoff] for key, values in subset.items()}
            )
            assert full[:cutoff] == smaller, f"prefix leakage in {spec.name} at {cutoff}"
        assert inherited == full, spec.name
        assert all(v is None or math.isfinite(v) for v in full), spec.name
        vals = [v for v in full if v is not None]
        assert len(vals) >= 10 and len(set(round(x, 7) for x in vals)) > 1, spec.name
        fingerprint = tuple(None if v is None else round(v, 7) for v in full)
        assert fingerprint not in unique_signatures, (
            f"non-distinct source outputs: {spec.name}, {unique_signatures.get(fingerprint)}"
        )
        unique_signatures[fingerprint] = spec.name


def test_bulk100_source_selector_rejects_unapproved_columns_and_tunable_lookbacks() -> None:
    raw, _ = synthetic(90)
    specs = {spec.name: spec for spec in research_feature_specs()}
    buk = next(s for s in specs.values() if s.name.startswith("buk_"))
    data = {key: raw[key] for key in buk.inputs}
    for updated in (
        buk.model_copy(update={"lookback": 20}),
        buk.model_copy(
            update={
                "parameters": {
                    "source_column": "volume_vpt",
                    "source_family": "volume",
                    "window_mode": "source_defaults_fixed",
                }
            }
        ),
    ):
        with pytest.raises(ValueError):
            calculate_feature(updated, data)
