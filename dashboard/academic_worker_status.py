"""Read-only sanitized observer of the local T4 supervised GPT process.

Heartbeat is NOT independent verification of live provider progress. A missing
supervisor directory is expected for the default chat-driven MCP setup.
Control contents (owner pid/nonce, requests, paths, secrets) are never returned.
"""

from __future__ import annotations

import json
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RE_SESSION = re.compile(r"^[0-9a-f]{32}$")
_VALID_STATES = frozenset(
    {
        "RUNNING",
        "PAUSED",
        "STOPPED",
        "COMPLETED",
        "AWAITING_PROVIDER",
        "REVIEW_REQUIRED",
    }
)
_WAITING = frozenset({"AWAITING_PLAN", "AWAITING_DIAGNOSIS"})


def _safe_read(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise ValueError("SYMLINK_CONTROL")
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 8192:
        raise ValueError("INVALID_CONTROL_FILE")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("INSECURE_CONTROL_PERMISSIONS")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise ValueError("INVALID_CONTROL_JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("INVALID_CONTROL_PAYLOAD")
    return payload


def _no_supervisor(phase: str) -> dict[str, Any]:
    if phase in _WAITING:
        return {
            "code": "PROVIDER_REQUIRED",
            "label": "외부 GPT 입력 대기",
            "detail": (
                "상주 연구 실행기가 확인되지 않았습니다. 다음 계획·진단을 GPT가 제출해야 합니다."
            ),
            "heartbeat_health": "NOT_RUNNING",
            "last_heartbeat_at_utc": None,
            "verified_worker_running": False,
            "can_proceed_without_model": False,
            "orders_enabled": False,
        }
    label = {
        "COMPLETED": "연구 세대 완료",
        "INTERRUPTED": "연구 오류 중단",
        "FAILED": "연구 실패",
        "CANCELLED": "연구 취소",
    }.get(phase, "실행 상태 확인 필요")
    return {
        "code": phase
        if phase in ("COMPLETED", "INTERRUPTED", "FAILED", "CANCELLED")
        else "NOT_RUNNING",
        "label": label,
        "detail": "연구 원장의 실제 상태를 확인하십시오.",
        "heartbeat_health": "NOT_RUNNING",
        "last_heartbeat_at_utc": None,
        "verified_worker_running": False,
        "can_proceed_without_model": False,
        "orders_enabled": False,
    }


def supervised_status(checkpoint_dir: Path, session_id: str, phase: str) -> dict[str, Any]:
    """Never mutates DB/control dir, never returns owner identity or auth tokens."""
    if not _RE_SESSION.fullmatch(session_id):
        return _no_supervisor(phase)
    directory = checkpoint_dir.resolve().parent / "academic-supervisor-control"
    if not directory.exists():
        return _no_supervisor(phase)
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("INVALID_CONTROL_DIR")
        if stat.S_IMODE(directory.stat().st_mode) & 0o077:
            raise ValueError("INSECURE_CONTROL_DIR")
        control = _safe_read(directory / (session_id + ".request.json"))
        record = _safe_read(directory / (session_id + ".status.json"))
        if control and (
            control.get("session_id") != session_id
            or control.get("desired") not in ("RUN", "PAUSE", "STOP")
        ):
            raise ValueError("INVALID_REQUEST_STATE")
        if record and (
            record.get("session_id") != session_id
            or record.get("supervisor_state") not in _VALID_STATES
            or record.get("orders_enabled") is not False
            or record.get("independent_oos_approved") is not False
        ):
            raise ValueError("INVALID_RUN_STATE")
        if not control and not record:
            return _no_supervisor(phase)
        desired = control.get("desired", "RUN") if control else "RUN"
        run_state = record.get("supervisor_state") if record else None
        last = record.get("heartbeat_at_utc") if record else None
        heartbeat_health = "NOT_RUNNING"
        if run_state == "RUNNING":
            heartbeat_health = "STALE_OR_UNVERIFIED"
            if record is not None and isinstance(last, str):
                try:
                    when = datetime.fromisoformat(last)
                    interval = float(record.get("heartbeat_interval_seconds", 2))
                    diff = (datetime.now(timezone.utc) - when).total_seconds()
                    if when.tzinfo is not None and 0 <= diff <= max(5, interval * 3):
                        heartbeat_health = "RECENT_UNVERIFIED"
                except (TypeError, ValueError, OverflowError):
                    pass
        # A terminal research DB status always takes priority over a stale
        # unrelated control status. No UI statement of confirmed live worker.
        if phase not in _WAITING and phase != "RUNNING":
            return _no_supervisor(phase)
        if desired == "STOP":
            code, label = "STOP_REQUESTED", "실행 중지 요청됨"
        elif desired == "PAUSE":
            code, label = "PAUSE_REQUESTED", "일시정지 요청됨"
        elif run_state == "PAUSED":
            code, label = "PAUSED", "실행기 일시정지됨"
        elif run_state == "STOPPED":
            code, label = "STOPPED", "실행기 중지됨"
        elif run_state == "REVIEW_REQUIRED":
            code, label = "REVIEW_REQUIRED", "오류 검토 필요"
        elif run_state == "RUNNING" and heartbeat_health == "RECENT_UNVERIFIED":
            code, label = "HEARTBEAT_UNVERIFIED", "최근 실행기 신호 감지 · 미확인"
        elif run_state == "RUNNING":
            code, label = "STALE_HEARTBEAT", "실행기 신호 끊김 · 상태 확인 필요"
        else:
            return _no_supervisor(phase)
        return {
            "code": code,
            "label": label,
            "detail": (
                "실행 상태 기록은 독립적인 프로세스 생존/모델 호출 검증이 아닙니다. "
                "재개 요청만으로 GPT가 실행되지 않습니다."
            ),
            "heartbeat_health": heartbeat_health,
            "last_heartbeat_at_utc": last if isinstance(last, str) and len(last) < 50 else None,
            "verified_worker_running": False,
            "can_proceed_without_model": False,
            "orders_enabled": False,
        }
    except (OSError, ValueError, TypeError, KeyError):
        return {
            "code": "CONTROL_STATE_UNAVAILABLE",
            "label": "실행기 상태 확인 불가",
            "detail": "상태 파일 또는 접근 권한 이상. 작업자 정상 실행을 가정하지 않습니다.",
            "heartbeat_health": "UNVERIFIED",
            "last_heartbeat_at_utc": None,
            "verified_worker_running": False,
            "can_proceed_without_model": False,
            "orders_enabled": False,
        }
