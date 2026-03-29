from __future__ import annotations

from pathlib import Path

from finance_autoresearch.research.models import KnowledgeSnippet, PlannerMemorySnapshot
from finance_autoresearch.research.planner_memory import PlannerMemory
from finance_autoresearch.research.planner_search import ResearchScheduler
from finance_autoresearch.state.sqlite_store import SQLiteStateStore


def test_planner_memory_builds_family_cooldown_and_linked_note_paths(tmp_path: Path) -> None:
    store = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    try:
        for iteration in range(1, 4):
            store.record_experiment(
                run_id="run-001",
                iteration=iteration,
                candidate_revision=f"candidate-{iteration}",
                baseline_revision="baseline-001",
                hypothesis="hypothesis",
                mutation_summary="mutation",
                backtest_metrics={"guardrail_failures": ["trade_count"]},
                decision="rollback",
            )
            store.record_research_plan(
                run_id="run-001",
                iteration=iteration,
                hypothesis="plan",
                summary="summary",
                plan_output={"experiment_type": "simplify_filters"},
            )
            store.record_analysis(
                run_id="run-001",
                iteration=iteration,
                analysis_output={
                    "strengths": [],
                    "weaknesses": ["QQQ bull weakness"],
                    "coverage_gaps": ["trade_count issue"],
                    "regime_observations": ["bear mismatch"],
                    "next_hypothesis_hints": [],
                    "summary": "QQQ bull weakness",
                },
                summary="QQQ bull weakness",
            )
            store.record_lesson(
                run_id="run-001",
                iteration=iteration,
                decision="rollback",
                summary="summary",
                lesson_output={
                    "lessons": [{"statement": f"lesson {iteration}"}],
                    "next_actions": [f"action {iteration}"],
                },
            )
        store.record_brain_note(
            note_type="iteration",
            path="01 Iterations/run-001-3.md",
            title="Iteration 3",
            generated=True,
            run_id="run-001",
            iteration=3,
            metadata={"tags": ["brain", "iteration"]},
        )

        snapshot = PlannerMemory(state_store=store, history_window=20).build_snapshot()
    finally:
        store.close()

    assert snapshot.family_counts["simplify_filters"] == 3
    assert "simplify_filters" in snapshot.family_cooldowns
    assert "qqq" in snapshot.repeated_failure_signals
    assert snapshot.linked_note_paths == ("01 Iterations/run-001-3.md",)
    assert snapshot.carry_forward_lessons[:3] == ("lesson 3", "action 3", "lesson 2")


def test_research_scheduler_avoids_saturated_family(tmp_path: Path) -> None:
    store = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    try:
        store.record_brain_note(
            note_type="failure",
            path="04 Failures/run-001-1.md",
            title="Failure",
            generated=True,
            metadata={"tags": ["failure"]},
        )
        snapshot = PlannerMemory(state_store=store, history_window=20).build_snapshot()
    finally:
        store.close()

    plan = ResearchScheduler().build_plan(
        baseline_evaluation={"guardrails_passed": True},
        latest_experiment=None,
        latest_analysis=None,
        latest_lesson=None,
        knowledge_snippets=[],
        planner_memory_snapshot=snapshot.__class__(
            history_window=snapshot.history_window,
            family_counts={"simplify_filters": 3},
            family_cooldowns=("simplify_filters",),
            repeated_failure_signals=("trade_count",),
            carry_forward_lessons=(),
            linked_note_paths=snapshot.linked_note_paths,
        ),
    )

    assert plan.family == "replace_indicator"


def test_research_scheduler_marks_split_regime_as_prefer_raw() -> None:
    plan = ResearchScheduler().build_plan(
        baseline_evaluation={"guardrails_passed": True},
        latest_experiment=None,
        latest_analysis=type(
            "Analysis",
            (),
            {
                "analysis_output": {
                    "summary": "bull and bear performance diverged by regime",
                    "strengths": [],
                    "weaknesses": [],
                    "coverage_gaps": [],
                    "regime_observations": [],
                    "next_hypothesis_hints": [],
                }
            },
        )(),
        latest_lesson=None,
        knowledge_snippets=[],
        planner_memory_snapshot=None,
    )

    assert plan.family == "split_regime"
    assert plan.artifact_mode == "prefer_raw"


def test_planner_memory_tracks_risk_and_metadata_tokens(tmp_path: Path) -> None:
    store = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    try:
        store.record_experiment(
            run_id="run-002",
            iteration=1,
            candidate_revision="candidate-1",
            baseline_revision="baseline-001",
            hypothesis="hypothesis",
            mutation_summary="mutation",
            backtest_metrics={
                "guardrail_failures": ["turbulence covariance sector metadata issue"]
            },
            decision="rollback",
        )
        store.record_analysis(
            run_id="run-002",
            iteration=1,
            analysis_output={
                "strengths": [],
                "weaknesses": ["turbulence covariance issue"],
                "coverage_gaps": ["sector metadata mismatch"],
                "regime_observations": [],
                "next_hypothesis_hints": [],
                "summary": "turbulence covariance sector metadata weakness",
            },
            summary="turbulence covariance sector metadata weakness",
        )

        snapshot = PlannerMemory(state_store=store, history_window=20).build_snapshot()
    finally:
        store.close()

    assert "turbulence" in snapshot.repeated_failure_signals
    assert "covariance" in snapshot.repeated_failure_signals
    assert "sector" in snapshot.repeated_failure_signals
    assert "metadata" in snapshot.repeated_failure_signals


def test_research_scheduler_uses_risk_and_metadata_vocabulary() -> None:
    plan = ResearchScheduler().build_plan(
        baseline_evaluation={"guardrails_passed": True},
        latest_experiment=None,
        latest_analysis=type(
            "Analysis",
            (),
            {
                "analysis_output": {
                    "summary": "turbulence and metadata drift across sector slices",
                    "strengths": [],
                    "weaknesses": [],
                    "coverage_gaps": [],
                    "regime_observations": ["covariance spikes during stress"],
                    "next_hypothesis_hints": [],
                }
            },
        )(),
        latest_lesson=None,
        knowledge_snippets=[
            KnowledgeSnippet(
                source_id="knowledge/factors/catalog.md",
                title="Factor Catalog",
                source_path="knowledge/factors/catalog.md",
                sha256="abc",
                excerpt="turbulence covariance metadata sector",
                tags=("turbulence", "covariance", "metadata", "sector", "atr"),
                relevance_reason="matched",
                score=3.0,
            )
        ],
        planner_memory_snapshot=PlannerMemorySnapshot(
            history_window=20,
            family_counts={},
            repeated_failure_signals=("turbulence", "metadata"),
        ),
    )

    assert any(
        item["area"] == "risk gating" and "turbulence" in item["intent"]
        for item in plan.planned_mutations
    )
    assert any("metadata slice" in item.lower() for item in plan.guardrails_to_watch)
