"""A10 isolated research integration: legacy 447 + vetted 40, not live deployment."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

import pytest

from core.features.calculators import calculate_feature
from core.features.contracts import FeatureSpec
from core.features.pandas_ta_pinned import _approved
from core.features.registry import research_feature_specs
from research.chart_pattern_bridge import chart_research_feature_specs
from research.llm.inherited_feature_compiler import _new_feature_vector
from scripts.v3_audit_335_features import synthetic
from strategy_ir.schema import FeatureRef

BASELINE = Path("tests/core/fixtures/v3_chart_a10_premerge_registry_20261029.json")
A0 = Path("docs/operations/quant-v3-chart-A0-baseline-20261029.json")
COHORT = Path("core/features/bulk40_manifest.json")


def _identity(specs: Iterable[FeatureSpec]) -> dict[str, dict[str, object]]:
    return {
        p.name: {
            "canonical_id": p.canonical_id,
            "version": p.version,
            "calculator": p.calculator,
            "inputs": list(p.inputs),
            "lookback": p.lookback,
        }
        for p in specs
    }


def test_untouched_447_plus_40_exact_registry_and_optin_44() -> None:
    frozen = json.loads(BASELINE.read_text())
    a = _identity(research_feature_specs())
    b = _identity(research_feature_specs(chart_research_opt_in=True))
    cohort = json.loads(COHORT.read_text())
    addition = {entry["name"] for entry in cohort["entries"]}
    prior = frozen["base"]
    original_opt = frozen["optin"]
    assert len(prior) == 447 and len(original_opt) == 491
    assert len(addition) == 40
    assert len(a) == 487 and len(b) == 531
    assert set(a) == set(prior) | addition
    assert set(b) == set(original_opt) | addition
    assert {key: a[key] for key in prior} == prior
    assert {key: b[key] for key in original_opt} == original_opt
    assert len(chart_research_feature_specs()) == 44
    assert not addition & set(original_opt)


def test_copied_upstream_40_contracts_equal_original_dirty_bytes() -> None:
    origin = Path("/shared/moon-workspace/AutoResearchFinance_v3-track1-strategy-20261027")
    source_sha = json.loads(A0.read_text())["local_bulk40"]["file_hash_sha256"]
    for relative, expected in source_sha.items():
        assert hashlib.sha256((origin / relative).read_bytes()).hexdigest() == expected
    for name in (
        "core/features/bulk40_manifest.json",
        "core/features/pandas_ta_manifest.json",
        "core/features/pandas_ta_pinned.py",
    ):
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == source_sha[name]
    manifest = json.loads(COHORT.read_text())
    assert manifest["source_license"] == "MIT"
    assert manifest["expected_after_registered"] == 475  # legacy 435 + 40
    assert len(manifest["entries"]) == 40
    assert (
        sum(x["formula_disposition"] == "UNREPRESENTED_FORMULA" for x in manifest["entries"]) == 6
    )
    assert len(_approved()) == 179


def test_exact_source_fidelity_unique_identity_and_frozen_lookback_guard() -> None:
    raw, market = synthetic(480)
    specs = {s.name: s for s in research_feature_specs()}
    rows = json.loads(COHORT.read_text())["entries"]
    expected = {row["name"] for row in rows}
    for name in expected:
        spec = specs[name]
        assert spec.source_licenses == ("MIT",)
        assert spec.calculator == "pandas_ta_pinned"
        assert spec.status == "REGISTERED"
        assert spec.lookback == 20
        input_map = {key: raw[key] for key in spec.inputs}
        values = calculate_feature(spec, input_map)
        assert len(values) == len(market.bars)
        assert values == _new_feature_vector(
            FeatureRef(feature_id=name, lookback=spec.lookback, inputs=spec.inputs),
            market,
        )
        for cutoff in (160, 320, 479):
            earlier = calculate_feature(
                spec, {key: series[:cutoff] for key, series in input_map.items()}
            )
            assert values[:cutoff] == earlier, (name, cutoff)
        with pytest.raises(ValueError, match="unapproved"):
            calculate_feature(spec.model_copy(update={"lookback": 14}), input_map)


def test_a10_acceptance_retains_default_off_and_ledger_provenance() -> None:
    audit = json.loads(
        Path("docs/operations/quant-v3-chart-A10-integration-acceptance-20261029.json").read_text()
    )
    assert audit["scope"] == "A10_STAGING_BRANCH_NO_MAIN_NO_OOS"
    assert audit["counts"] == {
        "prior_base": 447,
        "integrated_base": 487,
        "prior_chart_optin": 491,
        "integrated_chart_optin": 531,
        "new_channels": 40,
    }
    assert audit["source_files_verified"] == 4
    assert audit["name_collisions"] == []
    assert audit["legacy_canonical_changed"] == []
    assert audit["release_authorized"] is False
    assert audit["main_merged"] is False
