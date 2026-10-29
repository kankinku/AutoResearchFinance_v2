"""A4 research-only pivot contract gate, no protected data access."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.features.causal_pivots import CausalSwingConfig, CausalSwingTracker
from core.features.chart_patterns import PATTERNS, calculate_chart_pattern
from core.features.registry import research_feature_specs
from scripts.v3_chart_a2_a3_stream_audit import build_scenarios, reproduce
from tests.core.test_v3_causal_chart_patterns import bars

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"
ORACLE = ROOT / "tests/core/fixtures/v3_chart_pre_a4_baseline_20261029.json"


def validate(*, save: bool = True) -> dict[str, Any]:
    frozen = json.loads(ORACLE.read_text())
    scenarios = build_scenarios(190)
    scenarios["trend_wave"] = {key: tuple(values) for key, values in bars(190).items()}
    exact = 0
    for label, sample in scenarios.items():
        for pattern in PATTERNS:
            values = calculate_chart_pattern(sample, pattern)
            digest = hashlib.sha256(
                json.dumps(values, allow_nan=False, separators=(",", ":")).encode()
            ).hexdigest()
            assert digest == frozen["signals"][label][pattern]["sha256"], (label, pattern)
            exact += 1
    gate = reproduce(strict=False)
    assert gate["summary"]["checkpoints"] == 4608
    assert all(
        gate["summary"][x] == 0
        for x in ("prefix_mismatches", "timestamp_violations", "runtime_errors")
    )
    # Independent event-replacement fixture, including once-public but superseded state.
    tracker = CausalSwingTracker(CausalSwingConfig(confirmation_bars=2))
    highs = (10, 11, 14, 11, 12, 11, 17, 12, 11)
    for i, high in enumerate(highs):
        tracker.update(i, float(high), 8.0, 9.0)
    assert [x.kind for x in tracker.events] == ["APPEND", "REPLACE"]
    assert [x.known_at for x in tracker.events] == [4, 8]
    event_sample = [
        {
            "event_id": e.event_id,
            "stage": e.kind,
            "event_time": e.known_at,
            "swing_index": e.pivot.index if e.pivot else None,
            "swing_price": e.pivot.value if e.pivot else None,
            "previous_index": e.previous.index if e.previous else None,
        }
        for e in tracker.events
    ]
    registered = research_feature_specs()
    assert len(registered) == 447
    evidence = {
        "schema": "quant-v3-chart-A4-causal-pivot-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "frozen_reference_sha": frozen["source_sha"],
        "defaults": {
            "confirmation_bars": 2,
            "lookback": 160,
            "minimum_swing": 0.015,
            "mode": "percent",
        },
        "feature_counts": {"registered": 447, "chart": len(PATTERNS)},
        "oracle_exact": {"compared_outputs": exact, "mismatches": 0, "scenarios": list(scenarios)},
        "causal_stream_replay": gate["summary"],
        "event_log_example": event_sample,
        "experimental_threshold_modes": ["percent", "absolute", "atr"],
        "independent_multi_scale": True,
        "provisional_is_trade_eligible": False,
        "known_at_for_confirmed_pivot": "index + confirmation_bars",
        "same_kind_supersession": "REPLACE current pivot, append immutable event record",
        "lookback_window_bound": "2*confirmation_bars+1",
        "history_limitations": [
            "audit event ledger intentionally grows with event count",
            "Provisional developing swing is neither confirmed nor exposed as an order signal",
            "absolute/atr modes currently tracker-only; StrategyIR uses baseline percent output",
            "No actual market/OOS performance, numeric source parity or next-open trading gate",
            "Two known pattern false positives (Gartley and inverse H&S) still under A5/A7",
            "Official release checker uv is not installed; no release approval",
        ],
        "live_orders": "NOT_RUN",
        "separate_bulk40": "UNTOUCHED",
    }
    if save:
        (OUT / "quant-v3-chart-A4-pivot-acceptance-20261029.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        lines = [
            "# Quant V3 A4 · 공통 인과형 피벗·스윙 엔진 개선 보고",
            "",
            f"- 실측일: {evidence['observed_at_kst']}",
            "- 코드: `core/features/causal_pivots.py` 새 공통 tracker + 기존",
            "  `chart_patterns.py`의 버전 호환 계산 어댑터.",
            f"- 동결한 기존 차트 결과 {exact}개(12패턴×4합성경로) sha256 일치: **차이 0**",
            f"- A3 봉별 전길이 prefix {gate['summary']['checkpoints']}회:",
            f"  과거값 변경 {gate['summary']['prefix_mismatches']},",
            f"  확정 시점 위반 {gate['summary']['timestamp_violations']},",
            f"  계산 오류 {gate['summary']['runtime_errors']}.",
            "- 새 tracker의 상태 이벤트: **APPEND/REPLACE/RESET**. 더 극단적인",
            "  같은 방향 피벗이 나와도 이전에 보고된 관측 이벤트를 삭제하지 않음.",
            "- DEVELOPING은 오른쪽 확인 봉이 부족한 임시 후보로 제공되며",
            "  시장가 진입·확정 패턴으로 사용 금지.",
            "- threshold mode: percent(기존 기본값), absolute, ATR(과거 봉만 사용).",
            "  복수 스케일은 독립 tracker로 처리. 이벤트 로그는 증거 보존을 위해",
            "  누적 저장하며 활성 관측 창은 2*c+1 이내로 유지.",
            "- 모든 기존 지표/원장 보존: 447개 등록 유지. 신규 지표 수 증가 없음.",
            "",
            "## 후속 작업",
            "",
            "- A5 하모닉 BC/AB=CD/PRZ 원본 검증 및 4종 수식 보정",
            "- A6 파동 내부 서브웨이브 검증과 진행/무효화 상태 모델",
            "- A7 역헤드앤숄더 대칭 오탐·넥라인 확정 검증",
            "- A8/A9: experimental threshold modes의 StrategyIR opt-in, 성능/실데이터 검증",
            "",
            "## 제한",
            "",
            "- 원본 기준 차트 알고리즘 자체의 판정 오류 2개는 A5/A7까지 미수정.",
            "- Synthetic causal pass는 패턴의 금융적 예측력·거래 가능성 증명이 아님.",
            "- Main/G 원장/2026 sealed OOS/OAuth/MCP URL/실주문 설정 변경 없음.",
        ]
        (OUT / "quant-v3-chart-A4-pivot-engine-report-20261029.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
    return evidence


if __name__ == "__main__":
    report = validate()
    print(
        json.dumps(
            {
                "exact_outputs": report["oracle_exact"]["compared_outputs"],
                "streaming": report["causal_stream_replay"],
                "registered": report["feature_counts"]["registered"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
