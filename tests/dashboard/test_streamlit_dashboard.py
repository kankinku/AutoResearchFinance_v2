from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parents[2]


def test_streamlit_dashboard_exposes_korean_live_research_view() -> None:
    source = (ROOT / "dashboard.py").read_text(encoding="utf-8")

    for marker in (
        "퀀트 자동 연구 대시보드",
        "자동 연구 진행 상황",
        "처리된 세대",
        "현재 세대",
        "Codex 연결",
        "백그라운드 탐색과 연결됨",
        "이전 세대 이후",
        "첫 세대 시작 후",
        "장시간 대기 확인 필요",
        "사용 설명서",
        "@st.fragment(run_every=",
        "system/autoresearch.json",
        "llm/status.json",
        "research-events.jsonl",
        "현재 단계",
        "phase_started_at",
        "_elapsed_from_timestamp",
        "상세 실행 로그",
        "복구 시도",
        "성능 향상 추이",
        "인디케이터와 입력 자료",
        "제안 변경 내용",
        "백테스트 결과 대기",
        "분석할 세대",
        "feature_lineage",
        "qqq_cagr",
    ):
        assert marker in source


def test_streamlit_dashboard_uses_korean_visible_section_labels() -> None:
    source = (ROOT / "dashboard.py").read_text(encoding="utf-8")

    for marker in (
        'st.title(":material/monitoring: 퀀트 자동 연구 대시보드"',
        'st.subheader(":material/query_stats: 핵심 현황"',
        'st.subheader(":material/emoji_events: 최고 전략 성과"',
        'st.button(":material/play_arrow: 새 세대 실행"',
        'st.selectbox("분석할 세대"',
    ):
        assert marker in source


def test_streamlit_dashboard_renders_generation_analysis_without_exception() -> None:
    app = AppTest.from_file(str(ROOT / "dashboard.py")).run(timeout=30)

    assert not app.exception
    assert any(item.label == "분석할 세대" for item in app.selectbox)
    assert any(
        "현재 단계 경과" in item.value
        or "세대 이후" in item.value
        or "첫 세대 시작 후" in item.value
        for item in app.markdown
    )
