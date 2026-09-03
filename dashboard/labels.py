"""Canonical Korean labels for the legacy Streamlit dashboard surface."""

STATUS_LABELS = {
    "RUNNING": "실행 중",
    "COMPLETED": "완료",
    "COMPLETED_WITH_FALLBACKS": "fallback 포함 완료",
    "COMPLETED_WITH_ERRORS": "오류 포함 완료",
    "FAILED": "실패",
    "REPAIRED": "복구 후 평가",
    "FALLBACK": "부모 전략으로 대체 평가",
    "DEGRADED": "평가 오류",
    "ONLINE": "온라인",
    "OFFLINE": "오프라인",
    "STALE": "응답 지연",
    "VALIDATED": "검증 완료",
    "CONNECTED": "연결됨",
    "NOT_AVAILABLE": "미연결",
    "UNKNOWN": "확인 필요",
    "NONE": "호출 기록 없음",
}

TIMEFRAME_LABELS = {
    "1m": "1분봉",
    "5m": "5분봉",
    "15m": "15분봉",
    "1h": "1시간봉",
    "1d": "일봉",
    "1w": "1주봉",
    "1mo": "1개월봉",
}


def status_label(value: object) -> str:
    normalized = str(value or "UNKNOWN").upper()
    return STATUS_LABELS.get(normalized, normalized)


def timeframe_label(value: object) -> str:
    normalized = str(value or "UNKNOWN")
    return TIMEFRAME_LABELS.get(normalized, normalized)
