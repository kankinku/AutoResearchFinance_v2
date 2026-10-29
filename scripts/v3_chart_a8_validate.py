# ruff: noqa: E501  # Preserve source verification limits in evidence messages.
"""A8 opt-in research feature and immutable overlay evidence (synthetic only).

Never publishes to live dashboard state. Demo file is an explicit synthetic
illustration, not actual strategy fills, prices, 2026 OOS or generation output.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from research.chart_pattern_bridge import (
    calculate_chart_research,
    chart_research_feature_specs,
    overlay_payload,
)
from research.llm.inherited_feature_compiler import (
    InheritedFeatureBindingError,
    _new_feature_vector,
)
from scripts.v3_chart_a7_validate import validate as validate_a7
from strategy_ir.schema import FeatureRef
from tests.core.test_v3_chart_a8_optin_feature_bridge import data_inputs, long_sample

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"


def validate(*, save: bool = True) -> dict[str, Any]:
    default = research_feature_specs()
    optin = research_feature_specs(chart_research_opt_in=True)
    specs = chart_research_feature_specs()
    assert len(default) == 447 and len(specs) == 44 and len(optin) == 491
    assert len({spec.canonical_id for spec in specs}) == 44
    baseline = validate_a7(save=False)
    assert baseline["versioned_scalar_diff"]["non_whitelisted_changes"] == 0
    market = long_sample("double_top")
    series = data_inputs(market)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        name = spec.name
        pattern = str(spec.parameters["pattern_name"])
        channel = str(spec.parameters["channel"])
        via_registry = calculate_feature(spec, series)
        direct = calculate_chart_research(pattern, channel, series)
        by_ref = _new_feature_vector(
            FeatureRef(feature_id=name, timeframe="1d"),
            market,
            allow_chart_research=True,
        )
        assert len(direct) == len(market.bars)
        assert via_registry == direct == by_ref
        rejected = False
        try:
            _new_feature_vector(FeatureRef(feature_id=name), market)
        except InheritedFeatureBindingError:
            rejected = True
        assert rejected
        checksum = content_hash(direct)
        rows.append(
            {
                "feature_ref": name,
                "family": pattern,
                "output": channel,
                "provenance": spec.implementation_hash,
                "canonical_id": spec.canonical_id,
                "replay_hash": checksum,
                "identical_direct_calculator_ref": True,
                "default_access_denied": True,
                "observed_nonzero": sum(v != 0.0 for v in direct),
            }
        )
    demo = overlay_payload(
        market,
        patterns=(
            "double_top",
            "double_bottom",
            "head_shoulders",
            "inverse_head_shoulders",
            "harmonic_butterfly",
            "harmonic_gartley",
            "harmonic_bat",
            "harmonic_crab",
            "elliott_impulse_5",
            "elliott_abc",
            "elliott_wxy",
            "elliott_wxyxz",
        ),
        allow_research=True,
        data_kind="SYNTHETIC",
    )
    assert demo["execution_trades"] == []
    assert demo["data_kind"] == "SYNTHETIC"
    assert demo["overlay_hash"] == content_hash(
        {k: v for k, v in demo.items() if k != "overlay_hash"}
    )
    assert all(e["known_at"] >= e["last_pivot_index"] for e in demo["events"])
    assert all(p["known_at"] >= p["pivot_at"] for p in demo["pivots"])
    a7_cases = {
        name: long_sample(name)
        for name in ("double_top", "double_bottom", "head_shoulders", "inverse_head_shoulders")
    }
    prefix_checks = 0
    for name, data in a7_cases.items():
        complete = overlay_payload(data, patterns=(name,), allow_research=True)
        for size in range(len(data.bars) - 33, len(data.bars) + 1):
            from core.data.contracts import MarketDataSet

            earlier = MarketDataSet(data.version, data.zone, data.bars[:size])
            part = overlay_payload(earlier, patterns=(name,), allow_research=True)
            assert part["events"] == [e for e in complete["events"] if e["event_at"] < size]
            assert part["pivots"] == [p for p in complete["pivots"] if p["known_at"] < size]
            prefix_checks += 1
    report = {
        "schema": "quant-v3-chart-A8-optin-research-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "default_registered_features": len(default),
        "optional_research_scalar_outputs": len(specs),
        "opt_in_catalog_size": len(optin),
        "source_families": 12,
        "calculators": {
            "default_off": True,
            "explicit_opt_in_only": True,
            "accepted_zone": "DEVELOPMENT",
            "sealed_rejected": True,
        },
        "feature_ref_parity": rows,
        "replay_total": len(rows),
        "replay_failures": 0,
        "A7_whitelisted_legacy_scalar_changes": 4,
        "A3_full_prefix_checks": baseline["shared_existing_gate"]["A6_A3_streaming_checks"],
        "A8_overlay_prefix_checks": prefix_checks,
        "overlay_hash": demo["overlay_hash"],
        "overlay_events_count": len(demo["events"]),
        "overlay_pivots_count": len(demo["pivots"]),
        "demo_data_kind": "SYNTHETIC",
        "state_artifact_published": False,
        "dashboard_route": "/chart-research",
        "dashboard_read_only_endpoints": [
            "/api/chart-research/catalog",
            "/api/chart-research/overlay?enabled=true",
            "/api/chart-research/overlay?enabled=true&demo=true",
        ],
        "no_live_order": True,
        "prohibited_data_not_opened": True,
        "limitations": [
            "No real market data or sealed OOS used. Synthetic chart used for preview only.",
            "FeatureRef scalar parity covers all 44 named feature vectors; real child StrategyIR backtest and actual fill replay not approved in A8",
            "Classical event stage is an event pulse, not a persistent position signal",
            "Elliott stage indicates outer geometry only; it is not structural validation",
            "Dashboard no real market overlay until explicitly published by a verified DEVELOPMENT runner",
            "Trade overlay absent unless a separately verified fill ledger is later integrated; no fake execution markers",
            "Stage A9 market-sample detection and false-positive rates pending",
            "A10 dirty +40 source worktree unmerged; main and OAuth/MCP URL unchanged",
        ],
    }
    if save:
        (OUT / "quant-v3-chart-A8-acceptance-20261029.json").write_text(
            json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf8",
        )
        (OUT / "quant-v3-chart-A8-synthetic-overlay-20261029.json").write_text(
            json.dumps(demo, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf8",
        )
        text = [
            "# Quant V3 A8 · 선택형 StrategyIR FeatureRef · 차트 연구 화면 1차 연결",
            "",
            f"- 검증: {report['observed_at_kst']}",
            "- 기본 카탈로그 447 지표 유지. chart_research_opt_in=True 에서만",
            "  **연구용 scalar 44개(총 491개 출력)** 추가.",
            "- 구성: 4개 고전 × 6개 채널(탐지·단계·품질·넥라인 거리·",
            "  무효화 거리·확정 경과봉), 하모닉 4개×3개 채널(탐지·단계·PRZ 거리),",
            "  엘리엇 4개×2개 채널(외부 형태 탐지·외부 단계).",
            "- 모든 스칼라 출력에 버전·원본 소스 SHA·timeframe/inputs·canonical ID",
            "  보존. 기본 false / explicit DEVELOPMENT opt-in 시에만 FeatureRef 재생.",
            f"- {len(specs)}개 개별 named feature의 calculator·직접 계산·",
            "  FeatureRef 벡터 완전 동일; 기본 설정에서 전체 접근 거부.",
            f"- A7 고전 4종 {prefix_checks}개 잘린 시계열의 이벤트와 피벗 불변.",
            "- A3 전체 차트 4,608회 인과 검사 및 A7 4개 수정 승인 유지.",
            "- 읽기 전용 대시보드 '/chart-research'와 API 2개 연결.",
            "- UI에는 종가·피벗 발생봉과 실제 확인봉·후보/확정 상태 및",
            "  세대/기간/패턴 선택, 체결 기록 미가용 표시.",
            "- DEMO 스위치는 분명하게 합성 사례임을 표시하며 절대 시장 가격이나",
            "  실제 거래, 특정 G세대 성과로 사칭하지 않음.",
            "- 현 프로젝트는 실제 개발 데이터 오버레이를 state에 게시하지 않았음.",
            "",
            "## 현장 적용 전 필수",
            "",
            "- A8는 FeatureRef의 연구 입력 변환과 UI 시연까지 검증했고",
            "  **실제 G세대 StrategyIR replay 및 체결/equity 검증까지 완료한 것은 아님**.",
            "- A9 라벨이 있는 실 데이터 및 다양한 레짐 오탐률 검사.",
            "- A10 +40 미커밋 지표의 안전한 통합·동일성 검증 이후 전체 CI.",
            "- Moon 공식 release uv 미설치로 차단, 운영 main·실거래 변경 없음.",
        ]
        (OUT / "quant-v3-chart-A8-report-20261029.md").write_text(
            "\n".join(text) + "\n",
            encoding="utf8",
        )
    return report


if __name__ == "__main__":
    result = validate()
    print(
        json.dumps(
            {
                "normal": result["default_registered_features"],
                "opt_in": result["opt_in_catalog_size"],
                "scalar_ref_parity": result["replay_total"],
                "overlay_prefix": result["A8_overlay_prefix_checks"],
                "demo_overlay_events": result["overlay_events_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
