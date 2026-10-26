"""A generic registry entry is not an academic-eligible trading signal."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from application.quant_feature_bridge_audit import audit_feature_bridge
from core.integrity.hashes import content_hash


def _catalog(path: Path, *, tamper: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    signal = {
        "signal_id": "parkinson_variance",
        "status": "VERIFIED",
        "calculator": "parkinson_variance",
        "required_fields": ["high", "low"],
    }
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE indicators(signal_id text,status text,payload text,payload_hash text)"
        )
        db.execute(
            "INSERT INTO indicators VALUES (?,?,?,?)",
            (
                signal["signal_id"],
                signal["status"],
                json.dumps(signal),
                "0" * 64 if tamper else content_hash(signal),
            ),
        )


def test_feature_bridge_audit_never_counts_registry_as_academic(tmp_path: Path):
    path = tmp_path / "catalog-s6-v2.sqlite"
    _catalog(path)
    result = audit_feature_bridge(path)
    assert result["registry_total"] == 173
    assert result["academic_verified"] == 1
    assert result["academic_eligible_by_name"] == 0
    assert len(result["features"]) == 173
    assert any(x["name"] == "rsi" and not x["academic_verified"] for x in result["features"])
    assert result["model_calls"] == 0
    assert result["orders_enabled"] is False


def test_catalog_tampering_rejected(tmp_path: Path):
    path = tmp_path / "catalog-s6-v2.sqlite"
    _catalog(path, tamper=True)
    with pytest.raises(ValueError, match="academic catalog hash"):
        audit_feature_bridge(path)


def test_missing_or_symlinked_academic_catalog_rejected(tmp_path: Path):
    path = tmp_path / "catalog-s6-v2.sqlite"
    with pytest.raises(ValueError, match="missing"):
        audit_feature_bridge(path)
    original = tmp_path / "other.sqlite"
    _catalog(original)
    path.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        audit_feature_bridge(path)
