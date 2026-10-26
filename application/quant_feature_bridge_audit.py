"""Read-only generic registry ↔ academic compiler availability census.

Neither generic FeatureSpec registration nor synthetic numerical output is a
VERIFIED academic signal. This audit never writes the academic catalog, imports
market data, promotes a candidate or opens independently sealed OOS data.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash

_LOCAL = frozenset({"open", "high", "low", "close", "volume"})


def _read_signals(path: Path) -> dict[str, dict[str, Any]]:
    if path.is_symlink():
        raise ValueError("academic catalog symlink is not allowed")
    if not path.is_file():
        raise ValueError("academic catalog missing")
    if path.name != "catalog-s6-v2.sqlite":
        raise ValueError("unexpected academic catalog database filename")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT signal_id,status,payload,payload_hash FROM indicators").fetchall()
    signals = {}
    for sid, status, raw, checksum in rows:
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or payload.get("signal_id") != sid
            or payload.get("status") != status
            or content_hash(payload) != checksum
            or sid in signals
            or status not in ("PROPOSED", "VERIFIED", "QUARANTINED")
        ):
            raise ValueError("academic catalog hash/status conflict")
        signals[sid] = payload
    return signals


def audit_feature_bridge(catalog: Path) -> dict[str, Any]:
    """Classify without claiming unverified FeatureSpecs can execute in S2/S7."""
    specs = research_feature_specs()
    signals = _read_signals(catalog)
    features: list[dict[str, Any]] = []
    for spec in specs:
        academic = signals.get(spec.name)
        external_inputs = sorted(set(spec.inputs) - _LOCAL)
        if academic and academic["status"] == "VERIFIED":
            stage = "EXACT_ACADEMIC_VERIFIED_ID_REPLAY_STILL_REQUIRED"
        elif academic:
            stage = "ACADEMIC_NOT_VERIFIED"
        elif external_inputs:
            stage = "REQUIRES_ALIGNED_EXTERNAL_INPUTS"
        elif spec.data_contract not in ("scalar", "ohlcv"):
            stage = "REQUIRES_SPECIALIZED_DATA_ALIGNMENT"
        elif spec.status != "REGISTERED":
            stage = "GENERAL_FEATURE_NOT_REGISTERED"
        else:
            stage = "LOCAL_FEATURE_REQUIRES_TYPED_ACADEMIC_BRIDGE"
        features.append(
            {
                "name": spec.name,
                "family": spec.family,
                "calculator": spec.calculator,
                "registry_status": spec.status,
                "required_inputs": list(spec.inputs),
                "data_contract": spec.data_contract,
                "lookback": spec.lookback,
                "lag_bars": spec.lag_bars,
                "implementation_hash": spec.implementation_hash,
                "academic_signal_id_exact_match": academic["signal_id"] if academic else None,
                "academic_verified": bool(academic and academic["status"] == "VERIFIED"),
                "bridge_stage": stage,
                "eligible_for_counted_academic_research": False,
            }
        )
    return {
        "schema": "quant-feature-academic-bridge-readonly-audit-v1",
        "registry_total": len(features),
        "registry_status_counts": dict(
            sorted(Counter(x["registry_status"] for x in features).items())
        ),
        "bridge_stage_counts": dict(sorted(Counter(x["bridge_stage"] for x in features).items())),
        "academic_catalog_total": len(signals),
        "academic_verified": sum(item["status"] == "VERIFIED" for item in signals.values()),
        "academic_proposed": sum(item["status"] == "PROPOSED" for item in signals.values()),
        "academic_quarantined": sum(item["status"] == "QUARANTINED" for item in signals.values()),
        "academic_eligible_by_name": sum(x["academic_verified"] for x in features),
        "academic_verified_signals": sorted(
            k for k, v in signals.items() if v["status"] == "VERIFIED"
        ),
        "source_catalog_hash": content_hash(
            tuple(sorted((sid, payload) for sid, payload in signals.items()))
        ),
        "features": features,
        "model_calls": 0,
        "orders_enabled": False,
        "independent_oos_approved": False,
        "note": (
            "Generic registry and academic signal IDs are not interchangeable; "
            "no automatic promotion"
        ),
    }
