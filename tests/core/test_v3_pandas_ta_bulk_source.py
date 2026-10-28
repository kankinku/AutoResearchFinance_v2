"""Verified pinned 330-candidate importer: an added name must execute, stay causal and be traced."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.features.calculators import calculate_feature
from core.features.catalog import imported_feature_catalog
from core.features.registry import research_feature_specs
from core.features.source_multi_backend import KNOWN
from research.llm.inherited_feature_compiler import _new_feature_vector
from strategy_ir.schema import FeatureRef
from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture

MANIFEST = Path("core/features/pandas_ta_manifest.json")
LICENSE = Path("pandas_ta_classic/LICENSE")


def values(n: int = 425) -> dict[str, tuple[float, ...]]:
    close = tuple(200 + 0.12 * j + math.sin(j / 8) * 5 + math.cos(j / 31) * 2.1 for j in range(n))
    opening = tuple(c + math.sin(j / 2) * 1.1 for j, c in enumerate(close))
    return {
        "open": opening,
        "high": tuple(
            max(c, o) + 1.5 + 0.8 * abs(math.cos(j / 5))
            for j, (c, o) in enumerate(zip(close, opening, strict=True))
        ),
        "low": tuple(
            min(c, o) - 1.6 - 0.8 * abs(math.sin(j / 6))
            for j, (c, o) in enumerate(zip(close, opening, strict=True))
        ),
        "close": close,
        "volume": tuple(2000 + math.sin(j / 3) * 250 + 3 * (j % 17) for j in range(n)),
    }


def test_source_catalog_pins_license_identity_and_preserves_existing_specs() -> None:
    meta = json.loads(MANIFEST.read_text())
    assert len(meta["entries"]) >= 80
    assert meta["license"] == "MIT"
    assert meta["source_sha"] == "7c669b033582d53b70aa68b6388796d19ce33979"
    assert "MIT License" in LICENSE.read_text()
    assert len({e["name"] for e in meta["entries"]}) == len(meta["entries"])
    features = {s.name: s for s in research_feature_specs()}
    assert len(features) == 214 + len(meta["entries"]) + len(KNOWN)
    for entry in meta["entries"]:
        spec = features[entry["name"]]
        assert spec.status == "REGISTERED"
        assert spec.source_licenses == ("MIT",)
        assert meta["source_sha"] in spec.source_repositories[0]
        assert spec.inputs == tuple(entry["inputs"])
        assert spec.data_contract == "scalar"


def test_all_pinned_ports_emit_prefix_causal_finite_aligned_features() -> None:
    data = values()
    shorter = {name: signal[:-1] for name, signal in data.items()}
    meta = json.loads(MANIFEST.read_text())
    for e in meta["entries"]:
        s = imported_feature_catalog().resolve(e["name"])
        actual = calculate_feature(s, data)
        old = calculate_feature(s, shorter)
        assert len(actual) == len(data["close"]), e["name"]
        assert actual[:-1] == old, e["name"]
        assert all(x is None or math.isfinite(x) for x in actual), e["name"]
        assert any(x is not None for x in actual), e["name"]


def test_pinned_ports_fail_closed_for_unapproved_source_switch() -> None:
    spec = imported_feature_catalog().resolve("pta_alma")
    invalid = spec.model_copy(update={"parameters": {"source_name": "exec", "output_index": 0}})
    with pytest.raises(ValueError):
        calculate_feature(invalid, values(80))


def test_inherited_strategy_ir_can_bind_pinned_features() -> None:
    _, market = _warmup_fixture()
    for name in ("pta_alma", "pta_cdl_2crows"):
        spec = imported_feature_catalog().resolve(name)
        got = _new_feature_vector(
            FeatureRef(feature_id=name, lookback=2, inputs=spec.inputs), market
        )
        assert len(got) == len(market.bars)
