from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi.testclient import TestClient

from finance_autoresearch.backtest.data_loader import FIXED_MARKET_PACK_KEYS, MarketPack
from finance_autoresearch.integrations.cli import dispatch_command
from finance_autoresearch.integrations.dashboard_api import create_dashboard_api
from finance_autoresearch.integrations.telegram_report import TelegramReportAdapter
from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from finance_autoresearch.supervisor.service import SupervisorService
from finance_autoresearch.workers.autoresearch_runner import AutoresearchRunner
from finance_autoresearch.workers.pipeline_runner import PipelineRunner


MUTABLE_TARGET_PATH = Path(
    "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"
)


@dataclass(slots=True)
class FakeOpenClawClient:
    artifact: dict[str, Any]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def mutate(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        return dict(self.artifact)


@dataclass(slots=True)
class FakeHarness:
    results: list[dict[str, Any]]

    def __call__(self, strategy_path: Path) -> dict[str, Any]:
        if not self.results:
            raise AssertionError("unexpected harness call")
        return dict(self.results.pop(0))


@dataclass(slots=True)
class FakeEvaluator:
    results: list[dict[str, Any]]

    def __call__(self, raw_result: dict[str, Any]) -> dict[str, Any]:
        if not self.results:
            raise AssertionError("unexpected evaluator call")
        return dict(self.results.pop(0))


@dataclass(slots=True)
class FakeAnalyzer:
    output: dict[str, Any]

    def __call__(self, **_: Any) -> dict[str, Any]:
        return dict(self.output)


@dataclass(slots=True)
class FakeBot:
    messages: list[tuple[str, str]] = field(default_factory=list)

    async def send_message(self, *, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


def test_pipeline_then_autoresearch_smoke_flow(repository_root: Path) -> None:
    store = SQLiteStateStore(
        db_path=repository_root / "runtime" / "state.db",
        project_id="finance",
    )
    try:
        knowledge_dir = repository_root / "knowledge" / "indicators"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        (knowledge_dir / "rsi.md").write_text(
            "# RSI Notes\nRSI can be relaxed to recover trade count while preserving exits.",
            encoding="utf-8",
        )
        write_strategy_candidate(repository_root, "baseline")
        pipeline = PipelineRunner(
            state_store=store,
            cache_root=repository_root,
            market_pack_builder=lambda: build_market_pack_fixture(),
            openclaw_check=lambda: None,
            telegram_control_check=lambda: None,
            telegram_report_check=lambda: None,
            dashboard_check=lambda: None,
            baseline_strategy_path=repository_root / MUTABLE_TARGET_PATH,
            baseline_snapshot_path=repository_root
            / "runtime"
            / "baseline"
            / "accepted_strategy_candidate.py",
        )

        pipeline_result = pipeline.run()

        runner = AutoresearchRunner(
            state_store=store,
            repository_root=repository_root,
            openclaw_client=FakeOpenClawClient(
                artifact=make_mutation_artifact("candidate")
            ),
            harness=FakeHarness(
                results=[
                    {"phase": "baseline"},
                    {"phase": "baseline_seed_validation"},
                    {"phase": "candidate"},
                ]
            ),
            evaluator=FakeEvaluator(
                results=[
                    evaluation_result(0.40, guardrails_passed=True, tag="baseline"),
                    evaluation_result(
                        0.40,
                        guardrails_passed=True,
                        tag="baseline_seed_validation",
                    ),
                    evaluation_result(0.47, guardrails_passed=True, tag="candidate"),
                ]
            ),
            analyzer=FakeAnalyzer(output=analysis_result("candidate improved")),
            mutable_strategy_path=repository_root / MUTABLE_TARGET_PATH,
            baseline_snapshot_path=repository_root
            / "runtime"
            / "baseline"
            / "accepted_strategy_candidate.py",
        )
        supervisor = SupervisorService(
            state_store=store,
            seed_validator=runner.build_seed_validator(),
            run_id_factory=lambda: "run-001",
        )

        start_response = dispatch_command(
            supervisor=supervisor,
            command="start_autoresearch",
            source="cli",
            requested_by="cli-user",
            project_id="finance",
        )
        run_result = runner.run(run_id="run-001", max_iterations=1)

        report_bot = FakeBot()
        delivered = asyncio.run(
            TelegramReportAdapter(
                store=store,
                bot=report_bot,
                chat_id="reports",
            ).drain_pending()
        )
        dashboard = TestClient(create_dashboard_api(store=store, supervisor=supervisor))
        status_response = dashboard.get("/status")

        latest_experiment = store.get_latest_experiment()
        latest_analysis = store.get_latest_analysis()
        latest_plan = store.get_latest_research_plan()
        latest_lesson = store.get_latest_lesson()
        latest_knowledge = store.list_knowledge(limit=10)
        final_state = store.get_status()
    finally:
        store.close()

    assert pipeline_result.succeeded is True
    assert start_response["accepted"] is True
    assert start_response["run_id"] == "run-001"
    assert run_result["decision"] == "keep"
    assert latest_experiment is not None
    assert latest_experiment.decision == "keep"
    assert latest_analysis is not None
    assert latest_analysis.summary == "candidate improved"
    assert latest_plan is not None
    assert latest_plan.summary
    assert latest_lesson is not None
    assert latest_lesson.summary
    assert latest_knowledge
    assert any(
        record.source_path == "knowledge/indicators/rsi.md"
        for record in latest_knowledge
    )
    assert delivered
    assert report_bot.messages
    assert status_response.status_code == 200
    assert status_response.json()["project_state"] == "idle"
    assert status_response.json()["autoresearch_state"] == "success"
    assert final_state.pending_command is None


def build_market_pack_fixture() -> MarketPack:
    market_pack: MarketPack = {}
    for symbol, timeframe in FIXED_MARKET_PACK_KEYS:
        if timeframe == "1d":
            timestamps = pd.date_range(
                start="2020-01-01",
                periods=1_900,
                freq="D",
                tz="UTC",
            )
        else:
            timestamps = pd.date_range(
                start="2024-01-01",
                periods=6_600,
                freq="2h",
                tz="UTC",
            )
        close = pd.Series(range(len(timestamps)), dtype=float) + 100.0
        frame = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close + 0.5,
                "volume": 1_000.0,
                "symbol": symbol,
                "timeframe": timeframe,
            }
        )
        market_pack[(symbol, timeframe)] = frame
    return market_pack


def strategy_source(tag: str) -> str:
    return "\n".join(
        [
            "import pandas as pd",
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
        ]
    )


def write_strategy_candidate(repository_root: Path, tag: str) -> Path:
    target = repository_root / MUTABLE_TARGET_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(strategy_source(tag), encoding="utf-8")
    return target


def make_mutation_artifact(tag: str) -> dict[str, Any]:
    return {
        "kind": "strategy_replacement",
        "target_path": str(MUTABLE_TARGET_PATH).replace("\\", "/"),
        "hypothesis": f"Mutate to {tag}",
        "change_summary": f"Replace with {tag}",
        "full_file_contents": strategy_source(tag),
        "expected_effects": [f"Improve with {tag}"],
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
