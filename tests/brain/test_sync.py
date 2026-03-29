from __future__ import annotations

from pathlib import Path

from finance_autoresearch.brain import BrainSync, BrainWriter
from finance_autoresearch.localization import OutputLocalizer
from finance_autoresearch.state.sqlite_store import SQLiteStateStore


def test_brain_sync_exports_iteration_bundle_and_maps(tmp_path: Path) -> None:
    store = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    try:
        store.record_run(run_id="run-001", state="success")
        store.record_experiment(
            run_id="run-001",
            iteration=1,
            candidate_revision="candidate-001",
            baseline_revision="baseline-001",
            hypothesis="test hypothesis",
            mutation_summary="test mutation",
            backtest_metrics={"score": 1.2, "guardrail_failures": []},
            decision="keep",
        )
        store.record_research_plan(
            run_id="run-001",
            iteration=1,
            hypothesis="test plan",
            summary="test summary",
            plan_output={"family": "simplify_filters"},
        )
        store.record_analysis(
            run_id="run-001",
            iteration=1,
            analysis_output={
                "strengths": ["good"],
                "weaknesses": [],
                "coverage_gaps": [],
                "regime_observations": [],
                "next_hypothesis_hints": [],
                "summary": "analysis summary",
            },
            summary="analysis summary",
        )
        store.record_lesson(
            run_id="run-001",
            iteration=1,
            decision="keep",
            summary="lesson summary",
            lesson_output={"next_actions": ["next action"]},
        )
        store.record_lesson_graph(
            run_id="run-001",
            iteration=1,
            decision="keep",
            thesis="simplify",
            mutation_delta="remove one filter",
            observed_outcome="keep",
            failure_mode="",
            next_action="probe turnover",
            confidence="medium",
            novelty_score=0.5,
            knowledge_source_ids=("knowledge/indicators/rsi.md",),
        )
        store.record_family_memory(
            family="simplify_filters",
            symbol_scope="all",
            timeframe_scope="mixed",
            regime_scope="mixed",
            outcome="keep",
            linked_run_id="run-001",
            linked_iteration=1,
            novelty_score=0.5,
        )

        sync = BrainSync(
            store=store,
            writer=BrainWriter(root=tmp_path / "knowledge" / "vault"),
        )
        notes = sync.export_iteration_bundle(run_id="run-001", iteration=1)

        iteration_note = tmp_path / "knowledge" / "vault" / "01 Iterations" / "run-001-1.md"
        experiment_note = (
            tmp_path
            / "knowledge"
            / "vault"
            / "02 Experiments"
            / "run-001-1-candidate-001.md"
        )
        family_note = tmp_path / "knowledge" / "vault" / "08 Families" / "simplify_filters.md"
        map_note = tmp_path / "knowledge" / "vault" / "90 Maps" / "Active Experiments.md"
        family_map = tmp_path / "knowledge" / "vault" / "90 Maps" / "Family Memory.md"
        strategy_map = tmp_path / "knowledge" / "vault" / "90 Maps" / "Strategy Evolution.md"

        assert len(notes) >= 5
        assert iteration_note.exists()
        assert experiment_note.exists()
        assert family_note.exists()
        assert map_note.exists()
        assert family_map.exists()
        assert strategy_map.exists()
        assert "[[02 Experiments/run-001-1-candidate-001]]" in iteration_note.read_text(
            encoding="utf-8"
        )
        assert store.list_brain_maps(limit=10)[0].path == "90 Maps/Active Experiments.md"
    finally:
        store.close()


def test_brain_sync_rebuilds_missing_generated_notes_from_iteration_history(
    tmp_path: Path,
) -> None:
    store = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    try:
        store.record_run(run_id="run-001", state="success")
        store.record_experiment(
            run_id="run-001",
            iteration=1,
            candidate_revision="candidate-001",
            baseline_revision="baseline-001",
            hypothesis="test hypothesis",
            mutation_summary="test mutation",
            backtest_metrics={"score": 1.2, "guardrail_failures": []},
            decision="keep",
        )
        store.record_research_plan(
            run_id="run-001",
            iteration=1,
            hypothesis="test plan",
            summary="test summary",
            plan_output={"family": "simplify_filters"},
        )

        sync = BrainSync(
            store=store,
            writer=BrainWriter(root=tmp_path / "knowledge" / "vault"),
        )

        notes, maps = sync.rebuild_brain()
        iteration_note = tmp_path / "knowledge" / "vault" / "01 Iterations" / "run-001-1.md"
        family_map = tmp_path / "knowledge" / "vault" / "90 Maps" / "Family Memory.md"

        assert notes
        assert maps
        assert iteration_note.exists()
        assert family_map.exists()
    finally:
        store.close()


def test_brain_sync_renders_korean_markdown_when_docs_language_is_korean(
    tmp_path: Path,
) -> None:
    store = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    try:
        store.record_run(run_id="run-001", state="success")
        store.record_experiment(
            run_id="run-001",
            iteration=1,
            candidate_revision="candidate-001",
            baseline_revision="baseline-001",
            hypothesis="test hypothesis",
            mutation_summary="test mutation",
            backtest_metrics={"score": 1.2, "guardrail_failures": []},
            decision="keep",
        )
        store.record_lesson(
            run_id="run-001",
            iteration=1,
            decision="keep",
            summary="lesson summary",
            lesson_output={"next_actions": ["next action"]},
        )
        sync = BrainSync(
            store=store,
            writer=BrainWriter(
                root=tmp_path / "knowledge" / "vault",
                localizer=OutputLocalizer(output_language="ko", docs_output_language="ko"),
            ),
            localizer=OutputLocalizer(output_language="ko", docs_output_language="ko"),
        )

        sync.export_iteration_bundle(run_id="run-001", iteration=1)
        iteration_note = tmp_path / "knowledge" / "vault" / "01 Iterations" / "run-001-1.md"
        lesson_note = tmp_path / "knowledge" / "vault" / "03 Lessons" / "run-001-1-keep.md"
        map_note = tmp_path / "knowledge" / "vault" / "90 Maps" / "Active Experiments.md"

        assert "## 링크" in iteration_note.read_text(encoding="utf-8")
        assert "## 다음 액션" in lesson_note.read_text(encoding="utf-8")
        assert "# 진행 중 실험" in map_note.read_text(encoding="utf-8")
    finally:
        store.close()
