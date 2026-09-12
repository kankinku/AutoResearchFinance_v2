"""Read-only research evidence projections; missing evidence is never a pass."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore

PASSED = {"SURVIVOR", "FRONTIER"}


def _unmeasured(reason: str) -> dict[str, Any]:
    return {"status": "NOT_MEASURED", "value": None, "reason": reason}


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _best(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [r for r in rows if isinstance(r.get("score"), (int, float))]
    return max(scored, key=lambda r: (r["score"], r["candidate_hash"])) if scored else None


def _run_summary(run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    manifests = [e["payload"] for e in events if e["kind"] == "manifest"]
    attempts = {e["payload"]["attempt_id"]: e["payload"] for e in events if e["kind"] == "attempt"}
    finals = sorted(
        (e["payload"] for e in events if e["kind"] == "generation"), key=lambda r: r["generation"]
    )
    if len({r["generation"] for r in finals}) != len(finals):
        raise EvidenceIntegrityError("duplicate final generation")
    rows: list[dict[str, Any]] = []
    curves = []
    repeated = 0
    failed = 0
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for final in finals:
        selected = attempts.get(final.get("attempt_id"))
        if final.get("attempt_id") and (
            selected is None
            or selected["generation"] != final["generation"]
            or selected["status"] != "COMPLETED"
        ):
            raise EvidenceIntegrityError("invalid final attempt reference")
        candidates = selected.get("candidates", []) if selected else []
        for row in candidates:
            if row["status"] == "REJECT":
                signature = (row["candidate_hash"], tuple(sorted(row["failed_gates"])))
                repeated += int(signature in seen)
                failed += 1
                seen.add(signature)
        rows.extend(candidates)
        curves.append(
            {
                "generation": final["generation"],
                "status": final["status"],
                "candidate_count": len(candidates),
                "best_attempt": _best(candidates),
                "best_passed": _best([r for r in candidates if r["status"] in PASSED]),
            }
        )
    valid = [r for r in rows if r.get("validation_evaluated")]
    ends = [e["payload"] for e in events if e["kind"] == "end"]
    if len(manifests) > 1 or len(ends) > 1 or len(finals) > run["requested_generations"]:
        raise EvidenceIntegrityError("conflicting run evidence")
    if (
        ends
        and ends[0]["status"].startswith("COMPLETED")
        and (len(finals) != run["requested_generations"])
    ):
        raise EvidenceIntegrityError("completed run lacks final generations")
    return {
        **run,
        "status": ends[0]["status"] if ends else "INCOMPLETE",
        "comparison_key": manifests[0]["comparison_key"] if manifests else None,
        "manifest": manifests[0] if manifests else None,
        "completed_generations": len(finals),
        "completion_rate": _rate(len(finals), run["requested_generations"]),
        "generation_status_counts": dict(Counter(r["status"] for r in finals)),
        "fallback_rate": _rate(sum(r["status"] == "FALLBACK" for r in finals), len(finals)),
        "candidate_count": len(rows),
        "reject_count": sum(r["status"] == "REJECT" for r in rows),
        "unique_candidate_count": len({r["candidate_hash"] for r in rows}),
        "all_attempt_candidate_count": sum(len(a.get("candidates", [])) for a in attempts.values()),
        "evaluation_attempt_count": len(attempts),
        "failed_evaluation_attempt_count": sum(a["status"] == "FAILED" for a in attempts.values()),
        "pass_rate": _rate(sum(r["status"] in PASSED for r in rows), len(rows)),
        "pass_rate_reason": None if rows else "NO_EVALUATED_CANDIDATES",
        "failed_gates": dict(Counter(g for r in rows for g in r["failed_gates"])),
        "repeated_failure_rate": _rate(repeated, failed),
        "validation_survival": {
            "status": "MEASURED" if valid else "NOT_MEASURED",
            "value": _rate(sum(r.get("validation_passed") is True for r in valid), len(valid)),
            "evaluated": len(valid),
            "scope": (
                (str(manifests[0].get("data_zone", "unknown")) if manifests else "unknown")
                + "_walk_forward"
            ),
        },
        "champion_improvement": _unmeasured("NO_SCOPED_PROMOTION_EVENTS"),
        "hypothesis_success": _unmeasured("NO_VALIDATED_HYPOTHESIS_OUTCOMES"),
        "branch_extinction": _unmeasured("NO_BRANCH_LIFECYCLE_EVENTS"),
        "generations": curves,
    }


def research_evidence(state_dir: Path, run_id: str | None = None) -> dict[str, Any]:
    events = EvidenceStore(state_dir).events()
    runs = [e["payload"] for e in events if e["kind"] == "run"]
    if len({r["research_run_id"] for r in runs}) != len(runs):
        raise EvidenceIntegrityError("duplicate run")
    known = {r["research_run_id"] for r in runs}
    if any(e["payload"].get("research_run_id") not in known for e in events):
        raise EvidenceIntegrityError("orphan evidence")
    summaries = [
        _run_summary(
            r, [e for e in events if e["payload"]["research_run_id"] == r["research_run_id"]]
        )
        for r in runs
        if run_id is None or r["research_run_id"] == run_id
    ]
    legacy_count = 0
    legacy = state_dir / "test-records.jsonl"
    if legacy.is_file():
        try:
            with legacy.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip() and not json.loads(line).get("research_run_id"):
                        legacy_count += 1
        except (ValueError, AttributeError) as exc:
            raise EvidenceIntegrityError("legacy evidence is malformed") from exc
    families: dict[str, Any] = {}
    frontier_path = state_dir / "frontier.json"
    if frontier_path.is_file():
        try:
            families = json.loads(frontier_path.read_text(encoding="utf-8")).get("families", {})
            if not isinstance(families, dict):
                raise ValueError("invalid families")
        except (ValueError, AttributeError) as exc:
            raise EvidenceIntegrityError("frontier state is malformed") from exc
    return {
        "schema_version": 1,
        "status": "OK" if summaries else "EMPTY",
        "runs": summaries,
        "legacy": {
            "status": "LEGACY_UNSCOPED" if legacy_count else "ABSENT",
            "record_count": legacy_count,
        },
        "frontier": {
            "scope": "current_state_unscoped",
            "family_count": len(families),
            "distribution": {k: len(v) if isinstance(v, list) else 1 for k, v in families.items()},
        },
        "sealed_oos_survival": _unmeasured("NO_AUTHORIZED_SEALED_OOS_RESULTS"),
        "orders_enabled": False,
    }


def compare_runs(state_dir: Path, run_ids: list[str]) -> list[dict[str, Any]]:
    runs = {r["research_run_id"]: r for r in research_evidence(state_dir)["runs"]}
    if not run_ids or any(run_id not in runs for run_id in run_ids):
        raise ValueError("missing comparison run")
    selected = [runs[run_id] for run_id in run_ids]
    keys = {r["comparison_key"] for r in selected}
    if None in keys or len(keys) != 1:
        raise ValueError("comparison conditions differ or are unavailable")
    return selected
