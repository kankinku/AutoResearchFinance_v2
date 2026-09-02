from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dashboard.contracts import (
    AccountSnapshot,
    DashboardSnapshot,
    Holding,
    LLMStatus,
    ModeStatus,
    ResearchSummary,
    StrategySummary,
    TestRecord,
    TrendPoint,
    WorkerStatus,
)


class DashboardStateReader:
    def __init__(self, root: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.root = root
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def read(self) -> DashboardSnapshot:
        warnings: list[str] = []
        mode = self._read_mode(warnings)
        account = self._read_account(warnings)
        tests = self._read_tests(warnings)
        champion = self._json("champion.json", warnings, "CHAMPION_STATE_INVALID") or {}
        knowledge = self._json("knowledge.json", warnings, "KNOWLEDGE_STATE_INVALID") or {}
        frontier = self._json("frontier.json", warnings, "FRONTIER_STATE_INVALID") or {}
        rescue = self._json("rescue_pool.json", warnings, "RESCUE_POOL_STATE_INVALID") or {}
        strategy = self._read_strategy(champion, knowledge)
        research = self._read_research(frontier, knowledge, rescue)
        workers = self._read_workers(warnings)
        llm = self._read_llm(warnings)
        trend = [
            TrendPoint(
                generation=record.generation,
                timestamp=record.timestamp,
                score=strategy.score if record.strategy_hash == strategy.champion_hash else None,
                total_return=record.total_return,
                nasdaq_excess_return=record.nasdaq_excess_return,
                risk_compliant=record.risk_compliant,
            )
            for record in reversed(tests)
        ]
        return DashboardSnapshot(
            generated_at=self._clock().isoformat(),
            mode=mode,
            account=account,
            tests=tests,
            strategy=strategy,
            trend=trend,
            workers=workers,
            llm=llm,
            research=research,
            warning_codes=sorted(set(warnings)),
        )

    def _read_mode(self, warnings: list[str]) -> ModeStatus:
        payload = self._json("mode.json", warnings, "MODE_STATE_INVALID") or {}
        requested = str(payload.get("selected_mode", "paper"))
        if requested.lower() != "paper":
            warnings.append("LIVE_MODE_REJECTED")
        return ModeStatus(requested_mode=requested, effective_mode="paper", live_enabled=False)

    def _read_account(self, warnings: list[str]) -> AccountSnapshot:
        payload = self._json("account.json", warnings, "ACCOUNT_SNAPSHOT_INVALID")
        if payload is None:
            return AccountSnapshot()
        try:
            holdings = [Holding.model_validate(item) for item in payload.get("holdings", [])]
            return AccountSnapshot(
                status=payload.get("status", "UNKNOWN"),
                account_number=_mask_account(str(payload.get("account_number", ""))),
                equity=_optional_float(payload.get("equity")),
                cash=_optional_float(payload.get("cash")),
                buying_power=_optional_float(payload.get("buying_power")),
                holdings=holdings,
                open_orders=int(payload.get("open_orders", 0)),
                captured_at=payload.get("captured_at"),
                error_code=payload.get("error_code"),
            )
        except (TypeError, ValueError) as exc:
            del exc
            warnings.append("ACCOUNT_SNAPSHOT_INVALID")
            return AccountSnapshot(status="ERROR", error_code="invalid_snapshot")

    def _read_tests(self, warnings: list[str]) -> list[TestRecord]:
        path = self.root / "test-records.jsonl"
        if not path.is_file():
            return []
        records: list[TestRecord] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(TestRecord.model_validate(json.loads(line)))
            except (TypeError, ValueError, json.JSONDecodeError):
                warnings.append(f"TEST_RECORD_INVALID_{line_number}")
        return sorted(records, key=lambda record: record.timestamp, reverse=True)

    @staticmethod
    def _read_strategy(champion: dict[str, Any], knowledge: dict[str, Any]) -> StrategySummary:
        if isinstance(champion.get("champion"), Mapping):
            champion = {**champion, **champion["champion"]}
        candidate = next(
            (
                item
                for item in knowledge.get("known_good", [])
                if isinstance(item, Mapping)
                and item.get("candidate_hash") == champion.get("champion_hash")
            ),
            {},
        )
        raw_features = champion.get("feature_ids")
        if raw_features is None:
            raw_features = candidate.get("feature_ids", [])
        feature_ids = (
            [str(item) for item in raw_features]
            if isinstance(raw_features, (list, tuple))
            else []
        )
        return StrategySummary(
            champion_hash=champion.get("champion_hash"),
            status=str(champion.get("status", "EMPTY")),
            family=champion.get("family") or candidate.get("family"),
            score=_optional_float(champion.get("score", candidate.get("score"))),
            generation=_optional_int(champion.get("generation", candidate.get("generation"))),
            feature_ids=feature_ids,
            total_return=_optional_float(candidate.get("total_return")),
            nasdaq_excess_return=_optional_float(candidate.get("nasdaq_excess_return")),
            max_daily_loss_pct=_optional_float(candidate.get("max_daily_loss_pct")),
            risk_compliant=_optional_bool(candidate.get("risk_compliant")),
        )

    @staticmethod
    def _read_research(
        frontier: dict[str, Any], knowledge: dict[str, Any], rescue: dict[str, Any]
    ) -> ResearchSummary:
        raw_families = frontier.get("families", {})
        families: dict[str, int] = {}
        if isinstance(raw_families, Mapping):
            for family, entries in raw_families.items():
                if isinstance(entries, list):
                    families[str(family)] = sum(isinstance(entry, Mapping) for entry in entries)
        def list_count(name: str) -> int:
            value = knowledge.get(name, [])
            return len(value) if isinstance(value, list) else 0

        rescue_entries = rescue.get("entries", [])
        return ResearchSummary(
            frontier_count=sum(families.values()),
            family_count=len(families),
            frontier_families=families,
            known_good_count=list_count("known_good"),
            known_bad_count=list_count("known_bad"),
            unexplored_count=list_count("unexplored"),
            interactions_count=list_count("interactions"),
            rescue_count=len(rescue_entries) if isinstance(rescue_entries, list) else 0,
        )

    def _read_workers(self, warnings: list[str]) -> list[WorkerStatus]:
        directory = self.root / "worker-heartbeats"
        if not directory.is_dir():
            return []
        now = self._clock().astimezone(timezone.utc)
        workers: list[WorkerStatus] = []
        for path in sorted(directory.glob("*.json")):
            payload = self._json_path(path, warnings, "WORKER_HEARTBEAT_INVALID")
            if payload is None:
                continue
            last = _parse_datetime(payload.get("last_heartbeat"))
            age = max(0.0, (now - last).total_seconds()) if last else None
            terminal = str(payload.get("status", "")).upper() in {
                "SUCCEEDED",
                "FAILED",
                "CANCELLED",
                "RETRY_EXHAUSTED",
            }
            if age is None:
                online: Literal["ONLINE", "STALE", "OFFLINE", "UNKNOWN"] = "UNKNOWN"
            elif terminal:
                online = "OFFLINE"
            elif age <= 60:
                online = "ONLINE"
            elif age <= 300:
                online = "STALE"
            else:
                online = "OFFLINE"
            workers.append(
                WorkerStatus(
                    worker_id=str(payload.get("worker_id", path.stem)),
                    job_id=payload.get("job_id"),
                    role=str(payload.get("role", "unknown")),
                    status=str(payload.get("status", "UNKNOWN")),
                    last_heartbeat=payload.get("last_heartbeat"),
                    age_seconds=age,
                    online_state=online,
                    attempt=_optional_int(payload.get("attempt")) or 0,
                    error=payload.get("error"),
                )
            )
        return workers

    def _read_llm(self, warnings: list[str]) -> LLMStatus:
        payload = self._json("llm/status.json", warnings, "LLM_STATUS_INVALID")
        if payload is None:
            return LLMStatus()
        try:
            return LLMStatus(
                provider=str(payload.get("provider", "codex_desktop")),
                status=str(payload.get("status", "UNKNOWN")),
                last_result=str(payload.get("last_result", "UNKNOWN")),
                last_call_at=payload.get("last_call_at"),
            )
        except (TypeError, ValueError) as exc:
            del exc
            warnings.append("LLM_STATUS_INVALID")
            return LLMStatus()

    def _json(self, name: str, warnings: list[str], warning: str) -> dict[str, Any] | None:
        return self._json_path(self.root / name, warnings, warning)

    @staticmethod
    def _json_path(path: Path, warnings: list[str], warning: str) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            warnings.append(warning)
            return None
        if not isinstance(payload, dict):
            warnings.append(warning)
            return None
        return payload


class SnapshotStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, snapshot: DashboardSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                snapshot.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def read(self) -> DashboardSnapshot | None:
        if not self.path.is_file():
            return None
        return DashboardSnapshot.model_validate(json.loads(self.path.read_text(encoding="utf-8")))


def _optional_float(value: object) -> float | None:
    try:
        return float(str(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    try:
        return int(str(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _mask_account(value: str) -> str:
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) < 10:
        return "******"
    return f"******{digits[-4:-2]}-{digits[-2:]}"
