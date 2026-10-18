"""P0-2A: help GPT use EXISTING safe child->successor machinery.

No market orders, no artificial auto-promotion and no runtime DB mutation.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from research.llm.lineage_bootstrap_guidance import (
    LineageBootstrapIntegrityError,
    build_lineage_bootstrap_guidance,
)


def _source(generation: int, *, inherited: bool = False) -> dict:
    original = {
        "generation": generation,
        "evidence_hash": f"{generation:064x}",
        "audit_hash": "a" * 64,
        "dataset_hash": "b" * 64,
        "diagnostic_proposal_hash": "c" * 64,
        "algorithm_plan": {"plan_id": "research_plan_test_original"},
        "experiments": [
            {"hypothesis_id": "q1", "proposal_child_hash": "d" * 64},
        ],
    }
    if inherited:
        original["inherited_strategy_ir"] = {"strategy_id": "inherited"}
    return original


def _report(source: dict, *, gain: float = 1200, signals: int = 2, fills: int = 62) -> dict:
    return {
        "record_hash": "f" * 64,
        "original_generation_evidence_hash": source["evidence_hash"],
        "report": {
            "evidence_hash": source["evidence_hash"],
            "audit_hash": source["audit_hash"],
            "dataset_hash": source["dataset_hash"],
            "diagnostic_proposal_hash": source["diagnostic_proposal_hash"],
            "experiments": [
                {
                    "hypothesis_id": "q1",
                    "child_strategy_hash": "d" * 64,
                    "causal_status": "NOT_ESTABLISHED",
                    "child_fill_count": fills,
                    "parent_final_equity": 11000.0,
                    "child_final_equity": 11000 + gain,
                    "execution_delta": {
                        "added_event_count": signals,
                        "removed_event_count": 0,
                        "resized_event_count": 4,
                        "execution_timing_changed": signals > 0,
                    },
                },
            ],
        },
    }


def test_signal_candidates_only_and_no_mutation() -> None:
    originals = [_source(g) for g in range(1, 7)]
    reports = {
        1: _report(originals[0], gain=6000),
        2: _report(originals[1], signals=0),  # resizing alone not signal improvement
        3: _report(originals[2], gain=-10),
        4: _report(originals[3], fills=58),  # insufficient fill proxy
        5: _report(originals[4], gain=5000),
        6: _report(originals[5], gain=7000),
    }
    pristine = deepcopy((originals, reports))
    reduced = build_lineage_bootstrap_guidance(originals, reports, limit=2)
    assert reduced["status"] == "REPLAY_CANDIDATES_FOUND"
    assert reduced["possible_candidates"] == 3
    assert [x["source_generation"] for x in reduced["candidates"]] == [6, 1]
    assert reduced["candidates"][0]["child_strategy_hash"] == "d" * 64
    assert reduced["candidates"][0]["continuation_parent_strategy_id"] == (
        "research_plan_test_original"
    )
    assert all(x["status"] == "REPLAY_REQUIRED_NOT_PROMOTED" for x in reduced["candidates"])
    assert reduced["automatic_parent_promotion"] is False
    assert reduced["orders_enabled"] is False
    assert reduced["independent_oos_approved"] is False
    assert (originals, reports) == pristine
    assert build_lineage_bootstrap_guidance(originals, reports, limit=2) == reduced


def test_empty_and_non_replayable_are_honest() -> None:
    assert build_lineage_bootstrap_guidance([], {})["status"] == ("NO_SIGNAL_IMPROVING_CHILD_FOUND")
    source = _source(1)
    assert (
        build_lineage_bootstrap_guidance([source], {1: _report(source, signals=0)})[
            "possible_candidates"
        ]
        == 0
    )
    inherited = _source(1, inherited=True)
    assert (
        build_lineage_bootstrap_guidance([inherited], {1: _report(inherited)})[
            "possible_candidates"
        ]
        == 0
    )


def test_tampered_source_and_report_fail_closed() -> None:
    source = _source(1)
    report = _report(source)
    for tamper in (
        lambda x: x.__setitem__("original_generation_evidence_hash", "0" * 64),
        lambda x: x["report"].__setitem__("audit_hash", "0" * 64),
        lambda x: x["report"]["experiments"][0].__setitem__("child_strategy_hash", "0" * 64),
        lambda x: x["report"]["experiments"][0].__setitem__("hypothesis_id", "wrong"),
    ):
        damaged = deepcopy(report)
        tamper(damaged)
        with pytest.raises(LineageBootstrapIntegrityError):
            build_lineage_bootstrap_guidance([source], {1: damaged})


def test_bootstrap_limit_enforced() -> None:
    with pytest.raises(ValueError, match="limit"):
        build_lineage_bootstrap_guidance([], {}, limit=0)
    with pytest.raises(ValueError, match="limit"):
        build_lineage_bootstrap_guidance([], {}, limit=11)


def test_real_mcp_checkpoint_stays_unpromoted_without_verified_lineage(tmp_path) -> None:
    """The new advisory must not fabricate a parent or consume a generation."""
    from tests.integrations.test_academic_mcp_sessions import _setup
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    server, started = _setup(tmp_path)
    sid = started["session_id"]
    assert started["model_context"]["verified_lineage_bootstrap"]["status"] == (
        "NO_SIGNAL_IMPROVING_CHILD_FOUND"
    )
    provider = ScriptedResearcher()
    pending = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": sid,
            "checkpoint_token": started["checkpoint_token"],
            "plan": provider.propose(started["model_context"]),
        },
    )
    observed = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": sid,
            "checkpoint_token": pending["checkpoint_token"],
            "diagnosis": provider.propose(pending["model_context"]),
        },
    )
    assert observed["completed_generations"] == 1
    assert (
        observed["model_context"]["verified_lineage_bootstrap"]["automatic_parent_promotion"]
        is False
    )
    assert observed["model_context"]["counted_parent_inheritance_ready"] is False
    from application.academic_checkpoint_service import AcademicMCPCheckpointService

    svc = AcademicMCPCheckpointService(project_root=server.project_root, state_dir=server.state_dir)
    with svc._connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM parent_selections WHERE session_id=?", (sid,)
            ).fetchone()[0]
            == 0
        )
