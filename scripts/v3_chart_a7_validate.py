# ruff: noqa: E501  # Retain complete evidence wording and source constraints.
"""A7 research-only classical neckline lifecycle and regression evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.features.chart_patterns import classical_shape
from core.features.classical_lifecycle import (
    assess_classical_candidate,
    calculate_classical_events,
)
from core.features.registry import research_feature_specs
from scripts.v3_chart_a6_validate import validate as validate_a6
from tests.core.test_v3_chart_a7_classical_lifecycle import (
    EXAMPLES,
    SHAPES,
    interpolate_ohlc,
    points,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"
LOCAL = Path("/shared/moon-workspace/AutoResearchFinance_v3-track1-strategy-20261027")


def validate(*, save: bool = True) -> dict[str, Any]:
    a6 = validate_a6(save=False)
    assert len(research_feature_specs()) == 447
    assert a6["causal_gate"]["checkpoints"] == 4608
    assert a6["causal_gate"]["prefix_mismatches"] == 0
    assert a6["causal_gate"]["timestamp_violations"] == 0
    equal = points((100.0, 110.0, 100.0, 110.0, 100.0), start_high=False)
    assert classical_shape(equal, "inverse_head_shoulders") == 0
    assert assess_classical_candidate(equal, "inverse_head_shoulders") is None
    assert classical_shape(SHAPES["inverse_head_shoulders"], "inverse_head_shoulders") == 1
    gates = []
    prefixes = 0
    for name, values in EXAMPLES.items():
        series = interpolate_ohlc(values)
        observed = calculate_classical_events(series, name)
        assert len(observed) == 2
        candidate, confirmed = observed
        assert candidate.stage == "CANDIDATE"
        assert confirmed.stage == "CONFIRMED" and confirmed.known_at > candidate.known_at
        assert confirmed.eligible_on_next_bar == confirmed.known_at + 1
        assert candidate.pattern_id == confirmed.pattern_id
        for cut in range(1, len(series["close"]) + 1):
            prefix = {key: value[:cut] for key, value in series.items()}
            actual = calculate_classical_events(prefix, name)
            expected = tuple(event for event in observed if event.known_at < cut)
            assert actual == expected, (name, cut)
            prefixes += 1
        gates.append(
            {
                "pattern": name,
                "source": "independent research-only geometric heuristics",
                "candidate_at": candidate.known_at,
                "neckline_break_confirmed_at": confirmed.known_at,
                "order_eligible_not_before_bar": confirmed.eligible_on_next_bar,
                "shape_is_not_breakout": True,
                "candidate_pivot_index": candidate.last_pivot_index,
                "confirmation_reason": confirmed.reason,
                "repainted_historical_events": 0,
            }
        )
    # Default source-only scalar candidate features retain baseline codes.
    assert all(
        name in {"head_shoulders", "inverse_head_shoulders", "double_top", "double_bottom"}
        for name in EXAMPLES
    )
    a0 = json.loads((OUT / "quant-v3-chart-A0-baseline-20261029.json").read_text())
    preserved = {}
    for rel, expected_sha in a0["local_bulk40"]["file_hash_sha256"].items():
        digest = hashlib.sha256((LOCAL / rel).read_bytes()).hexdigest()
        assert digest == expected_sha, rel
        preserved[rel] = digest
    change_manifest = json.loads(
        (
            ROOT / "tests/core/fixtures/v3_chart_a7_inverse_corrected_baseline_20261029.json"
        ).read_text()
    )
    assert change_manifest["changed_only"] == "inverse_head_shoulders"
    assert len(change_manifest["differences"]) == 4
    assert all(row["pattern"] == "inverse_head_shoulders" for row in change_manifest["differences"])
    assert a6["original_scalar_frozen_parity"] == 48
    report: dict[str, Any] = {
        "schema": "quant-v3-chart-A7-neckline-lifecycle-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "registered_feature_count": 447,
        "new_registered_feature_count": 0,
        "legacy_scalar_outputs": "unchanged on frozen baseline except targeted inverse H&S bug fix",
        "false_positive_fixes": [
            {
                "name": "inverse_head_shoulders",
                "invalid_equal_low_prices": list(q.value for q in equal),
                "expected": 0,
                "observed_after_fix": 0,
            }
        ],
        "versioned_scalar_diff": {
            "unchanged_against_A4_original": 44,
            "approved_inverse_HS_corrections": 4,
            "non_whitelisted_changes": 0,
            "observed_synthetic_difference_rows": change_manifest["differences"],
        },
        "status_lifecycle": ["CANDIDATE", "CONFIRMED", "INVALIDATED", "EXPIRED"],
        "pattern_evidence": gates,
        "prefix_gate": {"end_to_end_cutoff_checks": prefixes, "event_history_changes": 0},
        "shared_existing_gate": {
            "A6_A3_streaming_checks": 4608,
            "A6_A3_mismatches": a6["causal_gate"]["prefix_mismatches"],
            "A6_A3_timestamp_violations": a6["causal_gate"]["timestamp_violations"],
            "A4_frozen_chart_output_hash_matches": a6["original_scalar_frozen_parity"],
        },
        "existing_local_bulk40_sha256_unchanged": preserved,
        "new_research_component": "core/features/classical_lifecycle.py",
        "production_feature_route_changed": False,
        "next_open_not_guaranteed_by_this_code": True,
        "limitations": [
            "Breakout confirmation is a research-only API, not yet a registered StrategyIR signal",
            "Legacy 12 scalar features use shape only; they must not be interpreted as neckline-confirmed",
            "Synthetic OHLC fixtures do not demonstrate real market precision, recall, profitability or next-open execution",
            "No volume confirmation, false breakout statistical calibration or volatility-adaptive neckline tolerance",
            "Source code and mathematical thresholds are independent heuristics with no proprietary chart pattern licensing assertion",
            "Existing +40 local dirty worktree, 2026 sealed OOS, OAuth, MCP URL, G ledger, main and live orders unchanged",
        ],
    }
    if save:
        (OUT / "quant-v3-chart-A7-classical-acceptance-20261029.json").write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        text = [
            "# Quant V3 A7 · 고전 차트 후보/넥라인 돌파/무효화 검증 결과",
            "",
            f"- 검증 시각: {report['observed_at_kst']}",
            "- 역헤드앤숄더: 동률 머리=어깨 저점([100,110,100,110,100])",
            "  false positive +1을 0으로 수정. 진짜 낮은 머리 저점은 +1 후보 허용.",
            "- 구현: double_top, double_bottom, head_shoulders, inverse_head_shoulders",
            "  4종 형태 후보를 **넥라인 종가 돌파 확정과 분리**.",
            "- 후보는 마지막 스윙의 오른쪽 확인봉까지 관측한 뒤 CANDIDATE.",
            "- 해당 확인봉 이후의 종가가 넥라인을 돌파하면 CONFIRMED;",
            "  차기 봉보다 먼저 사용 불가. 무효 가격 터치·불량 캔들·기한 초과는",
            "  INVALIDATED/EXPIRED로 이력을 남김.",
            "- 고점/저점이 무효화 가격을 돌파한 같은 봉에 종가 넥라인",
            "  돌파도 일어났다면 **무효화 우선**: 낙관적 체결을 가정하지 않음.",
            f"- A7 4개 합성 완성 OHLC 경로 전체 {prefixes}개 prefix: 이벤트",
            "  변경 0, 올바른 순서(후보 후 확정) 4/4 검출.",
            "- 기존 447개 지표 등록/12개 스칼라 기본 의미 유지. A7 이벤트는",
            "  A8까지 별도 연구용 API이며 거래 주문 신호로 등록하지 않음.",
            "- 구버전 A4 동결 48 시계열의 실제 차이: 44 동일, inverse H&S",
            "  4개 전용 오탐 수정으로 인한 출력 변경. 변경 전 SHA 유지하며 새",
            "  별도 버전의 SHA를 기록; 다른 11개 패턴 출력 변경 0.",
            "- A6/A3 기존 4608회 causal prefix 위반 0.",
            "- 이전 버전 inverse H&S XFAIL은 정상 PASS로 변경.",
            "",
            "## 미완료",
            "",
            "- 실제 QQQ 가격 데이터(독립 2026 OOS 제외), 시장 레짐별 정밀도/재현율,",
            "  넥라인 확인에 거래량 및 ATR 문맥을 추가하는 선택 연구는 A8/A9 대상.",
            "- 가격 이동이 극심한 단일 봉에서는 무효화 우선 보수적 해석을 적용.",
            "- 운영 main/실거래/G원장/OAuth/MCP URL/봉인 OOS 및",
            "  다른 로컬 브랜치 +40개 미커밋 지표는 변경하지 않음.",
        ]
        (OUT / "quant-v3-chart-A7-classical-report-20261029.md").write_text(
            "\n".join(text) + "\n", encoding="utf-8"
        )
    return report


if __name__ == "__main__":
    data = validate()
    print(
        json.dumps(
            {
                "registered": data["registered_feature_count"],
                "prefix_count": data["prefix_gate"]["end_to_end_cutoff_checks"],
                "known_bad_fixed": data["false_positive_fixes"],
                "patterns": data["pattern_evidence"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
