from __future__ import annotations

import json
from pathlib import Path

from research.llm.director import ResearchDirector
from research.llm.provider import CodexIntentProvider
from runtime.research_loop import (
    ResearchLoopConfig,
    _timing_summary,
    _write_autoresearch_status,
    run_autoresearch,
)
from strategy_ir.schema import StrategyIR


def _write_strategy(path: Path) -> None:
    path.write_text(
        "schema_version: 1\n"
        "id: loop-base\n"
        "family: trend\n"
        "generation: 0\n"
        "indicators:\n"
        "  fast: {type: SMA, period: 2}\n"
        "entry: {logic: AND, conditions: [{op: greater_than, left: close, value: 0}]}\n"
        "exit: {logic: AND, conditions: [{op: less_than, left: close, value: 0}]}\n"
        "risk: {stop_loss_pct: 0, take_profit_pct: 0}\n",
        encoding="utf-8",
    )


def test_autoresearch_connects_director_intent_to_each_generation(tmp_path: Path) -> None:
    source = tmp_path / "strategy.yaml"
    _write_strategy(source)
    calls: list[dict[str, object]] = []

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        current = kwargs["strategy_override"]
        assert isinstance(current, StrategyIR)
        return {
            "status": "COMPLETED",
            "candidate_count": 1,
            "best_strategy": current.model_dump(mode="json", by_alias=True),
        }

    provider = CodexIntentProvider(
        lambda context: {
            "mode": "structure",
            "parent_ids": [str(context["source_strategy"]["id"])],
            "operations": [],
            "rationale": "add an optional VIX regime input",
            "feature_selections": [
                {
                    "alias": "vix_regime",
                    "feature_id": "vix_percentile",
                    "inputs": ["VIX.close"],
                    "timeframe": "1d",
                    "lag_bars": 1,
                    "lookback": 20,
                    "parameters": {},
                }
            ],
        }
    )

    result = run_autoresearch(
        ResearchLoopConfig(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            source_path="strategy.yaml",
            data_path="data.parquet",
            generations=2,
        ),
        ResearchDirector(provider),
        evaluator=fake_evaluation,
    )

    assert result["status"] == "COMPLETED"
    assert result["completed_generations"] == 2
    assert len(calls) == 2
    assert [call["generation"] for call in calls] == [1, 2]
    assert all(
        any(operation.op == "ADD_FEATURE" for operation in kwargs["operations"])
        for kwargs in calls
    )
    state = json.loads(
        (tmp_path / "state" / "system" / "autoresearch.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "COMPLETED"
    assert state["research_run_id"] == result["research_run_id"]
    assert state["generations"][0]["intent"]["feature_selections"][0]["feature_id"] == (
        "vix_percentile"
    )


def test_autoresearch_queues_unregistered_feature_proposal_without_evaluating_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "strategy.yaml"
    _write_strategy(source)
    evaluated = False
    provider = CodexIntentProvider(
        lambda context: {
            "mode": "structure",
            "parent_ids": [str(context["source_strategy"]["id"])],
            "operations": [],
            "rationale": "propose a new macro feature",
            "feature_proposal": {
                "name": "new_macro",
                "family": "macro",
                "inputs": ["VIX.close"],
                "calculator": "percentile",
                "timeframe": "1d",
                "lookback": 20,
                "lag_bars": 0,
                "parameters": {},
                "formula": "percentile(VIX.close, 20)",
                "justification": "regime filter",
            },
        }
    )

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        nonlocal evaluated
        evaluated = True
        return {"status": "COMPLETED"}

    result = run_autoresearch(
        ResearchLoopConfig(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            source_path="strategy.yaml",
            data_path="data.parquet",
            generations=1,
        ),
        ResearchDirector(provider),
        evaluator=fake_evaluation,
    )

    assert result["status"] == "COMPLETED_WITH_FALLBACKS"
    assert result["completed_generations"] == 1
    assert evaluated is True
    assert result["generations"][0]["status"] == "FALLBACK"
    queued = json.loads(
        (tmp_path / "state" / "system" / "feature-proposals.jsonl")
        .read_text(encoding="utf-8")
    )
    assert queued["status"] == "PENDING_VERIFICATION"


def test_autoresearch_repairs_invalid_intent_and_continues(tmp_path: Path) -> None:
    source = tmp_path / "strategy.yaml"
    _write_strategy(source)
    repair_calls: list[tuple[dict[str, object] | None, str]] = []
    evaluated: list[tuple[object, object]] = []

    class RepairingProvider:
        def propose(self, context: dict[str, object]) -> dict[str, object]:
            return {
                "mode": "mixed",
                "parent_ids": [str(context["source_strategy"]["id"])],
                "rationale": "bad proposal",
                "feature_proposal": {
                    "name": "unregistered",
                    "family": "macro",
                    "inputs": ["VIX.close"],
                    "calculator": "percentile",
                    "lookback": 20,
                    "formula": "percentile(VIX.close, 20)",
                    "justification": "test",
                },
            }

        def repair(
            self,
            context: dict[str, object],
            invalid_intent: dict[str, object] | None,
            error: str,
        ) -> dict[str, object]:
            del context
            repair_calls.append((invalid_intent, error))
            return {
                "mode": "structure",
                "parent_ids": ["loop-base"],
                "operations": [],
                "rationale": "use a registered feature",
                "feature_selections": [
                    {
                        "alias": "vix_regime",
                        "feature_id": "vix_percentile",
                        "inputs": ["VIX.close"],
                        "lookback": 20,
                    }
                ],
            }

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        evaluated.append((kwargs["operations"], kwargs["strategy_override"]))
        return {"status": "COMPLETED", "candidate_count": 1}

    result = run_autoresearch(
        ResearchLoopConfig(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            source_path="strategy.yaml",
            data_path="data.parquet",
            generations=2,
        ),
        ResearchDirector(RepairingProvider()),
        evaluator=fake_evaluation,
    )

    assert result["status"] == "COMPLETED"
    assert result["completed_generations"] == 2
    assert len(repair_calls) == 2
    assert len(evaluated) == 2
    assert all(item["status"] == "REPAIRED" for item in result["generations"])


def test_autoresearch_records_compact_diagnostic_for_repair(tmp_path: Path) -> None:
    source = tmp_path / "strategy.yaml"
    _write_strategy(source)
    repair_errors: list[str] = []

    class RepairingProvider:
        def propose(self, context: dict[str, object]) -> dict[str, object]:
            return {
                "mode": "structure",
                "parent_ids": [str(context["source_strategy"]["id"])],
                "rationale": "invalid regime target",
                "operations": [
                    {
                        "op": "ADD_REGIME_FILTER",
                        "path": "regime_filters.0",
                        "condition": {
                            "op": "greater_than",
                            "left": "close",
                            "value": 1,
                        },
                    }
                ],
            }

        def repair(
            self,
            context: dict[str, object],
            invalid_intent: dict[str, object] | None,
            error: str,
        ) -> dict[str, object]:
            del context, invalid_intent
            repair_errors.append(error)
            return {
                "mode": "structure",
                "parent_ids": ["loop-base"],
                "operations": [],
                "rationale": "retain after invalid proposal",
            }

    result = run_autoresearch(
        ResearchLoopConfig(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            source_path="strategy.yaml",
            data_path="data.parquet",
            generations=1,
        ),
        ResearchDirector(RepairingProvider()),
        evaluator=lambda **kwargs: {"status": "COMPLETED", "candidate_count": 1},
    )

    assert result["status"] == "COMPLETED"
    assert len(repair_errors) == 1
    assert "code=INTENT_PATH_TARGET" in repair_errors[0]
    assert "expected=regime_filters" in repair_errors[0]
    events = [
        json.loads(line)
        for line in (tmp_path / "state" / "system" / "research-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    failed = next(event for event in events if event["event"] == "proposal_failed")
    assert failed["diagnostic"]["code"] == "INTENT_PATH_TARGET"
    assert failed["diagnostic"]["generation"] == 1
    knowledge = [
        json.loads(line)
        for line in (tmp_path / "state" / "system" / "repair-knowledge.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert knowledge[0]["diagnostic"]["path_expected"] == "regime_filters"


def test_autoresearch_fallbacks_after_repair_exhaustion_and_reaches_all_generations(
    tmp_path: Path,
) -> None:
    source = tmp_path / "strategy.yaml"
    _write_strategy(source)
    calls: list[dict[str, object]] = []

    class FailingProvider:
        def propose(self, context: dict[str, object]) -> dict[str, object]:
            return {
                "mode": "structure",
                "parent_ids": [str(context["source_strategy"]["id"])],
                "rationale": "invalid feature",
                "feature_selections": [{"alias": "bad", "feature_id": "missing"}],
            }

        def repair(
            self,
            context: dict[str, object],
            invalid_intent: dict[str, object] | None,
            error: str,
        ) -> dict[str, object]:
            del context, invalid_intent, error
            return {
                "mode": "structure",
                "parent_ids": ["loop-base"],
                "rationale": "still invalid",
                "feature_selections": [{"alias": "bad", "feature_id": "missing"}],
            }

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"status": "COMPLETED", "candidate_count": 1}

    result = run_autoresearch(
        ResearchLoopConfig(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            source_path="strategy.yaml",
            data_path="data.parquet",
            generations=2,
            intent_repair_attempts=2,
        ),
        ResearchDirector(FailingProvider()),
        evaluator=fake_evaluation,
    )

    assert result["status"] == "COMPLETED_WITH_FALLBACKS"
    assert result["completed_generations"] == 2
    assert len(calls) == 2
    assert all(not call["operations"] for call in calls)
    assert all(item["status"] == "FALLBACK" for item in result["generations"])
    assert all(item["repair_attempts"] == 1 for item in result["generations"])


def test_autoresearch_skips_duplicate_repair_payload_and_records_knowledge(
    tmp_path: Path,
) -> None:
    source = tmp_path / "strategy.yaml"
    _write_strategy(source)
    repair_calls = 0

    class RepeatingProvider:
        def propose(self, context: dict[str, object]) -> dict[str, object]:
            return {
                "mode": "structure",
                "parent_ids": [str(context["source_strategy"]["id"])],
                "rationale": "invalid feature",
                "feature_selections": [{"alias": "bad", "feature_id": "missing"}],
            }

        def repair(
            self,
            context: dict[str, object],
            invalid_intent: dict[str, object] | None,
            error: str,
        ) -> dict[str, object]:
            nonlocal repair_calls
            del context, invalid_intent, error
            repair_calls += 1
            return {
                "mode": "structure",
                "parent_ids": ["loop-base"],
                "rationale": "same invalid repair",
                "feature_selections": [{"alias": "bad", "feature_id": "missing"}],
            }

    result = run_autoresearch(
        ResearchLoopConfig(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            source_path="strategy.yaml",
            data_path="data.parquet",
            generations=1,
            intent_repair_attempts=3,
        ),
        ResearchDirector(RepeatingProvider()),
        evaluator=lambda **kwargs: {"status": "COMPLETED", "candidate_count": 1},
    )

    assert result["generations"][0]["status"] == "FALLBACK"
    assert repair_calls == 1
    events = [
        json.loads(line)
        for line in (tmp_path / "state" / "system" / "research-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(event["event"] == "repair_skipped_duplicate" for event in events)
    knowledge = (tmp_path / "state" / "system" / "repair-knowledge.jsonl").read_text(
        encoding="utf-8"
    )
    assert "INTENT_UNREGISTERED_FEATURE" in knowledge


def test_autoresearch_status_write_permission_error_does_not_abort_research(
    tmp_path: Path, monkeypatch
) -> None:
    config = ResearchLoopConfig(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        source_path="strategy.yaml",
        data_path="data.parquet",
    )

    def denied_replace(source: Path, target: Path) -> None:
        del source, target
        raise PermissionError("simulated Windows file lock")

    monkeypatch.setattr("runtime.research_loop.os.replace", denied_replace)

    _write_autoresearch_status(
        config,
        "RUNNING",
        completed_generations=0,
        records=[],
        current_generation=1,
        current_phase="PROPOSING",
    )


def test_autoresearch_processes_all_requested_generations(tmp_path: Path) -> None:
    source = tmp_path / "strategy.yaml"
    _write_strategy(source)
    provider = CodexIntentProvider(
        lambda context: {
            "mode": "structure",
            "parent_ids": [str(context["source_strategy"]["id"])],
            "operations": [],
            "rationale": "retain the current strategy for a bounded run",
        }
    )
    evaluated: list[int] = []

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        evaluated.append(int(kwargs["seed"]))
        return {"status": "COMPLETED", "candidate_count": 1}

    result = run_autoresearch(
        ResearchLoopConfig(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            source_path="strategy.yaml",
            data_path="data.parquet",
            generations=100,
            intent_repair_attempts=0,
        ),
        ResearchDirector(provider),
        evaluator=fake_evaluation,
    )

    assert result["status"] == "COMPLETED"
    assert result["completed_generations"] == 100
    assert len(result["generations"]) == 100
    assert evaluated == list(range(100))


def test_autoresearch_writes_phase_events_and_live_phase_status(tmp_path: Path) -> None:
    source = tmp_path / "strategy.yaml"
    _write_strategy(source)
    observed: dict[str, object] = {}

    def proposal(context: dict[str, object]) -> dict[str, object]:
        status = json.loads(
            (tmp_path / "state" / "system" / "autoresearch.json").read_text(
                encoding="utf-8"
            )
        )
        observed["proposal_phase"] = status["current_phase"]
        observed["proposal_generation"] = status["current_generation"]
        return {
            "mode": "structure",
            "parent_ids": [str(context["source_strategy"]["id"])],
            "operations": [],
            "rationale": "record phase timing",
        }

    provider = CodexIntentProvider(proposal)

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        status = json.loads(
            (tmp_path / "state" / "system" / "autoresearch.json").read_text(
                encoding="utf-8"
            )
        )
        observed["evaluation_phase"] = status["current_phase"]
        return {"status": "COMPLETED", "candidate_count": 1}

    run_autoresearch(
        ResearchLoopConfig(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            source_path="strategy.yaml",
            data_path="data.parquet",
            generations=1,
        ),
        ResearchDirector(provider),
        evaluator=fake_evaluation,
    )

    assert observed == {
        "proposal_phase": "PROPOSING",
        "proposal_generation": 1,
        "evaluation_phase": "BACKTESTING",
    }
    events = [
        json.loads(line)
        for line in (tmp_path / "state" / "system" / "research-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["event"] for event in events] == [
        "run_started",
        "generation_started",
        "proposal_started",
        "preflight_completed",
        "proposal_completed",
        "evaluation_started",
        "evaluation_completed",
        "generation_completed",
        "run_completed",
    ]
    assert all(event["timestamp"] for event in events)
    assert all(event["generation"] in {None, 1} for event in events)
    assert all(
        "duration_seconds" in event
        for event in events
        if event["event"].endswith("completed")
    )
    final_state = json.loads(
        (tmp_path / "state" / "system" / "autoresearch.json").read_text(
            encoding="utf-8"
        )
    )
    assert final_state["current_phase"] == "COMPLETED"
    assert final_state["last_event"] == "run_completed"
    assert final_state["completed_generations"] == 1
    timing = final_state["timing_summary"]
    assert timing["proposal"]["count"] == 1
    assert timing["repair"]["count"] == 0
    assert timing["backtest"]["count"] == 1
    assert timing["generation"]["count"] == 1
    assert timing["proposal"]["p50_seconds"] >= 0
    assert timing["proposal"]["p95_seconds"] >= timing["proposal"]["p50_seconds"]


def test_timing_summary_pairs_research_events_and_calculates_percentiles() -> None:
    events = [
        {
            "event": "generation_started",
            "generation": 1,
            "timestamp": "2026-09-03T00:00:00+00:00",
        },
        {
            "event": "proposal_started",
            "generation": 1,
            "timestamp": "2026-09-03T00:00:01+00:00",
        },
        {
            "event": "preflight_completed",
            "generation": 1,
            "timestamp": "2026-09-03T00:00:03+00:00",
        },
        {
            "event": "evaluation_started",
            "generation": 1,
            "timestamp": "2026-09-03T00:00:03+00:00",
        },
        {
            "event": "evaluation_completed",
            "generation": 1,
            "timestamp": "2026-09-03T00:00:04.500000+00:00",
        },
        {
            "event": "generation_completed",
            "generation": 1,
            "timestamp": "2026-09-03T00:00:05+00:00",
        },
    ]

    summary = _timing_summary(events)

    assert summary["proposal"] == {
        "count": 1,
        "total_seconds": 2.0,
        "p50_seconds": 2.0,
        "p95_seconds": 2.0,
        "max_seconds": 2.0,
    }
    assert summary["repair"]["count"] == 0
    assert summary["backtest"]["total_seconds"] == 1.5
    assert summary["generation"]["total_seconds"] == 5.0
