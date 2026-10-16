"""Read-only SQLite-backed observer of *existing* academic MCP research sessions.

Uses the canonical generation/S7 evidence and ignores tokens, model prompts,
trade-level private inputs and sealed-OOS data. Never writes a research database.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash
from dashboard.academic_benchmark import (
    inferred_qqq_market_path,
    qqq_buyhold_for_session,
)
from dashboard.academic_timing import generation_timing
from dashboard.academic_worker_status import supervised_status
from research.llm.autonomous_cycle import AcademicCycleService

_SESSION_RE = re.compile(r"^[0-9a-f]{32}$")
_PUBLIC_METRICS = (
    "total_return",
    "cagr",
    "max_drawdown",
    "sharpe",
    "sortino",
    "calmar",
    "win_rate",
    "trade_count",
    "turnover",
    "profit_factor",
    "exposure",
)
_PHASES = {
    "RUNNING": "연구 계산 중",
    "AWAITING_PLAN": "다음 모델 계획 대기",
    "AWAITING_DIAGNOSIS": "진단 입력 대기",
    "INTERRUPTED": "중단됨",
    "CANCELLED": "취소됨",
    "FAILED": "실패",
    "COMPLETED": "100% 완료",
}


class ResearchMonitorUnavailable(RuntimeError):
    """Missing SQLite files or inconsistent/invalid evidence: no guessed values."""


class ResearchSessionNotFound(LookupError):
    """No such registered session (no arbitrary SQL or path)."""


class AcademicMonitorReader:
    def __init__(
        self,
        checkpoint_dir: Path,
        *,
        qqq_reference_path: Path | None = None,
    ) -> None:
        self.directory = checkpoint_dir.resolve()
        self.qqq_reference_path = (
            qqq_reference_path
            if qqq_reference_path is not None
            else inferred_qqq_market_path(self.directory)
        )

    def _db(self, filename: str) -> sqlite3.Connection:
        path = self.directory / filename
        if not path.is_file() or path.is_symlink():
            raise ResearchMonitorUnavailable("RESEARCH_STATE_UNAVAILABLE")
        try:
            conn = sqlite3.connect(
                f"file:{path.as_posix()}?mode=ro",
                uri=True,
                timeout=2,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA busy_timeout=2000")
            return conn
        except (sqlite3.Error, OSError) as exc:
            raise ResearchMonitorUnavailable("RESEARCH_STATE_UNAVAILABLE") from exc

    @staticmethod
    def _listed(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        return [
            {
                "session_id": row["id"],
                "requested": row["requested"],
                "completed": row["completed"],
                "status": row["status"],
            }
            for row in conn.execute(
                "SELECT id, requested, completed, status FROM sessions "
                "ORDER BY rowid DESC LIMIT 100"
            )
        ]

    def sessions(self) -> list[dict[str, Any]]:
        with closing(self._db("cycles.sqlite")) as conn:
            return self._listed(conn)

    @staticmethod
    def _checkpoint_status(phase: str, status: str) -> dict[str, Any]:
        # A terminal cycle always overrides an older waiting gateway phase.
        # Otherwise a cancelled/failed run can be misleadingly shown as active.
        if status in ("INTERRUPTED", "CANCELLED", "FAILED", "COMPLETED"):
            phase = status
        if phase in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
            return {
                "code": phase,
                "label": _PHASES[phase],
                "is_actively_running": False,
                "requires_external_action": True,
            }
        effective = phase if phase in _PHASES else status
        return {
            "code": effective,
            "label": _PHASES.get(effective, "상태 확인 필요"),
            "is_actively_running": effective == "RUNNING",
            "requires_external_action": effective in ("INTERRUPTED", "FAILED"),
        }

    def snapshot(self, session_id: str | None = None) -> dict[str, Any]:
        if session_id is not None and not _SESSION_RE.fullmatch(session_id):
            raise ResearchSessionNotFound("INVALID_SESSION_ID")
        try:
            with (
                closing(self._db("cycles.sqlite")) as cycles,
                closing(self._db("gateway.sqlite")) as gateway,
            ):
                sessions = self._listed(cycles)
                selected = session_id or (sessions[0]["session_id"] if sessions else None)
                if selected is None:
                    return {
                        "status": "NO_RESEARCH_SESSIONS",
                        "sessions": [],
                        "selected_session_id": None,
                        "observed_at_utc": _utc_now(),
                        "orders_enabled": False,
                        "point_in_time_verified": False,
                        "independent_oos_approved": False,
                    }
                session = cycles.execute(
                    "SELECT id,requested,completed,status,error_type,dataset_hash "
                    "FROM sessions WHERE id=?",
                    (selected,),
                ).fetchone()
                stage = gateway.execute(
                    "SELECT phase,plan_json FROM stages WHERE session_id=?",
                    (selected,),
                ).fetchone()
                if session is None or stage is None:
                    raise ResearchSessionNotFound("SESSION_NOT_FOUND")
                phase = stage["phase"]
                done, target = session["completed"], session["requested"]
                if (
                    not isinstance(done, int)
                    or not isinstance(target, int)
                    or not 0 <= done <= target <= 10000
                ):
                    raise ResearchMonitorUnavailable("INVALID_GENERATION_COUNTS")
                generation_rows = cycles.execute(
                    "SELECT generation,evidence_json,evidence_hash FROM generations "
                    "WHERE session_id=? ORDER BY generation",
                    (selected,),
                ).fetchall()
                if len(generation_rows) != done:
                    raise ResearchMonitorUnavailable("GENERATION_RECORD_COUNT_MISMATCH")
                s7_rows = gateway.execute(
                    "SELECT generation,report_json,report_hash FROM experiment_reports "
                    "WHERE session_id=? ORDER BY generation",
                    (selected,),
                ).fetchall()
                s7 = {r["generation"]: r for r in s7_rows}
                if len(s7) != len(s7_rows):
                    raise ResearchMonitorUnavailable("DUPLICATE_S7_GENERATION")
                history: list[dict[str, Any]] = []
                previous: str | None = None
                missing_s7 = 0
                for index, row in enumerate(generation_rows, 1):
                    if row["generation"] != index:
                        raise ResearchMonitorUnavailable("GENERATION_SEQUENCE_MISMATCH")
                    raw = json.loads(row["evidence_json"])
                    if (
                        raw.get("previous_evidence_hash") != previous
                        or raw.get("dataset_hash") != session["dataset_hash"]
                        or raw.get("broker_executable") is not False
                        or raw.get("independent_oos_approved") is not False
                        or AcademicCycleService._row_evidence_hash(
                            selected,
                            index,
                            previous,
                            raw,
                        )
                        != row["evidence_hash"]
                    ):
                        raise ResearchMonitorUnavailable("GENERATION_EVIDENCE_MISMATCH")
                    previous = row["evidence_hash"]
                    record = s7.get(index)
                    trial_status = "S7_NOT_MEASURED"
                    if record is not None:
                        result = json.loads(record["report_json"])
                        if (
                            content_hash(result) != record["report_hash"]
                            or result.get("original_generation_evidence_hash") != previous
                            or result.get("session_id") != selected
                            or result.get("generation") != index
                            or result.get("report", {}).get("broker_executable") is not False
                        ):
                            raise ResearchMonitorUnavailable("S7_EVIDENCE_MISMATCH")
                        measured = result["report"].get("experiments", [])
                        if not isinstance(measured, list) or sorted(
                            x.get("hypothesis_id") for x in measured
                        ) != sorted(raw.get("hypothesis_ids", [])):
                            raise ResearchMonitorUnavailable("S7_HYPOTHESIS_MISMATCH")
                        trial_status = "MEASURED"
                    else:
                        missing_s7 += 1
                    metrics = raw.get("metrics", {})
                    if not isinstance(metrics, dict):
                        raise ResearchMonitorUnavailable("INVALID_GENERATION_METRICS")
                    plan = raw.get("algorithm_plan", {})
                    history.append(
                        {
                            "generation": index,
                            "plan_id": str(plan.get("plan_id", ""))[:96],
                            "metrics": {k: metrics.get(k) for k in _PUBLIC_METRICS},
                            "s7_status": trial_status,
                            "evidence_hash_prefix": previous[:12],
                            "validated_profitability": False,
                        }
                    )
                if set(s7) - set(range(1, done + 1)):
                    raise ResearchMonitorUnavailable("ORPHAN_S7_RECORD")
                timing, intervals = generation_timing(
                    gateway, session_id=selected, completed=done, requested=target,
                    phase=phase, evidence_hashes=[row['evidence_hash'] for row in generation_rows],
                )
                for observed, model in zip(intervals, history, strict=True):
                    model.update(duration_seconds=observed['duration_seconds'],
                                 timing_status=observed['timing_status'])
                # The pending plan is not committed and its backtest metrics are
                # not in the two immutable SQLite tables. Never substitute the
                # most recent completed model's metrics for it.
                pending_plan_id = None
                if phase == "AWAITING_DIAGNOSIS":
                    pending_raw = json.loads(stage["plan_json"] or "{}")
                    if not isinstance(pending_raw, dict):
                        raise ResearchMonitorUnavailable("INVALID_STAGED_PLAN")
                    pending_plan_id = str(pending_raw.get("plan_id", ""))[:96]
                benchmark = qqq_buyhold_for_session(
                    self.qqq_reference_path,
                    expected_dataset_hash=session["dataset_hash"],
                )
                if benchmark["status"] == "DEVELOPMENT_ONLY":
                    for model in history:
                        total = model["metrics"].get("total_return")
                        model["qqq_excess_return_pp"] = (
                            100 * (total - benchmark["total_return"])
                            if isinstance(total, (int, float))
                            else None
                        )
                else:
                    for model in history:
                        model["qqq_excess_return_pp"] = None
                by_return = max(
                    history,
                    key=lambda r: (
                        r["metrics"].get("total_return")
                        if isinstance(r["metrics"].get("total_return"), (float, int))
                        else float("-inf")
                    ),
                    default=None,
                )
                by_sharpe = max(
                    history,
                    key=lambda r: (
                        r["metrics"].get("sharpe")
                        if isinstance(r["metrics"].get("sharpe"), (float, int))
                        else float("-inf")
                    ),
                    default=None,
                )
                return {
                    "status": "OK",
                    "selected_session_id": selected,
                    "observed_at_utc": _utc_now(),
                    "sessions": sessions,
                    "checkpoint": self._checkpoint_status(phase, session["status"]),
                    "supervisor": supervised_status(
                        self.directory,
                        selected,
                        self._checkpoint_status(phase, session["status"])["code"],
                    ),
                    "completed": done,
                    "requested": target,
                    "progress_pct": round(100 * done / target, 2) if target else 0,
                    "current_model": {
                        "plan_id": pending_plan_id or (history[-1]["plan_id"] if history else None),
                        "generation": done + 1 if pending_plan_id else (done if done else None),
                        "metrics": None
                        if pending_plan_id
                        else (history[-1]["metrics"] if history else None),
                        "evaluation_status": (
                            "STAGED_NOT_COMMITTED"
                            if pending_plan_id
                            else "LAST_COMMITTED_GENERATION"
                            if history
                            else "NO_MODEL"
                        ),
                    },
                    "latest_completed_model": history[-1] if history else None,
                    "buyhold_benchmark": benchmark,
                    "best_model_vs_qqq_pp": (
                        by_return["qqq_excess_return_pp"] if by_return else None
                    ),
                    "latest_model_vs_qqq_pp": (
                        history[-1]["qqq_excess_return_pp"] if history else None
                    ),
                    "best_by_return": by_return,
                    "best_by_sharpe": by_sharpe,
                    "missing_s7_count": missing_s7,
                    "timing": timing,
                    "history": history,
                    "data_label": "QQQ 연구 개발 데이터 — 사후 수집 NON_PIT",
                    "orders_enabled": False,
                    "point_in_time_verified": False,
                    "independent_oos_approved": False,
                    "profitability_verified": False,
                    "auto_execution_verified": False,
                    "disclosure": (
                        "계산된 수익률은 과거 개발 데이터의 백테스트 결과입니다. "
                        "PIT·독립 OOS·실거래 수익 검증이 아닙니다. "
                        "호스트에서 차단된 요청은 연구 DB에 기록되지 않을 수 있습니다."
                    ),
                }
        except ResearchSessionNotFound:
            raise
        except ResearchMonitorUnavailable:
            raise
        except (sqlite3.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchMonitorUnavailable("ACADEMIC_READ_INTEGRITY_ERROR") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
