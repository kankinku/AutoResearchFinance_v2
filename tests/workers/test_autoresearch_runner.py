from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from finance_autoresearch.research.models import (
    ExperimentPlan,
    KnowledgeSnippet,
    LessonCard,
    ResearchBrief,
)
from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from finance_autoresearch.supervisor.service import SupervisorService


MUTABLE_TARGET_PATH = Path(
    "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"
)


@dataclass(slots=True)
class FakeOpenClawClient:
    mutation_artifacts: list[dict[str, Any]] = field(default_factory=list)
    mutation_calls: list[dict[str, Any]] = field(default_factory=list)
    on_mutate: Any = None

    def mutate(self, request: dict[str, Any]) -> dict[str, Any]:
        self.mutation_calls.append(dict(request))
        if not self.mutation_artifacts:
            raise AssertionError("unexpected mutate() call")
        artifact = self.mutation_artifacts.pop(0)
        if isinstance(artifact, Exception):
            raise artifact
        if callable(self.on_mutate):
            self.on_mutate(dict(request), artifact)
        return artifact


@dataclass(slots=True)
class FakeHarness:
    results: list[Any]
    calls: list[str] = field(default_factory=list)
    smoke_results: list[Any] = field(default_factory=list)
    smoke_calls: list[str] = field(default_factory=list)

    def __call__(self, strategy_path: Path) -> Any:
        self.calls.append(extract_strategy_tag(strategy_path.read_text(encoding="utf-8")))
        if not self.results:
            raise AssertionError("unexpected harness call")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def smoke(self, strategy_path: Path) -> Any:
        self.smoke_calls.append(extract_strategy_tag(strategy_path.read_text(encoding="utf-8")))
        if not self.smoke_results:
            raise AssertionError("unexpected smoke() call")
        result = self.smoke_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@dataclass(slots=True)
class FakeEvaluator:
    results: list[dict[str, Any]]
    calls: list[Any] = field(default_factory=list)

    def __call__(self, raw_result: Any) -> dict[str, Any]:
        self.calls.append(raw_result)
        if not self.results:
            raise AssertionError("unexpected evaluator call")
        return dict(self.results.pop(0))


@dataclass(slots=True)
class FakeAnalyzer:
    outputs: list[dict[str, Any]]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        if not self.outputs:
            raise AssertionError("unexpected analyzer call")
        return dict(self.outputs.pop(0))


@dataclass(slots=True)
class FakeKnowledgeLoader:
    snippets: list[KnowledgeSnippet]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def load(self, **kwargs: Any) -> list[KnowledgeSnippet]:
        self.calls.append(dict(kwargs))
        return list(self.snippets)


@dataclass(slots=True)
class FakePlanner:
    plans: list[ExperimentPlan | ResearchBrief | Exception]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def build_plan(self, **kwargs: Any) -> ExperimentPlan | ResearchBrief:
        self.calls.append(dict(kwargs))
        if not self.plans:
            raise AssertionError("unexpected build_plan() call")
        plan = self.plans.pop(0)
        if isinstance(plan, Exception):
            raise plan
        return plan


@dataclass(slots=True)
class FakeLessonBuilder:
    lessons: list[LessonCard]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def build(self, **kwargs: Any) -> LessonCard:
        self.calls.append(dict(kwargs))
        if not self.lessons:
            raise AssertionError("unexpected build() call")
        return self.lessons.pop(0)


@dataclass(slots=True)
class FakeFalsifier:
    reports: list[dict[str, Any]]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        if not self.reports:
            raise AssertionError("unexpected falsifier call")
        return dict(self.reports.pop(0))


@dataclass(slots=True)
class FakeBrainSync:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def export_iteration_bundle(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(dict(kwargs))
        return []


@dataclass(slots=True)
class SequenceLockChecker:
    values: deque[bool]

    def __call__(self) -> bool:
        if self.values:
            return self.values.popleft()
        return True


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStateStore:
    repository = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    yield repository
    repository.close()


def strategy_source(tag: str) -> str:
    return "\n".join(
        [
            "import pandas as pd",
            "",
            "from finance_autoresearch.strategy.base_contract import StrategyContext, StrategyDefinition",
            "",
            "def build_strategy(context: StrategyContext) -> StrategyDefinition:",
            "    regime = context.regimes.classify_ema200_regime(context.close)",
            "    regime_valid = context.indicators.ema(context.close, 200).notna()",
            "    no_signal = (context.close > (context.close + 1)) & regime_valid",
            "    return StrategyDefinition(",
            "        long_entries=no_signal,",
            "        long_exits=no_signal,",
            "        short_entries=no_signal,",
            "        short_exits=no_signal,",
            "        regime=regime,",
            f"        params={{'tag': '{tag}'}}," ,
            f"        diagnostics={{'tag': '{tag}', 'summary': '{tag}'}}," ,
            "    )",
            "",
        ]
    )


def make_mutation_artifact(tag: str) -> dict[str, Any]:
    return {
        "kind": "strategy_replacement",
        "target_path": str(MUTABLE_TARGET_PATH).replace("\\", "/"),
        "hypothesis": f"Mutate toward {tag}",
        "change_summary": f"Replace with {tag}",
        "full_file_contents": strategy_source(tag),
        "expected_effects": [f"Improve {tag}"],
    }


def make_knowledge_snippet(tag: str) -> KnowledgeSnippet:
    return KnowledgeSnippet(
        source_id=f"knowledge/indicators/{tag}.md",
        title=f"{tag.title()} Notes",
        source_path=f"knowledge/indicators/{tag}.md",
        sha256=tag * 8,
        excerpt=f"{tag} can be used to refine the strategy without adding too much complexity.",
        tags=("knowledge-pack", "indicators", tag),
        relevance_reason=f"{tag} matched the active research problem.",
        score=3.5,
    )


def make_plan(summary: str, *, hypothesis: str | None = None) -> ExperimentPlan:
    return ExperimentPlan(
        hypothesis=hypothesis or f"{summary} hypothesis",
        objective="Beat baseline score by at least 0.05 without guardrail failures.",
        plan_summary=summary,
        experiment_type="simplify_filters",
        target_problem="Trade coverage is too thin.",
        expected_effect="Recover trade count without destabilizing exits.",
        regime_policy="preserve_current_regime_model",
        change_budget={"target_path": str(MUTABLE_TARGET_PATH).replace("\\", "/"), "max_files": 1},
        guardrails_to_watch=("trade_count",),
        carry_forward_lessons=("Preserve regime exposure before chasing extra score.",),
        planned_mutations=(
            {
                "area": "entry logic",
                "intent": "relax one confirmation gate",
                "reason": "Recover trade count.",
            },
        ),
        knowledge_source_ids=("knowledge/indicators/rsi.md",),
    )


def make_research_brief(
    summary: str,
    *,
    family: str = "simplify_filters",
    artifact_mode: str = "prefer_genome",
    regime_policy: str = "preserve_current_regime_model",
) -> ResearchBrief:
    return ResearchBrief(
        hypothesis=f"{summary} hypothesis",
        objective="Beat baseline score by at least 0.05 without guardrail failures.",
        plan_summary=summary,
        family=family,
        target_problem="Trade coverage is too thin.",
        expected_effect="Recover trade count without destabilizing exits.",
        regime_policy=regime_policy,
        complexity_budget={
            "target_path": str(MUTABLE_TARGET_PATH).replace("\\", "/"),
            "max_files": 1,
        },
        historical_risks=("trade_count", "bull"),
        guardrails_to_watch=("trade_count",),
        carry_forward_lessons=("Preserve regime exposure before chasing extra score.",),
        planned_mutations=(
            {
                "area": "entry logic",
                "intent": "relax one confirmation gate",
                "reason": "Recover trade count.",
            },
        ),
        artifact_mode=artifact_mode,
        allowed_indicator_pool=("rsi", "atr"),
        knowledge_evidence=(
            {
                "source_id": "knowledge/indicators/rsi.md",
                "title": "RSI Notes",
                "relevance_reason": "rsi matched the active research problem.",
            },
        ),
        knowledge_source_ids=("knowledge/indicators/rsi.md",),
    )


def make_lesson(summary: str, *, decision: str = "keep") -> LessonCard:
    return LessonCard(
        decision=decision,
        summary=summary,
        referenced_plan_summary="Plan summary",
        lessons=(
            {
                "category": "guardrail",
                "statement": "Preserve exposure while tuning thresholds.",
                "evidence": ["analysis.summary"],
                "confidence": "high",
            },
        ),
        next_actions=("Try the next threshold adjustment.",),
        knowledge_source_ids=("knowledge/indicators/rsi.md",),
        supporting_signals={"score": 0.47},
    )


def evaluation_result(
    score: float,
    *,
    guardrails_passed: bool,
    tag: str,
) -> dict[str, Any]:
    return {
        "score": score,
        "metrics": {
            "tag": tag,
            "combinations": {},
            "aggregate": {
                "mean_out_of_sample_turnover": 1.0,
                "mean_out_of_sample_total_return": score,
                "worst_out_of_sample_max_drawdown": 0.1,
            },
        },
        "guardrails_passed": guardrails_passed,
        "guardrail_failures": [] if guardrails_passed else ["trade_count"],
    }


def analysis_result(summary: str) -> dict[str, Any]:
    return {
        "strengths": [f"{summary} strengths"],
        "weaknesses": [f"{summary} weaknesses"],
        "coverage_gaps": [f"{summary} gaps"],
        "regime_observations": [f"{summary} regimes"],
        "next_hypothesis_hints": [f"{summary} next"],
        "summary": summary,
    }


def smoke_backtest_result(
    *,
    exposure: float = 0.4,
    trade_count: int = 24,
    turnover: float = 4.0,
    validation_sharpe: float = 0.5,
    oos_sharpe: float = 0.4,
) -> dict[str, Any]:
    from tests.backtest.test_evaluator import make_backtest_results

    result = make_backtest_results(
        [oos_sharpe, oos_sharpe, oos_sharpe, oos_sharpe, oos_sharpe, oos_sharpe]
    )
    for combination in result["combinations"].values():
        combination["splits"]["validation"]["sharpe"] = validation_sharpe
        combination["splits"]["out_of_sample"]["sharpe"] = oos_sharpe
        combination["splits"]["out_of_sample"]["exposure"] = exposure
        combination["splits"]["out_of_sample"]["trade_count"] = trade_count
        combination["splits"]["out_of_sample"]["turnover"] = turnover
    return result


def write_mutable_strategy(repository_root: Path, tag: str) -> Path:
    target_path = repository_root / MUTABLE_TARGET_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(strategy_source(tag), encoding="utf-8")
    return target_path


def extract_strategy_tag(source: str) -> str:
    marker = "params={'tag': '"
    if marker not in source:
        return "unknown"
    return source.split(marker, 1)[1].split("'", 1)[0]


def make_runner(
    repository_root: Path,
    store: SQLiteStateStore,
    *,
    openclaw_client: FakeOpenClawClient | None = None,
    harness: FakeHarness | None = None,
    evaluator: FakeEvaluator | None = None,
    analyzer: FakeAnalyzer | None = None,
    knowledge_loader: FakeKnowledgeLoader | None = None,
    planner: FakePlanner | None = None,
    lesson_builder: FakeLessonBuilder | None = None,
    brain_sync: FakeBrainSync | None = None,
    brain_auto_export: bool = True,
    falsifier: FakeFalsifier | None = None,
    lock_checker: SequenceLockChecker | None = None,
    prescreener: Any = None,
    trial_manager: Any = None,
    candidate_frontier_selector: Any = None,
    frontier_promotion_limit: int = 2,
) -> object:
    from finance_autoresearch.workers.autoresearch_runner import AutoresearchRunner

    return AutoresearchRunner(
        state_store=store,
        repository_root=repository_root,
        openclaw_client=openclaw_client or FakeOpenClawClient(),
        harness=harness or FakeHarness(results=[]),
        evaluator=evaluator or FakeEvaluator(results=[]),
        analyzer=analyzer or FakeAnalyzer(outputs=[]),
        falsifier=falsifier,
        prescreener=prescreener,
        trial_manager=trial_manager,
        candidate_frontier_selector=candidate_frontier_selector,
        knowledge_loader=knowledge_loader,
        planner=planner,
        lesson_builder=lesson_builder,
        brain_sync=brain_sync,
        brain_auto_export=brain_auto_export,
        mutable_strategy_path=repository_root / MUTABLE_TARGET_PATH,
        baseline_snapshot_path=repository_root
        / "runtime"
        / "baseline"
        / "accepted_strategy_candidate.py",
        lock_is_held=lock_checker or SequenceLockChecker(deque([True])),
        frontier_promotion_limit=frontier_promotion_limit,
    )


def test_autoresearch_runner_rolls_back_failed_candidate(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    client = FakeOpenClawClient(mutation_artifacts=[make_mutation_artifact("candidate")])
    harness = FakeHarness(results=[{"phase": "baseline"}, {"phase": "candidate"}])
    evaluator = FakeEvaluator(
        results=[
            evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
            evaluation_result(0.42, guardrails_passed=False, tag="candidate"),
        ]
    )
    analyzer = FakeAnalyzer(outputs=[analysis_result("candidate analysis")])
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=client,
        harness=harness,
        evaluator=evaluator,
        analyzer=analyzer,
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    mutable_contents = (tmp_path / MUTABLE_TARGET_PATH).read_text(encoding="utf-8")
    baseline_contents = (
        tmp_path / "runtime" / "baseline" / "accepted_strategy_candidate.py"
    ).read_text(
        encoding="utf-8"
    )
    latest_experiment = store.get_latest_experiment()
    final_state = store.get_status()

    assert result["decision"] == "rollback"
    assert extract_strategy_tag(mutable_contents) == "baseline"
    assert extract_strategy_tag(baseline_contents) == "baseline"
    assert latest_experiment is not None
    assert latest_experiment.decision == "rollback"
    assert final_state.project_state == "idle"
    assert final_state.autoresearch_state == "success"


def test_autoresearch_runner_keeps_only_when_score_beats_threshold(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=FakeOpenClawClient(
            mutation_artifacts=[make_mutation_artifact("winner")]
        ),
        harness=FakeHarness(results=[{"phase": "baseline"}, {"phase": "winner"}]),
        evaluator=FakeEvaluator(
            results=[
                evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
                evaluation_result(0.46, guardrails_passed=True, tag="winner"),
            ]
        ),
        analyzer=FakeAnalyzer(outputs=[analysis_result("winner analysis")]),
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    mutable_contents = (tmp_path / MUTABLE_TARGET_PATH).read_text(encoding="utf-8")
    baseline_contents = (
        tmp_path / "runtime" / "baseline" / "accepted_strategy_candidate.py"
    ).read_text(
        encoding="utf-8"
    )
    latest_experiment = store.get_latest_experiment()
    final_state = store.get_status()

    assert result["decision"] == "keep"
    assert extract_strategy_tag(mutable_contents) == "winner"
    assert extract_strategy_tag(baseline_contents) == "winner"
    assert latest_experiment is not None
    assert latest_experiment.decision == "keep"
    assert final_state.baseline_revision == final_state.candidate_revision


def test_ties_are_not_kept(tmp_path: Path, store: SQLiteStateStore) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=FakeOpenClawClient(
            mutation_artifacts=[make_mutation_artifact("tie-candidate")]
        ),
        harness=FakeHarness(results=[{"phase": "baseline"}, {"phase": "candidate"}]),
        evaluator=FakeEvaluator(
            results=[
                evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
                evaluation_result(0.40, guardrails_passed=True, tag="tie-candidate"),
            ]
        ),
        analyzer=FakeAnalyzer(outputs=[analysis_result("tie analysis")]),
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    mutable_contents = (tmp_path / MUTABLE_TARGET_PATH).read_text(encoding="utf-8")

    assert result["decision"] == "rollback"
    assert extract_strategy_tag(mutable_contents) == "baseline"


def test_crash_is_recorded_as_crash_not_plain_rollback(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=FakeOpenClawClient(
            mutation_artifacts=[make_mutation_artifact("broken")]
        ),
        harness=FakeHarness(
            results=[{"phase": "baseline"}, RuntimeError("candidate crash")]
        ),
        evaluator=FakeEvaluator(
            results=[evaluation_result(0.40, guardrails_passed=True, tag="baseline")]
        ),
        analyzer=FakeAnalyzer(outputs=[]),
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    mutable_contents = (tmp_path / MUTABLE_TARGET_PATH).read_text(encoding="utf-8")
    latest_experiment = store.get_latest_experiment()
    pending_events = store.list_pending_outbox()

    assert result["decision"] == "crash"
    assert extract_strategy_tag(mutable_contents) == "baseline"
    assert latest_experiment is not None
    assert latest_experiment.decision == "crash"
    assert any(event.event_type == "candidate_crashed" for event in pending_events)


def test_runner_honors_pending_stop_at_next_stage_boundary(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    client = FakeOpenClawClient(mutation_artifacts=[make_mutation_artifact("candidate")])
    def stop_after_mutation(_: dict[str, Any], __: dict[str, Any]) -> None:
        store.set_pending_command("stop_autoresearch")
    client.on_mutate = stop_after_mutation
    harness = FakeHarness(results=[{"phase": "baseline"}, {"phase": "candidate"}])
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=client,
        harness=harness,
        evaluator=FakeEvaluator(
            results=[evaluation_result(0.40, guardrails_passed=True, tag="baseline")]
        ),
        analyzer=FakeAnalyzer(outputs=[]),
    )

    result = runner.run(run_id="run-001", max_iterations=5)
    mutable_contents = (tmp_path / MUTABLE_TARGET_PATH).read_text(encoding="utf-8")
    final_state = store.get_status()

    assert result["decision"] == "stopped"
    assert harness.calls == ["baseline"]
    assert extract_strategy_tag(mutable_contents) == "baseline"
    assert final_state.project_state == "idle"
    assert final_state.autoresearch_state == "success"
    assert final_state.pending_command is None


def test_runner_uses_research_plan_before_mutation_and_persists_plan_and_lesson(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    client = FakeOpenClawClient(mutation_artifacts=[make_mutation_artifact("winner")])
    knowledge_loader = FakeKnowledgeLoader(snippets=[make_knowledge_snippet("rsi")])
    planner = FakePlanner(plans=[make_plan("Relax one entry gate and keep exits stable.")])
    lesson_builder = FakeLessonBuilder(
        lessons=[make_lesson("Planned simplification improved the candidate enough.")]
    )
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=client,
        harness=FakeHarness(results=[{"phase": "baseline"}, {"phase": "winner"}]),
        evaluator=FakeEvaluator(
            results=[
                evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
                evaluation_result(0.47, guardrails_passed=True, tag="winner"),
            ]
        ),
        analyzer=FakeAnalyzer(outputs=[analysis_result("winner analysis")]),
        knowledge_loader=knowledge_loader,
        planner=planner,
        lesson_builder=lesson_builder,
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    mutation_context = client.mutation_calls[0]["context"]
    latest_plan = store.get_latest_research_plan()
    latest_lesson = store.get_latest_lesson()
    knowledge_records = store.list_knowledge(limit=10)

    assert result["decision"] == "keep"
    assert len(knowledge_loader.calls) == 1
    assert len(planner.calls) == 1
    assert mutation_context["plan_summary"] == "Relax one entry gate and keep exits stable."
    assert mutation_context["guardrails_to_watch"] == ["trade_count"]
    assert mutation_context["workspace_refs"][0]["source_path"] == "knowledge/indicators/rsi.md"
    assert latest_plan is not None
    assert latest_plan.summary == "Relax one entry gate and keep exits stable."
    assert latest_lesson is not None
    assert latest_lesson.summary == "Planned simplification improved the candidate enough."
    assert knowledge_records[0].source_path == "knowledge/indicators/rsi.md"


def test_runner_passes_research_brief_fields_and_raw_preference_for_split_regime(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    client = FakeOpenClawClient(mutation_artifacts=[make_mutation_artifact("winner")])
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=client,
        harness=FakeHarness(results=[{"phase": "baseline"}, {"phase": "winner"}]),
        evaluator=FakeEvaluator(
            results=[
                evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
                evaluation_result(0.47, guardrails_passed=True, tag="winner"),
            ]
        ),
        analyzer=FakeAnalyzer(outputs=[analysis_result("winner analysis")]),
        knowledge_loader=FakeKnowledgeLoader(snippets=[make_knowledge_snippet("rsi")]),
        planner=FakePlanner(
            plans=[
                make_research_brief(
                    "Split bull and bear handling.",
                    family="split_regime",
                    artifact_mode="prefer_raw",
                    regime_policy="consider_split_bull_bear",
                )
            ]
        ),
        lesson_builder=FakeLessonBuilder(lessons=[make_lesson("split regime raw path used.")]),
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    mutation_context = client.mutation_calls[0]["context"]

    assert result["decision"] == "keep"
    assert mutation_context["family"] == "split_regime"
    assert mutation_context["historical_risks"] == ["trade_count", "bull"]
    assert mutation_context["allowed_indicator_pool"] == ["rsi", "atr"]
    assert mutation_context["knowledge_evidence"][0]["source_id"] == "knowledge/indicators/rsi.md"
    assert mutation_context["artifact_mode"] == "prefer_raw"
    assert mutation_context["preferred_artifact_kind"] == "strategy_replacement"
    assert mutation_context["artifact_capabilities"]["strategy_genome_v1"] == {
        "supports_true_regime_split": False,
        "direction_mode": "mirrored_long_short",
        "max_indicator_count": 4,
        "max_new_conditions": 2,
    }


def test_runner_rolls_back_when_planning_fails_before_backtest(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    client = FakeOpenClawClient(mutation_artifacts=[])
    harness = FakeHarness(results=[{"phase": "baseline"}])
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=client,
        harness=harness,
        evaluator=FakeEvaluator(
            results=[evaluation_result(0.40, guardrails_passed=True, tag="baseline")]
        ),
        analyzer=FakeAnalyzer(outputs=[]),
        knowledge_loader=FakeKnowledgeLoader(snippets=[make_knowledge_snippet("atr")]),
        planner=FakePlanner(plans=[ValueError("planner failed")]),
        lesson_builder=FakeLessonBuilder(lessons=[]),
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    latest_experiment = store.get_latest_experiment()

    assert result["decision"] == "rollback"
    assert client.mutation_calls == []
    assert harness.calls == ["baseline"]
    assert latest_experiment is not None
    assert latest_experiment.decision == "rollback"
    assert latest_experiment.mutation_summary == "planner failed"
    assert store.get_latest_research_plan() is None


def test_recovery_marks_autoresearch_running_as_stale_and_emits_event(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "candidate")
    baseline_path = (
        tmp_path / "runtime" / "baseline" / "accepted_strategy_candidate.py"
    )
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(strategy_source("baseline"), encoding="utf-8")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    store.set_current_stage("analyze_results")
    store.set_pending_command("stop_autoresearch")
    store.set_recovery_marker("run-001:2:analyze_results")
    runner = make_runner(tmp_path, store)

    recovered = runner.recover_startup_state()
    final_state = store.get_status()
    mutable_contents = (tmp_path / MUTABLE_TARGET_PATH).read_text(encoding="utf-8")
    pending_events = store.list_pending_outbox()

    assert recovered is True
    assert extract_strategy_tag(mutable_contents) == "baseline"
    assert final_state.project_state == "degraded"
    assert final_state.autoresearch_state == "stale"
    assert final_state.active_run_id is None
    assert final_state.current_stage is None
    assert final_state.pending_command is None
    assert final_state.recovery_marker == "crash_recovered:run-001:2:analyze_results"
    assert any(
        event.event_type == "autoresearch_recovered_stale" for event in pending_events
    )


def test_recovery_marks_pipeline_running_as_failed_and_emits_event(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    runner = make_runner(tmp_path, store)
    store.set_status(
        project_state="active",
        pipeline_state="running",
        autoresearch_state="idle",
    )

    recovered = runner.recover_startup_state()
    final_state = store.get_status()
    pending_events = store.list_pending_outbox()

    assert recovered is True
    assert final_state.project_state == "degraded"
    assert final_state.pipeline_state == "failed"
    assert any(event.event_type == "pipeline_recovered_stale" for event in pending_events)


def test_start_autoresearch_rejects_invalid_seed_strategy(tmp_path: Path) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    store.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )
    runner = make_runner(
        tmp_path,
        store,
        harness=FakeHarness(results=[{"phase": "baseline"}]),
        evaluator=FakeEvaluator(
            results=[evaluation_result(0.10, guardrails_passed=False, tag="baseline")]
        ),
        analyzer=FakeAnalyzer(outputs=[]),
    )
    supervisor = SupervisorService(
        state_store=store,
        seed_validator=runner.build_seed_validator(),
        run_id_factory=lambda: "run-001",
    )

    response = supervisor.handle(
        {
            "command": "start_autoresearch",
            "project_id": "finance",
            "source": "cli",
            "requested_by": "tester",
            "requested_at": "2026-03-25T00:00:00+00:00",
            "payload": {},
        }
    )
    final_state = store.get_status()
    store.close()

    assert response["accepted"] is False
    assert response["project_state"] == "degraded"
    assert response["autoresearch_state"] == "failed"
    assert final_state.project_state == "degraded"


def test_runner_stops_when_process_lock_is_lost(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=FakeOpenClawClient(
            mutation_artifacts=[make_mutation_artifact("candidate")]
        ),
        harness=FakeHarness(results=[{"phase": "baseline"}, {"phase": "candidate"}]),
        evaluator=FakeEvaluator(
            results=[evaluation_result(0.40, guardrails_passed=True, tag="baseline")]
        ),
        analyzer=FakeAnalyzer(outputs=[]),
        lock_checker=SequenceLockChecker(deque([True, True, False])),
    )

    result = runner.run(run_id="run-001", max_iterations=2)
    mutable_contents = (tmp_path / MUTABLE_TARGET_PATH).read_text(encoding="utf-8")
    final_state = store.get_status()

    assert result["decision"] == "lock_lost"
    assert extract_strategy_tag(mutable_contents) == "baseline"
    assert final_state.project_state == "degraded"
    assert final_state.autoresearch_state == "failed"


def test_runner_rolls_back_when_falsifier_fails_even_if_score_beats_threshold(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=FakeOpenClawClient(
            mutation_artifacts=[make_mutation_artifact("winner")]
        ),
        harness=FakeHarness(results=[{"phase": "baseline"}, {"phase": "winner"}]),
        evaluator=FakeEvaluator(
            results=[
                evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
                evaluation_result(0.52, guardrails_passed=True, tag="winner"),
            ]
        ),
        analyzer=FakeAnalyzer(outputs=[analysis_result("winner analysis")]),
        falsifier=FakeFalsifier(
            reports=[
                {
                    "passed": False,
                    "summary": "validation instability",
                    "checks": {
                        "validation_stability": {
                            "passed": False,
                            "message": "validation diverged from oos",
                        }
                    },
                }
            ]
        ),
        lesson_builder=FakeLessonBuilder(lessons=[make_lesson("winner failed falsification", decision="rollback")]),
        planner=FakePlanner(plans=[make_plan("Relax one entry gate and keep exits stable.")]),
        knowledge_loader=FakeKnowledgeLoader(snippets=[make_knowledge_snippet("rsi")]),
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    latest_experiment = store.get_latest_experiment()
    falsifications = store.list_falsifications(limit=10)

    assert result["decision"] == "rollback"
    assert latest_experiment is not None
    assert latest_experiment.decision == "rollback"
    assert falsifications[0].passed is False
    assert falsifications[0].summary == "validation instability"


def test_runner_records_lesson_graph_and_family_memory(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=FakeOpenClawClient(
            mutation_artifacts=[make_mutation_artifact("winner")]
        ),
        harness=FakeHarness(results=[{"phase": "baseline"}, {"phase": "winner"}]),
        evaluator=FakeEvaluator(
            results=[
                evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
                evaluation_result(0.47, guardrails_passed=True, tag="winner"),
            ]
        ),
        analyzer=FakeAnalyzer(outputs=[analysis_result("winner analysis")]),
        falsifier=FakeFalsifier(
            reports=[
                {
                    "passed": True,
                    "summary": "all checks passed",
                    "checks": {
                        "validation_stability": {"passed": True, "message": "ok"},
                        "startup_stability": {"passed": True, "message": "ok"},
                        "complexity_budget": {"passed": True, "message": "ok"},
                    },
                }
            ]
        ),
        knowledge_loader=FakeKnowledgeLoader(snippets=[make_knowledge_snippet("rsi")]),
        planner=FakePlanner(plans=[make_plan("Relax one entry gate and keep exits stable.")]),
        lesson_builder=FakeLessonBuilder(
            lessons=[make_lesson("Structured mutation improved score without guardrail regressions.")]
        ),
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    lesson_graphs = store.list_lesson_graph(limit=10)
    family_memory = store.list_family_memory(limit=10)
    trials = store.list_trials(limit=10)

    assert result["decision"] == "keep"
    assert lesson_graphs[0].observed_outcome == "keep"
    assert lesson_graphs[0].knowledge_source_ids == ("knowledge/indicators/rsi.md",)
    assert family_memory[0].family == "simplify_filters"
    assert family_memory[0].outcome == "keep"
    assert trials[0].artifact_kind == "strategy_replacement"
    assert trials[0].falsification_pass is True


def test_runner_fails_after_three_consecutive_crashes(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=FakeOpenClawClient(
            mutation_artifacts=[
                make_mutation_artifact("candidate-1"),
                make_mutation_artifact("candidate-2"),
                make_mutation_artifact("candidate-3"),
            ]
        ),
        harness=FakeHarness(
            results=[
                {"phase": "baseline"},
                RuntimeError("crash-1"),
                RuntimeError("crash-2"),
                RuntimeError("crash-3"),
            ]
        ),
        evaluator=FakeEvaluator(
            results=[evaluation_result(0.40, guardrails_passed=True, tag="baseline")]
        ),
        analyzer=FakeAnalyzer(outputs=[]),
    )

    result = runner.run(run_id="run-001", max_iterations=3)
    final_state = store.get_status()

    assert result["decision"] == "crash_threshold_exceeded"
    assert final_state.project_state == "degraded"
    assert final_state.autoresearch_state == "failed"


def test_runner_records_frontier_and_only_evaluates_promoted_candidates(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    from finance_autoresearch.search.candidate_frontier import select_candidate_frontier
    from finance_autoresearch.search.optuna_adapter import OptunaAdapter
    from finance_autoresearch.search.trial_manager import TrialManager
    from tests.strategy.test_strategy_dsl_compiler import make_genome

    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    harness = FakeHarness(
        results=[
            {"phase": "baseline"},
            {"phase": "official-a"},
            {"phase": "official-b"},
        ],
        smoke_results=[
            smoke_backtest_result(exposure=0.6, trade_count=30, turnover=4.0, oos_sharpe=0.2),
            smoke_backtest_result(exposure=0.7, trade_count=28, turnover=3.0, oos_sharpe=0.6),
            smoke_backtest_result(exposure=0.0, trade_count=1, turnover=2.0, oos_sharpe=0.1),
        ],
    )
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=FakeOpenClawClient(
            mutation_artifacts=[
                make_genome(
                    hypothesis="Genome candidate",
                    change_summary="Use structured genome",
                )
            ]
        ),
        harness=harness,
        evaluator=FakeEvaluator(
            results=[
                evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
                evaluation_result(0.44, guardrails_passed=True, tag="official-a"),
                evaluation_result(0.48, guardrails_passed=True, tag="official-b"),
            ]
        ),
        analyzer=FakeAnalyzer(
            outputs=[
                analysis_result("official-a analysis"),
                analysis_result("official-b analysis"),
            ]
        ),
        falsifier=FakeFalsifier(
            reports=[
                {"passed": True, "summary": "pass-a", "checks": {}},
                {"passed": True, "summary": "pass-b", "checks": {}},
            ]
        ),
        planner=FakePlanner(plans=[make_plan("Run structured genome search.")]),
        lesson_builder=FakeLessonBuilder(
            lessons=[make_lesson("The best promoted genome variant improved the score.")]
        ),
        knowledge_loader=FakeKnowledgeLoader(snippets=[make_knowledge_snippet("rsi")]),
        trial_manager=TrialManager(
            optuna_adapter=OptunaAdapter(max_variants=2),
            frontier_candidate_limit=3,
        ),
        candidate_frontier_selector=select_candidate_frontier,
        frontier_promotion_limit=2,
    )

    result = runner.run(run_id="run-001", max_iterations=1)
    frontier = store.list_candidate_frontier(limit=10)
    trials = store.list_trials(limit=10)

    assert result["decision"] == "keep"
    assert len(harness.smoke_calls) == 3
    assert len(harness.calls) == 3
    assert len(frontier) == 3
    assert sum(1 for item in frontier if item.promoted) == 2
    assert trials[0].artifact_kind == "strategy_genome_v1"


def test_runner_skips_auto_brain_export_when_disabled(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    write_mutable_strategy(tmp_path, "baseline")
    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")
    brain_sync = FakeBrainSync()
    runner = make_runner(
        tmp_path,
        store,
        openclaw_client=FakeOpenClawClient(
            mutation_artifacts=[make_mutation_artifact("winner")]
        ),
        harness=FakeHarness(results=[{"phase": "baseline"}, {"phase": "winner"}]),
        evaluator=FakeEvaluator(
            results=[
                evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
                evaluation_result(0.47, guardrails_passed=True, tag="winner"),
            ]
        ),
        analyzer=FakeAnalyzer(outputs=[analysis_result("winner analysis")]),
        planner=FakePlanner(plans=[make_plan("Relax one entry gate and keep exits stable.")]),
        lesson_builder=FakeLessonBuilder(
            lessons=[make_lesson("Structured mutation improved score without guardrail regressions.")]
        ),
        knowledge_loader=FakeKnowledgeLoader(snippets=[make_knowledge_snippet("rsi")]),
        brain_sync=brain_sync,
        brain_auto_export=False,
    )

    result = runner.run(run_id="run-001", max_iterations=1)

    assert result["decision"] == "keep"
    assert brain_sync.calls == []
