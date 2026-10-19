"""Recover an S7-verified parent from ordinary AlgorithmPlan generations.

This guards the missing bridge in genuine 350-generation research: the first
inherited generation must not require an earlier counted inherited generation.
Historical databases are only read as input and are never mutated.
"""

from __future__ import annotations

import sqlite3

from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
from research.llm.lineage_selection import choose_development_parent, replay_counted_s7_child
from tests.research.test_lineage_p0_3 import _actual_source


def test_replay_first_ordinary_s7_child_into_parent_pool():
    catalog, data, original, measured, hypothesis, _ = _actual_source(generation=29)
    assert original.get("inherited_strategy_ir") is None
    baseline = compile_algorithm_plan(
        catalog, AlgorithmPlan.model_validate(original["algorithm_plan"]), data
    )
    child, compiled = replay_counted_s7_child(
        catalog, data, original, measured, baseline.compiled, hypothesis["hypothesis_id"]
    )
    assert child["source_generation"] == 29
    assert child["source_kind"] == "COUNTED_S7_CHILD"
    assert child["source_evidence_hash"] == original["evidence_hash"]
    assert child["successor_strategy_hash"] == compiled.strategy_hash
    assert child["successor_total_return"] > child["child_total_return"]
    assert child["successor_closed_trades"] >= 30
    assert choose_development_parent([child]) is not None


def test_existing_ordinary_g33_session_bootstraps_without_sidecar(tmp_path):
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    from research.llm.autonomous_cycle import AcademicCycleService
    from tests.research.historical_g33_fixture import copy_historical_g33_checkpoint
    from tests.research.test_lineage_p0_3 import ROOT, SID

    clone = copy_historical_g33_checkpoint(tmp_path)
    with sqlite3.connect(clone / "gateway.sqlite") as db:
        db.execute("DELETE FROM parent_selections WHERE session_id=?", (SID,))
        db.execute("DELETE FROM successor_lineages WHERE session_id=?", (SID,))
    service = AcademicMCPCheckpointService(project_root=ROOT, state_dir=tmp_path)
    service.cycle = AcademicCycleService(clone / "cycles.sqlite")
    after = service.get({"session_id": SID})
    selected = after["model_context"]["selected_development_parent"]
    assert selected is not None
    assert selected["source_kind"] == "COUNTED_S7_CHILD"
    assert selected["source_generation"] >= 26
    assert after["model_context"]["counted_parent_inheritance_ready"] is True
    assert after["completed_generations"] == 33
    assert after["orders_enabled"] is False
    assert (
        service.get({"session_id": SID})["model_context"]["selected_development_parent"] == selected
    )


def test_bootstrapped_parent_is_the_actual_counted_next_generation(tmp_path):
    """S7 ordinary child -> selected parent -> real mutated G34, not a proxy."""
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    from research.llm.autonomous_cycle import AcademicCycleService
    from tests.research.historical_g33_fixture import copy_historical_g33_checkpoint
    from tests.research.test_lineage_p0_3 import ROOT, SID
    from tests.research.test_p0_3b_reinherit import _advance

    dst = copy_historical_g33_checkpoint(tmp_path)
    with sqlite3.connect(dst / "gateway.sqlite") as db:
        db.execute("DELETE FROM parent_selections WHERE session_id=?", (SID,))
        db.execute("DELETE FROM successor_lineages WHERE session_id=?", (SID,))
    service = AcademicMCPCheckpointService(project_root=ROOT, state_dir=tmp_path)
    service.cycle = AcademicCycleService(dst / "cycles.sqlite")
    selected = service.get({"session_id": SID})["model_context"]["selected_development_parent"]
    assert selected is not None
    counted = _advance(service, 0.28, 0.25)
    assert counted["completed_generations"] == 34
    last = counted["history"][-1]
    assert last["inherited_parent"]["source_generation"] == selected["source_generation"]
    assert last["inherited_parent"]["parent_strategy_hash"] == selected["successor_strategy_hash"]
    assert last["inherited_parent"]["parent_selection_hash"] == selected["selection_hash"]
    assert last["inherited_strategy_ir"] is not None
    assert (
        counted["latest_controlled_experiments"]["original_generation_evidence_hash"]
        == last["evidence_hash"]
    )
    assert counted["orders_enabled"] is False
    with sqlite3.connect(dst / "cycles.sqlite") as db:
        assert (
            db.execute(
                "SELECT count(*) FROM generations WHERE session_id=? AND generation=34", (SID,)
            ).fetchone()[0]
            == 1
        )


def test_plain_s7_bootstrap_rejects_forged_original_and_fees():
    from copy import deepcopy

    import pytest

    from core.integrity.hashes import content_hash
    from research.llm.lineage_selection import LineageSelectionError

    catalog, data, original, stored, hypothesis, _ = _actual_source(generation=29)
    baseline = compile_algorithm_plan(
        catalog, AlgorithmPlan.model_validate(original["algorithm_plan"]), data
    )
    altered = deepcopy(original)
    altered["plan_hash"] = "f" * 64
    with pytest.raises(LineageSelectionError, match="cannot replay"):
        replay_counted_s7_child(
            catalog, data, altered, stored, baseline.compiled, hypothesis["hypothesis_id"]
        )
    falsified = deepcopy(stored)
    falsified["report"]["experiments"][0]["execution_delta"]["child_costs"] += 100
    falsified["record_hash"] = content_hash(
        {key: value for key, value in falsified.items() if key != "record_hash"}
    )
    with pytest.raises(LineageSelectionError, match="replay mismatch"):
        replay_counted_s7_child(
            catalog,
            data,
            original,
            falsified,
            baseline.compiled,
            hypothesis["hypothesis_id"],
        )
