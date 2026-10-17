"""Read-only, development-only diagnostic of GPT research checkpoint ledgers.

This is NOT a Sharpe significance test, independent OOS, proof of causality,
or a live trading evaluator. SQLite backups are used to avoid editing active WALs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def snapshot_ledger(checkpoint: Path, destination: Path) -> dict[str, object]:
    """Create once-only online SQLite backups; never checkpoint or mutate source.

    Separate DB backups cannot promise a cross-database atomic instant. The
    auditor consequently checks session/generation completeness before using them.
    """
    destination.mkdir(parents=True, exist_ok=False)
    metadata: dict[str, dict[str, object]] = {}
    for name in ("cycles.sqlite", "gateway.sqlite"):
        target = destination / name
        with _open_readonly(checkpoint / name) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
            check = dst.execute("PRAGMA integrity_check").fetchone()
            if check != ("ok",):
                raise ValueError(f"corrupt snapshot: {name}")
        metadata[name] = {"sha256": _sha256(target), "bytes": target.stat().st_size}
    manifest: dict[str, object] = {
        "schema": "academic-campaign-audit-snapshot-v1",
        "files": metadata,
        "source_was_mutated": False,
        "cross_database_snapshot_atomic": False,
        "claim": "SQLite snapshot, not original cryptographic evidence verification",
    }
    (destination / "snapshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def _validate_snapshot(snapshot: Path) -> None:
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text(encoding="utf-8"))
    for name in ("cycles.sqlite", "gateway.sqlite"):
        if _sha256(snapshot / name) != manifest["files"][name]["sha256"]:
            raise ValueError(f"snapshot checksum mismatch: {name}")


def _get_sessions(db: sqlite3.Connection, ids: tuple[str, str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for identifier in ids:
        row = db.execute(
            "SELECT requested,completed,status,dataset_hash FROM sessions WHERE id=?",
            (identifier,),
        ).fetchone()
        if row is None:
            raise ValueError(f"missing session: {identifier}")
        result[identifier] = dict(
            zip(("requested", "completed", "status", "dataset_hash"), row, strict=True)
        )
    return result


def _read_generations(db: sqlite3.Connection, session: str) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for number, raw, stored_hash in db.execute(
        "SELECT generation,evidence_json,evidence_hash FROM generations "
        "WHERE session_id=? ORDER BY generation",
        (session,),
    ):
        if number in result or not isinstance(stored_hash, str) or len(stored_hash) != 64:
            raise ValueError("invalid or duplicate generation evidence reference")
        payload = json.loads(raw)
        if payload.get("generation") != number:
            raise ValueError("generation evidence number mismatch")
        result[number] = payload
    return result


def _read_reports(db: sqlite3.Connection, session: str) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for number, raw, stored_hash in db.execute(
        "SELECT generation,report_json,report_hash FROM experiment_reports "
        "WHERE session_id=? ORDER BY generation",
        (session,),
    ):
        if number in result or not isinstance(stored_hash, str) or not stored_hash:
            raise ValueError("invalid or duplicate experiment report reference")
        result[number] = json.loads(raw)
    return result


def _read_champion(db: sqlite3.Connection, session: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT selection_json FROM parent_selections "
        "WHERE session_id=? ORDER BY next_generation DESC LIMIT 1",
        (session,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def _economic_records(
    evidences: dict[int, dict[str, Any]], reports: dict[int, dict[str, Any]]
) -> dict[str, object]:
    counts: Counter[str] = Counter()
    child_hashes: Counter[str] = Counter()
    outcome_signatures: Counter[tuple[float, int]] = Counter()
    prediction: Counter[str] = Counter()
    costs_parent = costs_child = 0.0
    measured_costs = 0
    for number, report in reports.items():
        experiments = report.get("report", {}).get("experiments")
        if not isinstance(experiments, list) or len(experiments) != 1:
            raise ValueError(f"unsupported S7 experiments at generation {number}")
        exp = experiments[0]
        evidence = evidences[number]
        expected_reference = (evidence.get("experiments") or [{}])[0].get("proposal_child_hash")
        if expected_reference and exp.get("child_strategy_hash") != expected_reference:
            raise ValueError("S7 proposal/child identity mismatch")
        parent_equity = float(exp["parent_final_equity"])
        child_equity = float(exp["child_final_equity"])
        if parent_equity <= 0 or child_equity < 0:
            raise ValueError("invalid economic equity")
        # Equity difference is the real economic direction regardless of which
        # trade-count/drawdown/return hypothesis was tested.
        if child_equity > parent_equity + 1e-6:
            counts["better"] += 1
            if exp.get("status") == "DIRECTION_MATCHED_DEVELOPMENT_ONLY":
                counts["matched_and_better"] += 1
        elif child_equity < parent_equity - 1e-6:
            counts["worse"] += 1
            if exp.get("status") == "DIRECTION_MATCHED_DEVELOPMENT_ONLY":
                counts["matched_but_worse"] += 1
        else:
            counts["same"] += 1
        if bool(exp.get("same_fill_trace")):
            counts["unchanged_execution"] += 1
        prediction[str(exp.get("status", "UNKNOWN"))] += 1
        child_hash = str(exp["child_strategy_hash"])
        child_hashes[child_hash] += 1
        outcome_signatures[(round(child_equity, 6), int(exp.get("child_fill_count", 0)))] += 1
        cost = exp.get("execution_delta") or {}
        if cost.get("parent_costs") is not None and cost.get("child_costs") is not None:
            costs_parent += float(cost["parent_costs"])
            costs_child += float(cost["child_costs"])
            measured_costs += 1
    return {
        "experiments": len(reports),
        "better": counts["better"],
        "worse": counts["worse"],
        "same": counts["same"],
        "matched_and_better": counts["matched_and_better"],
        "matched_but_worse": counts["matched_but_worse"],
        "unchanged_execution": counts["unchanged_execution"],
        "unique_child_hashes": len(child_hashes),
        "duplicate_child_hashes": sum(v - 1 for v in child_hashes.values()),
        "same_result_signature_pairs": sum(v * (v - 1) // 2 for v in outcome_signatures.values()),
        "same_result_signature_is_proof_of_same_fills": False,
        "prediction_status_counts": dict(sorted(prediction.items())),
        "cost_observations": measured_costs,
        "parent_cost_total": round(costs_parent, 6),
        "child_cost_total": round(costs_child, 6),
        "cost_delta_total": round(costs_child - costs_parent, 6),
        "cost_sum_is_not_a_portfolio_pnl": True,
    }


def _candidate_risk_coverage(
    gateway: sqlite3.Connection, session: str, reports: dict[int, dict[str, Any]]
) -> dict[str, object]:
    """Join verified selection reviews by generation+child hash, not by return.

    Absent child portfolio MDD/exposure remains missing: window-level drawdown
    is NOT a substitute for full-period portfolio maximum drawdown.
    """
    reviewed: dict[tuple[int, str], dict[str, Any]] = {}
    for (raw,) in gateway.execute(
        "SELECT selection_json FROM parent_selections WHERE session_id=?", (session,)
    ):
        selection = json.loads(raw)
        for candidate in selection.get("candidate_review", {}).get("comparisons", []):
            if candidate.get("replay_verified") is not True:
                continue
            key = (int(candidate["source_generation"]), str(candidate["child_strategy_hash"]))
            reviewed[key] = candidate
    complete = 0
    missing: list[int] = []
    for generation, report in reports.items():
        exp = report["report"]["experiments"][0]
        key = (generation, str(exp["child_strategy_hash"]))
        candidate = reviewed.get(key)
        if candidate and all(
            candidate.get(k) is not None
            for k in ("total_return", "max_drawdown", "market_exposure", "closed_trades")
        ):
            complete += 1
        else:
            missing.append(generation)
    return {
        "replayed_full_period_risk_coverage": complete,
        "missing_full_period_risk_generations_local": missing,
        "missing_risk_not_inferred_from_development_windows": True,
    }


def audit_campaign(
    snapshot: Path, *, origin_session: str, active_session: str
) -> dict[str, object]:
    """Conservative quality report; fail closed on ledger discontinuity."""
    _validate_snapshot(snapshot)
    sessions_ids = (origin_session, active_session)
    with (
        _open_readonly(snapshot / "cycles.sqlite") as cycles,
        _open_readonly(snapshot / "gateway.sqlite") as gateway,
    ):
        sessions = _get_sessions(cycles, sessions_ids)
        evidences: dict[str, dict[int, dict[str, Any]]] = {}
        reports: dict[str, dict[int, dict[str, Any]]] = {}
        for session in sessions_ids:
            stored = evidences[session] = _read_generations(cycles, session)
            measured = reports[session] = _read_reports(gateway, session)
            complete = sessions[session]["completed"]
            expected = set(range(1, complete + 1))
            if set(stored) != expected or set(measured) != expected:
                raise ValueError(f"generation mismatch in {session}")
            if any(
                ev.get("dataset_hash") != sessions[session]["dataset_hash"]
                for ev in stored.values()
            ):
                raise ValueError("dataset mismatch within session")
            phase = gateway.execute(
                "SELECT phase FROM stages WHERE session_id=?", (session,)
            ).fetchone()
            if phase is None:
                raise ValueError(f"missing gateway stage: {session}")
        champion = _read_champion(gateway, active_session)
        coverage = _candidate_risk_coverage(gateway, active_session, reports[active_session])
    if sessions[origin_session]["dataset_hash"] != sessions[active_session]["dataset_hash"]:
        raise ValueError("campaign dataset mismatch")
    quality = champion.get("parent_quality") if champion else None
    return {
        "schema": "academic-campaign-quality-audit-v1",
        "scope": "REUSED_DEVELOPMENT_ONLY",
        "origin_session": origin_session,
        "active_session": active_session,
        "origin_completed": sessions[origin_session]["completed"],
        "active_completed": sessions[active_session]["completed"],
        "generation_count": sum(int(item["completed"]) for item in sessions.values()),
        "dataset_hash": sessions[active_session]["dataset_hash"],
        "active_s7": _economic_records(evidences[active_session], reports[active_session]),
        "origin_s7": _economic_records(evidences[origin_session], reports[origin_session]),
        "active_s7_portfolio_risk_coverage": coverage,
        "latest_selected_parent": (
            {
                "source_generation_local": champion.get("source_generation") if champion else None,
                "total_return": quality.get("total_return"),
                "mdd": quality.get("max_drawdown"),
                "exposure": quality.get("market_exposure"),
                "closed_trades": quality.get("closed_trades"),
                "qqq_buy_and_hold_return": quality.get("qqq_buy_and_hold_return"),
            }
            if isinstance(quality, dict)
            else None
        ),
        "risk_flags": {
            "same_development_dataset": True,
            "independent_oos_unverified": not all(
                ev.get("independent_oos_approved") is True
                for group in evidences.values()
                for ev in group.values()
            ),
            "causal_inference_unverified": True,
            "multiple_testing_selection_risk": True,
            "random_vs_llm_comparison_absent": True,
            "sealed_oos_accessed": False,
            "global_mdd_for_each_s7_child_available": (
                coverage["replayed_full_period_risk_coverage"] == len(reports[active_session])
            ),
        },
        "integrity_scope": (
            "SQLite consistency + snapshot SHA256; "
            "source evidence hashes not independently replayed"
        ),
        "orders_enabled": False,
    }
