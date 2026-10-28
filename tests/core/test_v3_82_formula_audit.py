"""Freeze the exact seven proved duplicates, without blocking other formula families."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from scripts.v3_audit_82_formula_overlap import ALGEBRAIC_MODES, get_source_output, run
from scripts.v3_audit_335_features import synthetic

PATH = Path("docs/operations/quant-v3-82-formula-overlap-audit-20261029.json")


def test_formula_82_manifest_is_complete_and_counts_are_coherent() -> None:
    source = json.loads(PATH.read_text())
    assert source["registered_current"] == 435
    assert source["prior_numerical_candidates"] == 145
    assert source["excluded_prior_direct_name_match"] == 63
    assert len(source["items"]) == source["evaluated_remaining"] == 82
    assert len({e["candidate"] for e in source["items"]}) == 82
    assert source["counts"] == {
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY": 34,
        "ALGEBRAIC_DUPLICATE": 16,
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION": 26,
        "UNREPRESENTED_FORMULA": 6,
    }
    assert all(Path(e["source_path"]).is_file() for e in source["items"])
    assert all(
        e["existing_comparison_target"] is None or e["existing_catalog_calculator"] is not None
        for e in source["items"]
    )
    # Recompute all 82 classifications and cross-reference the pinned source.
    assert run()["counts"] == source["counts"]


@pytest.mark.parametrize(
    "candidate",
    sorted(
        row["candidate"]
        for row in json.loads(PATH.read_text())["items"]
        if row["formula_disposition"] == "ALGEBRAIC_DUPLICATE"
    ),
)
def test_proved_equivalences_hold_for_inverted_trending_market(candidate: str) -> None:
    original, _ = synthetic(480)
    data = {
        "open": tuple(700 - p for p in original["open"]),
        "high": tuple(700 - p for p in original["low"]),
        "low": tuple(700 - p for p in original["high"]),
        "close": tuple(700 - p for p in original["close"]),
        "volume": tuple(v * (1 + i % 5 / 20) for i, v in enumerate(original["volume"])),
    }
    evidence = json.loads(PATH.read_text())
    entry = next(item for item in evidence["items"] if item["candidate"] == candidate)
    source = get_source_output(entry, data)
    specs = {s.name: s for s in research_feature_specs()}
    existing = specs[entry["existing_comparison_target"]].model_copy(update={"lookback": 20})
    values = calculate_feature(existing, {field: data[field] for field in existing.inputs})
    native = np.asarray([np.nan if value is None else float(value) for value in values])
    mode = ALGEBRAIC_MODES[entry["source"]]
    expected = {
        "identity": native,
        "plus_one": native + 1,
        "plus_one_times_100": 100 * (native + 1),
    }[mode]
    assert np.array_equal(np.isnan(source), np.isnan(expected)), candidate
    assert np.allclose(source, expected, rtol=1e-9, atol=1e-8, equal_nan=True), candidate
