from __future__ import annotations

from dataclasses import dataclass

from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash


@dataclass(frozen=True)
class BacktestRequest:
    run_id: str
    strategy_hash: str
    dataset: MarketDataSet
    initial_cash: float


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    strategy_hash: str
    data_hash: str
    equity_curve: tuple[float, ...]
    equity_curve_hash: str
    exit_status: str


class BacktestEngine:
    def run(self, request: BacktestRequest) -> BacktestResult:
        if not request.run_id or request.initial_cash <= 0:
            raise ValueError("run_id and positive initial cash are required")
        equity = [request.initial_cash]
        for previous, current in zip(request.dataset.bars, request.dataset.bars[1:], strict=True):
            equity.append(equity[-1] * (current.close / previous.close))
        curve = tuple(equity)
        return BacktestResult(
            request.run_id,
            request.strategy_hash,
            request.dataset.dataset_hash,
            curve,
            content_hash(curve),
            "SUCCEEDED",
        )
