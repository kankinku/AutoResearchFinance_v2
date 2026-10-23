"""Replay existing G452 source in a disposable checkpoint, without GPT calls.

This only shows V3 negative research memories in the *next* real-model
planning context. It does not emit a GPT Plan, counted generation or broker order.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from research.llm.autonomous_cycle import CycleStateError
from research.llm.v3_parent_sidecar import ResearchParentSidecar

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "state/moon-http/fresh-20261021"
ORIGINAL = SOURCE / "research/academic-gpt-checkpoints"
SID = (SOURCE / "session-id.txt").read_text().strip()
SIDECAR = (
    ROOT
    / "state/moon-http/quant-v3-parent-sidecar-20261023"
    / "v3-research-parent-candidates.sqlite"
)
COHORT = "v3-3-parent-g452-development-20261023"
HEAD = "e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337"


def head() -> tuple[int, str]:
    with sqlite3.connect(
        "file:" + str((ORIGINAL / "cycles.sqlite").resolve()) + "?mode=ro",
        uri=True,
    ) as db:
        return (
            db.execute("SELECT count(*) FROM generations").fetchone()[0],
            db.execute(
                "SELECT evidence_hash FROM generations ORDER BY generation DESC LIMIT 1"
            ).fetchone()[0],
        )


def main() -> None:
    assert head() == (452, HEAD)
    with tempfile.TemporaryDirectory(prefix="quant-v3-context-integration-") as temp:
        state = Path(temp) / "research"
        copied = state / "academic-gpt-checkpoints"
        copied.mkdir(parents=True)
        for filename in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
            with (
                sqlite3.connect(ORIGINAL / filename) as original,
                sqlite3.connect(copied / filename) as clone,
            ):
                original.backup(clone)
        svc = AcademicMCPCheckpointService(
            project_root=ROOT,
            state_dir=state,
            parent_portfolio_v2=True,
            v3_research_memory=(SIDECAR, COHORT),
        )
        started = svc.extend_completed_session(SID, additional_generations=1)
        assert started["completed_generations"] == 452
        checkpoint = svc.get({"session_id": SID})
        assert checkpoint["checkpoint_phase"] == "AWAITING_PLAN"
        assert checkpoint["model_context"]["generation"] == 453
        memory = checkpoint["model_context"]["v3_prior_crossover_research"]
        selected = checkpoint["model_context"]["selected_development_parent"]
        assert memory["attempt_count"] == 6
        assert memory["source_ledger_head"] == HEAD
        assert memory["dataset_hash"] == checkpoint["history"][-1]["dataset_hash"]
        assert memory["official_generation_increment"] == 0
        assert memory["origin"] == "SCRIPTED_NOT_GPT"
        assert memory["automatic_parent_adoption"] is False
        assert memory["model_autonomy_verified"] is False
        assert selected["selection_hash"] != memory["last_event_hash"]
        assert sum(memory["decisions"].values()) == 6
        assert (
            svc.get({"session_id": SID})["model_context"]["v3_prior_crossover_research"] == memory
        )

        invalid = AcademicMCPCheckpointService(
            project_root=ROOT,
            state_dir=state,
            parent_portfolio_v2=True,
            v3_research_memory=(SIDECAR, "nonexistent-v3-cohort"),
        )
        try:
            invalid.get({"session_id": SID})
        except CycleStateError as exc:
            assert "V3 research-memory source integrity" in str(exc)
        else:
            raise AssertionError("unverified crossover memory was accepted")
        independent = AcademicMCPCheckpointService(
            project_root=ROOT, state_dir=state, parent_portfolio_v2=True
        )
        assert (
            "v3_prior_crossover_research"
            not in independent.get({"session_id": SID})["model_context"]
        )
        print(
            "V3_CLONE_CONTEXT_PASS",
            json.dumps(
                {
                    "future_generation": 453,
                    "checked_earlier_crossovers": memory["attempt_count"],
                    "decisions": memory["decisions"],
                    "memory_chain_head": memory["last_event_hash"],
                    "actual_development_parent_source_gen": selected["source_generation"],
                    "actual_development_parent_strategy_hash": selected["successor_strategy_hash"],
                    "model_generated_new_generations": 0,
                    "broker_orders": 0,
                    "original_g452_head": HEAD,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    assert head() == (452, HEAD)
    verified = ResearchParentSidecar.read_verified_summary(
        SIDECAR,
        COHORT,
        dataset_hash=memory["dataset_hash"],
        known_ancestor_hashes=(HEAD,),
    )
    assert verified["last_event_hash"] == memory["last_event_hash"]


if __name__ == "__main__":
    main()
