"""퀀트 자동 연구 모니터링 대시보드.

Information hierarchy:
  L1  Global system status (mode, orders enabled)
  L2  Critical KPIs (champion performance metrics)
  L3  Pipeline health (frontier families)
  L4  Alerts / abnormal states
  L5  Knowledge base diagnostics
  L7  Actions (sidebar)
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="퀀트 자동 연구 대시보드",
    page_icon=":material/monitoring:",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATE_DIR = Path(__file__).resolve().parent / "state"
RESEARCH_STALE_AFTER_SECONDS = 10 * 60


# ---------------------------------------------------------------------------
# Data loading — thin wrappers with TTL caching
# ---------------------------------------------------------------------------


@st.cache_data(ttl=5, show_spinner=False)
def load_state(filename: str) -> dict[str, object] | None:
    """Load a JSON state file; returns None if missing or corrupt."""
    filepath = STATE_DIR / filename
    if not filepath.exists():
        return None
    try:
        result = json.loads(filepath.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else None
    except Exception:
        return None


@st.cache_data(ttl=5, show_spinner=False)
def last_modified(filename: str) -> str:
    """Return a human-readable last-modified timestamp for a state file."""
    filepath = STATE_DIR / filename
    if not filepath.exists():
        return "확인 불가"
    mtime = filepath.stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


@st.cache_data(ttl=5, show_spinner=False)
def load_jsonl(filename: str) -> list[dict[str, object]]:
    """백테스트 원장을 읽어 화면용 세대별 자료로 제공한다."""

    filepath = STATE_DIR / filename
    if not filepath.is_file():
        return []
    rows: list[dict[str, object]] = []
    try:
        for line in filepath.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return rows
    return rows


def _fmt_pct(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "없음"
    return f"{value * 100:.{decimals}f}%"


def _fmt_float(value: float | None, decimals: int = 3) -> str:
    if value is None:
        return "없음"
    return f"{value:.{decimals}f}"


# ---------------------------------------------------------------------------
# Load all state upfront (fast — reading small JSON files)
# ---------------------------------------------------------------------------
mode_state = load_state("mode.json")
champion_state = load_state("champion.json")
frontier_state = load_state("frontier.json")
knowledge_state = load_state("knowledge.json")
rescue_pool_state = load_state("rescue_pool.json")

current_mode: str = (
    str(mode_state.get("selected_mode", "unknown")) if mode_state else "unknown"
)
orders_enabled: bool = (
    bool(mode_state.get("orders_enabled", False)) if mode_state else False
)
champion_status: str = (
    str(champion_state.get("status", "EMPTY")) if champion_state else "EMPTY"
)
champion_data: dict[str, object] | None = (
    champion_state.get("champion")  # type: ignore[assignment]
    if champion_state
    else None
)
families: dict[str, object] = (
    champion_state.get("families", {})  # type: ignore[assignment]
    if frontier_state
    else {}
)
# Re-read families from frontier_state (champion_data assignment was wrong above)
families = (
    frontier_state.get("families", {})  # type: ignore[assignment]
    if frontier_state
    else {}
)
frontier_count: int = (
    sum(len(v) for v in families.values())  # type: ignore[arg-type]
    if families
    else 0
)
family_count: int = len(families)
known_good: list[object] = (
    list(knowledge_state.get("known_good", [])) if knowledge_state else []
)
known_bad: list[object] = (
    list(knowledge_state.get("known_bad", [])) if knowledge_state else []
)
unexplored: list[object] = (
    list(knowledge_state.get("unexplored", [])) if knowledge_state else []
)
interactions: list[object] = (
    list(knowledge_state.get("interactions", [])) if knowledge_state else []
)
total_known: int = len(known_good) + len(known_bad) + len(unexplored)
rescue_entries: list[object] = (
    list(rescue_pool_state.get("entries", [])) if rescue_pool_state else []
)


def _status_label(status: object) -> str:
    labels = {
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
        "VALIDATED": "검증 완료",
        "NONE": "호출 기록 없음",
    }
    value = str(status or "UNKNOWN").upper()
    return labels.get(value, value)


def _status_color(status: object) -> str:
    value = str(status or "UNKNOWN").upper()
    if value in {"RUNNING", "ONLINE", "VALIDATED", "COMPLETED", "REPAIRED"}:
        return "green"
    if value in {"FALLBACK", "COMPLETED_WITH_FALLBACKS", "DEGRADED"}:
        return "orange"
    if value in {"FAILED", "OFFLINE", "COMPLETED_WITH_ERRORS"}:
        return "red"
    return "gray"


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _safe_float_value(value: object, default: float | None = None) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _phase_label(phase: object) -> str:
    labels = {
        "STARTING": "시작 준비",
        "GENERATION": "세대 시작",
        "PROPOSING": "Codex 전략 제안 중",
        "REPAIRING": "Codex 복구 중",
        "BACKTESTING": "백테스트 중",
        "FINALIZING": "결과 기록 중",
        "COMPLETED": "완료",
        "FAILED": "실패",
    }
    value = str(phase or "UNKNOWN").upper()
    return labels.get(value, value)


def _event_rows(events: list[dict[str, object]]) -> list[dict[str, str]]:
    labels = {
        "run_started": "연구 시작",
        "generation_started": "세대 시작",
        "proposal_started": "전략 제안 호출 시작",
        "proposal_completed": "전략 제안 완료",
        "proposal_failed": "전략 제안 실패",
        "repair_started": "복구 호출 시작",
        "repair_completed": "복구 호출 완료",
        "repair_failed": "복구 호출 실패",
        "repair_unavailable": "복구 호출 불가",
        "evaluation_started": "백테스트 시작",
        "evaluation_completed": "백테스트 완료",
        "evaluation_failed": "백테스트 실패",
        "fallback_evaluation_started": "대체 백테스트 시작",
        "fallback_evaluation_failed": "대체 백테스트 실패",
        "generation_completed": "세대 기록 완료",
        "run_completed": "연구 완료",
        "run_failed": "연구 실패",
    }
    rows: list[dict[str, str]] = []
    for event in reversed(events[-12:]):
        detail = event.get("detail")
        detail_text = ""
        if isinstance(detail, dict):
            detail_text = ", ".join(
                f"{key}={value}" for key, value in detail.items()
            )
        error = str(event.get("error", ""))
        if error:
            detail_text = f"오류: {error}"
        rows.append(
            {
                "시각": str(event.get("timestamp", "확인 불가")),
                "세대": str(event.get("generation", "-")),
                "단계": _phase_label(event.get("phase")),
                "이벤트": labels.get(str(event.get("event")), str(event.get("event"))),
                "경과 시간": f"{_safe_float_value(event.get('duration_seconds'), 0.0):.1f}초",
                "상세": detail_text[:240],
            }
        )
    return rows


def _elapsed_since(filename: str) -> float | None:
    """Return seconds since a state file was last updated."""

    filepath = STATE_DIR / filename
    try:
        return max(0.0, time.time() - filepath.stat().st_mtime)
    except OSError:
        return None


def _elapsed_from_timestamp(value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        started = datetime.fromisoformat(value)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max(0.0, time.time() - started.timestamp())
    except ValueError:
        return None


def _format_elapsed(seconds: float | None) -> str:
    if seconds is None:
        return "확인 불가"
    total_seconds = int(seconds)
    minutes, remainder = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}시간 {minutes}분"
    if minutes:
        return f"{minutes}분 {remainder}초"
    return f"{remainder}초"


def _best_generation_record(
    records: list[dict[str, object]], generation: int
) -> dict[str, object] | None:
    """해당 세대의 통과 후보를 우선하고, 없으면 최고 점수 탈락 후보를 반환한다."""

    candidates = [
        record
        for record in records
        if _safe_int(record.get("generation"), -1) == generation
    ]
    if not candidates:
        return None
    eligible = [record for record in candidates if str(record.get("status")) != "REJECT"]
    pool = eligible or candidates
    return max(pool, key=lambda item: float(item.get("score", float("-inf"))))


def _lineage_rows(record: dict[str, object]) -> list[dict[str, object]]:
    lineage = record.get("feature_lineage")
    if not isinstance(lineage, list):
        return []
    rows: list[dict[str, object]] = []
    for item in lineage:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "인디케이터": str(item.get("feature_id", "없음")),
                "별칭": str(item.get("alias", "없음")),
                "입력 자료": ", ".join(str(value) for value in item.get("inputs", [])),
                "시간봉": str(item.get("timeframe", "없음")),
                "지연 봉": str(item.get("lag_bars", "없음")),
                "기간": str(item.get("lookback", "없음")),
                "파라미터": json.dumps(
                    item.get("parameters", {}), ensure_ascii=False, sort_keys=True
                ),
                "출처": ", ".join(str(value) for value in item.get("source_repositories", []))
                or "내장 등록",
            }
        )
    return rows


def _intent_lineage_rows(intent: object) -> list[dict[str, object]]:
    if not isinstance(intent, dict):
        return []
    selections = intent.get("feature_selections")
    if not isinstance(selections, list):
        return []
    rows: list[dict[str, object]] = []
    for item in selections:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "인디케이터": str(item.get("feature_id", "없음")),
                "별칭": str(item.get("alias", "없음")),
                "입력 자료": ", ".join(str(value) for value in item.get("inputs", []))
                or "전략 기본 자료",
                "시간봉": str(item.get("timeframe", "1d")),
                "지연 봉": str(item.get("lag_bars", 0)),
                "기간": str(item.get("lookback", "자동")),
                "파라미터": json.dumps(
                    item.get("parameters", {}), ensure_ascii=False, sort_keys=True
                ),
                "출처": "Codex 제안 · 등록 여부 검증 대상",
            }
        )
    return rows


@st.fragment(run_every="5s")
def render_live_research() -> None:
    """백그라운드 Mimir 탐색 상태를 주기적으로 다시 읽어 표시한다."""

    research_state = load_state("system/autoresearch.json") or {}
    llm_state = load_state("llm/status.json") or {}
    status = str(research_state.get("status", "UNKNOWN"))
    completed = _safe_int(research_state.get("completed_generations"))
    requested = _safe_int(research_state.get("requested_generations"))
    current_generation = _safe_int(
        research_state.get("current_generation"), completed + 1
    )
    current_phase = str(research_state.get("current_phase", "UNKNOWN"))
    repair_attempt = _safe_int(research_state.get("repair_attempt"), 0)
    repair_allowed = _safe_int(
        research_state.get("repair_attempts_allowed"), 0
    )
    progress = min(completed / requested, 1.0) if requested > 0 else 0.0
    records = research_state.get("generations", [])
    last_record = records[-1] if isinstance(records, list) and records else None
    phase_elapsed = _elapsed_from_timestamp(research_state.get("phase_started_at"))
    if phase_elapsed is None:
        phase_elapsed = _safe_float_value(research_state.get("phase_elapsed_seconds"))
    elapsed = (
        phase_elapsed
        if status == "RUNNING" and phase_elapsed is not None
        else _elapsed_since("system/autoresearch.json")
    )
    elapsed_label = "현재 단계 경과" if phase_elapsed is not None else (
        "이전 세대 이후" if completed > 0 else "첫 세대 시작 후"
    )
    elapsed_text = _format_elapsed(elapsed)
    stale = status == "RUNNING" and elapsed is not None and elapsed >= RESEARCH_STALE_AFTER_SECONDS
    elapsed_color = "orange" if stale else "green"
    elapsed_suffix = " · 장시간 대기 확인 필요" if stale else ""

    st.subheader(":material/sync: 자동 연구 진행 상황", anchor=False)
    with st.container(border=True):
        top_left, top_right = st.columns([3, 1])
        with top_left:
            st.markdown(
                f"**{_status_label(status)}** · 백그라운드 탐색과 연결됨 · "
                f":{elapsed_color}[{elapsed_label} {elapsed_text}{elapsed_suffix}]"
            )
            st.progress(progress, text=f"처리된 세대 {completed} / {requested}")
        with top_right:
            st.metric("진행률", f"{progress * 100:.1f}%")

        detail_left, detail_mid, detail_right, detail_extra = st.columns(4)
        with detail_left:
            st.metric("현재 세대", str(current_generation if status == "RUNNING" else completed))
        with detail_mid:
            st.metric("Codex 연결", _status_label(llm_state.get("status")))
        with detail_right:
            st.metric("주문", "비활성화")
        with detail_extra:
            repair_text = (
                f"{repair_attempt} / {repair_allowed}"
                if repair_allowed
                else "없음"
            )
            st.metric("복구 시도", repair_text)
        st.caption(f"현재 단계: {_phase_label(current_phase)}")
        st.badge(_status_label(status), color=_status_color(status), icon=":material/info:")

        if isinstance(last_record, dict):
            last_status = last_record.get("status", "UNKNOWN")
            last_generation = last_record.get("generation", "-")
            st.caption(
                f"최근 처리: {last_generation}세대 · {_status_label(last_status)} · "
                f"마지막 상태 확인 {last_modified('system/autoresearch.json')}"
            )
        elif status == "RUNNING":
            st.info(
                "첫 번째 세대의 전략 제안을 생성하고 있습니다. 이 화면은 자동으로 갱신됩니다.",
                icon=":material/hourglass_top:",
            )
        else:
            st.caption(f"마지막 상태 확인: {last_modified('system/autoresearch.json')}")

        events = load_jsonl("system/research-events.jsonl")
        if events:
            with st.expander("상세 실행 로그", expanded=False, icon=":material/list:"):
                st.dataframe(pd.DataFrame(_event_rows(events)), hide_index=True)


render_live_research()


with st.expander("사용 설명서", expanded=False, icon=":material/help:"):
    st.markdown(
        "**자동 연구 시작**  \n"
        "저장된 QQQ 전략·데이터 설정으로 원하는 세대 수만큼 백테스트합니다."
    )
    st.code("Mimir /research 200 --intent-repairs 3", language="powershell")
    st.markdown(
        "- `실행 중`: Codex 제안 또는 백테스트가 진행 중입니다.\n"
        "- `복구 후 평가`: 잘못된 제안을 독립 읽기 전용 Codex가 수정했습니다.\n"
        "- `부모 전략으로 대체 평가`: 복구에 실패해도 다음 세대로 계속 진행합니다.\n"
        "- `오류 포함 완료`: 일부 세대의 평가가 실패했지만 전체 세대 처리는 끝났습니다."
    )
    st.caption(
        "이 대시보드는 상태 파일을 읽기만 합니다. 주문을 실행하지 않으며, "
        "명령은 저장소 루트 터미널에서 직접 실행하세요."
    )


def _safe_float(value: object, default: float | None = None) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _performance_rows(records: list[dict[str, object]]) -> list[dict[str, object]]:
    generations = sorted(
        {
            _safe_int(record.get("generation"), -1)
            for record in records
            if _safe_int(record.get("generation"), -1) >= 0
        }
    )
    rows: list[dict[str, object]] = []
    for generation in generations:
        record = _best_generation_record(records, generation)
        if record is None:
            continue
        strategy_cagr = _safe_float(record.get("strategy_cagr"))
        qqq_cagr = _safe_float(record.get("qqq_cagr"))
        if strategy_cagr is None or qqq_cagr is None:
            continue
        rows.append(
            {
                "세대": generation,
                "전략 연복리": strategy_cagr,
                "QQQ 연복리": qqq_cagr,
            }
        )
    return rows


def _fold_rows(record: dict[str, object]) -> list[dict[str, object]]:
    folds = record.get("validation_folds")
    if not isinstance(folds, list):
        return []
    rows: list[dict[str, object]] = []
    for fold in folds:
        if not isinstance(fold, dict):
            continue
        rows.append(
            {
                "검증 구간": str(fold.get("fold", "없음")),
                "학습 범위": f"{fold.get('train_start', '?')} ~ {fold.get('train_end', '?')}",
                "검증 범위": f"{fold.get('test_start', '?')} ~ {fold.get('test_end', '?')}",
                "전략 연복리": _fmt_pct(_safe_float(fold.get("strategy_cagr"))),
                "QQQ 연복리": _fmt_pct(_safe_float(fold.get("qqq_cagr"))),
                "거래 횟수": str(fold.get("trade_count", "없음")),
                "통과": "통과" if fold.get("passed") else "미통과",
            }
        )
    return rows


@st.fragment(run_every="5s")
def render_generation_analysis() -> None:
    """현재·이전 세대의 최고 후보 구성과 성능 추이를 표시한다."""

    research_state = load_state("system/autoresearch.json") or {}
    test_records = load_jsonl("test-records.jsonl")
    research_records = research_state.get("generations", [])
    if not isinstance(research_records, list):
        research_records = []
    completed = _safe_int(research_state.get("completed_generations"))
    generations = sorted(
        {
            _safe_int(record.get("generation"), -1)
            for record in test_records
            if _safe_int(record.get("generation"), -1) > 0
        }
        | {
            _safe_int(record.get("generation"), -1)
            for record in research_records
            if isinstance(record, dict)
            and _safe_int(record.get("generation"), -1) > 0
        },
        reverse=True,
    )

    st.subheader(":material/insights: 세대별 최고 전략 분석", anchor=False)
    if not generations:
        st.info(
            "백테스트 원장이 아직 없습니다. 첫 세대 평가가 끝나면 인디케이터와 성능이 표시됩니다.",
            icon=":material/hourglass_top:",
        )
        return

    option_labels = [
        "현재 세대" if generation == completed else f"{generation}세대"
        for generation in generations
    ]
    selected_label = st.selectbox("분석할 세대", option_labels, key="generation_detail_select")
    selected_index = option_labels.index(selected_label)
    selected_generation = generations[selected_index]
    best = _best_generation_record(test_records, selected_generation)
    intent_record = next(
        (
            item
            for item in research_records
            if isinstance(item, dict)
            and _safe_int(item.get("generation"), -1) == selected_generation
        ),
        {},
    )

    if best is None and not intent_record:
        st.warning("선택한 세대의 후보 기록을 아직 찾지 못했습니다.")
        return

    strategy_cagr = _safe_float(best.get("strategy_cagr")) if best else None
    qqq_cagr = _safe_float(best.get("qqq_cagr")) if best else None
    qqq_delta = _safe_float(best.get("qqq_cagr_delta")) if best else None
    score = _safe_float(best.get("score")) if best else None
    status = (
        str(best.get("status", "UNKNOWN"))
        if best
        else str(intent_record.get("intent_status", "PENDING"))
    )
    with st.container(border=True):
        result_label = "최고 후보" if best else "제안된 후보 · 백테스트 결과 대기"
        strategy_hash = best.get("strategy_hash", "평가 전") if best else "평가 전"
        st.markdown(
            f"**{selected_label} {result_label}** · {_status_label(status)} · "
            f"전략 해시 `{strategy_hash}`"
        )
        metric_left, metric_mid, metric_right, metric_last = st.columns(4)
        with metric_left:
            st.metric("전략 연복리", _fmt_pct(strategy_cagr))
        with metric_mid:
            st.metric("QQQ 연복리", _fmt_pct(qqq_cagr))
        with metric_right:
            st.metric("QQQ 대비", _fmt_pct(qqq_delta), delta_color="normal")
        with metric_last:
            st.metric("최고 점수", _fmt_float(score))

        lineage = (_lineage_rows(best) if best else []) or _intent_lineage_rows(
            intent_record.get("intent") if isinstance(intent_record, dict) else None
        )
        st.markdown("**인디케이터와 입력 자료**")
        if lineage:
            st.dataframe(
                pd.DataFrame(lineage),
                hide_index=True,
                column_config={
                    "인디케이터": st.column_config.TextColumn(pinned=True),
                    "입력 자료": st.column_config.TextColumn(width="medium"),
                    "파라미터": st.column_config.TextColumn(width="medium"),
                    "출처": st.column_config.TextColumn(width="medium"),
                },
            )
        else:
            st.caption("이 후보에 연결된 인디케이터 상세가 기록되지 않았습니다.")

        if isinstance(intent_record, dict) and isinstance(intent_record.get("intent"), dict):
            intent = intent_record["intent"]
            if isinstance(intent, dict):
                operation_rows = intent.get("operations", [])
                with st.expander(
                    "제안 변경 내용",
                    expanded=False,
                    icon=":material/tune:",
                ):
                    st.caption(
                        "해당 세대에 제안된 Strategy IR 변경입니다. "
                        "실제 적용 여부는 아래 후보 상태와 백테스트 결과로 확인합니다."
                    )
                    st.json(
                        {
                            "탐색 모드": intent.get("mode", "없음"),
                            "부모 전략": intent.get("parent_ids", []),
                            "변경 작업": operation_rows,
                        },
                        expanded=False,
                    )

        data_left, data_right = st.columns(2)
        with data_left:
            st.table(
                {
                    "전략 데이터 해시": str(best.get("dataset_hash", "평가 전"))
                    if best
                    else "평가 전",
                    "벤치마크 데이터 해시": str(
                        best.get("benchmark_dataset_hash", "평가 전")
                    )
                    if best
                    else "평가 전",
                    "전체 거래 횟수": str(best.get("trade_count", "평가 전"))
                    if best
                    else "평가 전",
                    "위험 준수": (
                        "통과" if best.get("risk_compliant") else "미통과"
                    )
                    if best
                    else "평가 전",
                }
            )
        with data_right:
            st.table(
                {
                    "전략 누적 수익률": (
                        _fmt_pct(_safe_float(best.get("total_return")))
                        if best
                        else "평가 전"
                    ),
                    "최대 낙폭": (
                        _fmt_pct(_safe_float(best.get("max_drawdown")))
                        if best
                        else "평가 전"
                    ),
                    "샤프 지수": (
                        _fmt_float(_safe_float(best.get("sharpe")))
                        if best
                        else "평가 전"
                    ),
                    "수익 요인": (
                        _fmt_float(_safe_float(best.get("profit_factor")))
                        if best
                        else "평가 전"
                    ),
                }
            )

        fold_rows = _fold_rows(best) if best else []
        if fold_rows:
            with st.expander("검증 구간별 결과", expanded=False, icon=":material/fact_check:"):
                st.dataframe(pd.DataFrame(fold_rows), hide_index=True)

        intent = intent_record.get("intent") if isinstance(intent_record, dict) else None
        if isinstance(intent, dict) and intent.get("rationale"):
            st.caption(f"Codex 제안 이유: {intent['rationale']}")

    performance_rows = _performance_rows(test_records)
    if performance_rows:
        st.markdown("**성능 향상 추이**")
        performance_df = pd.DataFrame(performance_rows)
        chart = (
            alt.Chart(performance_df)
            .transform_fold(
                ["전략 연복리", "QQQ 연복리"],
                as_=["비교 대상", "연복리 수익률"],
            )
            .mark_line(point=True)
            .encode(
                x=alt.X("세대:Q", title="세대"),
                y=alt.Y("연복리 수익률:Q", title="연복리 수익률", axis=alt.Axis(format="%")),
                color=alt.Color("비교 대상:N", title="비교 대상"),
                tooltip=[
                    alt.Tooltip("세대:Q", title="세대"),
                    alt.Tooltip("비교 대상:N", title="비교 대상"),
                    alt.Tooltip("연복리 수익률:Q", title="연복리", format=".2%"),
                ],
            )
            .properties(height=280)
        )
        with st.container(border=True):
            st.altair_chart(chart)
            st.caption(
                "각 세대의 통과 후보를 우선합니다. 없으면 최고 점수 후보를 표시합니다."
            )


render_generation_analysis()



# ---------------------------------------------------------------------------
# Sidebar — global controls (actions)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title(":material/monitoring: 퀀트 자동 연구", anchor=False)
    st.caption("백그라운드 연구 상태를 실시간으로 확인합니다.")

    st.divider()

    # Mode badge — global context
    if current_mode == "live" and orders_enabled:
        st.badge("실전투자 · 주문 허용", color="red", icon=":material/bolt:")
    elif current_mode == "live":
        st.badge("실전투자 · 주문 차단", color="orange", icon=":material/bolt:")
    else:
        st.badge("모의투자 · 주문 차단", color="blue", icon=":material/description:")

    st.divider()
    st.subheader(":material/tune: 운영 모드", anchor=False)

    if st.button(
        ":material/description: 모의투자 모드 적용",
        help="CLI: python cli.py set-mode --mode paper",
    ):
        st.info(
            "터미널에서 `python cli.py set-mode --mode paper`를 실행하세요.",
            icon=":material/terminal:",
        )

    if st.button(
        ":material/bolt: 실전투자 승인 요청",
        type="primary",
        help="CLI: python cli.py request-live-approval --champion-hash <hash>",
    ):
        st.warning(
            "실전투자 모드는 터미널에서 사람의 승인이 필요합니다.",
            icon=":material/warning:",
        )
        st.caption(
            "`python cli.py request-live-approval --champion-hash <hash>`"
        )

    st.divider()
    st.subheader(":material/science: 연구 실행", anchor=False)
    st.caption(
        "LLM이 이전 평가를 분석하고 후보 전략을 만들어 백테스트합니다."
    )
    if st.button(":material/play_arrow: 새 세대 실행"):
        st.info(
            "터미널에서 `Mimir /research <세대수>`를 실행하세요.",
            icon=":material/terminal:",
        )

    st.divider()
    if st.button(":material/refresh: 지금 새로고침", type="tertiary"):
        st.cache_data.clear()
        st.rerun()

    st.caption(
        f"모드 상태: {last_modified('mode.json')}  \n"
        f"최고 전략: {last_modified('champion.json')}"
    )


# ===========================================================================
# MAIN CONTENT
# ===========================================================================

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

with st.container(
    horizontal=True,
    horizontal_alignment="distribute",
    vertical_alignment="center",
):
    st.title(":material/monitoring: 퀀트 자동 연구 대시보드", anchor=False)
    if current_mode == "live" and orders_enabled:
        st.badge("실전투자 · 주문 허용", color="red", icon=":material/bolt:")
    elif current_mode == "live":
        st.badge("실전투자 · 주문 차단", color="orange", icon=":material/bolt:")
    else:
        st.badge("모의투자 · 주문 차단", color="blue", icon=":material/description:")


# ---------------------------------------------------------------------------
# L4 — ALERTS (surface problems above the fold immediately)
# ---------------------------------------------------------------------------

alerts: list[tuple[str, str]] = []

if champion_status == "EMPTY":
    alerts.append((
        "critical",
        "아직 최고 전략이 없습니다. Mimir 자동 연구를 실행하세요.",
    ))
if frontier_count == 0:
    alerts.append((
        "warning",
        "프론티어 전략이 없습니다. 통과한 후보가 아직 없습니다.",
    ))
if total_known == 0:
    alerts.append((
        "info",
        "연구 지식이 아직 없습니다. 백테스트 기록을 쌓아보세요.",
    ))
if current_mode == "live" and not orders_enabled:
    alerts.append((
        "warning",
        "실전투자 모드지만 주문은 차단되어 있습니다.",
    ))

if alerts:
    with st.container(border=True):
        for sev, msg in alerts:
            if sev == "critical":
                st.error(msg, icon=":material/error:")
            elif sev == "warning":
                st.warning(msg, icon=":material/warning:")
            else:
                st.info(msg, icon=":material/info:")


# ---------------------------------------------------------------------------
# L2 — PRIMARY KPI ROW
# ---------------------------------------------------------------------------

st.subheader(":material/query_stats: 핵심 현황", anchor=False)

with st.container(horizontal=True):
    champ_display = "활성" if champion_status == "CHAMPION" else _status_label(champion_status)
    champ_delta = "현재 적용 전략" if champion_status == "CHAMPION" else None
    st.metric(
        "최고 전략",
        champ_display,
        delta=champ_delta,
        delta_color="off",
        border=True,
    )
    st.metric(
        "프론티어 전략",
        str(frontier_count),
        delta=f"전략 계열 {family_count}개" if family_count > 0 else "계열 없음",
        delta_color="off",
        border=True,
    )
    st.metric(
        "연구 지식",
        f"{total_known}개 기록",
        delta=(
            f"검증 {len(known_good)} · 주의 {len(known_bad)} · 미확인 {len(unexplored)}"
            if total_known > 0
            else None
        ),
        delta_color="off",
        border=True,
    )
    st.metric(
        "재검토 후보",
        f"{len(rescue_entries)}개 전략",
        delta="다시 평가할 후보" if rescue_entries else None,
        delta_color="off",
        border=True,
    )


# ---------------------------------------------------------------------------
# L2 — Champion performance metrics
# ---------------------------------------------------------------------------

st.subheader(":material/emoji_events: 최고 전략 성과", anchor=False)

if champion_data:
    metrics_data: dict[str, object] | None = (
        champion_data.get("metrics")  # type: ignore[assignment]
    )
    with st.container(border=True):
        st.caption(
            f"전략 ID: `{champion_data.get('strategy_id', '없음')}` · "
            f"계열: `{champion_data.get('family', '없음')}`"
        )

        if metrics_data:
            sharpe = metrics_data.get("sharpe")
            sortino = metrics_data.get("sortino")
            cagr = metrics_data.get("cagr")
            total_return = metrics_data.get("total_return")
            max_drawdown = metrics_data.get("max_drawdown")
            calmar = metrics_data.get("calmar")
            win_rate = metrics_data.get("win_rate")
            profit_factor = metrics_data.get("profit_factor")
            trade_count = metrics_data.get("trade_count")

            with st.container(horizontal=True):
                st.metric(
                    "샤프 지수",
                    _fmt_float(sharpe),
                    help="위험을 고려한 수익성입니다. 1.0 이상을 목표로 합니다.",
                    border=True,
                )
                st.metric(
                    "소르티노 지수",
                    _fmt_float(sortino),
                    help="하락 위험만 반영한 수익성입니다.",
                    border=True,
                )
                st.metric(
                    "연복리 수익률",
                    _fmt_pct(cagr),
                    help="기간을 1년 기준으로 환산한 수익률입니다.",
                    border=True,
                )
                st.metric(
                    "최대 낙폭",
                    _fmt_pct(max_drawdown),
                    delta=f"칼마 지수: {_fmt_float(calmar)}",
                    delta_color="off",
                    help="고점에서 저점까지 가장 크게 하락한 폭입니다.",
                    border=True,
                )

            with st.container(horizontal=True):
                st.metric(
                    "승률",
                    _fmt_pct(win_rate),
                    help="전체 거래 중 수익 거래의 비율입니다.",
                    border=True,
                )
                st.metric(
                    "수익 요인",
                    _fmt_float(profit_factor),
                    help="총이익을 총손실로 나눈 값입니다. 1.0 초과가 기본입니다.",
                    border=True,
                )
                st.metric(
                    "거래 횟수",
                    str(trade_count) if trade_count is not None else "없음",
                    help="백테스트 기간 중 발생한 전체 거래 횟수입니다.",
                    border=True,
                )
                st.metric(
                    "누적 수익률",
                    _fmt_pct(total_return),
                    help="백테스트 기간 전체의 누적 수익률입니다.",
                    border=True,
                )
        else:
            st.info(
                "최고 전략은 있지만 성과 지표가 기록되지 않았습니다.",
                icon=":material/info:",
            )
            with st.expander("최고 전략 원시 데이터", icon=":material/code:"):
                st.json(champion_data)
else:
    with st.container(border=True):
        st.info(
            "아직 승격된 최고 전략이 없습니다. 왼쪽의 연구 실행 안내를 확인하세요.",
            icon=":material/emoji_events:",
        )


# ---------------------------------------------------------------------------
# L3 — Frontier strategies
# ---------------------------------------------------------------------------

st.subheader(":material/leaderboard: 프론티어 전략", anchor=False)

if not families:
    with st.container(border=True):
        st.info(
            "프론티어 전략이 없습니다. 평가를 통과한 후보가 여기에 표시됩니다.",
            icon=":material/leaderboard:",
        )
else:
    rows: list[dict[str, object]] = []
    for family_name, strategies in families.items():
        for strat in strategies:  # type: ignore[union-attr]
            row: dict[str, object] = {
                "전략 계열": family_name,
                "전략 ID": strat.get("strategy_id", "없음"),  # type: ignore[union-attr]
                "상태": _status_label(strat.get("status", "UNKNOWN")),  # type: ignore[union-attr]
                "점수": strat.get("score"),  # type: ignore[union-attr]
            }
            if isinstance(strat.get("metrics"), dict):  # type: ignore[union-attr]
                m = strat["metrics"]  # type: ignore[index]
                row["샤프"] = m.get("sharpe")  # type: ignore[union-attr]
                row["연복리 수익률"] = m.get("cagr")  # type: ignore[union-attr]
                row["최대 낙폭"] = m.get("max_drawdown")  # type: ignore[union-attr]
                row["거래 횟수"] = m.get("trade_count")  # type: ignore[union-attr]
            rows.append(row)

    frontier_df = pd.DataFrame(rows)

    col_left, col_right = st.columns([3, 1])

    with col_left:
        with st.container(border=True):
            st.markdown("**전략 목록**")
            col_config: dict = {
                "전략 ID": st.column_config.TextColumn(pinned=True),
                "점수": st.column_config.NumberColumn(format="%.4f"),
            }
            if "샤프" in frontier_df.columns:
                col_config["샤프"] = st.column_config.NumberColumn(format="%.3f")
            if "연복리 수익률" in frontier_df.columns:
                col_config["연복리 수익률"] = st.column_config.NumberColumn(format="percent")
            if "최대 낙폭" in frontier_df.columns:
                col_config["최대 낙폭"] = st.column_config.NumberColumn(format="percent")
            if "거래 횟수" in frontier_df.columns:
                col_config["거래 횟수"] = st.column_config.NumberColumn()
            st.dataframe(
                frontier_df,
                hide_index=True,
                column_config=col_config,
            )

    with col_right:
        with st.container(border=True):
            st.markdown("**계열별 전략 수**")
            family_summary = (
                frontier_df.groupby("전략 계열")
                .size()
                .reset_index(name="개수")
                .sort_values("개수", ascending=True)
            )
            chart = (
                alt.Chart(family_summary)
                .mark_bar()
                .encode(
                    y=alt.Y("전략 계열:N", sort="-x", title=None),
                    x=alt.X(
                        "개수:Q",
                        title="전략 수",
                        axis=alt.Axis(tickMinStep=1),
                    ),
                    color=alt.value("#3182f6"),
                    tooltip=["전략 계열:N", "개수:Q"],
                )
                .properties(height=max(120, family_count * 44))
            )
            st.altair_chart(chart)


# ---------------------------------------------------------------------------
# L5 — Knowledge base diagnostics
# ---------------------------------------------------------------------------

st.subheader(":material/psychology: 연구 지식", anchor=False)

col_kg, col_kb, col_ux, col_ix = st.columns(4)

with col_kg:
    with st.container(border=True):
        st.markdown(":green[**검증된 패턴**]")
        st.metric("재사용 가능", len(known_good))
        if known_good:
            with st.expander("목록 보기", icon=":material/list:"):
                for item in known_good[:10]:
                    st.caption(f"- {item}")
                if len(known_good) > 10:
                    st.caption(f"... 외 {len(known_good) - 10}개")

with col_kb:
    with st.container(border=True):
        st.markdown(":red[**주의 패턴**]")
        st.metric("피해야 할 패턴", len(known_bad))
        if known_bad:
            with st.expander("목록 보기", icon=":material/list:"):
                for item in known_bad[:10]:
                    st.caption(f"- {item}")
                if len(known_bad) > 10:
                    st.caption(f"... 외 {len(known_bad) - 10}개")

with col_ux:
    with st.container(border=True):
        st.markdown(":orange[**미탐색 영역**]")
        st.metric("검증 대기", len(unexplored))

with col_ix:
    with st.container(border=True):
        st.markdown(":blue[**상호작용**]")
        st.metric("시너지·충돌 조합", len(interactions))

if total_known > 0:
    kg_data = pd.DataFrame(
        {
            "구분": ["검증된 패턴", "주의 패턴", "미탐색 영역"],
            "개수": [len(known_good), len(known_bad), len(unexplored)],
            "color": ["#12b886", "#d13030", "#f59f00"],
        }
    ).sort_values("개수", ascending=True)

    with st.container(border=True):
        st.markdown("**연구 지식 구성**")
        chart = (
            alt.Chart(kg_data)
            .mark_bar()
            .encode(
                y=alt.Y("구분:N", sort="-x", title=None),
                x=alt.X(
                    "개수:Q",
                    title="기록 수",
                    axis=alt.Axis(tickMinStep=1),
                ),
                color=alt.Color("color:N", scale=None, legend=None),
                tooltip=["구분:N", "개수:Q"],
            )
            .properties(height=120)
        )
        st.altair_chart(chart)


# ---------------------------------------------------------------------------
# L6 — System detail (drill-down, collapsed by default)
# ---------------------------------------------------------------------------

with st.expander("시스템 상세 상태", icon=":material/settings:"):
    col_d1, col_d2 = st.columns(2)

    with col_d1:
        st.markdown("**운영 모드**")
        st.table(
            {
                "운영 모드": "실전투자" if current_mode == "live" else "모의투자",
                "주문 허용": "예" if orders_enabled else "아니오",
                "변경 요청자": (
                    mode_state.get("requested_by", "없음") if mode_state else "없음"
                ),
            }
        )

    with col_d2:
        st.markdown("**재검토 후보**")
        if rescue_entries:
            st.dataframe(pd.DataFrame(rescue_entries), hide_index=True)
        else:
            st.caption("재검토할 후보가 없습니다.")

    st.markdown("**최고 전략 원시 데이터**")
    st.json(champion_state or {})

    st.markdown("**프론티어 원시 데이터**")
    st.json(frontier_state or {})


# ---------------------------------------------------------------------------
# Footer — data freshness
# ---------------------------------------------------------------------------
st.caption(
    f"상태 확인 시각 — 모드: {last_modified('mode.json')} · "
    f"최고 전략: {last_modified('champion.json')} · "
    f"프론티어: {last_modified('frontier.json')}"
)
