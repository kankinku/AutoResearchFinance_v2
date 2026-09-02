from __future__ import annotations

import json
from pathlib import Path

from research.llm.director import ResearchDirector
from research.llm.provider import CodexIntentProvider
from runtime.research_loop import ResearchLoopConfig, run_autoresearch
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
    assert all(
        any(operation.op == "ADD_FEATURE" for operation in kwargs["operations"])
        for kwargs in calls
    )
    state = json.loads(
        (tmp_path / "state" / "system" / "autoresearch.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "COMPLETED"
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

    assert result["status"] == "BLOCKED"
    assert evaluated is False
    queued = json.loads(
        (tmp_path / "state" / "system" / "feature-proposals.jsonl")
        .read_text(encoding="utf-8")
    )
    assert queued["status"] == "PENDING_VERIFICATION"
