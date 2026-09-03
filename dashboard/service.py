from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from core.features.registry import research_feature_specs
from dashboard.contracts import (
    AccountSnapshot,
    BacktestCapability,
    BacktestResearchStatus,
    BacktestSnapshot,
    BacktestSummary,
    DashboardHealth,
    DashboardSnapshot,
    GenerationSummary,
    Holding,
    TestRecord,
)
from dashboard.state import DashboardStateReader, SnapshotStore
from integrations.kis.client import KISAccountSnapshot, KISPaperClient
from research.policy import default_evaluation_thresholds
from strategy_ir.contracts import CANONICAL_TIMEFRAMES


class PaperReadOnlyClient(Protocol):
    def health(self) -> dict[str, object]: ...

    def account_snapshot(self) -> KISAccountSnapshot: ...


class DashboardService:
    def __init__(
        self,
        state_dir: Path,
        *,
        kis_client: PaperReadOnlyClient | None = None,
        clock: Callable[[], datetime] | None = None,
        initial_warning: str | None = None,
    ) -> None:
        self.state_dir = state_dir
        self._reader = DashboardStateReader(state_dir, clock=clock)
        self._store = SnapshotStore(state_dir / "dashboard.json")
        self._kis = kis_client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initial_warning = initial_warning

    @classmethod
    def from_environment(cls, state_dir: Path, env_path: Path) -> DashboardService:
        try:
            from integrations.kis.config import PaperKISConfig

            config = PaperKISConfig.from_env(env_path)
            return cls(state_dir, kis_client=KISPaperClient(config))
        except (OSError, ValueError) as exc:
            del exc
            return cls(state_dir, initial_warning="KIS_CONFIG_MISSING")

    def snapshot(self) -> DashboardSnapshot:
        stored = self._store.read()
        if stored is None:
            snapshot = self._reader.read()
        else:
            fresh = self._reader.read()
            snapshot = stored.model_copy(
                update={
                    "mode": fresh.mode,
                    "tests": fresh.tests,
                    "strategy": fresh.strategy,
                    "trend": fresh.trend,
                    "workers": fresh.workers,
                    "llm": fresh.llm,
                    "research": fresh.research,
                    "warning_codes": sorted(set((*stored.warning_codes, *fresh.warning_codes))),
                }
            )
        return self._with_health(snapshot)

    def refresh(self) -> DashboardSnapshot:
        current = self.snapshot()
        if self._kis is None:
            return self._save(self._with_warning(current, "KIS_CONFIG_MISSING"))
        try:
            kis_health = self._kis.health()
            if str(kis_health.get("mode", "paper")).lower() != "paper":
                raise ValueError("non-paper client rejected")
            account = self._kis.account_snapshot()
            updated = current.model_copy(
                update={
                    "account": AccountSnapshot(
                        status="ONLINE",
                        account_number=account.account_number,
                        equity=account.equity,
                        cash=account.cash,
                        buying_power=account.buying_power,
                        holdings=[
                            Holding(
                                symbol=item.symbol,
                                quantity=item.quantity,
                                market_value=item.market_value,
                                profit_loss=item.profit_loss,
                            )
                            for item in account.holdings
                        ],
                        captured_at=account.captured_at,
                    ),
                    "warning_codes": [
                        code
                        for code in current.warning_codes
                        if code not in {"KIS_CONFIG_MISSING", "KIS_REFRESH_FAILED"}
                    ],
                }
            )
            return self._save(self._with_health(updated, kis_status="ONLINE"))
        except Exception:
            degraded = self._with_warning(current, "KIS_REFRESH_FAILED")
            return self._save(self._with_health(degraded, kis_status="OFFLINE"))

    def feature_catalog(self) -> list[dict[str, object]]:
        """Return a credential-free projection for the dashboard catalog."""

        supported_timeframes = list(CANONICAL_TIMEFRAMES)
        return [
            {
                "canonical_name": spec.name,
                "canonical_id": spec.canonical_id,
                "aliases": list(spec.aliases),
                "family": spec.family,
                "calculator": spec.calculator,
                "source_repositories": list(spec.source_repositories),
                "source_licenses": list(spec.source_licenses),
                "verification_status": spec.status,
                "data_contract": spec.data_contract,
                "supported_timeframes": supported_timeframes,
                "duplicate_group": spec.duplicate_group,
                "output_name": spec.output_name,
            }
            for spec in research_feature_specs()
        ]

    def strategy_catalog(self) -> list[dict[str, object]]:
        """Return the persisted strategy catalog without credentials or source code."""

        candidates = [
            self.state_dir / "strategies" / "catalog.json",
            self.state_dir.parent / "strategies" / "catalog.json",
        ]
        catalog_path = next((path for path in candidates if path.is_file()), None)
        if catalog_path is None:
            return []
        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            return []
        result: list[dict[str, object]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            source = record.get("source", {})
            source = source if isinstance(source, dict) else {}
            result.append(
                {
                    "record_id": record.get("record_id"),
                    "status": record.get("status", "UNKNOWN"),
                    "origin": source.get("origin", "unknown"),
                    "source_path": source.get("source_path", ""),
                    "strategy_id": record.get("strategy_id"),
                    "strategy_hash": record.get("strategy_hash"),
                    "duplicate_kind": record.get("duplicate_kind", "NOT_APPLICABLE"),
                    "duplicate_of": record.get("duplicate_of"),
                    "reason": record.get("reason", ""),
                    "profile": record.get("profile", {}),
                }
            )
        return result

    def _research_state(self) -> dict[str, Any]:
        path = self.state_dir / "system" / "autoresearch.json"
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def backtest_snapshot(self) -> BacktestSnapshot:
        """Return the read-only backtest view backed by the existing run ledger."""

        snapshot = self.snapshot()
        runs = snapshot.tests
        success_statuses = {"SUCCEEDED", "SURVIVOR", "PASS", "VALIDATED"}
        rejected_statuses = {"REJECT", "FAILED", "FAIL"}
        research_state = self._research_state()
        generations = _generation_summaries(runs, research_state)
        best_ids = {item.best_run_id for item in generations}
        best = _best_record([run for run in runs if run.run_id in best_ids])
        risk_count = sum(run.risk_compliant is True for run in runs)
        summary = BacktestSummary(
            total_runs=len(runs),
            succeeded_runs=sum(run.status.upper() in success_statuses for run in runs),
            rejected_runs=sum(run.status.upper() in rejected_statuses for run in runs),
            risk_compliant_runs=sum(run.risk_compliant is True for run in runs),
            latest_run_at=runs[0].timestamp if runs else None,
            best_run_id=best.run_id if best else None,
            best_total_return=best.total_return if best else None,
            best_strategy_cagr=best.strategy_cagr if best else None,
            best_qqq_cagr=best.qqq_cagr if best else None,
            best_qqq_cagr_delta=best.qqq_cagr_delta if best else None,
            best_max_drawdown=best.max_drawdown if best else None,
            best_sharpe=best.sharpe if best else None,
            best_sortino=best.sortino if best else None,
            best_profit_factor=best.profit_factor if best else None,
            best_trade_count=best.trade_count if best else None,
            best_turnover=best.turnover if best else None,
            best_exposure=best.exposure if best else None,
            risk_compliance_rate=(risk_count / len(runs)) if runs else None,
            generation_count=len(generations),
            passing_generation_count=sum(
                item.status.upper() in success_statuses for item in generations
            ),
        )
        thresholds = default_evaluation_thresholds()
        capabilities = [
            BacktestCapability(
                id="validate_strategy",
                label="전략 IR 검증",
                status="CONNECTED",
                description="현재 저장소의 Strategy IR 정규화·검증 명령과 연결됩니다.",
                command="python cli.py validate-strategy --source <strategy.py>",
            ),
            BacktestCapability(
                id="run_generation",
                label="세대 백테스트",
                status="CONNECTED",
                description="검증된 전략과 Parquet 데이터를 Generation Pipeline으로 평가합니다.",
                command=(
                    "python cli.py run-generation --source <strategy.py> "
                    "--data <data.parquet> --method grid --count 1 --seed 0 "
                    f"--min-trades 10 --min-annual-trades {thresholds.min_annual_trades} "
                    f"--min-qqq-cagr {thresholds.min_qqq_cagr_delta:g}"
                ),
            ),
            BacktestCapability(
                id="run_ledger",
                label="실행 원장",
                status="CONNECTED",
                description="state/test-records.jsonl의 기록을 최신순으로 표시합니다.",
            ),
            BacktestCapability(
                id="equity_curve",
                label="성과 곡선",
                status="NOT_AVAILABLE",
                description="현재 실행 원장에는 시계열 equity curve가 저장되어 있지 않습니다.",
            ),
        ]
        return BacktestSnapshot(
            generated_at=snapshot.generated_at,
            mode=snapshot.mode,
            summary=summary,
            research=_research_status(research_state, self._clock()),
            generations=generations,
            runs=runs,
            capabilities=capabilities,
            warning_codes=snapshot.warning_codes,
        )

    def _save(self, snapshot: DashboardSnapshot) -> DashboardSnapshot:
        self._store.write(snapshot)
        return snapshot

    def _with_warning(self, snapshot: DashboardSnapshot, code: str) -> DashboardSnapshot:
        codes = sorted(set((*snapshot.warning_codes, code)))
        return snapshot.model_copy(update={"warning_codes": codes})

    def _with_health(
        self, snapshot: DashboardSnapshot, *, kis_status: str | None = None
    ) -> DashboardSnapshot:
        if self._initial_warning and self._initial_warning not in snapshot.warning_codes:
            snapshot = self._with_warning(snapshot, self._initial_warning)
        previous_kis = snapshot.health.kis_status if snapshot.health else "UNKNOWN"
        kis = kis_status or previous_kis
        if kis == "UNKNOWN" and snapshot.account.status == "ONLINE":
            kis = "ONLINE"
        online = sum(worker.online_state == "ONLINE" for worker in snapshot.workers)
        stale = sum(worker.online_state == "STALE" for worker in snapshot.workers)
        status: Literal["ONLINE", "DEGRADED", "OFFLINE"] = (
            "DEGRADED" if snapshot.warning_codes or kis in {"OFFLINE", "ERROR"} else "ONLINE"
        )
        return snapshot.model_copy(
            update={
                "health": DashboardHealth(
                    status=status,
                    checked_at=self._clock().isoformat(),
                    kis_status=kis,
                    docker_status="UNKNOWN",
                    online_workers=online,
                    stale_workers=stale,
                    warnings=list(snapshot.warning_codes),
                )
            }
        )


def _best_record(records: list[TestRecord]) -> TestRecord | None:
    if not records:
        return None
    eligible = [record for record in records if record.status.upper() != "REJECT"]
    pool = eligible or records
    return max(
        pool,
        key=lambda record: record.score if record.score is not None else float("-inf"),
    )


def _proposal_for_generation(state: dict[str, Any], generation: int) -> dict[str, object]:
    entries = state.get("generations", [])
    if not isinstance(entries, list):
        return {}
    entry = next(
        (
            item
            for item in entries
            if isinstance(item, dict) and _as_int(item.get("generation")) == generation
        ),
        None,
    )
    if not isinstance(entry, dict):
        return {}
    intent = entry.get("intent")
    result: dict[str, object] = {
        "status": entry.get("status", "UNKNOWN"),
        "intent_status": entry.get("intent_status", "UNKNOWN"),
        "intent_error": entry.get("intent_error"),
        "operations": entry.get("operations", []),
    }
    if isinstance(intent, dict):
        for key in ("mode", "parent_ids", "rationale", "feature_selections", "operations"):
            if key in intent:
                result[key] = intent[key]
    return {key: value for key, value in result.items() if value not in (None, [], {})}


def _generation_summaries(
    runs: list[TestRecord], research_state: dict[str, Any]
) -> list[GenerationSummary]:
    grouped: dict[int, list[TestRecord]] = {}
    for run in runs:
        grouped.setdefault(run.generation, []).append(run)
    summaries: list[GenerationSummary] = []
    for generation in sorted(grouped):
        best = _best_record(grouped[generation])
        if best is None:
            continue
        summaries.append(
            GenerationSummary(
                generation=generation,
                status=best.status,
                candidate_count=len(grouped[generation]),
                best_run_id=best.run_id,
                best_score=best.score,
                best_strategy_cagr=best.strategy_cagr,
                best_qqq_cagr=best.qqq_cagr,
                best_qqq_cagr_delta=best.qqq_cagr_delta,
                best_total_return=best.total_return,
                best_max_drawdown=best.max_drawdown,
                best_sharpe=best.sharpe,
                best_sortino=best.sortino,
                best_profit_factor=best.profit_factor,
                best_trade_count=best.trade_count,
                best_risk_compliant=best.risk_compliant,
                proposal=_proposal_for_generation(research_state, generation),
            )
        )
    return summaries


def _research_status(state: dict[str, Any], now: datetime) -> BacktestResearchStatus:
    requested = _as_int(state.get("requested_generations"), 0) or 0
    completed = _as_int(state.get("completed_generations"), 0) or 0
    current = _as_int(state.get("current_generation"))
    phase_started = state.get("phase_started_at")
    elapsed: float | None = None
    if isinstance(phase_started, str):
        try:
            started = datetime.fromisoformat(phase_started)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            reference = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
            elapsed = max(
                0.0,
                (
                    reference.astimezone(timezone.utc) - started.astimezone(timezone.utc)
                ).total_seconds(),
            )
        except ValueError:
            elapsed = None
    if elapsed is None:
        elapsed = _as_float(state.get("phase_elapsed_seconds"))
    if current is None and str(state.get("status", "")).upper() == "RUNNING":
        current = completed + 1
    return BacktestResearchStatus(
        status=str(state.get("status", "UNKNOWN")),
        requested_generations=requested,
        completed_generations=completed,
        current_generation=current,
        current_phase=str(state.get("current_phase", "UNKNOWN")),
        phase_started_at=phase_started if isinstance(phase_started, str) else None,
        phase_elapsed_seconds=elapsed,
        last_completed_generation=completed or None,
    )


def _as_int(value: object, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _as_float(value: object, default: float | None = None) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default
