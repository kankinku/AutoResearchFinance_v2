from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact
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


@dataclass(slots=True, frozen=True)
class IterationContext:
    run_id: str
    iteration: int
    hypothesis: str
    mutation_summary: str
    candidate_revision: str | None = None


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
        mutable_strategy_path: Path | str = DEFAULT_BASELINE_STRATEGY_PATH,
        baseline_snapshot_path: Path | str = DEFAULT_BASELINE_SNAPSHOT_PATH,
        mutation_agent_id: str = "research",
        analysis_agent_id: str = "critic",
        patch_applier=apply_strategy_artifact,
        lock_is_held=None,
    ) -> None:
        self._state_store = state_store
        self._repository_root = Path(repository_root)
        self._openclaw_client = openclaw_client
        self._harness = harness
        self._evaluator = evaluator
        self._analyzer = analyzer
        self._mutable_strategy_path = self._repository_root / Path(mutable_strategy_path)
        self._baseline_snapshot_path = self._repository_root / Path(baseline_snapshot_path)
        self._mutation_agent_id = mutation_agent_id
        self._analysis_agent_id = analysis_agent_id
        self._patch_applier = patch_applier
        self._lock_is_held = lock_is_held or (lambda: True)
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

        if not bool(baseline_evaluation["guardrails_passed"]):
            return SeedBaselineValidation(
                valid=False,
                message="seed baseline guardrails failed",
            )

        self._state_store.set_candidate_revision(baseline_revision)
        self._state_store.set_baseline_revision(baseline_revision)
        return SeedBaselineValidation(valid=True, message="seed baseline validated")

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

            try:
                self._set_stage(run_id=run_id, iteration=iteration, stage="hypothesis")
                boundary = self._boundary_decision(in_iteration=False)
                if boundary is not None:
                    return boundary

                self._set_stage(run_id=run_id, iteration=iteration, stage="mutate_strategy")
                artifact = self._request_mutation(iteration_context)
                hypothesis = str(artifact.get("hypothesis", iteration_context.hypothesis))
                mutation_summary = str(
                    artifact.get("change_summary", "Mutated strategy candidate")
                )
                iteration_context = IterationContext(
                    run_id=run_id,
                    iteration=iteration,
                    hypothesis=hypothesis,
                    mutation_summary=mutation_summary,
                )
                self._patch_applier(artifact, repository_root=self._repository_root)
                candidate_revision = self._revision_for_path(self._mutable_strategy_path)
                self._state_store.set_candidate_revision(candidate_revision)
                iteration_context = IterationContext(
                    run_id=run_id,
                    iteration=iteration,
                    hypothesis=hypothesis,
                    mutation_summary=mutation_summary,
                    candidate_revision=candidate_revision,
                )

                boundary = self._boundary_decision(in_iteration=True)
                if boundary is not None:
                    return boundary

                self._set_stage(run_id=run_id, iteration=iteration, stage="run_backtest")
                candidate_raw = self._run_harness(self._mutable_strategy_path)
                boundary = self._boundary_decision(in_iteration=True)
                if boundary is not None:
                    return boundary

                self._set_stage(run_id=run_id, iteration=iteration, stage="evaluate_results")
                candidate_evaluation = self._run_evaluator(candidate_raw)
                boundary = self._boundary_decision(in_iteration=True)
                if boundary is not None:
                    return boundary

                self._set_stage(run_id=run_id, iteration=iteration, stage="analyze_results")
                analysis_output = self._run_analyzer(
                    run_id=run_id,
                    iteration=iteration,
                    baseline_evaluation=baseline_evaluation,
                    candidate_evaluation=candidate_evaluation,
                )
                boundary = self._boundary_decision(in_iteration=True)
                if boundary is not None:
                    return boundary

                self._set_stage(
                    run_id=run_id,
                    iteration=iteration,
                    stage="decide_keep_or_rollback",
                )
                decision = self._decide(candidate_evaluation, baseline_score)
                last_result = self._record_iteration_result(
                    iteration_context=iteration_context,
                    baseline_revision=baseline_revision,
                    candidate_evaluation=candidate_evaluation,
                    analysis_output=analysis_output,
                    decision=decision,
                )

                if decision == "keep":
                    self._accept_candidate()
                    baseline_revision = candidate_revision
                    baseline_score = float(candidate_evaluation["score"])
                    baseline_evaluation = dict(candidate_evaluation)
                    self._state_store.set_baseline_revision(baseline_revision)
                    self._state_store.append_outbox_event(
                        event_type="candidate_kept",
                        payload={
                            "run_id": run_id,
                            "iteration": iteration,
                            "candidate_revision": candidate_revision,
                        },
                    )
                else:
                    self._restore_baseline()
                    self._state_store.append_outbox_event(
                        event_type="candidate_rolled_back",
                        payload={
                            "run_id": run_id,
                            "iteration": iteration,
                            "candidate_revision": candidate_revision,
                        },
                    )

                consecutive_crashes = 0
                iteration += 1
            except ValueError as exc:
                # mutation/application failures are rollback-class failures
                candidate_revision = (
                    self._revision_for_path(self._mutable_strategy_path)
                    if self._mutable_strategy_path.exists()
                    else baseline_revision
                )
                self._state_store.set_candidate_revision(candidate_revision)
                self._record_iteration_result(
                    iteration_context=IterationContext(
                        run_id=run_id,
                        iteration=iteration,
                        hypothesis=iteration_context.hypothesis,
                        mutation_summary=str(exc),
                        candidate_revision=candidate_revision,
                    ),
                    baseline_revision=baseline_revision,
                    candidate_evaluation={
                        "score": baseline_score,
                        "metrics": {},
                        "guardrails_passed": False,
                        "guardrail_failures": [str(exc)],
                    },
                    analysis_output=self._empty_analysis(summary=str(exc)),
                    decision="rollback",
                )
                self._restore_baseline()
                self._state_store.append_outbox_event(
                    event_type="candidate_rolled_back",
                    payload={"run_id": run_id, "iteration": iteration, "message": str(exc)},
                )
                last_result = {"decision": "rollback", "iteration": iteration}
                consecutive_crashes = 0
                iteration += 1
            except Exception as exc:  # noqa: BLE001
                candidate_revision = (
                    self._revision_for_path(self._mutable_strategy_path)
                    if self._mutable_strategy_path.exists()
                    else baseline_revision
                )
                self._state_store.set_candidate_revision(candidate_revision)
                self._record_iteration_result(
                    iteration_context=IterationContext(
                        run_id=run_id,
                        iteration=iteration,
                        hypothesis=iteration_context.hypothesis,
                        mutation_summary=str(exc),
                        candidate_revision=candidate_revision,
                    ),
                    baseline_revision=baseline_revision,
                    candidate_evaluation={
                        "score": baseline_score,
                        "metrics": {},
                        "guardrails_passed": False,
                        "guardrail_failures": [str(exc)],
                    },
                    analysis_output=self._empty_analysis(summary=str(exc)),
                    decision="crash",
                )
                self._restore_baseline()
                self._state_store.append_outbox_event(
                    event_type="candidate_crashed",
                    payload={"run_id": run_id, "iteration": iteration, "message": str(exc)},
                )
                last_result = {"decision": "crash", "iteration": iteration}
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

    def _request_mutation(self, context: IterationContext) -> dict[str, Any]:
        method = getattr(self._openclaw_client, "mutate", None)
        if method is None:
            raise TypeError("openclaw_client must provide a mutate method")

        try:
            response = method(
                run_id=context.run_id,
                iteration=context.iteration,
                stage="mutate_strategy",
                agent_id=self._mutation_agent_id,
                context={
                    "hypothesis": context.hypothesis,
                    "baseline_revision": self._state_store.get_status().baseline_revision,
                },
            )
        except TypeError:
            response = method(
                {
                    "run_id": context.run_id,
                    "iteration": context.iteration,
                    "stage": "mutate_strategy",
                    "agent_id": self._mutation_agent_id,
                    "context": {"hypothesis": context.hypothesis},
                }
            )

        return self._unwrap_artifact(response)

    def _run_harness(self, strategy_path: Path) -> Any:
        if callable(self._harness):
            try:
                return self._harness(strategy_path)
            except TypeError:
                return self._harness(strategy_path=strategy_path)

        method = getattr(self._harness, "run", None)
        if callable(method):
            try:
                return method(strategy_path)
            except TypeError:
                return method(strategy_path=strategy_path)

        raise TypeError("harness must be callable or expose run()")

    def _run_evaluator(self, raw_results: Any) -> dict[str, Any]:
        if callable(self._evaluator):
            try:
                return dict(self._evaluator(raw_results))
            except TypeError:
                return dict(self._evaluator(raw_results=raw_results))

        method = getattr(self._evaluator, "evaluate", None)
        if callable(method):
            return dict(method(raw_results))

        raise TypeError("evaluator must be callable or expose evaluate()")

    def _run_analyzer(
        self,
        *,
        run_id: str,
        iteration: int,
        baseline_evaluation: dict[str, Any],
        candidate_evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        if self._analyzer is not None:
            if callable(self._analyzer):
                return dict(
                    self._analyzer(
                        run_id=run_id,
                        iteration=iteration,
                        baseline_evaluation=baseline_evaluation,
                        candidate_evaluation=candidate_evaluation,
                    )
                )
            method = getattr(self._analyzer, "analyze", None)
            if callable(method):
                return dict(
                    method(
                        run_id=run_id,
                        iteration=iteration,
                        baseline_evaluation=baseline_evaluation,
                        candidate_evaluation=candidate_evaluation,
                    )
                )

        analyze_method = getattr(self._openclaw_client, "analyze", None)
        if callable(analyze_method):
            response = analyze_method(
                run_id=run_id,
                iteration=iteration,
                stage="analyze_results",
                agent_id=self._analysis_agent_id,
                context={
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

    def _decide(self, candidate_evaluation: dict[str, Any], baseline_score: float) -> str:
        candidate_score = float(candidate_evaluation["score"])
        if not bool(candidate_evaluation["guardrails_passed"]):
            return "rollback"
        if candidate_score >= baseline_score + KEEP_SCORE_DELTA:
            return "keep"
        return "rollback"

    def _record_iteration_result(
        self,
        *,
        iteration_context: IterationContext,
        baseline_revision: str,
        candidate_evaluation: dict[str, Any],
        analysis_output: dict[str, Any],
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
        return {
            "decision": decision,
            "iteration": iteration_context.iteration,
            "candidate_score": candidate_evaluation["score"],
            "baseline_score": candidate_evaluation["score"]
            if decision == "keep"
            else None,
        }

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._json_safe(inner) for key, inner in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        return value

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
            self._finish_success(run_id=status.active_run_id)
            return {"decision": "stopped"}
        if status.project_state == "paused":
            self._heartbeat.clear()
            self._state_store.set_current_stage(None)
            return {"decision": "paused"}
        return None

    def _set_stage(self, *, run_id: str, iteration: int, stage: str) -> None:
        self._state_store.set_current_stage(stage)
        self._state_store.set_recovery_marker(f"{run_id}:{iteration}:{stage}")
        self._heartbeat.touch()

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
        if run_id is not None:
            self._state_store.record_run(run_id=run_id, state="success")

    def _finish_failed(self, *, run_id: str | None, message: str) -> None:
        self._state_store.set_status(project_state="degraded", autoresearch_state="failed")
        self._state_store.set_active_run(None)
        self._state_store.set_current_stage(None)
        self._state_store.set_pending_command(None)
        self._heartbeat.clear()
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
        if ok is True and isinstance(artifact, dict):
            return dict(artifact)
        if ok is False:
            raise ValueError(str(message))
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
