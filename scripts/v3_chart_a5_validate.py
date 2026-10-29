# ruff: noqa: E501  # Keep audited evidentiary strings verbatim.
"""A5 research-only harmonic acceptance gate and provenance report.

Calculates only deterministic synthetic OHLCV; no real-market/OOS/trading data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.features.chart_patterns import calculate_chart_pattern, harmonic_xabcd
from core.features.harmonic_geometry import RULES, assess_harmonic, projected_reversal_zone
from core.features.registry import research_feature_specs
from scripts.v3_chart_a2_a3_stream_audit import reproduce
from scripts.v3_chart_a4_validate import validate as validate_a4
from tests.core.test_v3_chart_a5_harmonic_geometry import (
    INVALID,
    VALID,
    interpolate_ohlc,
    points,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"


def validate(*, save: bool = True) -> dict[str, Any]:
    assert set(RULES) == set(VALID) == set(INVALID)
    rows = []
    for name, rule in RULES.items():
        valid_result = assess_harmonic(points(VALID[name]), name)
        invalid_result = assess_harmonic(points(INVALID[name]), name)
        assert valid_result.accepted and valid_result.direction == 1
        assert not invalid_result.accepted and invalid_result.direction == 0
        assert valid_result.failed_rules == ()
        assert invalid_result.failed_rules
        assert harmonic_xabcd(points(INVALID[name]), name) == 0
        zone = projected_reversal_zone(points(VALID[name][:4]), name)
        assert zone and zone[0] <= VALID[name][4] <= zone[1]
        directions = {}
        for direction in ("bullish", "bearish"):
            shape = VALID[name] if direction == "bullish" else tuple(220 - x for x in VALID[name])
            candles = interpolate_ohlc(shape)
            signal = calculate_chart_pattern(candles, name)
            assert len(signal) == 30
            assert signal[26] == (1.0 if direction == "bullish" else -1.0)
            assert sum(x != 0.0 for x in signal) == 1
            assert all(v == 0.0 for v in signal[:26])
            directions[direction] = {
                "nonzero_events": 1,
                "observed_at": 26,
                "pivot_d_index": 24,
                "confirmed_after_right_bars": 2,
            }
        invalid = calculate_chart_pattern(interpolate_ohlc(INVALID[name]), name)
        assert all(x == 0.0 for x in invalid)
        rows.append(
            {
                "name": name,
                "source_url": rule.source_url,
                "commercial_license": valid_result.commercial_license,
                "b_gate": [rule.b_min, rule.b_max],
                "d_xa_target": rule.xa_at_d,
                "d_xa_tolerance": rule.xa_tolerance,
                "bc_extension": [rule.bc_min, rule.bc_max],
                "bc_retracement": [rule.bc_retrace_min, rule.bc_retrace_max],
                "abcd_alternatives": list(rule.cd_over_ab_targets),
                "abcd_tolerance": rule.cd_over_ab_tolerance,
                "abcd_minimum_only": rule.abcd_minimum_only,
                "positive": {
                    "points": list(VALID[name]),
                    "ratios": dict(valid_result.ratios),
                    "prz": [valid_result.prz_low, valid_result.prz_high],
                    "detected": True,
                },
                "negative": {
                    "points": list(INVALID[name]),
                    "failed_rules": list(invalid_result.failed_rules),
                    "detected": False,
                },
                "realized_scalar_events": directions,
                "invalid_series_events": 0,
                "rule_source_parity_certified": False,
            }
        )
    a3 = reproduce(strict=False)
    assert a3["summary"]["checkpoints"] == 4608
    assert all(
        a3["summary"][x] == 0
        for x in ("prefix_mismatches", "timestamp_violations", "runtime_errors")
    )
    a4 = validate_a4(save=False)
    assert a4["oracle_exact"]["compared_outputs"] == 48
    assert len(research_feature_specs()) == 447
    retained_frozen = json.loads(
        (ROOT / "tests/core/fixtures/v3_chart_a5_harmonic_baseline_20261029.json").read_text()
    )
    assert len(retained_frozen["signals"]) == 4
    assert retained_frozen["legacy_changes"] == []  # those synthetic paths had no events
    report = {
        "schema": "quant-v3-chart-A5-sourced-harmonic-rules-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "registered_chart_features": 12,
        "registered_total": 447,
        "new_registered_features": 0,
        "patterns": rows,
        "checks": {
            "canonical_bullish_detected": 4,
            "canonical_bearish_detected": 4,
            "canonical_invalid_rejected": 4,
            "legacy_gartley_false_positive_fixed": True,
            "legacy_crab_false_positive_fixed": True,
            "historical_synthetic_output_parity": 48,
            "historical_synthetic_path_changes": 0,
            "stream_prefix_checks": a3["summary"]["checkpoints"],
            "stream_prefix_mismatches": a3["summary"]["prefix_mismatches"],
            "timestamp_violations": a3["summary"]["timestamp_violations"],
            "runtime_errors": a3["summary"]["runtime_errors"],
            "remaining_known_inverse_hs_bug": True,
        },
        "copyright_and_license": [
            "HarmonicTrader pattern names and commercial trademark use NOT CLEARED",
            "Only mathematical ratios from credited public references; no proprietary code imported",
            "Not licensed or certified full proprietary pattern detection; numeric thresholds are independent research choices",
        ],
        "out_of_scope": [
            "No OOS / 2026 market research, no paid/trademark clearance, no actual profitability claim",
            "No live orders, no new strategy generations, no production data/config mutations",
            "Pattern stage output remains scalar +/-1 or 0; PRZ diagnostic is separate research API",
        ],
    }
    if save:
        (OUT / "quant-v3-chart-A5-harmonic-acceptance-20261029.json").write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            "# Quant V3 A5 · 하모닉 4종 정밀 수정 및 인과성 검증",
            "",
            f"- 실측 시각: {report['observed_at_kst']}",
            "- 대상: 가틀리·버터플라이·배트·크랩 기존 등록 4종, 지표 수 증설 없음(447개 유지).",
            "- 공통 파동 계산: XABCD 가격 방향, AB/XA, BC/AB, CD/BC, CD/AB, AD/XA;",
            "  XA와 BC의 독립 목표 가격 구간 교집합(PRZ) 및 AB=CD 보조 조건.",
            "- 가틀리: B/XA .618±3%, XA .786 되돌림, CD/BC 1.13–1.618.",
            "- 버터플라이: B/XA .786 근접, A 기준 XA 1.27 확장, CD/BC 1.618–2.618.",
            "- 배트: B/XA .382–.50 부근, XA .886 되돌림, CD/BC 1.618–2.618.",
            "- 크랩: B/XA .382–.618 부근, XA 1.618 확장, CD/BC 2.24–3.618.",
            "- 네 패턴 모두 원문 근거로 게이트를 강화했으나 ±허용 범위는 독립 휴리스틱.",
            "- 이전 Gartley CD/BC 1.70588 과대 확장, Crab CD/BC 5.472 오탐 제거.",
            "- 검증: 유효 4×상승·하락=8개 경로 D 확인봉 index26에서 각 1신호;",
            "  무효 4개 경로 신호 0, D 확인 이전 신호 0.",
            f"- A3 전체 bar-by-bar {a3['summary']['checkpoints']}회: 과거값 변경",
            f"  {a3['summary']['prefix_mismatches']} / 피벗 확정 지연 위반",
            f"  {a3['summary']['timestamp_violations']} / 계산 예외",
            f"  {a3['summary']['runtime_errors']}.",
            "- A4 기존 기준 48개 합성 출력 SHA 일치. 이 합성 경로에서 하모닉 이벤트",
            "  발생 건수가 0이었으므로 수치 수정의 실효성은 새 유효/무효 fixture로 검증.",
            "- 기존 역헤드앤숄더 XFAIL은 A7까지 유지.",
            "",
            "## 주의·미완료",
            "",
            "- 공개 원본의 피보나치 가격 비율을 비교한 연구용 독립 구현이며",
            "  원저작자·상표권자의 상업적 사용 허가를 받은 구현이 아니다.",
            "- 실제 시장의 신호 분포, 복합 PRZ가 수익에 미치는 효과, 원본 프로프라이어터리",
            "  코드와 모든 수치가 동치인지 여부, 독립 봉인 OOS 및 거래가능성은 미검증.",
            "- A5 변경은 별도 research 브랜치에서만 유지. 운영 main/기존 +40 및",
            "  Quant 주문·인증·G원장·sealed OOS는 변경하지 않음.",
            "",
            "## 수식 참고",
            *[f"- {r.source_url}" for r in RULES.values()],
        ]
        (OUT / "quant-v3-chart-A5-harmonic-report-20261029.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    result = validate()
    print(json.dumps(result["checks"], ensure_ascii=False, indent=2))
