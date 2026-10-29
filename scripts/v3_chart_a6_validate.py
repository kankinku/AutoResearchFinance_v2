# ruff: noqa: E501  # Preserve technical evidence strings and source URLs.
"""A6 Elliott structural diagnostics gate; synthetic/research-only, no orders."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.features.elliott_structure import (
    WaveHypothesisStream,
    analyze_abc,
    analyze_combination,
    analyze_impulse,
    analyze_multiscale_abc,
    analyze_multiscale_impulse,
)
from core.features.registry import research_feature_specs
from scripts.v3_chart_a2_a3_stream_audit import reproduce
from scripts.v3_chart_a5_validate import validate as validate_a5
from tests.core.test_v3_chart_a6_elliott_structure import (
    pivots,
    subdivisions,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"


def validate(*, save: bool = True) -> dict[str, Any]:
    impulse = pivots([100, 110, 105, 122, 115, 130])
    stages = []
    for n in range(1, 6):
        info = analyze_impulse(impulse[: n + 1], decision_at=impulse[n].known_at)
        assert info.known_at == impulse[n].known_at
        assert info.wave_number == n
        assert info.stage == ("CONFIRMED" if n == 5 else "DEVELOPING")
        stages.append(
            {
                "wave": n,
                "stage": info.stage,
                "known_at": info.known_at,
                "structurally_verified": info.structurally_verified,
            }
        )
    nested = subdivisions(impulse, (5, 3, 5, 3, 5))
    verified = analyze_impulse(impulse, subwaves=nested)
    fine = tuple(q for segment in nested for q in segment[:-1]) + (nested[-1][-1],)
    inferred = analyze_multiscale_impulse(impulse, fine)
    assert verified.structurally_verified and inferred.structurally_verified
    assert not analyze_multiscale_impulse(impulse, fine[:-2]).structurally_verified
    zigzag = pivots([100, 110, 105, 116])
    flat = pivots([100, 110, 100.8, 111.5])
    zig_children = subdivisions(zigzag, (5, 3, 5))
    flat_children = subdivisions(flat, (3, 3, 5))
    zig_result = analyze_abc(zigzag, zig_children)
    flat_result = analyze_abc(flat, flat_children)
    assert zig_result.structurally_verified and zig_result.subtype == "ZIGZAG"
    assert flat_result.structurally_verified and flat_result.subtype == "FLAT"
    zig_fine = tuple(q for leg in zig_children for q in leg[:-1]) + (zig_children[-1][-1],)
    assert analyze_multiscale_abc(zigzag, zig_fine).structurally_verified
    combination = pivots(
        [100, 110, 105, 116, 106, 111, 99, 110, 105, 116, 106, 111, 99, 110, 105, 116]
    )
    comps = tuple(subdivisions(combination[3 * i : 3 * i + 4], (5, 3, 5)) for i in range(5))
    wxy = analyze_combination(combination[:10], comps[:3], count=3)
    wxyxz = analyze_combination(combination, comps, count=5)
    assert all(x.structurally_verified for x in (wxy, wxyxz))
    wave_stream = WaveHypothesisStream()
    snapshots = []
    for p in impulse:
        prior = wave_stream.history
        state = wave_stream.ingest(p)
        assert wave_stream.history[:-1] == prior
        assert state.known_at == p.known_at
        snapshots.append(
            {
                "pivot_index": p.index,
                "known_at": p.known_at,
                "stage": state.stage,
                "candidate_alternatives": state.alternative_counts,
            }
        )
    a5 = validate_a5(save=False)
    a3 = reproduce(strict=False)
    assert a3["summary"]["checkpoints"] == 4608
    assert all(
        a3["summary"][key] == 0
        for key in ("prefix_mismatches", "timestamp_violations", "runtime_errors")
    )
    assert a5["checks"]["historical_synthetic_output_parity"] == 48
    assert len(research_feature_specs()) == 447
    report: dict[str, Any] = {
        "schema": "quant-v3-chart-A6-elliott-structure-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "feature_count": 447,
        "new_scalar_features": 0,
        "experimental_structure_api_only": True,
        "registered_calculator_changed": False,
        "verified_subwave_topologies": {
            "impulse": "5-3-5-3-5",
            "zigzag": "5-3-5",
            "flat": "3-3-5",
        },
        "developing_wave_1_5": stages,
        "structurally_verified": {
            "impulse_5": verified.structurally_verified,
            "impulse_from_dual_scale": inferred.structurally_verified,
            "zigzag": zig_result.structurally_verified,
            "flat": flat_result.structurally_verified,
            "wxy": wxy.structurally_verified,
            "wxyxz": wxyxz.structurally_verified,
        },
        "sample_causal_stream": snapshots,
        "causal_gate": a3["summary"],
        "original_scalar_frozen_parity": a5["checks"]["historical_synthetic_output_parity"],
        "rejects": {
            "wave2_origin": "WAVE2_RETRACE_ORIGIN",
            "wave3_shortest": "WAVE3_SHORTEST",
            "wave4_overlap": "WAVE4_OVERLAPS_1",
            "subwave_count": "SUBWAVE_TOPOLOGY",
            "future_subwave_knowledge": "SUBWAVE_NOT_KNOWN",
            "wxy_connector_mismatch": "CONNECTOR_MISMATCH",
        },
        "source_urls": [
            "https://www.elliottwave.com/waveopedia/impulse/",
            "https://www.elliottwave.com/waveopedia/zigzags/",
            "https://www.elliottwave.com/waveopedia/flats/",
            "https://www.elliottwave.com/waveopedia/corrective-waves/",
        ],
        "limitations": [
            "Full scalar chart feature names/outputs unchanged; diagnostics are opt-in API only until A8",
            "Multi-scale structural verification requires fine-scale confirmed pivots with exact matching endpoints, otherwise no structural verification",
            "Outer five-pivot count confirmed is only geometric unless verified 5-3-5-3-5 fine subwaves are supplied",
            "WXY groups use verified ABC zigzag or flat components; no diagonals, triangles, running flats, alternate wave degrees or perfect count claims",
            "Competing count names are bounded hypotheses, not confidence probabilities",
            "Synthetic cases only; no QQQ actual data/OOS, no financial signal quality, next-open order checks",
            "A7 inverse H&S false positive still pending; production main, OAuth, MCP URL, G ledger and live order settings unchanged",
            "Moon official release gate uv not installed",
        ],
        "main_branch_modified": False,
        "existing_dirty_bulk40_modified": False,
    }
    if save:
        (OUT / "quant-v3-chart-A6-elliott-acceptance-20261029.json").write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            "# Quant V3 A6 · 엘리엇 파동 계층 검증 및 진행 상태 연구 모듈",
            "",
            f"- 실측: {report['observed_at_kst']}",
            "- 범위: core/features/elliott_structure.py 추가, **기존 447개 등록 지표 불변**.",
            "- 1~4파 단계는 DEVELOPING, 5파 외곽 조건 통과는 CONFIRMED이나",
            "  실제 5-3-5-3-5 세부파가 확인되지 않으면 structurally_verified=False.",
            "- 매 파동의 known_at과 차트 스윙 확정 시각을 구분하고, 다음 관측",
            "  가능한 봉 이전에는 신호/확인으로 사용하지 않음. 대안 카운트 최대 3개.",
            "- 필수 규칙: 2파 시작점 침범, 3파 최단, 4파 1파 영역 교차 및",
            "  5파 추세 정점 미갱신을 각각 INVALIDATED로 구분.",
            "- 조정 ABC: 외곽 4 피벗만 존재하면 OUTER_ONLY, Zigzag는 5-3-5,",
            "  Flat은 3-3-5 확인된 하위 피벗과 B 되돌림 범위가 함께 충족되어야 구분.",
            "- W-X-Y 및 W-X-Y-X-Z: W/X/Y/(X/Z) 각 컴포넌트가 세 구간",
            "  ABC 계열과 확인된 세부파로 나뉘어야 구조 검증.",
            "- 다중 스케일의 세부 피벗이 시작/끝/시점에서 정렬되지 않으면",
            "  억지로 보간하거나 완성 파동으로 확정하지 않음.",
            "- 발행된 WaveHypothesisStream 기록은 불변이며 후속 가격으로",
            "  과거 가설을 수정·삭제하지 않음.",
            "- A3 기존 12개 차트 4,608회 전체 prefix 결과 변경",
            f"  {a3['summary']['prefix_mismatches']} / 확정시각 위반",
            f"  {a3['summary']['timestamp_violations']} / 실행 예외",
            f"  {a3['summary']['runtime_errors']}.",
            "- A5 이전 지표용 동결 해시 비교 48개 유지. 신규 계산기는 기존",
            "  StrategyIR 지표/실매매 경로로 연결하지 않았음.",
            "",
            "## 현재 제한",
            "",
            "- 이 결과는 세부파가 *명시적으로 확인된 경우*의 수학적 판정기.",
            "  실제 모든 시장 파동을 자동으로 참값 라벨링하는 모델이 아님.",
            "- Triangle, diagonal, ending truncated fifth, 복수 파동 차수의 대안",
            "  탐색, OOS 수익성 및 실거래는 A8/A9 이후 별도 연구 대상.",
            "- Source named above is reference only; copied third-party code 없음.",
            "- A7 역헤드앤숄더 기존 오탐 1개는 여전히 예상 실패.",
            "- 운영 main/OAuth/MCP URL/G원장/2026 sealed OOS/주문설정 변경 없음.",
        ]
        (OUT / "quant-v3-chart-A6-elliott-report-20261029.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    r = validate()
    print(
        json.dumps(
            {
                "feature_count": r["feature_count"],
                "five_wave_stages": r["developing_wave_1_5"],
                "verified_families": r["structurally_verified"],
                "causal_checks": r["causal_gate"]["checkpoints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
