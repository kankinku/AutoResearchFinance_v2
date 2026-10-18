"""P0-2B: replay REAL stored S7 child→successor→counted S2/S7, isolated.

This is a development-only reproducibility/connection test. It does NOT run a
real remote GPT provider, grant trading access or touch the production ledger.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService

ROOT = Path("/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory")
SID = "c1eadd67bad94d7ea182dc274224dbce"
SOURCE_GENERATION = 25
G54 = 54
EXPECTED_SOURCE_DATASET_HASH = "328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6"


def _shadow(tmp_path: Path) -> AcademicMCPCheckpointService:
    source = ROOT / "state/moon-http/research/academic-gpt-checkpoints"
    if not all(
        (source / name).exists()
        for name in (
            "cycles.sqlite",
            "gateway.sqlite",
            "catalog-s6-v2.sqlite",
        )
    ):
        pytest.skip("Pinned real Moon 53-generation research snapshot not installed")
    target = tmp_path / "academic-gpt-checkpoints"
    target.mkdir()
    for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        source_db = sqlite3.connect(f"file:{source / name}?mode=ro", uri=True)
        copied_db = sqlite3.connect(target / name)
        try:
            source_db.backup(copied_db)
            assert copied_db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            copied_db.close()
            source_db.close()
    return AcademicMCPCheckpointService(project_root=ROOT, state_dir=tmp_path)


def _continuation(parent_id: str) -> dict:
    return {
        "mode": "structure",
        "parent_ids": [parent_id],
        "operations": [
            {
                "op": "REPLACE_RULE",
                "path": "exit.conditions.0",
                "condition": {"left": "plan_vote_score", "op": "less_equal", "value": 0.78},
            }
        ],
        "rationale": (
            "Controlled development test of exit confirmation for the exact "
            "costed S7 child; the new rule may miss trends as well as avoid losses."
        ),
    }


def test_real_g25_child_promotes_as_verified_parent_then_counted_g54(tmp_path: Path) -> None:
    service = _shadow(tmp_path)
    first = service.get({"session_id": SID})
    assert first["completed_generations"] == 53
    assert first["checkpoint_phase"] == "AWAITING_PLAN"
    assert first["model_context"]["selected_development_parent"] is None
    assert first["model_context"]["verified_lineage_bootstrap"]["possible_candidates"] == 7
    original_53_hashes = [x["evidence_hash"] for x in first["history"]]
    source = first["history"][SOURCE_GENERATION - 1]
    proposal = source["experiments"][0]
    assert source["dataset_hash"] == EXPECTED_SOURCE_DATASET_HASH
    assert proposal["hypothesis_id"] == "t4_g025_s7_rule_structure"

    continuation = _continuation(proposal["proposed_intent"]["parent_ids"][0])
    request = {
        "session_id": SID,
        "generation": SOURCE_GENERATION,
        "checkpoint_token": first["checkpoint_token"],
        "hypothesis_id": proposal["hypothesis_id"],
        "child_strategy_hash": proposal["proposal_child_hash"],
        "continuation_intent": continuation,
    }
    with pytest.raises(ValueError, match="child|identity|mismatch"):
        service.continue_verified_child({**request, "child_strategy_hash": "0" * 64})

    lineage = service.continue_verified_child(request)
    assert service.continue_verified_child(request) == lineage  # replay idempotent
    assert lineage["reproduced_child_strategy_hash"] == proposal["proposal_child_hash"]
    assert lineage["child_total_return"] == pytest.approx(0.2870318011, abs=1e-9)
    assert lineage["successor_total_return"] == pytest.approx(0.3687998095, abs=1e-9)
    assert lineage["independent_oos_approved"] is False
    assert lineage["broker_executable"] is False
    assert lineage["generation_counter_incremented"] is False

    prepared = service.get({"session_id": SID})
    assert prepared["completed_generations"] == 53  # sidecar cannot count a generation
    chosen = prepared["model_context"]["selected_development_parent"]
    assert chosen is not None
    assert chosen["source_generation"] == SOURCE_GENERATION
    assert chosen["successor_strategy_hash"] == lineage["successor_strategy_hash"]
    assert chosen["lineage_report_hash"] == lineage["report_hash"]
    assert chosen["independent_oos_approved"] is False
    assert prepared["model_context"]["output_contract"] == "InheritedResearchIntent"
    parent_id = prepared["model_context"]["inherited_parent_strategy_id"]

    # Existing strict S2 preflight MUST reject unchanged executions without
    # consuming the same GPT planning checkpoint; no silent generation count.
    def candidate(threshold: float) -> dict:  # exact parent, single bounded operation
        return {
            "mode": "structure",
            "parent_ids": [parent_id],
            "operations": [
                {
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": {
                        "left": "plan_vote_score",
                        "op": "less_equal",
                        "value": threshold,
                    },
                }
            ],
            "rationale": (
                "Change exit confirmation of replayed S7 descendant and "
                "compare original immutable execution evidence."
            ),
        }

    with pytest.raises(ValueError, match="UNCHANGED_CANONICAL_FILLS"):
        service.submit_plan(
            {
                "session_id": SID,
                "checkpoint_token": prepared["checkpoint_token"],
                "plan": candidate(0.75),
                "require_execution_change": True,
            }
        )
    assert service.get({"session_id": SID})["completed_generations"] == 53

    staged = service.submit_plan(
        {
            "session_id": SID,
            "checkpoint_token": prepared["checkpoint_token"],
            "plan": candidate(0.82),
            "require_execution_change": True,
        }
    )
    assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    audit = staged["model_context"]
    assert audit["s2_execution_preflight"]["status"] == "VERIFIED_DIFFERENT_COSTED_FILLS"
    assert audit["s2_execution_preflight"]["same_fill_trace"] is False
    example = audit["observations"]["loss_cases"][0]

    diagnosis = {
        "context_hash": audit["context_hash"],
        "audit_hash": audit["audit_hash"],
        "strategy_hash": audit["strategy_hash"],
        "dataset_hash": audit["dataset_hash"],
        "summary": (
            "The inherited development strategy changed real costed fills, "
            "but those changes might worsen risk or fees. Investigate the "
            "observed losing trade via a frozen-parent S7 comparison."
        ),
        "hypotheses": [
            {
                "hypothesis_id": "t4_p0_2b_shadow_g54_exit",
                "observed_ids": [example["trade_id"]],
                "mechanism": "An earlier exit could reduce the duration of trend reversal losses.",
                "alternative": "Earlier exits could increase turnover and remove winners.",
                "expected_metric": "trade_count",
                "predicted_direction": "INCREASE",
                "test_design": "RULE_STRUCTURE",
                "control": "PARENT_UNCHANGED",
                "next_intent": {
                    **candidate(0.72),
                    "parent_ids": [audit["algorithm_parent_id"]],
                },
            }
        ],
    }
    committed = service.submit_diagnosis(
        {
            "session_id": SID,
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": diagnosis,
        }
    )
    assert committed["completed_generations"] == G54
    assert committed["checkpoint_phase"] == "AWAITING_PLAN"
    assert [x["evidence_hash"] for x in committed["history"][:53]] == original_53_hashes
    g54 = committed["history"][-1]
    assert g54["previous_evidence_hash"] == original_53_hashes[-1]
    assert g54["inherited_parent"]["parent_selection_hash"] == chosen["selection_hash"]
    assert g54["inherited_parent"]["parent_strategy_hash"] == lineage["successor_strategy_hash"]
    assert g54["broker_executable"] is False
    assert g54["independent_oos_approved"] is False
    report = service.evaluate_experiments({"session_id": SID, "generation": G54})
    assert report["original_generation_evidence_hash"] == g54["evidence_hash"]
    assert report["report"]["experiments"][0]["status"] == (
        "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY"
    )  # A genuine negative follow-up stays in the ledger.

    with service._connect() as db:
        parent_count = db.execute(
            "SELECT count(*) FROM parent_selections WHERE session_id=?", (SID,)
        ).fetchone()[0]
        successor_count = db.execute(
            "SELECT count(*) FROM successor_lineages WHERE session_id=?", (SID,)
        ).fetchone()[0]
        recorded = db.execute(
            "SELECT count(*) FROM experiment_reports WHERE session_id=?", (SID,)
        ).fetchone()[0]
    assert parent_count >= 1
    assert successor_count == 1
    assert recorded == 54
