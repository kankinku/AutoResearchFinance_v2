from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DashboardModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModeStatus(DashboardModel):
    requested_mode: str = "paper"
    effective_mode: Literal["paper"] = "paper"
    live_enabled: Literal[False] = False
    safety_status: Literal["PAPER_ONLY"] = "PAPER_ONLY"


class Holding(DashboardModel):
    symbol: str
    quantity: float
    market_value: float
    profit_loss: float


class AccountSnapshot(DashboardModel):
    status: Literal["UNKNOWN", "ONLINE", "STALE", "ERROR"] = "UNKNOWN"
    account_number: str = "******"
    equity: float | None = None
    cash: float | None = None
    buying_power: float | None = None
    holdings: list[Holding] = Field(default_factory=list)
    open_orders: int = 0
    captured_at: str | None = None
    error_code: str | None = None


class TestRecord(DashboardModel):
    run_id: str
    strategy_hash: str
    generation: int = 0
    timestamp: str
    score: float | None = None
    total_return: float | None = None
    nasdaq_excess_return: float | None = None
    qqq_excess_return: float | None = None
    qqq_cagr_delta: float | None = None
    max_drawdown: float | None = None
    risk_compliant: bool | None = None
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)
    dataset_hash: str | None = None
    benchmark_dataset_hash: str | None = None
    strategy_cagr: float | None = None
    qqq_cagr: float | None = None
    nasdaq_cagr: float | None = None
    trade_count: int | None = None
    sharpe: float | None = None
    sortino: float | None = None
    profit_factor: float | None = None
    turnover: float | None = None
    exposure: float | None = None
    gates: list[dict[str, object]] = Field(default_factory=list)
    validation_folds: list[dict[str, object]] = Field(default_factory=list)
    yearly_metrics: list[dict[str, object]] = Field(default_factory=list)
    status: str


class StrategySummary(DashboardModel):
    champion_hash: str | None = None
    status: str = "EMPTY"
    family: str | None = None
    score: float | None = None
    generation: int | None = None
    feature_ids: list[str] = Field(default_factory=list)
    total_return: float | None = None
    nasdaq_excess_return: float | None = None
    max_daily_loss_pct: float | None = None
    risk_compliant: bool | None = None


class TrendPoint(DashboardModel):
    generation: int
    timestamp: str
    score: float | None = None
    total_return: float | None = None
    nasdaq_excess_return: float | None = None
    risk_compliant: bool | None = None


class WorkerStatus(DashboardModel):
    worker_id: str
    job_id: str | None = None
    role: str = "unknown"
    status: str = "UNKNOWN"
    last_heartbeat: str | None = None
    age_seconds: float | None = None
    online_state: Literal["ONLINE", "STALE", "OFFLINE", "UNKNOWN"] = "UNKNOWN"
    attempt: int = 0
    error: str | None = None


class LLMStatus(DashboardModel):
    provider: str = "codex_desktop"
    status: str = "UNKNOWN"
    last_result: str = "UNKNOWN"
    last_call_at: str | None = None


class DashboardHealth(DashboardModel):
    status: Literal["ONLINE", "DEGRADED", "OFFLINE"] = "ONLINE"
    checked_at: str
    kis_status: str = "UNKNOWN"
    docker_status: str = "UNKNOWN"
    online_workers: int = 0
    stale_workers: int = 0
    warnings: list[str] = Field(default_factory=list)


class ResearchSummary(DashboardModel):
    frontier_count: int = 0
    family_count: int = 0
    frontier_families: dict[str, int] = Field(default_factory=dict)
    known_good_count: int = 0
    known_bad_count: int = 0
    unexplored_count: int = 0
    interactions_count: int = 0
    rescue_count: int = 0


class BacktestSummary(DashboardModel):
    total_runs: int = 0
    succeeded_runs: int = 0
    rejected_runs: int = 0
    risk_compliant_runs: int = 0
    latest_run_at: str | None = None
    best_run_id: str | None = None
    best_total_return: float | None = None


class BacktestCapability(DashboardModel):
    id: str
    label: str
    status: Literal["CONNECTED", "NOT_AVAILABLE"]
    description: str
    command: str | None = None


class BacktestSnapshot(DashboardModel):
    generated_at: str
    mode: ModeStatus = Field(default_factory=ModeStatus)
    summary: BacktestSummary = Field(default_factory=BacktestSummary)
    runs: list[TestRecord] = Field(default_factory=list)
    capabilities: list[BacktestCapability] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)


class DashboardSnapshot(DashboardModel):
    schema_version: int = 1
    generated_at: str
    mode: ModeStatus = Field(default_factory=ModeStatus)
    account: AccountSnapshot = Field(default_factory=AccountSnapshot)
    tests: list[TestRecord] = Field(default_factory=list)
    strategy: StrategySummary = Field(default_factory=StrategySummary)
    trend: list[TrendPoint] = Field(default_factory=list)
    workers: list[WorkerStatus] = Field(default_factory=list)
    llm: LLMStatus = Field(default_factory=LLMStatus)
    research: ResearchSummary = Field(default_factory=ResearchSummary)
    health: DashboardHealth | None = None
    warning_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_paper_only(self) -> DashboardSnapshot:
        if self.mode.effective_mode != "paper" or self.mode.live_enabled:
            raise ValueError("dashboard snapshot must remain paper-only")
        return self
