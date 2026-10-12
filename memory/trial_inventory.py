"""Read-only cross-workspace accounting of *observed* research attempts.

Never treat candidate instances as independent statistical trials. Sources
must be supplied explicitly; discovery across devices or private directories
is not possible from this module. Original immutable evidence is untouched.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from math import isfinite
from pathlib import Path
from typing import Any

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore, digest


def research_trial_inventory(state_dirs: Sequence[Path]) -> dict[str, Any]:
    """Aggregate checksum-validated EvidenceStores, fail closed on run conflicts.

    Exact mirrors of a run contribute only once. Partial or conflicting mirror
    records are rejected; they cannot quietly merge different attempt histories.
    """
    if not state_dirs or len(state_dirs) > 32:
        raise ValueError("explicitly provide between 1 and 32 workspace state directories")
    resolved = sorted({Path(path).resolve() for path in state_dirs})
    def numeric_or_nan(value: object) -> float:
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            return float(value)
        return float("nan")

    run_snapshots: dict[str, dict[str, tuple[str, str, dict[str, Any]]]] = {}
    duplicate_copies = 0
    for state in resolved:
        events = EvidenceStore(state).events()  # validates all immutable checksums
        local: dict[str, dict[str, tuple[str, str, dict[str, Any]]]] = defaultdict(dict)
        for item in events:
            event_id = item["id"]
            kind = item["kind"]
            payload = item["payload"]
            run_id = payload["research_run_id"]
            if event_id in local[run_id]:
                raise EvidenceIntegrityError("duplicate event identity")
            local[run_id][event_id] = (kind, digest([event_id, kind, payload]), payload)
        for run_id, snapshot in local.items():
            if run_id in run_snapshots:
                old = run_snapshots[run_id]
                if {key: (value[0], value[1]) for key, value in old.items()} != {
                    key: (value[0], value[1]) for key, value in snapshot.items()
                }:
                    raise EvidenceIntegrityError("conflicting or partial research run mirror")
                duplicate_copies += 1
            else:
                run_snapshots[run_id] = snapshot

    seen_attempt_ids: set[str] = set()
    scope_rows: dict[str, dict[str, Any]] = {}
    attempted_hashes: list[str] = []
    semantic_hashes: list[str] = []
    missing_semantic_hashes = 0
    attempted = final = attempts = failed = skipped = 0
    no_skip_measurements = False
    unscoped = unverified = unfinished = 0
    estimated_cohorts = 0
    unmeasured_cohorts = 0
    dependence_summaries: list[dict[str, Any]] = []
    for run_id, snapshot_events in sorted(run_snapshots.items()):
        by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for kind, _checksum, payload in snapshot_events.values():
            by_kind[kind].append(payload)
        if len(by_kind["run"]) != 1:
            raise EvidenceIntegrityError("research run registration missing or conflicting")
        if len(by_kind["manifest"]) > 1 or len(by_kind["end"]) > 1:
            raise EvidenceIntegrityError("conflicting manifest or run ending")
        manifests = by_kind["manifest"]
        key = manifests[0]["comparison_key"] if manifests else None
        if key is not None and (not isinstance(key, str) or not key):
            raise EvidenceIntegrityError("invalid comparison scope")
        if key is not None:
            scope = scope_rows.setdefault(
                key, {"run_ids": set(), "hashes": [], "semantic_hashes": [], "missing_semantic": 0}
            )
            scope["run_ids"].add(run_id)
        else:
            scope = None

        attempt_by_id: dict[str, dict[str, Any]] = {}
        for row in by_kind["attempt"]:
            attempt_id = row["attempt_id"]
            if attempt_id in seen_attempt_ids:
                raise EvidenceIntegrityError("attempt identity reused across research runs")
            seen_attempt_ids.add(attempt_id)
            attempt_by_id[attempt_id] = row
            attempts += 1
            failed += int(row["status"] == "FAILED")
            candidates = row["candidates"]
            count = len(candidates)
            dependence = row.get("trial_dependence")
            if dependence is None:
                unmeasured_cohorts += 1
            else:
                if not isinstance(dependence, dict) or not isinstance(
                    dependence.get("status"), str
                ):
                    raise EvidenceIntegrityError("invalid trial dependence summary")
                status = dependence["status"]
                if status == "ESTIMATED_TRAIN_ONLY_COHORT":
                    rank = dependence.get("effective_rank")
                    avg = dependence.get("average_absolute_correlation")
                    dispersion = dependence.get("observed_sharpe_dispersion")
                    rank_num = numeric_or_nan(rank)
                    avg_num = numeric_or_nan(avg)
                    dispersion_num = numeric_or_nan(dispersion)
                    bars = dependence.get("return_observations")
                    cutoff = dependence.get("training_cutoff_at")
                    if (
                        dependence.get("dsr_calibrated") is not False
                        or dependence.get("method")
                        != "CORRELATION_ENTROPY_EFFECTIVE_RANK"
                        or type(bars) is not int or bars < 30
                        or type(dependence.get("candidate_count")) is not int
                        or dependence["candidate_count"] != count
                        or not isinstance(cutoff, str)
                        or not cutoff
                        or not all(isfinite(v) for v in (rank_num, avg_num, dispersion_num))
                        or not 1.0 <= rank_num <= count
                        or not 0.0 <= avg_num <= 1.0
                        or dispersion_num < 0.0
                    ):
                        raise EvidenceIntegrityError("invalid empirical trial dependence")
                    estimated_cohorts += 1
                    dependence_summaries.append({
                        "research_run_id": run_id,
                        "generation": row["generation"],
                        "candidate_count": count,
                        "return_observations": bars,
                        "effective_rank_estimate": rank_num,
                        "average_absolute_correlation": avg_num,
                        "observed_sharpe_dispersion": dispersion_num,
                        "training_cutoff_at": cutoff,
                        "dsr_calibrated": False,
                    })
                else:
                    if dependence.get("effective_rank") is not None:
                        raise EvidenceIntegrityError("unmeasured dependence cannot report rank")
                    unmeasured_cohorts += 1
            attempted += count
            if row.get("verification") == "UNVERIFIED_EVALUATOR":
                unverified += count
            hashes = [item["candidate_hash"] for item in candidates]
            if any(not h for h in hashes):
                raise EvidenceIntegrityError("empty candidate identity")
            attempted_hashes.extend(hashes)
            for candidate in candidates:
                semantic = candidate.get("semantic_strategy_hash")
                if semantic is None:
                    missing_semantic_hashes += 1
                    if scope is not None:
                        scope["missing_semantic"] += 1
                elif (
                    not isinstance(semantic, str)
                    or len(semantic) != 64
                    or any(character not in "0123456789abcdef" for character in semantic)
                ):
                    raise EvidenceIntegrityError("invalid semantic strategy hash")
                else:
                    semantic_hashes.append(semantic)
                    if scope is not None:
                        scope["semantic_hashes"].append(semantic)
            if scope is not None:
                scope["hashes"].extend(hashes)
            else:
                unscoped += count

        linked_attempt_ids: set[str] = set()
        generation_ids: set[int] = set()
        for row in by_kind["generation"]:
            generation = row["generation"]
            if generation in generation_ids:
                raise EvidenceIntegrityError("duplicate final generation")
            generation_ids.add(generation)
            ref = row.get("attempt_id")
            if ref is not None:
                selected = attempt_by_id.get(ref)
                if (
                    selected is None
                    or selected["generation"] != generation
                    or selected["status"] != "COMPLETED"
                    or ref in linked_attempt_ids
                ):
                    raise EvidenceIntegrityError("invalid final research attempt reference")
                linked_attempt_ids.add(ref)
                final += len(selected["candidates"])
            if "duplicate_skipped" not in row:
                no_skip_measurements = True
            else:
                value = row["duplicate_skipped"]
                if type(value) is not int or value < 0:
                    raise EvidenceIntegrityError("invalid skipped candidate count")
                skipped += value

        if len(generation_ids) > by_kind["run"][0]["requested_generations"]:
            raise EvidenceIntegrityError("more final generations than requested")
        if not by_kind["end"] or len(generation_ids) < by_kind["run"][0]["requested_generations"]:
            unfinished += 1
        if by_kind["end"] and by_kind["end"][0]["status"] == "FAILED":
            unfinished += int(len(generation_ids) == by_kind["run"][0]["requested_generations"])

    scopes = []
    for key, group in sorted(scope_rows.items()):
        hashes = group["hashes"]
        scopes.append(
            {
                "comparison_key": key,
                "run_count": len(group["run_ids"]),
                "candidate_evaluation_instances": len(hashes),
                "unique_candidate_hashes": len(set(hashes)),
                "duplicate_candidate_evaluations": len(hashes) - len(set(hashes)),
                "manifest_provenance": "SELF_DECLARED_NOT_INDEPENDENTLY_VERIFIED",
                "unique_semantic_strategy_hashes": (
                    len(set(group["semantic_hashes"]))
                    if not group["missing_semantic"] and group["semantic_hashes"]
                    else None
                ),
                "missing_semantic_hash_instances": group["missing_semantic"],
            }
        )
    unique = len(set(attempted_hashes))
    return {
        "status": "OBSERVED" if run_snapshots else "EMPTY",
        "workspace_count": len(resolved),
        "research_run_count": len(run_snapshots),
        "duplicate_research_run_copies": duplicate_copies,
        "evaluation_attempt_count": attempts,
        "failed_evaluation_attempt_count": failed,
        "candidate_evaluation_instances": attempted,
        "finalized_candidate_instances": final,
        "nonfinal_candidate_instances": attempted - final,
        "unique_candidate_hashes_global": unique,
        "unique_semantic_strategy_hashes_global": (
            len(set(semantic_hashes)) if not missing_semantic_hashes and semantic_hashes else None
        ),
        "missing_semantic_hash_instances": missing_semantic_hashes,
        "duplicate_candidate_evaluations_global": attempted - unique,
        "total_skipped_duplicate_candidates": None if no_skip_measurements else skipped,
        "unscoped_candidate_evaluation_instances": unscoped,
        "unverified_evaluator_candidate_instances": unverified,
        "unfinished_research_runs": unfinished,
        "scopes": scopes,
        "comparability": "MANIFEST_SCOPED_ONLY",
        "effective_independent_trials": None,
        "effective_trials_status": "NOT_MEASURED",
        "trial_dependence_estimated_cohorts": estimated_cohorts,
        "trial_dependence_unmeasured_cohorts": unmeasured_cohorts,
        "trial_dependence_diagnostics_sample": dependence_summaries[-10:],
        "trial_dependence_scope": "TRAIN_ONLY_COHORT_NOT_GLOBAL_DSR",
        "history_complete": False,
        "coverage": "EXPLICIT_WORKSPACE_EVIDENCE_ONLY",
        "note": (
            "Observed candidate rows are not independent hypothesis tests. "
            "Unregistered external workspaces and legacy attempts are not counted; "
            "a matching manifest does not prove source timing or data quality."
        ),
    }
