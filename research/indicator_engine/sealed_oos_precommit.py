"""V04 development selection precommit, WITHOUT reading sealed OOS material.

An exclusively-created evidence receipt binds the typed algorithm plan, data
prefix, indicator definitions and compiled strategy. It is a local hash anchor,
not a trusted timestamp, signed independent custodian, or OOS approval.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import timezone
from pathlib import Path
from typing import Any

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    compile_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError

_ID = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_MAX_RECEIPT_SIZE = 16_384
_VERSION = "v04-development-selection-precommit-v1"


def _receipt(
    catalog: ResearchCatalog,
    plan: AlgorithmPlan,
    training: MarketDataSet,
    study_id: str,
) -> dict[str, Any]:
    if not isinstance(study_id, str) or _ID.fullmatch(study_id) is None:
        raise ResearchCatalogError("invalid bounded study identifier")
    if training.zone != DataZone.DEVELOPMENT or len(training.bars) < 2:
        raise ResearchCatalogError("precommit accepts DEVELOPMENT prefix only")
    if training.timeframe != "1d" or training.calendar != "us_equities":
        raise ResearchCatalogError("daily US-equity development prefix required")
    if len({b.symbol for b in training.bars}) != 1:
        raise ResearchCatalogError("selection precommit requires one symbol")
    # Compile only development data, never a SEALED_OOS or VALIDATION dataset.
    frozen = compile_algorithm_plan(catalog, plan, training)
    if frozen.sealed_oos_approved is not False or frozen.broker_executable is not False:
        raise ResearchCatalogError("compiler returned unexpected execution permissions")
    proof: dict[str, Any] = {
        "schema": _VERSION,
        "study_id": study_id,
        "symbol": training.bars[0].symbol,
        "training_zone": "development",
        "training_dataset_hash": training.dataset_hash,
        "training_bars": len(training.bars),
        "training_first_utc": training.bars[0].timestamp.astimezone(timezone.utc).isoformat(),
        "selection_cutoff_utc": training.bars[-1].timestamp.astimezone(timezone.utc).isoformat(),
        "training_source_retrieved_at": (
            training.provenance.retrieved_at.astimezone(timezone.utc).isoformat()
            if training.provenance is not None else None
        ),
        "training_provenance_hash": (
            content_hash(training.provenance.record())
            if training.provenance is not None else None
        ),
        "plan_id": plan.plan_id,
        "plan_hash": frozen.plan_hash,
        "indicator_definitions_hash": frozen.definitions_hash,
        "strategy_ir_hash": frozen.compiled.strategy_hash,
        "compiler_replay_hash": frozen.compiled.replay.replay_hash,
        "oos_access_performed": False,
        "oos_dataset_digest_known": False,
        "oos_result_evaluated": False,
        "independent_custodian_signature_verified": False,
        "historical_pit_verified": False,
        "selection_locked_for_research": True,
        "candidate_promotable": False,
        "sealed_oos_approved": False,
        "broker_executable": False,
        "status": "DEVELOPMENT_PRECOMMIT_ONLY_OOS_UNOPENED",
    }
    proof["receipt_hash"] = content_hash(proof)
    return proof


def prepare_development_precommit(
    catalog: ResearchCatalog,
    plan: AlgorithmPlan,
    training: MarketDataSet,
    *,
    study_id: str,
) -> dict[str, Any]:
    """Compute in-memory evidence only; no OOS access or persistent writes."""
    return _receipt(catalog, plan, training, study_id)


def _check_receipt_path(path: Path) -> None:
    if (
        path.suffix != ".json"
        or path.is_symlink()
        or path.parent.is_symlink()
        or not path.parent.is_dir()
    ):
        raise ResearchCatalogError("precommit evidence path must be a regular local JSON")
    # Do not allow symlinks in intermediate parents, even to otherwise valid dirs.
    if any(parent.is_symlink() for parent in path.parents):
        raise ResearchCatalogError("precommit path contains symlinked directory")


def record_development_precommit(
    catalog: ResearchCatalog,
    plan: AlgorithmPlan,
    training: MarketDataSet,
    *,
    study_id: str,
    evidence_path: Path,
) -> dict[str, Any]:
    """One-shot exclusive receipt; never overwrites or self-approves OOS."""
    _check_receipt_path(evidence_path)
    receipt = _receipt(catalog, plan, training, study_id)
    payload = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(payload) > _MAX_RECEIPT_SIZE:
        raise ResearchCatalogError("precommit evidence payload oversized")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(evidence_path, flags, 0o600)
    except OSError as exc:
        raise ResearchCatalogError("precommit evidence exists or cannot be created") from exc
    try:
        with os.fdopen(descriptor, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        evidence_path.unlink(missing_ok=True)
        raise
    return receipt


def verify_development_precommit(
    catalog: ResearchCatalog,
    plan: AlgorithmPlan,
    training: MarketDataSet,
    *,
    study_id: str,
    evidence_path: Path,
) -> dict[str, Any]:
    """Recompute exact development receipt; fail closed on any changed byte."""
    _check_receipt_path(evidence_path)
    try:
        info = evidence_path.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= _MAX_RECEIPT_SIZE:
            raise ResearchCatalogError("invalid precommit evidence file")
        source = evidence_path.read_bytes()
        persisted = json.loads(source)
    except (OSError, ValueError, TypeError) as exc:
        raise ResearchCatalogError("cannot read or decode precommit evidence") from exc
    expected = _receipt(catalog, plan, training, study_id)
    if (
        not isinstance(persisted, dict)
        or persisted != expected
        or source != (json.dumps(expected, sort_keys=True, indent=2) + "\n").encode()
    ):
        raise ResearchCatalogError("precommit plan, source or indicator evidence changed")
    return {
        "status": "PRECOMMIT_REPLAY_MATCHED_OOS_STILL_SEALED",
        "receipt_hash": expected["receipt_hash"],
        "study_id": study_id,
        "selection_cutoff_utc": expected["selection_cutoff_utc"],
        "oos_access_performed": False,
        "sealed_oos_approved": False,
        "candidate_promotable": False,
        "historical_pit_verified": False,
        "broker_executable": False,
        "independently_timestamped": False,
    }
