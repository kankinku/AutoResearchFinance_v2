from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finance_autoresearch.mutation.patch_applier import (
    MutationApplicationResult,
    apply_mutation_artifact,
)
from finance_autoresearch.backtest.prescreener import prescreen_candidate
from finance_autoresearch.research.family_memory import build_family_memory
from finance_autoresearch.research.experiment_planner import HeuristicExperimentPlanner
from finance_autoresearch.research.lesson_graph import build_lesson_graph
from finance_autoresearch.research.lesson_capture import LessonBuilder
from finance_autoresearch.research.models import (
    ExperimentPlan,
    KnowledgeSnippet,
    PlannerMemorySnapshot,
    ResearchBrief,
)
from finance_autoresearch.research.workspace_knowledge import WorkspaceKnowledgeLoader
from finance_autoresearch.state.repository import StateRepository
from finance_autoresearch.supervisor.transition_guard import SeedBaselineValidation
from finance_autoresearch.workers.heartbeat import WorkerHeartbeat
from finance_autoresearch.workers.pipeline_runner import (
    DEFAULT_BASELINE_SNAPSHOT_PATH,
    DEFAULT_BASELINE_STRATEGY_PATH,
    ensure_accepted_baseline_snapshot,
    validate_baseline_strategy,
)


KEEP_SCORE_DELTA = 0.05
CRASH_THRESHOLD = 3
GENOME_ARTIFACT_CAPABILITIES = {
    "strategy_genome_v1": {
        "supports_true_regime_split": False,
        "direction_mode": "mirrored_long_short",
        "max_indicator_count": 4,
        "max_new_conditions": 2,
    }
}


@dataclass(slots=True, frozen=True)
class IterationContext:
    run_id: str
    iteration: int
    hypothesis: str
    mutation_summary: str
    candidate_revision: str | None = None


@dataclass(slots=True, frozen=True)
class CandidateEvaluationBundle:
    candidate_id: str
    iteration_context: IterationContext
    mutation_result: MutationApplicationResult
    raw_results: Any
    evaluation: dict[str, Any]
    falsification_report: dict[str, Any]
    analysis_output: dict[str, Any]
    decision: str


class AutoresearchRunner:
    def __init__(
        self,
        *,
        state_store: StateRepository,
        repository_root: Path | str,
        openclaw_client: object,
        harness: object,
        evaluator: object,
        analyzer: object | None = None,
        falsifier: object | None = None,
        prescreener: object | None = None,
        trial_manager: object | None = None,
        candidate_frontier_selector=None,
        knowledge_loader: object | None = None,
        planner: object | None = None,
        planner_memory: object | None = None,
        lesson_builder: object | None = None,
        brain_sync: object | None = None,
        brain_auto_export: bool = True,
        mutable_strategy_path: Path | str = DEFAULT_BASELINE_STRATEGY_PATH,
        baseline_snapshot_path: Path | str = DEFAULT_BASELINE_SNAPSHOT_PATH,
        mutation_agent_id: str = "research",
        analysis_agent_id: str = "critic",
        patch_applier=apply_mutation_artifact,
        lock_is_held=None,
        progress_notifier=None,
        genome_shadow_mode: bool = True,
        frontier_promotion_limit: int = 2,
        allow_invalid_seed_baseline: bool = False,
    ) -> None:
        self._state_store = state_store
        self._repository_root = Path(repository_root)
        self._openclaw_client = openclaw_client
        self._harness = harness
        self._evaluator = evaluator
        self._analyzer = analyzer
        self._falsifier = falsifier
        self._prescreener = prescreener
        self._trial_manager = trial_manager
        self._candidate_frontier_selector = candidate_frontier_selector
        self._mutable_strategy_path = self._repository_root / Path(mutable_strategy_path)
        self._baseline_snapshot_path = self._repository_root / Path(baseline_snapshot_path)
        self._knowledge_loader = knowledge_loader or WorkspaceKnowledgeLoader(
            repository_root=self._repository_root
        )
        self._planner = planner or HeuristicExperimentPlanner()
        self._planner_memory = planner_memory
        self._lesson_builder = lesson_builder or LessonBuilder()
        self._brain_sync = brain_sync
        self._brain_auto_export = brain_auto_export
        self._mutation_agent_id = mutation_agent_id
        self._analysis_agent_id = analysis_agent_id
        self._patch_applier = patch_applier
        self._lock_is_held = lock_is_held or (lambda: True)
        self._progress_notifier = progress_notifier
        self._genome_shadow_mode = genome_shadow_mode
        self._frontier_promotion_limit = frontier_promotion_limit
        self._allow_invalid_seed_baseline = allow_invalid_seed_baseline
        self._heartbeat = WorkerHeartbeat(state_store=state_store, worker_name="autoresearch")

    def build_seed_validator(self):
        def validate(_: str | None) -> SeedBaselineValidation:
            return self.validate_seed_strategy()

        return validate

    def validate_seed_strategy(self) -> SeedBaselineValidation:
        try:
            baseline_evaluation, baseline_revision = self._initialize_baseline()
        except Exception as exc:
            return SeedBaselineValidation(valid=False, message=str(exc))

        guardrails_passed = bool(baseline_evaluation["guardrails_passed"])
        if not guardrails_passed and not self._allow_invalid_seed_baseline:
            return SeedBaselineValidation(
                valid=False,
                message="seed baseline guardrails failed",
            )

        self._state_store.set_candidate_revision(baseline_revision)
        self._state_store.set_baseline_revision(baseline_revision)
        if guardrails_passed:
            return SeedBaselineValidation(valid=True, message="seed baseline validated")
        return SeedBaselineValidation(
            valid=True,
            message="seed baseline guardrails bypassed by FINANCE_AUTORESEARCH_ALLOW_INVALID_SEED_BASELINE",
        )

    def recover_startup_state(self) -> bool:
        status = self._state_store.get_status()
        pipeline_recovered = status.pipeline_state == "running"
        autoresearch_recovered = status.autoresearch_state in {"running", "paused"}

        if not pipeline_recovered and not autoresearch_recovered and status.current_stage is None:
            return False

        if self._baseline_snapshot_path.exists():
            self._restore_baseline()

        if pipeline_recovered:
            self._state_store.set_status(pipeline_state="failed")
            self._state_store.append_outbox_event(
                event_type="pipeline_recovered_stale",
                payload={"previous_state": "running"},
            )

        if autoresearch_recovered:
            self._state_store.set_status(autoresearch_state="stale")
            self._state_store.append_outbox_event(
                event_type="autoresearch_recovered_stale",
                payload={"previous_state": status.autoresearch_state},
            )

        if pipeline_recovered or autoresearch_recovered:
            self._state_store.set_status(project_state="degraded")

        self._state_store.set_active_run(None)
        self._state_store.set_current_stage(None)
        self._state_store.set_pending_command(None)
        self._heartbeat.clear()

        if status.recovery_marker is not None:
            self._state_store.set_recovery_marker(
                f"crash_recovered:{status.recovery_marker}"
            )

        lock_path = self._derive_process_lock_path()
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass
        return True

    def run(self, *, run_id: str, max_iterations: int | None = None) -> dict[str, Any]:
        baseline_evaluation, baseline_revision = self._initialize_baseline()
        self._progress_event(
            "progress_started",
            run_id=run_id,
            max_iterations=max_iterations,
            baseline_revision=baseline_revision,
        )
        baseline_score = float(baseline_evaluation["score"])
        consecutive_crashes = 0
        last_result: dict[str, Any] = {
            "decision": "no_iterations",
            "iteration": 0,
            "baseline_score": baseline_score,
        }

        self._state_store.set_baseline_revision(baseline_revision)
        self._state_store.set_candidate_revision(baseline_revision)

        iteration = 1
        while max_iterations is None or iteration <= max_iterations:
            status = self._state_store.get_status()
            if status.project_state == "paused":
                self._heartbeat.clear()
                return {"decision": "paused", "iteration": iteration - 1}

            if status.project_state == "degraded":
                self._heartbeat.clear()
                return {"decision": "degraded", "iteration": iteration - 1}

            iteration_context = IterationContext(
                run_id=run_id,
                iteration=iteration,
                hypothesis=f"Iteration {iteration} hypothesis",
                mutation_summary="",
            )
            selected_knowledge: list[KnowledgeSnippet] = []
            research_plan: ExperimentPlan | ResearchBrief | None = None
            planner_memory_snapshot: PlannerMemorySnapshot | None = None
            mutation_result: MutationApplicationResult | None = None
            falsification_report: dict[str, Any] | None = None
            latest_experiment = self._state_store.get_latest_experiment()
            latest_analysis = self._state_store.get_latest_analysis()
            latest_lesson = self._state_store.get_latest_lesson()

            try:
                self._set_stage(run_id=run_id, iteration=iteration, stage="hypothesis")
                boundary = self._checkpoint_boundary(in_iteration=False)
                if boundary is not None:
                    return boundary

                self._set_stage(run_id=run_id, iteration=iteration, stage="retrieve_knowledge")
                planner_memory_snapshot = self._build_planner_memory_snapshot()
                selected_knowledge = self._load_knowledge(
                    latest_experiment=latest_experiment,
                    latest_analysis=latest_analysis,
                    latest_lesson=latest_lesson,
                    planner_memory_snapshot=planner_memory_snapshot,
                )
                self._persist_knowledge(
                    run_id=run_id,
                    iteration=iteration,
                    knowledge_snippets=selected_knowledge,
                )
                boundary = self._checkpoint_boundary(in_iteration=False)
                if boundary is not None:
                    return boundary

                self._set_stage(run_id=run_id, iteration=iteration, stage="plan_experiment")
                research_plan = self._build_research_plan(
                    baseline_evaluation=baseline_evaluation,
                    latest_experiment=latest_experiment,
                    latest_analysis=latest_analysis,
                    latest_lesson=latest_lesson,
                    knowledge_snippets=selected_knowledge,
                    planner_memory_snapshot=planner_memory_snapshot,
                )
                self._state_store.record_research_plan(
                    run_id=run_id,
                    iteration=iteration,
                    hypothesis=research_plan.hypothesis,
                    summary=research_plan.plan_summary,
                    plan_output=research_plan.to_payload(),
                )
                iteration_context = IterationContext(
                    run_id=run_id,
                    iteration=iteration,
                    hypothesis=research_plan.hypothesis,
                    mutation_summary=research_plan.plan_summary,
                )
                boundary = self._checkpoint_boundary(in_iteration=False)
                if boundary is not None:
                    return boundary

                self._set_stage(run_id=run_id, iteration=iteration, stage="mutate_strategy")
                artifact = self._request_mutation(
                    iteration_context,
                    research_plan=research_plan,
                    knowledge_snippets=selected_knowledge,
                    latest_experiment=latest_experiment,
                    latest_analysis=latest_analysis,
                    latest_lesson=latest_lesson,
                    planner_memory_snapshot=planner_memory_snapshot,
                )
                hypothesis = str(artifact.get("hypothesis", iteration_context.hypothesis))
                mutation_summary = str(
                    artifact.get(
                        "change_summary",
                        research_plan.plan_summary
                        if research_plan is not None
                        else "Mutated strategy candidate",
                    )
                )
                iteration_context = IterationContext(
                    run_id=run_id,
                    iteration=iteration,
                    hypothesis=hypothesis,
                    mutation_summary=mutation_summary,
                )
                boundary = self._checkpoint_boundary(in_iteration=True)
                if boundary is not None:
                    return boundary
                trial_candidates = self._build_trial_candidates(
                    run_id=run_id,
                    iteration=iteration,
                    artifact=artifact,
                )
                frontier = self._build_candidate_frontier(
                    run_id=run_id,
                    iteration=iteration,
                    trial_candidates=trial_candidates,
                )
                promoted_ids = {
                    str(item["candidate_id"])
                    for item in frontier
                    if bool(item.get("promoted"))
                }
                if not promoted_ids:
                    raise ValueError("prescreen rejected every candidate")

                boundary = self._checkpoint_boundary(in_iteration=True)
                if boundary is not None:
                    return boundary

                promoted_results: list[CandidateEvaluationBundle] = []
                promoted_candidates = [
                    candidate
                    for candidate in trial_candidates
                    if candidate.candidate_id in promoted_ids
                ]
                for promoted_candidate in promoted_candidates:
                    mutation_result = self._normalize_mutation_result(
                        self._patch_applier(
                            promoted_candidate.artifact,
                            repository_root=self._repository_root,
                        ),
                        artifact=promoted_candidate.artifact,
                    )
                    candidate_revision = self._revision_for_path(self._mutable_strategy_path)
                    self._state_store.set_candidate_revision(candidate_revision)
                    candidate_context = IterationContext(
                        run_id=run_id,
                        iteration=iteration,
                        hypothesis=hypothesis,
                        mutation_summary=mutation_summary,
                        candidate_revision=candidate_revision,
                    )

                    self._set_stage(run_id=run_id, iteration=iteration, stage="run_backtest")
                    candidate_raw = self._run_harness(self._mutable_strategy_path)
                    boundary = self._checkpoint_boundary(in_iteration=True)
                    if boundary is not None:
                        return boundary

                    self._set_stage(run_id=run_id, iteration=iteration, stage="evaluate_results")
                    candidate_evaluation = self._run_evaluator(candidate_raw)
                    boundary = self._checkpoint_boundary(in_iteration=True)
                    if boundary is not None:
                        return boundary

                    self._set_stage(run_id=run_id, iteration=iteration, stage="falsify_candidate")
                    candidate_falsification = self._run_falsifier(
                        candidate_raw=candidate_raw,
                        candidate_evaluation=candidate_evaluation,
                        mutation_result=mutation_result,
                    )
                    boundary = self._checkpoint_boundary(in_iteration=True)
                    if boundary is not None:
                        return boundary

                    self._set_stage(run_id=run_id, iteration=iteration, stage="analyze_results")
                    analysis_output = self._run_analyzer(
                        run_id=run_id,
                        iteration=iteration,
                        candidate_raw=candidate_raw,
                        baseline_evaluation=baseline_evaluation,
                        candidate_evaluation=candidate_evaluation,
                    )
                    boundary = self._checkpoint_boundary(in_iteration=True)
                    if boundary is not None:
                        return boundary

                    decision = self._decide(
                        candidate_evaluation,
                        baseline_score,
                        falsification_report=candidate_falsification,
                    )
                    promoted_results.append(
                        CandidateEvaluationBundle(
                            candidate_id=promoted_candidate.candidate_id,
                            iteration_context=candidate_context,
                            mutation_result=mutation_result,
                            raw_results=candidate_raw,
                            evaluation=candidate_evaluation,
                            falsification_report=candidate_falsification,
                            analysis_output=analysis_output,
                            decision=decision,
                        )
                    )

                selected_result = self._select_candidate_result(promoted_results)
                iteration_context = selected_result.iteration_context
                mutation_result = selected_result.mutation_result
                candidate_evaluation = selected_result.evaluation
                falsification_report = selected_result.falsification_report
                analysis_output = selected_result.analysis_output
                decision = selected_result.decision
                self._patch_applier(
                    {
                        **next(
                            candidate.artifact
                            for candidate in promoted_candidates
                            if candidate.candidate_id == selected_result.candidate_id
                        )
                    },
                    repository_root=self._repository_root,
                )
                self._record_falsification(
                    run_id=run_id,
                    iteration=iteration,
                    candidate_revision=iteration_context.candidate_revision or baseline_revision,
                    report=falsification_report,
                )

                self._set_stage(
                    run_id=run_id,
                    iteration=iteration,
                    stage="decide_keep_or_rollback",
                )
                last_result = self._record_iteration_result(
                    iteration_context=iteration_context,
                    research_plan=research_plan,
                    baseline_revision=baseline_revision,
                    candidate_evaluation=candidate_evaluation,
                    analysis_output=analysis_output,
                    mutation_result=mutation_result,
                    falsification_report=falsification_report,
                    decision=decision,
                )
                self._progress_event(
                    "progress_decision",
                    run_id=run_id,
                    iteration=iteration,
                    decision=decision,
                    candidate_score=candidate_evaluation.get("score"),
                    baseline_score=baseline_score,
                    hypothesis=iteration_context.hypothesis,
                )
                if research_plan is not None:
                    self._record_lesson(
                        run_id=run_id,
                        iteration=iteration,
                        decision=decision,
                        research_plan=research_plan,
                        knowledge_snippets=selected_knowledge,
                        candidate_evaluation=candidate_evaluation,
                        analysis_output=analysis_output,
                    )
                    self._record_lesson_graph_and_family_memory(
                        run_id=run_id,
                        iteration=iteration,
                        decision=decision,
                        research_plan=research_plan,
                        knowledge_snippets=selected_knowledge,
                        candidate_evaluation=candidate_evaluation,
                        analysis_output=analysis_output,
                    )
                self._export_brain_iteration(run_id=run_id, iteration=iteration)

                if decision == "keep":
                    self._accept_candidate()
                    baseline_revision = iteration_context.candidate_revision or baseline_revision
                    baseline_score = float(candidate_evaluation["score"])
                    baseline_evaluation = dict(candidate_evaluation)
                    self._state_store.set_baseline_revision(baseline_revision)
                    self._state_store.append_outbox_event(
                        event_type="candidate_kept",
                        payload={
                            "run_id": run_id,
                            "iteration": iteration,
                            "candidate_revision": baseline_revision,
                        },
                    )
                else:
                    self._restore_baseline()
                    self._state_store.append_outbox_event(
                        event_type="candidate_rolled_back",
                        payload={
                            "run_id": run_id,
                            "iteration": iteration,
                            "candidate_revision": iteration_context.candidate_revision
                            or baseline_revision,
                        },
                    )

                consecutive_crashes = 0
                iteration += 1
            except ValueError as exc:
                last_result = self._handle_iteration_failure(
                    run_id=run_id,
                    iteration=iteration,
                    baseline_score=baseline_score,
                    baseline_revision=baseline_revision,
                    iteration_context=iteration_context,
                    research_plan=research_plan,
                    knowledge_snippets=selected_knowledge,
                    decision="rollback",
                    event_type="candidate_rolled_back",
                    message=str(exc),
                )
                consecutive_crashes = 0
                iteration += 1
            except Exception as exc:  # noqa: BLE001
                last_result = self._handle_iteration_failure(
                    run_id=run_id,
                    iteration=iteration,
                    baseline_score=baseline_score,
                    baseline_revision=baseline_revision,
                    iteration_context=iteration_context,
                    research_plan=research_plan,
                    knowledge_snippets=selected_knowledge,
                    decision="crash",
                    event_type="candidate_crashed",
                    message=str(exc),
                )
                consecutive_crashes += 1
                if consecutive_crashes >= CRASH_THRESHOLD:
                    self._finish_failed(run_id=run_id, message="crash threshold exceeded")
                    return {
                        "decision": "crash_threshold_exceeded",
                        "iteration": iteration,
                    }
                iteration += 1

        self._finish_success(run_id=run_id)
        return last_result

    def _initialize_baseline(self) -> tuple[dict[str, Any], str]:
        validate_baseline_strategy(self._mutable_strategy_path)
        ensure_accepted_baseline_snapshot(
            baseline_strategy_path=self._mutable_strategy_path,
            baseline_snapshot_path=self._baseline_snapshot_path,
        )
        baseline_raw = self._run_harness(self._mutable_strategy_path)
        baseline_evaluation = self._run_evaluator(baseline_raw)
        baseline_revision = self._revision_for_path(self._mutable_strategy_path)
        return baseline_evaluation, baseline_revision

    def _request_mutation(
        self,
        context: IterationContext,
        *,
        research_plan: ExperimentPlan | ResearchBrief | None,
        knowledge_snippets: list[KnowledgeSnippet],
        latest_experiment: Any,
        latest_analysis: Any,
        latest_lesson: Any,
        planner_memory_snapshot: PlannerMemorySnapshot | None,
    ) -> dict[str, Any]:
        method = getattr(self._openclaw_client, "mutate", None)
        if method is None:
            raise TypeError("openclaw_client must provide a mutate method")

        mutation_context = {
            "hypothesis": context.hypothesis,
            "baseline_revision": self._state_store.get_status().baseline_revision,
            "plan_summary": research_plan.plan_summary if research_plan else "",
            "objective": research_plan.objective if research_plan else "",
            "experiment_type": research_plan.experiment_type if research_plan else "",
            "family": getattr(research_plan, "family", research_plan.experiment_type if research_plan else ""),
            "target_problem": research_plan.target_problem if research_plan else "",
            "expected_effect": research_plan.expected_effect if research_plan else "",
            "regime_policy": research_plan.regime_policy if research_plan else "",
            "change_budget": research_plan.change_budget if research_plan else {},
            "historical_risks": list(getattr(research_plan, "historical_risks", ())),
            "guardrails_to_watch": list(research_plan.guardrails_to_watch)
            if research_plan
            else [],
            "carry_forward_lessons": list(research_plan.carry_forward_lessons)
            if research_plan
            else [],
            "planned_mutations": [dict(item) for item in research_plan.planned_mutations]
            if research_plan
            else [],
            "allowed_indicator_pool": list(
                getattr(research_plan, "allowed_indicator_pool", ())
            ),
            "knowledge_evidence": [
                dict(item) for item in getattr(research_plan, "knowledge_evidence", ())
            ],
            "workspace_refs": [snippet.to_payload() for snippet in knowledge_snippets],
            "artifact_paths": [snippet.source_path for snippet in knowledge_snippets],
            "latest_experiment": self._serialize_experiment_context(latest_experiment),
            "latest_analysis": getattr(latest_analysis, "analysis_output", None),
            "latest_lesson": getattr(latest_lesson, "lesson_output", None),
            "planner_memory": planner_memory_snapshot.to_payload()
            if planner_memory_snapshot is not None
            else None,
            "artifact_mode": getattr(research_plan, "artifact_mode", "prefer_genome"),
            "artifact_capabilities": GENOME_ARTIFACT_CAPABILITIES,
            "preferred_artifact_kind": (
                "strategy_replacement"
                if getattr(research_plan, "artifact_mode", "prefer_genome") == "prefer_raw"
                else "strategy_genome_v1"
            ),
            "allowed_artifact_kinds": ["strategy_genome_v1", "strategy_replacement"],
            "genome_shadow_mode": self._genome_shadow_mode,
        }

        try:
            response = method(
                run_id=context.run_id,
                iteration=context.iteration,
                stage="mutate_strategy",
                agent_id=self._mutation_agent_id,
                context=mutation_context,
            )
        except TypeError:
            response = method(
                {
                    "run_id": context.run_id,
                    "iteration": context.iteration,
                    "stage": "mutate_strategy",
                    "agent_id": self._mutation_agent_id,
                    "context": mutation_context,
                }
            )

        return self._unwrap_artifact(response)

    def _run_harness(self, strategy_path: Path) -> Any:
        return self._call_component(
            self._harness,
            method_name="run",
            positional_argument=strategy_path,
            keyword_name="strategy_path",
            error_message="harness must be callable or expose run()",
        )

    def _run_smoke_harness(self, strategy_path: Path) -> Any:
        return self._call_component(
            self._harness,
            method_name="smoke",
            positional_argument=strategy_path,
            keyword_name="strategy_path",
            error_message="harness must be callable or expose smoke() for prescreening",
        )

    def _run_evaluator(self, raw_results: Any) -> dict[str, Any]:
        return dict(
            self._call_component(
                self._evaluator,
                method_name="evaluate",
                positional_argument=raw_results,
                keyword_name="raw_results",
                error_message="evaluator must be callable or expose evaluate()",
            )
        )

    def _build_trial_candidates(
        self,
        *,
        run_id: str,
        iteration: int,
        artifact: dict[str, Any],
    ) -> list[Any]:
        if self._trial_manager is None:
            return [
                type(
                    "TrialCandidate",
                    (),
                    {
                        "candidate_id": f"{run_id}-{iteration}-base",
                        "artifact": dict(artifact),
                        "artifact_kind": str(artifact.get("kind", "strategy_replacement")),
                        "search_origin": "base",
                    },
                )()
            ]
        return list(
            self._call_component(
                self._trial_manager,
                method_name="build_candidates",
                error_message="trial_manager must be callable or expose build_candidates()",
                run_id=run_id,
                iteration=iteration,
                artifact=artifact,
            )
        )

    def _build_candidate_frontier(
        self,
        *,
        run_id: str,
        iteration: int,
        trial_candidates: list[Any],
    ) -> list[dict[str, Any]]:
        prescreen_results: list[dict[str, Any]] = []
        for trial_candidate in trial_candidates:
            if (
                self._prescreener is None
                and self._trial_manager is None
                and self._candidate_frontier_selector is None
            ):
                report = {
                    "candidate_id": trial_candidate.candidate_id,
                    "passed": True,
                    "reason": "prescreener_disabled",
                    "score": 0.0,
                    "metrics": {},
                }
            else:
                self._patch_applier(
                    trial_candidate.artifact,
                    repository_root=self._repository_root,
                )
                smoke_results = self._run_smoke_harness(self._mutable_strategy_path)
                report = self._run_prescreener(
                    candidate_id=trial_candidate.candidate_id,
                    backtest_results=smoke_results,
                )
            prescreen_results.append(
                {
                    **report,
                    "artifact_kind": getattr(trial_candidate, "artifact_kind", "strategy_replacement"),
                    "search_origin": getattr(trial_candidate, "search_origin", "base"),
                }
            )

        if self._candidate_frontier_selector is None:
            frontier = self._rank_candidate_frontier(prescreen_results)
        else:
            candidate_limit = int(
                getattr(self._trial_manager, "candidate_limit", len(trial_candidates))
            )
            frontier = list(
                self._call_component(
                    self._candidate_frontier_selector,
                    method_name="select",
                    error_message="candidate_frontier_selector must be callable or expose select()",
                    prescreen_results=prescreen_results,
                    candidate_limit=candidate_limit,
                    promotion_limit=self._frontier_promotion_limit,
                )
            )

        for item in frontier:
            self._state_store.record_candidate_frontier(
                run_id=run_id,
                iteration=iteration,
                candidate_id=str(item["candidate_id"]),
                rank=int(item["rank"]),
                promoted=bool(item["promoted"]),
                prescreen_reason=str(item["reason"]),
                prescreen_score=float(item["score"]),
                metadata={
                    "artifact_kind": item.get("artifact_kind", "strategy_replacement"),
                    "search_origin": item.get("search_origin", "base"),
                    "metrics": item.get("metrics", {}),
                },
            )
        return frontier

    def _rank_candidate_frontier(
        self,
        prescreen_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ranked = sorted(
            prescreen_results,
            key=lambda item: (
                0 if bool(item.get("passed")) else 1,
                -float(item.get("score", 0.0)),
                str(item.get("candidate_id", "")),
            ),
        )
        promoted = 0
        frontier: list[dict[str, Any]] = []
        for index, item in enumerate(ranked, start=1):
            is_promoted = bool(item.get("passed")) and promoted < self._frontier_promotion_limit
            if is_promoted:
                promoted += 1
            frontier.append(
                {
                    **item,
                    "rank": index,
                    "promoted": is_promoted,
                }
            )
        return frontier

    def _run_prescreener(
        self,
        *,
        candidate_id: str,
        backtest_results: Any,
    ) -> dict[str, Any]:
        component = self._prescreener or prescreen_candidate
        report = self._call_component(
            component,
            method_name="prescreen",
            error_message="prescreener must be callable or expose prescreen()",
            candidate_id=candidate_id,
            backtest_results=backtest_results,
        )
        if hasattr(report, "to_payload"):
            return dict(report.to_payload())
        return dict(report)

    def _select_candidate_result(
        self,
        candidates: list[CandidateEvaluationBundle],
    ) -> CandidateEvaluationBundle:
        if not candidates:
            raise ValueError("no promoted candidates were available for official evaluation")
        keep_candidates = [item for item in candidates if item.decision == "keep"]
        target = keep_candidates or candidates
        return max(
            target,
            key=lambda item: float(item.evaluation["score"]),
        )

    def _run_falsifier(
        self,
        *,
        candidate_raw: Any,
        candidate_evaluation: dict[str, Any],
        mutation_result: MutationApplicationResult | None,
    ) -> dict[str, Any]:
        if self._falsifier is None:
            return {
                "passed": True,
                "summary": "falsifier disabled",
                "checks": {},
            }
        return dict(
            self._call_component(
                self._falsifier,
                method_name="falsify",
                error_message="falsifier must be callable or expose falsify()",
                backtest_results=candidate_raw,
                evaluation=candidate_evaluation,
                strategy_path=self._mutable_strategy_path,
                compile_result=mutation_result.compile_result if mutation_result is not None else None,
            )
        )

    def _run_analyzer(
        self,
        *,
        run_id: str,
        iteration: int,
        candidate_raw: Any,
        baseline_evaluation: dict[str, Any],
        candidate_evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        if self._analyzer is not None:
            if callable(self._analyzer):
                try:
                    return dict(
                        self._analyzer(
                            backtest_results=candidate_raw,
                            evaluation=candidate_evaluation,
                            run_id=run_id,
                            iteration=iteration,
                            baseline_evaluation=baseline_evaluation,
                            candidate_evaluation=candidate_evaluation,
                        )
                    )
                except TypeError:
                    return dict(
                        self._analyzer(
                            candidate_raw,
                            candidate_evaluation,
                        )
                    )
            method = getattr(self._analyzer, "analyze", None)
            if callable(method):
                try:
                    return dict(
                        method(
                            backtest_results=candidate_raw,
                            evaluation=candidate_evaluation,
                            run_id=run_id,
                            iteration=iteration,
                            baseline_evaluation=baseline_evaluation,
                            candidate_evaluation=candidate_evaluation,
                        )
                    )
                except TypeError:
                    return dict(method(candidate_raw, candidate_evaluation))

        analyze_method = getattr(self._openclaw_client, "analyze", None)
        if callable(analyze_method):
            response = analyze_method(
                run_id=run_id,
                iteration=iteration,
                stage="analyze_results",
                agent_id=self._analysis_agent_id,
                context={
                    "candidate_backtest_results": candidate_raw,
                    "baseline_evaluation": baseline_evaluation,
                    "candidate_evaluation": candidate_evaluation,
                },
            )
            return self._unwrap_artifact(response)

        score_delta = float(candidate_evaluation["score"]) - float(
            baseline_evaluation["score"]
        )
        if score_delta >= KEEP_SCORE_DELTA:
            return self._empty_analysis(summary="Candidate improved over baseline")
        return self._empty_analysis(summary="Candidate did not beat baseline")

    def _decide(
        self,
        candidate_evaluation: dict[str, Any],
        baseline_score: float,
        *,
        falsification_report: dict[str, Any] | None,
    ) -> str:
        candidate_score = float(candidate_evaluation["score"])
        if not bool(candidate_evaluation["guardrails_passed"]):
            return "rollback"
        if falsification_report is not None and not bool(falsification_report.get("passed", False)):
            return "rollback"
        if candidate_score >= baseline_score + KEEP_SCORE_DELTA:
            return "keep"
        return "rollback"

    def _record_iteration_result(
        self,
        *,
        iteration_context: IterationContext,
        research_plan: ExperimentPlan | ResearchBrief | None,
        baseline_revision: str,
        candidate_evaluation: dict[str, Any],
        analysis_output: dict[str, Any],
        mutation_result: MutationApplicationResult | None,
        falsification_report: dict[str, Any] | None,
        decision: str,
    ) -> dict[str, Any]:
        candidate_revision = iteration_context.candidate_revision or baseline_revision
        metrics_payload = {
            "score": candidate_evaluation["score"],
            "metrics": self._json_safe(candidate_evaluation.get("metrics", {})),
            "guardrails_passed": candidate_evaluation["guardrails_passed"],
            "guardrail_failures": candidate_evaluation.get("guardrail_failures", []),
        }
        self._state_store.record_experiment(
            run_id=iteration_context.run_id,
            iteration=iteration_context.iteration,
            candidate_revision=candidate_revision,
            baseline_revision=baseline_revision,
            hypothesis=iteration_context.hypothesis,
            mutation_summary=iteration_context.mutation_summary,
            backtest_metrics=metrics_payload,
            decision=decision,
        )
        self._state_store.record_analysis(
            run_id=iteration_context.run_id,
            iteration=iteration_context.iteration,
            analysis_output=analysis_output,
            summary=analysis_output["summary"],
        )
        if research_plan is not None and mutation_result is not None:
            self._state_store.record_trial(
                run_id=iteration_context.run_id,
                iteration=iteration_context.iteration,
                family=research_plan.experiment_type,
                artifact_kind=mutation_result.artifact_kind,
                candidate_revision=candidate_revision,
                baseline_revision=baseline_revision,
                compile_status=mutation_result.compile_status,
                falsification_pass=bool(
                    falsification_report.get("passed", True)
                    if falsification_report is not None
                    else True
                ),
                decision=decision,
                metadata={
                    "compile_result": mutation_result.compile_result or {},
                    "shadow_comparison": mutation_result.shadow_comparison or {},
                },
            )
        return {
            "decision": decision,
            "iteration": iteration_context.iteration,
            "candidate_score": candidate_evaluation["score"],
            "baseline_score": candidate_evaluation["score"]
            if decision == "keep"
            else None,
        }

    def _record_falsification(
        self,
        *,
        run_id: str,
        iteration: int,
        candidate_revision: str,
        report: dict[str, Any] | None,
    ) -> None:
        if report is None:
            return
        self._state_store.record_falsification(
            run_id=run_id,
            iteration=iteration,
            candidate_revision=candidate_revision,
            passed=bool(report.get("passed", False)),
            checks=dict(report.get("checks", {})),
            summary=str(report.get("summary", "")),
        )

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._json_safe(inner) for key, inner in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        return value

    def _load_knowledge(
        self,
        *,
        latest_experiment: Any,
        latest_analysis: Any,
        latest_lesson: Any,
        planner_memory_snapshot: PlannerMemorySnapshot | None = None,
    ) -> list[KnowledgeSnippet]:
        if self._knowledge_loader is None:
            return []
        return list(
            self._call_component(
                self._knowledge_loader,
                method_name="load",
                error_message="knowledge_loader must be callable or expose load()",
                latest_experiment=latest_experiment,
                latest_analysis=latest_analysis,
                latest_lesson=latest_lesson,
                planner_memory_snapshot=planner_memory_snapshot,
            )
        )

    def _persist_knowledge(
        self,
        *,
        run_id: str,
        iteration: int,
        knowledge_snippets: list[KnowledgeSnippet],
    ) -> None:
        for snippet in knowledge_snippets:
            self._state_store.record_knowledge(
                run_id=run_id,
                iteration=iteration,
                source_path=snippet.source_path,
                title=snippet.title,
                excerpt=snippet.excerpt,
                metadata=snippet.to_payload(),
            )

    def _build_research_plan(
        self,
        *,
        baseline_evaluation: dict[str, Any],
        latest_experiment: Any,
        latest_analysis: Any,
        latest_lesson: Any,
        knowledge_snippets: list[KnowledgeSnippet],
        planner_memory_snapshot: PlannerMemorySnapshot | None = None,
    ) -> ExperimentPlan | ResearchBrief:
        if self._planner is None:
            raise TypeError("planner must be configured")
        return self._call_component(
            self._planner,
            method_name="build_plan",
            error_message="planner must be callable or expose build_plan()",
            baseline_evaluation=baseline_evaluation,
            latest_experiment=latest_experiment,
            latest_analysis=latest_analysis,
            latest_lesson=latest_lesson,
            knowledge_snippets=knowledge_snippets,
            planner_memory_snapshot=planner_memory_snapshot,
        )

    def _record_lesson(
        self,
        *,
        run_id: str,
        iteration: int,
        decision: str,
        research_plan: ExperimentPlan | ResearchBrief,
        knowledge_snippets: list[KnowledgeSnippet],
        candidate_evaluation: dict[str, Any],
        analysis_output: dict[str, Any],
    ) -> None:
        lesson = self._call_component(
            self._lesson_builder,
            method_name="build",
            error_message="lesson_builder must be callable or expose build()",
            plan=research_plan,
            decision=decision,
            candidate_evaluation=candidate_evaluation,
            analysis_output=analysis_output,
            knowledge_snippets=knowledge_snippets,
        )
        self._state_store.record_lesson(
            run_id=run_id,
            iteration=iteration,
            decision=decision,
            summary=lesson.summary,
            lesson_output=lesson.to_payload(),
        )

    def _record_lesson_graph_and_family_memory(
        self,
        *,
        run_id: str,
        iteration: int,
        decision: str,
        research_plan: ExperimentPlan | ResearchBrief,
        knowledge_snippets: list[KnowledgeSnippet],
        candidate_evaluation: dict[str, Any],
        analysis_output: dict[str, Any],
    ) -> None:
        lesson_graph = build_lesson_graph(
            research_plan=research_plan,
            decision=decision,
            knowledge_snippets=knowledge_snippets,
            candidate_evaluation=candidate_evaluation,
            analysis_output=analysis_output,
        )
        self._state_store.record_lesson_graph(
            run_id=run_id,
            iteration=iteration,
            decision=decision,
            thesis=lesson_graph.thesis,
            mutation_delta=lesson_graph.mutation_delta,
            observed_outcome=lesson_graph.observed_outcome,
            failure_mode=lesson_graph.failure_mode,
            next_action=lesson_graph.next_action,
            confidence=lesson_graph.confidence,
            novelty_score=lesson_graph.novelty_score,
            knowledge_source_ids=lesson_graph.knowledge_source_ids,
        )
        family_memory = build_family_memory(
            research_plan=research_plan,
            decision=decision,
            analysis_output=analysis_output,
        )
        self._state_store.record_family_memory(
            family=family_memory.family,
            symbol_scope=family_memory.symbol_scope,
            timeframe_scope=family_memory.timeframe_scope,
            regime_scope=family_memory.regime_scope,
            outcome=family_memory.outcome,
            linked_run_id=run_id,
            linked_iteration=iteration,
            novelty_score=family_memory.novelty_score,
        )

    def _serialize_experiment_context(self, latest_experiment: Any) -> dict[str, Any] | None:
        if latest_experiment is None:
            return None
        return {
            "run_id": getattr(latest_experiment, "run_id", None),
            "iteration": getattr(latest_experiment, "iteration", None),
            "candidate_revision": getattr(latest_experiment, "candidate_revision", None),
            "baseline_revision": getattr(latest_experiment, "baseline_revision", None),
            "hypothesis": getattr(latest_experiment, "hypothesis", None),
            "mutation_summary": getattr(latest_experiment, "mutation_summary", None),
            "backtest_metrics": getattr(latest_experiment, "backtest_metrics", None),
            "decision": getattr(latest_experiment, "decision", None),
        }

    def _checkpoint_boundary(self, *, in_iteration: bool) -> dict[str, Any] | None:
        return self._boundary_decision(in_iteration=in_iteration)

    def _handle_iteration_failure(
        self,
        *,
        run_id: str,
        iteration: int,
        baseline_score: float,
        baseline_revision: str,
        iteration_context: IterationContext,
        research_plan: ExperimentPlan | ResearchBrief | None,
        knowledge_snippets: list[KnowledgeSnippet],
        decision: str,
        event_type: str,
        message: str,
    ) -> dict[str, Any]:
        candidate_revision = (
            self._revision_for_path(self._mutable_strategy_path)
            if self._mutable_strategy_path.exists()
            else baseline_revision
        )
        self._state_store.set_candidate_revision(candidate_revision)
        candidate_evaluation = {
            "score": baseline_score,
            "metrics": {},
            "guardrails_passed": False,
            "guardrail_failures": [message],
        }
        analysis_output = self._empty_analysis(summary=message)
        self._record_iteration_result(
            iteration_context=IterationContext(
                run_id=run_id,
                iteration=iteration,
                hypothesis=iteration_context.hypothesis,
                mutation_summary=message,
                candidate_revision=candidate_revision,
            ),
            research_plan=research_plan,
            baseline_revision=baseline_revision,
            candidate_evaluation=candidate_evaluation,
            analysis_output=analysis_output,
            mutation_result=None,
            falsification_report=None,
            decision=decision,
        )
        if research_plan is not None:
            self._record_lesson(
                run_id=run_id,
                iteration=iteration,
                decision=decision,
                research_plan=research_plan,
                knowledge_snippets=knowledge_snippets,
                candidate_evaluation={
                    "score": baseline_score,
                    "guardrail_failures": [message],
                },
                analysis_output=analysis_output,
            )
            self._record_lesson_graph_and_family_memory(
                run_id=run_id,
                iteration=iteration,
                decision=decision,
                research_plan=research_plan,
                knowledge_snippets=knowledge_snippets,
                candidate_evaluation={
                    "score": baseline_score,
                    "guardrail_failures": [message],
                },
                analysis_output=analysis_output,
            )
        self._export_brain_iteration(run_id=run_id, iteration=iteration)
        self._restore_baseline()
        self._state_store.append_outbox_event(
            event_type=event_type,
            payload={"run_id": run_id, "iteration": iteration, "message": message},
        )
        return {"decision": decision, "iteration": iteration}

    def _normalize_mutation_result(
        self,
        result: Any,
        *,
        artifact: dict[str, Any],
    ) -> MutationApplicationResult:
        if isinstance(result, MutationApplicationResult):
            return result
        if isinstance(result, Path):
            return MutationApplicationResult(
                artifact_kind=str(artifact.get("kind", "strategy_replacement")),
                written_path=result,
                hypothesis=str(artifact.get("hypothesis", "")),
                change_summary=str(artifact.get("change_summary", "")),
                compile_status="raw_applied",
            )
        raise TypeError("patch_applier must return a Path or MutationApplicationResult")

    def _call_component(
        self,
        component: Any,
        *,
        method_name: str,
        positional_argument: Any = None,
        keyword_name: str | None = None,
        error_message: str,
        **kwargs: Any,
    ) -> Any:
        method = getattr(component, method_name, None)
        if callable(method):
            try:
                if keyword_name is None:
                    return method(**kwargs)
                return method(positional_argument, **kwargs)
            except TypeError:
                if keyword_name is None:
                    raise
                return method(**{keyword_name: positional_argument, **kwargs})

        if callable(component):
            try:
                if keyword_name is None:
                    return component(**kwargs)
                return component(positional_argument, **kwargs)
            except TypeError:
                if keyword_name is None:
                    raise
                return component(**{keyword_name: positional_argument, **kwargs})

        raise TypeError(error_message)

    def _boundary_decision(self, *, in_iteration: bool) -> dict[str, Any] | None:
        if not bool(self._lock_is_held()):
            if in_iteration:
                self._restore_baseline()
            self._finish_failed(run_id=self._state_store.get_status().active_run_id, message="process lock lost")
            return {"decision": "lock_lost"}

        status = self._state_store.get_status()
        if status.pending_command == "stop_autoresearch":
            if in_iteration:
                self._restore_baseline()
            self._progress_event(
                "progress_stopped",
                run_id=status.active_run_id,
                iteration=self._latest_iteration_for_run(status.active_run_id),
                message="autoresearch stopped by command",
            )
            self._finish_success(run_id=status.active_run_id)
            return {"decision": "stopped"}
        if status.project_state == "paused":
            self._heartbeat.clear()
            self._state_store.set_current_stage(None)
            self._progress_event(
                "progress_paused",
                run_id=status.active_run_id,
                iteration=self._latest_iteration_for_run(status.active_run_id),
            )
            return {"decision": "paused"}
        return None

    def _set_stage(self, *, run_id: str, iteration: int, stage: str) -> None:
        self._state_store.set_current_stage(stage)
        self._state_store.set_recovery_marker(f"{run_id}:{iteration}:{stage}")
        self._heartbeat.touch()
        self._progress_event(
            "progress_stage_changed",
            run_id=run_id,
            iteration=iteration,
            stage=stage,
        )

    def _accept_candidate(self) -> None:
        self._baseline_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._mutable_strategy_path, self._baseline_snapshot_path)

    def _restore_baseline(self) -> None:
        if not self._baseline_snapshot_path.exists():
            return
        self._mutable_strategy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._baseline_snapshot_path, self._mutable_strategy_path)

    def _finish_success(self, *, run_id: str | None) -> None:
        self._state_store.set_status(project_state="idle", autoresearch_state="success")
        self._state_store.set_active_run(None)
        self._state_store.set_current_stage(None)
        self._state_store.set_pending_command(None)
        self._heartbeat.clear()
        self._progress_event(
            "progress_success",
            run_id=run_id,
            iteration=self._latest_iteration_for_run(run_id),
            message="autoresearch finished successfully",
        )
        if run_id is not None:
            self._state_store.record_run(run_id=run_id, state="success")

    def _finish_failed(self, *, run_id: str | None, message: str) -> None:
        self._state_store.set_status(project_state="degraded", autoresearch_state="failed")
        self._state_store.set_active_run(None)
        self._state_store.set_current_stage(None)
        self._state_store.set_pending_command(None)
        self._heartbeat.clear()
        self._progress_event(
            "progress_failed",
            run_id=run_id,
            iteration=self._latest_iteration_for_run(run_id),
            message=message,
        )
        self._state_store.append_outbox_event(
            event_type="autoresearch_failed",
            payload={"message": message},
        )
        if run_id is not None:
            self._state_store.record_run(run_id=run_id, state="failed")

    def _revision_for_path(self, path: Path) -> str:
        contents = path.read_text(encoding="utf-8")
        return hashlib.sha256(contents.encode("utf-8")).hexdigest()[:12]

    def _unwrap_artifact(self, response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            return dict(response)

        ok = getattr(response, "ok", None)
        artifact = getattr(response, "artifact", None)
        message = getattr(response, "message", "OpenClaw call failed")
        stage = getattr(response, "stage", None)
        error_code = getattr(response, "error_code", None)
        if ok is True and isinstance(artifact, dict):
            return dict(artifact)
        if ok is False:
            parts = [part for part in (stage, error_code) if isinstance(part, str) and part]
            prefix = f"[{'/'.join(parts)}] " if parts else ""
            raise ValueError(f"{prefix}{message}")
        raise TypeError("OpenClaw response must be a mapping or expose ok/artifact fields")

    def _empty_analysis(self, *, summary: str) -> dict[str, Any]:
        return {
            "strengths": [],
            "weaknesses": [],
            "coverage_gaps": [],
            "regime_observations": [],
            "next_hypothesis_hints": [],
            "summary": summary,
        }

    def _derive_process_lock_path(self) -> Path:
        db_path = getattr(self._state_store, "_db_path", self._repository_root / "runtime" / "state.db")
        project_id = getattr(self._state_store, "_project_id", "project")
        resolved_db_path = Path(db_path)
        return resolved_db_path.with_name(f"{resolved_db_path.name}.{project_id}.supervisor.lock")

    def _latest_iteration_for_run(self, run_id: str | None) -> int | None:
        if run_id is None:
            return None
        latest = self._state_store.get_latest_experiment()
        if latest is None or latest.run_id != run_id:
            return None
        return latest.iteration

    def _progress_event(self, event_type: str, **payload: Any) -> None:
        if self._progress_notifier is None:
            return
        self._state_store.append_outbox_event(
            event_type=event_type,
            payload={key: value for key, value in payload.items() if value is not None},
        )
        try:
            self._progress_notifier()
        except Exception:
            pass

    def _build_planner_memory_snapshot(self) -> PlannerMemorySnapshot | None:
        if self._planner_memory is None:
            return None
        return self._call_component(
            self._planner_memory,
            method_name="build_snapshot",
            error_message="planner_memory must be callable or expose build_snapshot()",
        )

    def _export_brain_iteration(self, *, run_id: str, iteration: int) -> None:
        if self._brain_sync is None or not self._brain_auto_export:
            return
        try:
            self._call_component(
                self._brain_sync,
                method_name="export_iteration_bundle",
                error_message="brain_sync must be callable or expose export_iteration_bundle()",
                run_id=run_id,
                iteration=iteration,
            )
        except Exception:  # noqa: BLE001
            self._state_store.append_outbox_event(
                event_type="brain_export_failed",
                payload={"run_id": run_id, "iteration": iteration},
            )
