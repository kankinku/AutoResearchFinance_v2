"""T4 guarded G179->G180 fixture drill on disposable SQLite backups.

Uses a deterministic DIAGNOSTIC SMOKE PROPOSAL, not external ChatGPT
inference, not an approved counted live generation, and not a strategy tip.
No production database, launcher, OAuth state, or OOS source is modified.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.integrity.hashes import content_hash


class ShadowCheckpointError(ValueError):
    """Refuse an unsafe snapshot or unverifiable clone."""


def _clone_db(origin: Path, target: Path) -> None:
    if not origin.is_file() or target.exists():
        raise ShadowCheckpointError("snapshot missing or destination already exists")
    with sqlite3.connect(f"file:{origin}?mode=ro", uri=True) as old, sqlite3.connect(target) as new:
        old.backup(new)


def shadow_checkpoint(
    *, project_root: Path, snapshot: Path, session_id: str, expected_generations: int
) -> dict[str, Any]:
    """Asserts old→new evidence continuity via actual checkpoint orchestration.

    The next intent is intentionally specified before seeing the new diagnosis
    or result. The risk hypothesis is hypothetical; S7 return is NOT alpha.
    """
    if not snapshot.is_dir() or project_root.resolve() == snapshot.resolve():
        raise ShadowCheckpointError("missing independent frozen snapshot")
    if len(session_id) != 32 or expected_generations <= 0:
        raise ShadowCheckpointError("invalid existing session identity")
    with tempfile.TemporaryDirectory(prefix="t4-shadow-") as directory:
        state = Path(directory) / "academic-gpt-checkpoints"
        state.mkdir()
        for filename in ("cycles.sqlite", "gateway.sqlite"):
            _clone_db(snapshot / filename, state / filename)
        _clone_db(snapshot / "catalog-for-risk-replay.sqlite", state / "catalog-s6-v2.sqlite")
        service = AcademicMCPCheckpointService(project_root=project_root, state_dir=Path(directory))
        initial = service.get({"session_id": session_id})
        context = initial["model_context"]
        if (
            initial["completed_generations"] != expected_generations
            or initial["checkpoint_phase"] != "AWAITING_PLAN"
            or context.get("output_contract") != "InheritedResearchIntent"
            or context.get("cross_generation_memory", {}).get("counted_s7_trials")
            != expected_generations
            or context.get("paired_s7_evidence_link", {}).get("independent_oos_approved")
            is not False
            or context.get("trade_cohort_review", {}).get("causal_status") != "NOT_ESTABLISHED"
        ):
            raise ShadowCheckpointError("pre-existing checkpoint or integration evidence missing")
        old_hashes = [row["evidence_hash"] for row in initial["history"]]
        # Fixed smoke input, NOT selected after checking child results.
        plan = {
            "mode": "structure",
            "parent_ids": [context["inherited_parent_strategy_id"]],
            "rationale": (
                "SHADOW_SMOKE_ONLY: change an existing Parkinson entry gate "
                "under canonical replay, not a trading recommendation"
            ),
            "operations": [
                {
                    "op": "REPLACE_RULE",
                    "path": "entry.conditions.1",
                    "condition": {
                        "left": "parkinson_variance",
                        "op": "less_equal",
                        "value": 0.00008,
                        "enabled": True,
                    },
                }
            ],
        }
        stage = service.submit_plan(
            {
                "session_id": session_id,
                "checkpoint_token": initial["checkpoint_token"],
                "plan": plan,
            }
        )
        if stage["checkpoint_phase"] != "AWAITING_DIAGNOSIS":
            raise ShadowCheckpointError("G180 shadow plan was not stageable")
        diagnostic = stage["model_context"]
        obs = diagnostic["observations"]
        examples = obs["loss_cases"] or obs["execution_samples"]
        if not examples:
            raise ShadowCheckpointError("no verified decision/trade references")
        first = examples[0]
        ids = [first.get(k) for k in ("trade_id", "fill_id", "decision_id") if first.get(k)]
        if not ids:
            raise ShadowCheckpointError("missing stable S2 evidence references")
        next_intent = {
            "mode": "structure",
            "parent_ids": [diagnostic["algorithm_parent_id"]],
            "rationale": (
                "Counterfactual smoke only: isolate the effect of the exit "
                "vote threshold, with parent unchanged as control"
            ),
            "operations": [
                {
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": {
                        "left": "plan_vote_score",
                        "op": "less_equal",
                        "value": 0.65,
                        "enabled": True,
                    },
                }
            ],
        }
        diagnosis = {
            "context_hash": diagnostic["context_hash"],
            "audit_hash": diagnostic["audit_hash"],
            "strategy_hash": diagnostic["strategy_hash"],
            "dataset_hash": diagnostic["dataset_hash"],
            "summary": (
                "Observed G180 inherited candidate and measured costed trades. "
                "Changing a threshold cannot prove cause; isolate next experiment."
            ),
            "hypotheses": [
                {
                    "hypothesis_id": "shadow-g180-exit-vote-ablation",
                    "observed_ids": ids[:1],
                    "mechanism": (
                        "A revised exit vote may shorten adverse holdings within "
                        "the selected development regime, not proven causal."
                    ),
                    "alternative": (
                        "Changed thresholds may also close profitable holdings "
                        "earlier or alter trading costs with no net benefit."
                    ),
                    "expected_metric": "max_drawdown",
                    "predicted_direction": "DECREASE",
                    "test_design": "PARAMETER",
                    "control": "PARENT_UNCHANGED",
                    "next_intent": next_intent,
                }
            ],
        }
        advanced = service.submit_diagnosis(
            {
                "session_id": session_id,
                "checkpoint_token": stage["checkpoint_token"],
                "diagnosis": diagnosis,
            }
        )
        new_history = advanced["history"]
        if (
            advanced["completed_generations"] != expected_generations + 1
            or [row["evidence_hash"] for row in new_history[:-1]] != old_hashes
            or not advanced["latest_controlled_experiments"]
            or advanced.get("orders_enabled") is not False
            or advanced["model_context"]["cross_generation_memory"]["counted_s7_trials"]
            != expected_generations + 1
            or advanced["model_context"]["trade_cohort_review"]["causal_status"]
            != "NOT_ESTABLISHED"
        ):
            raise ShadowCheckpointError("shadow next-generation counted evidence mismatch")
        repeat = service.get({"session_id": session_id})
        if (
            repeat["completed_generations"] != advanced["completed_generations"]
            or repeat["history"] != advanced["history"]
        ):
            raise ShadowCheckpointError("new-generation replay / resume not idempotent")
        evidence = {
            "status": "SHADOW_G180_S2_S7_REPLAY_VERIFIED_NO_LIVE_MUTATION",
            "original_generations": expected_generations,
            "shadow_generations": advanced["completed_generations"],
            "original_history_hash": content_hash(old_hashes),
            "new_generation_evidence_hash": new_history[-1]["evidence_hash"],
            "new_generation_s7_record_hash": advanced["latest_controlled_experiments"][
                "record_hash"
            ],
            "next_plan_evidence_sources": [
                key
                for key in (
                    "loss_attribution",
                    "trade_cohort_review",
                    "paired_s7_evidence_link",
                    "cross_generation_memory",
                )
                if key in advanced["model_context"]
            ],
            "shadow_s7_tested_hypotheses": len(
                advanced["latest_controlled_experiments"]["report"]["experiments"]
            ),
            "real_external_gpt_mcp_called": False,
            "actual_production_generation_advanced": False,
            "orders_enabled": False,
            "independent_oos_approved": False,
        }
        return {**evidence, "receipt_hash": content_hash(evidence)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--completed", type=int, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            shadow_checkpoint(
                project_root=args.root,
                snapshot=args.snapshot,
                session_id=args.session_id,
                expected_generations=args.completed,
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
