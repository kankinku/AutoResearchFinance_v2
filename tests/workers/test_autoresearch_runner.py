from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

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

    def __call__(self, strategy_path: Path) -> Any:
        self.calls.append(extract_strategy_tag(strategy_path.read_text(encoding="utf-8")))
        if not self.results:
            raise AssertionError("unexpected harness call")
        result = self.results.pop(0)
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
    lock_checker: SequenceLockChecker | None = None,
) -> object:
    from finance_autoresearch.workers.autoresearch_runner import AutoresearchRunner

    return AutoresearchRunner(
        state_store=store,
        repository_root=repository_root,
        openclaw_client=openclaw_client or FakeOpenClawClient(),
        harness=harness or FakeHarness(results=[]),
        evaluator=evaluator or FakeEvaluator(results=[]),
        analyzer=analyzer or FakeAnalyzer(outputs=[]),
        mutable_strategy_path=repository_root / MUTABLE_TARGET_PATH,
        baseline_snapshot_path=repository_root
        / "runtime"
        / "baseline"
        / "accepted_strategy_candidate.py",
        lock_is_held=lock_checker or SequenceLockChecker(deque([True])),
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
