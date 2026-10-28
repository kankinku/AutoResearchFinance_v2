"""Candid 330-name audit: every candidate must have a disposition, no silent promotion."""

from __future__ import annotations

import json
from pathlib import Path

from core.features.registry import research_feature_specs


def test_330_source_names_have_exhaustive_dispositions() -> None:
    report = json.loads(
        Path("docs/operations/quant-v3-330-source-full-disposition-20261028.json").read_text()
    )
    assert report["prior_source_name_candidates"] == 330
    assert len(report["dispositions"]) == 330
    assert len({r["canonical_candidate"] for r in report["dispositions"]}) == 330
    assert sum(report["states"].values()) == 330
    specs = {s.name: s for s in research_feature_specs()}
    active = [r for r in report["dispositions"] if r["state"].startswith("PORTED_")]
    assert len(active) == report["registered_new_source_candidate_groups"]
    assert report["registered_new_feature_outputs"] == 335 - 214
    assert len(specs) == 435
    assert all(row["registered_name"] in specs for row in active)
    assert all(
        row["registered_name"] is None
        for row in report["dispositions"]
        if not row["state"].startswith("PORTED_")
    )


def test_pinned_external_code_retains_original_mit_text_and_source_hash() -> None:
    assert "MIT License" in Path("pandas_ta_classic/LICENSE").read_text()
    pin = Path("pandas_ta_classic/PINNED_SOURCE").read_text()
    assert "7c669b033582d53b70aa68b6388796d19ce33979" in pin
    data = json.loads(Path("core/features/pandas_ta_manifest.json").read_text())
    assert data["source_sha"] in pin
