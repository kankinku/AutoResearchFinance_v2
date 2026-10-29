"""Keep the A0-A2 source audit reproducible and preserve known-red bug gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.features.chart_patterns import ConfirmedPivot, classical_shape, harmonic_xabcd
from core.features.registry import research_feature_specs

ROOT = Path("docs/operations")


def _p(values: list[float]) -> list[ConfirmedPivot]:
    return [
        ConfirmedPivot(i, float(v), "low" if i % 2 == 0 else "high", i + 2)
        for i, v in enumerate(values)
    ]


def test_a0_a1_inventory_count_and_separate_uncommitted_work() -> None:
    a0 = json.loads((ROOT / "quant-v3-chart-A0-baseline-20261029.json").read_text())
    a1 = json.loads((ROOT / "quant-v3-chart-A1-feature-audit-20261029.json").read_text())
    features = research_feature_specs()
    assert len(features) == len(a1["feature_rows"]) == 447
    assert {r["name"] for r in a1["feature_rows"]} == {s.name for s in features}
    assert a0["chart_branch"]["registered"] == 447
    assert a0["chart_branch"]["chart_patterns"] == 12
    assert a0["local_bulk40"]["registered"] == 475
    assert a0["local_bulk40"]["new_candidates"] == 40
    assert not set(a0["local_bulk40"]["new_names"]) & set(a0["chart_branch"]["new_names"])
    assert a0["cross_branch_merge"] == "NOT_DONE"


def test_a2_matrix_is_complete_and_license_boundaries_visible() -> None:
    a2 = json.loads((ROOT / "quant-v3-chart-A2-formula-source-matrix-20261029.json").read_text())
    patterns = [r for r in a2["patterns"] if r["status"] == "REGISTERED_HEURISTIC"]
    assert len(patterns) == 12
    assert {r["name"] for r in patterns} == {
        s.name.removeprefix("chart_")
        for s in research_feature_specs()
        if s.name.startswith("chart_")
    }
    assert a2["source_references"]
    assert all(r["rules"] and r["required_evidence"] for r in a2["patterns"])
    assert any("IP" in r["risk"] for r in a2["patterns"])


@pytest.mark.xfail(strict=True, reason="A1-F01 inverse H&S equal lows false positive")
def test_known_defect_inverse_shoulders_equal_lows_must_be_rejected() -> None:
    assert classical_shape(_p([100, 110, 100, 110, 100]), "inverse_head_shoulders") == 0


def test_a5_gartley_cd_bc_ratio_outside_gate_now_rejected() -> None:
    assert harmonic_xabcd(_p([100, 120, 107.64, 112.4, 104.28]), "harmonic_gartley") == 0
