from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain
from orchestration.evaluation_runner import run_local_evaluation
from runtime.evaluation_executor import QueuedEvaluationExecutor
from strategy_ir.schema import StrategyIR


class EvaluationService:
    """Application entry point for the existing deterministic local evaluator."""

    def __init__(self, *, project_root: Path, state_dir: Path) -> None:
        self.project_root = project_root.resolve()
        self.state_dir = state_dir.resolve()
        self.executor = QueuedEvaluationExecutor(self.state_dir)

    def run(
        self,
        *,
        source_path: object,
        data_path: object,
        method: str = "grid",
        count: int = 1,
        seed: int = 0,
        min_trades: int = 10,
        parameter_domains: Sequence[ParameterDomain] = (),
        operations: Sequence[MutationOperation] = (),
        strategy_override: StrategyIR | None = None,
        generation: int | None = None,
        series_data_path: object | None = None,
        min_qqq_cagr_delta: float | None = None,
        min_annual_trades: int | None = 30,
        research_run_id: str | None = None,
        attempt_id: str | None = None,
    ) -> dict[str, object]:
        return self.executor.run(
            run_local_evaluation,
            project_root=self.project_root,
            state_dir=self.state_dir,
            source_path=source_path,
            data_path=data_path,
            method=method,
            count=count,
            seed=seed,
            min_trades=min_trades,
            parameter_domains=parameter_domains,
            operations=operations,
            strategy_override=strategy_override,
            generation=generation,
            series_data_path=series_data_path,
            min_qqq_cagr_delta=min_qqq_cagr_delta,
            min_annual_trades=min_annual_trades,
            research_run_id=research_run_id,
            attempt_id=attempt_id,
        )
