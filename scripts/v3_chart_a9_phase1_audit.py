# ruff: noqa: E501  # Preserve full acceptance criteria and report text.
"""A9 phase-1 synthetic robustness and opt-in FeatureRef coverage evidence.

NEVER reads real/sealed/OOS market data; all scenarios are deterministic and
invented here. Not a trading-backtest or a strategy performance experiment.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from core.features.chart_patterns import PATTERNS, calculate_chart_pattern
from core.features.classical_lifecycle import assess_classical_candidate, calculate_classical_events
from core.features.elliott_structure import (
    analyze_abc,
    analyze_combination,
    analyze_impulse,
)
from core.features.harmonic_geometry import assess_harmonic
from core.features.registry import research_feature_specs
from research.chart_pattern_bridge import (
    calculate_chart_research,
    chart_research_feature_specs,
)
from tests.core.test_v3_chart_a5_harmonic_geometry import (
    INVALID,
    VALID,
    interpolate_ohlc,
)
from tests.core.test_v3_chart_a5_harmonic_geometry import (
    points as harmonic_points,
)
from tests.core.test_v3_chart_a6_elliott_structure import (
    pivots as elliott_points,
)
from tests.core.test_v3_chart_a6_elliott_structure import (
    subdivisions,
)
from tests.core.test_v3_chart_a7_classical_lifecycle import (
    EXAMPLES,
    SHAPES,
)
from tests.core.test_v3_chart_a7_classical_lifecycle import (
    interpolate_ohlc as classical_ohlc,
)
from tests.core.test_v3_chart_a7_classical_lifecycle import (
    points as classical_points,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"
RANGE_NAMES = (
    "oscillating",
    "uptrend",
    "downtrend",
    "shock",
    "high_volatility",
    "quiet_low_liquidity",
)


def synthetic_scenarios(n: int = 144) -> dict[str, dict[str, tuple[float, ...]]]:
    """Six reproducible OHLCV regimes; volume is not an A8 feature input."""
    results: dict[str, dict[str, tuple[float, ...]]] = {}
    for name in RANGE_NAMES:
        close: list[float] = []
        volume: list[float] = []
        for i in range(n):
            phase = i / 5.0
            drift = 0.0
            oscillation = 5 * math.sin(phase) + 2 * math.sin(i / 11)
            shock = 0.0
            if name == "uptrend":
                drift = 0.38 * i
            elif name == "downtrend":
                drift = -0.3 * i
            elif name == "high_volatility":
                oscillation = 17 * math.sin(i / 2.6) + 5 * math.sin(i / 1.7)
            elif name == "quiet_low_liquidity":
                oscillation = 0.8 * math.sin(i / 6)
            elif name == "shock":
                shock = -27 if 60 <= i <= 75 else -14 if 76 <= i <= 88 else 0
            value = 120 + drift + oscillation + shock
            close.append(value)
            volume.append(10.0 if name == "quiet_low_liquidity" else 1000.0)
        h = tuple(c + (0.2 if name == "quiet_low_liquidity" else 1.1) for c in close)
        low = tuple(c - (0.2 if name == "quiet_low_liquidity" else 1.1) for c in close)
        results[name] = {"high": h, "low": low, "close": tuple(close), "volume": tuple(volume)}
    return results


def goldens() -> dict[str, Any]:
    """Labeled geometrical fixtures: not natural-market ground truth."""
    harmonic_positive = {}
    harmonic_negative = {}
    for name, prices in VALID.items():
        positive = assess_harmonic(harmonic_points(prices), name)
        negative = assess_harmonic(harmonic_points(INVALID[name]), name)
        assert positive.accepted and positive.direction == 1
        assert not negative.accepted
        series = calculate_chart_pattern(interpolate_ohlc(prices), name)
        assert series[26] == 1 and sum(v != 0 for v in series) == 1
        rejected = calculate_chart_pattern(interpolate_ohlc(INVALID[name]), name)
        assert not any(rejected)
        harmonic_positive[name] = {"geom": 1, "stream_at": 26}
        harmonic_negative[name] = {"geom": 0, "stream_events": 0}
    classical_positive = {}
    classical_negative = {}
    for name, outer in SHAPES.items():
        positive = assess_classical_candidate(outer, name)
        assert positive is not None
        path = classical_ohlc(EXAMPLES[name])
        events = calculate_classical_events(path, name)
        assert [e.stage for e in events] == ["CANDIDATE", "CONFIRMED"]
        classical_positive[name] = {
            "candidate_at": events[0].known_at,
            "confirmed_at": events[1].known_at,
            "confirmation_lag_bars": events[1].known_at - events[0].known_at,
        }
        if name == "inverse_head_shoulders":
            invalid = classical_points((100.0, 110.0, 100.0, 110.0, 100.0), start_high=False)
        else:
            invalid = outer[:-1]
        assert assess_classical_candidate(invalid, name) is None
        classical_negative[name] = {"geometry_candidate": False}
    impulse = elliott_points([100, 110, 105, 122, 115, 130])
    zigzag = elliott_points([100, 110, 105, 116])
    flat = elliott_points([100, 110, 100.8, 111.5])
    combo = elliott_points(
        [
            100,
            110,
            105,
            116,
            106,
            111,
            99,
            110,
            105,
            116,
            106,
            111,
            99,
            110,
            105,
            116,
        ]
    )
    components = tuple(subdivisions(combo[3 * i : 3 * i + 4], (5, 3, 5)) for i in range(5))
    elliott_positive = {
        "elliott_impulse_5": analyze_impulse(
            impulse, subwaves=subdivisions(impulse, (5, 3, 5, 3, 5))
        ).structurally_verified,
        "elliott_abc_zigzag": analyze_abc(
            zigzag, subdivisions(zigzag, (5, 3, 5))
        ).structurally_verified,
        "elliott_abc_flat": analyze_abc(flat, subdivisions(flat, (3, 3, 5))).structurally_verified,
        "elliott_wxy": analyze_combination(
            combo[:10], components[:3], count=3
        ).structurally_verified,
        "elliott_wxyxz": analyze_combination(combo, components, count=5).structurally_verified,
    }
    assert all(elliott_positive.values())
    wrong = elliott_points([100, 110, 105, 111, 109, 128])
    negative = analyze_impulse(wrong)
    assert negative.stage == "INVALIDATED" and "WAVE3_SHORTEST" in negative.violations
    return {
        "harmonic_positive": harmonic_positive,
        "harmonic_negative": harmonic_negative,
        "classical_positive": classical_positive,
        "classical_negative": classical_negative,
        "elliott_structure_positive": elliott_positive,
        "elliott_structure_negative": {
            "impulse_wave3_shortest": negative.stage,
        },
    }


def run_audit(*, n: int = 144, save: bool = True) -> dict[str, Any]:
    standard = research_feature_specs()
    optin = research_feature_specs(chart_research_opt_in=True)
    extras = chart_research_feature_specs()
    assert len(standard) == 487 and len(extras) == 44 and len(optin) == 531
    assert set(s.name for s in extras).isdisjoint(s.name for s in standard)
    samples = synthetic_scenarios(n)
    by_name = {s.name: s for s in extras}
    rows: list[dict[str, Any]] = []
    timings: list[float] = []
    prefix_checks = 0
    leakage = 0
    for regime, data in samples.items():
        inputs = {key: data[key] for key in ("high", "low", "close")}
        full: dict[str, tuple[float, ...]] = {}
        for name, spec in by_name.items():
            started = perf_counter()
            values = calculate_chart_research(
                str(spec.parameters["pattern_name"]),
                str(spec.parameters["channel"]),
                inputs,
            )
            timings.append((perf_counter() - started) * 1000)
            assert len(values) == n
            assert all(math.isfinite(x) for x in values)
            full[name] = values
            zeros = sum(v == 0 for v in values)
            channel = str(spec.parameters["channel"])
            rows.append(
                {
                    "regime": regime,
                    "name": name,
                    "family": str(spec.parameters["pattern_name"]),
                    "channel": channel,
                    "bars": n,
                    "nonzero": n - zeros,
                    "zero_ratio": zeros / n,
                    "events_per_1000_bars": (
                        sum(v != 0 for v in values) * 1000 / n if channel == "detected" else None
                    ),
                    "unique_values": len(set(values)),
                    "hash": hashlib.sha256(
                        json.dumps(values, separators=(",", ":")).encode()
                    ).hexdigest(),
                }
            )
        # No-lookahead replay for sampled checkpoints across all 44 channels,
        # not just full-run whole-vector equality.
        for cutoff in (32, 64, 96, n):
            if cutoff > n:
                continue
            partial = {key: vec[:cutoff] for key, vec in inputs.items()}
            for name, spec in by_name.items():
                found = calculate_chart_research(
                    str(spec.parameters["pattern_name"]),
                    str(spec.parameters["channel"]),
                    partial,
                )
                prefix_checks += 1
                if found != full[name][:cutoff]:
                    leakage += 1
    grouped = Counter(
        row["family"] for row in rows if row["channel"] == "detected" and row["nonzero"] == 0
    )
    sorted_ms = sorted(timings)
    evidence: dict[str, Any] = {
        "schema": "quant-v3-chart-A9-phase1-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "scope": "SYNTHETIC_ONLY_PHASE1_NOT_COMPLETE_A9",
        "registered_default": len(standard),
        "registered_research_opt_in": len(optin),
        "research_scalar_channels": len(extras),
        "pattern_families": len(PATTERNS),
        "scenarios": list(samples),
        "bars_each": n,
        "scalar_rows": rows,
        "golden_oracles": goldens(),
        "summary": {
            "scalar_vectors_evaluated": len(rows),
            "all_zero_vectors": sum(x["nonzero"] == 0 for x in rows),
            "detected_all_zero_family_regimes": dict(grouped),
            "nonfinite_values": 0,
            "prefix_checks": prefix_checks,
            "prefix_mismatches": leakage,
            "measured_vector_runtime_median_ms": sorted_ms[len(sorted_ms) // 2],
            "measured_vector_runtime_p95_ms": sorted_ms[
                min(len(sorted_ms) - 1, int(0.95 * len(sorted_ms)))
            ],
            "synth_classical_confirmation_lags": [
                r["confirmation_lag_bars"] for r in goldens()["classical_positive"].values()
            ],
        },
        "validation_layers": {
            "labeled_positive_negative": "SYNTHETIC_PASS",
            "multi_regime_price_metamorphic": "SYNTHETIC_PARTIAL",
            "missing_invalid_flats_corporate_actions": "NOT_COMPLETE",
            "strategy_parent_replay_regression": "NOT_COMPLETE",
            "independent_market_labeled_precision_recall": "NOT_AVAILABLE",
            "protected_2026_OOS": "NOT_ACCESSED",
            "full_CI_release": "NOT_RUN_UV_MISSING",
        },
        "market_precision": None,
        "market_recall": None,
        "net_profit": None,
        "known_limitations": [
            "Synthetic category low-liquidity only changes simulated volume; research OHLC inputs do not include volume",
            "Event frequency for non-event channels is not a meaningful pattern count",
            "Missing true market labels make real false positive/false negative rate unknowable",
            "Benchmark durations are one-host development probe, not production CPU/SLA",
            "Existing research-only opt-in execution and order routing remain disabled",
            "A9 other layers, real G lineage replay, sealed evaluation and release CI remain open",
        ],
    }
    assert leakage == 0
    if save:
        file = OUT / "quant-v3-chart-A9-phase1-synthetic-audit-20261029.json"
        file.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        lines = [
            "# Quant V3 A9 — 1차 합성 레짐·44채널 신호 전수 품질 검사",
            "",
            "상태: **PHASE1 ONLY**. A9 전체 종료·실시장 알파 검증·릴리스 승인 아님.",
            f"- 측정 시각: {evidence['observed_at_kst']}",
            f"- 기본 등록 {len(standard)}, 선택형 연구 출력 {len(extras)}, 선택 시 합계 {len(optin)}.",
            f"- 합성 가격 경로 {len(samples)}개 × 각 {n}봉, 입력 지표 44개.",
            f"- 출력 시계열 {len(rows)}개; 0 신호만 있는 벡터 {evidence['summary']['all_zero_vectors']}개.",
            f"- 44채널 prefix 검사 {prefix_checks}회; 과거 출력 변경 {leakage}개.",
            "- 4 하모닉 양성 + 음성 4, 4 고전 양성+음성 4, 엘리엇",
            "  구조 정답 5종 및 3파 최단 위반 1종을 별도 명명 오라클로 확인.",
            f"- 합성 고전 후보→확정 지연 {evidence['summary']['synth_classical_confirmation_lags']}봉.",
            f"- 로컬 실행 성능 중간값 {evidence['summary']['measured_vector_runtime_median_ms']:.2f}ms,",
            f"  p95 {evidence['summary']['measured_vector_runtime_p95_ms']:.2f}ms (호스트 한정, 무보증).",
            "",
            "## 명시적으로 검증하지 않은 항목",
            "",
            "- 실제 주식 레짐별 예측 정확도/재현율: 실제 라벨 데이터가 없어 계산 불가.",
            "- 2026 OOS는 연구에 사용하지 않음. 부모 G세대 StrategyIR 재생·거래 체결 미수행.",
            "- 결측/동률/수정주가·기업행위/극단 체결/전 기간 메모리 성능: 추가 A9 필요.",
            "- Low liquidity 시나리오는 거래량 입력이 없는 채널이므로 가격 유동성",
            "  효과를 입증하지 않음. 실사용 차트 출력으로 자동 승격 불가.",
            "- 릴리스 CI는 Moon의 uv 실행환경 부재가 해소되기 전까지 BLOCKED.",
            "",
            "## 다음 작업",
            "",
            "- A9 2차: 가격 단위 변환·기업행위·결측·검출 지연 경계·실제 개발",
            "  데이터 라벨 샘플/부모 replay, 이후 A10 +40 안전 병합 준비.",
            "",
        ]
        (OUT / "quant-v3-chart-A9-phase1-report-20261029.md").write_text(
            "\n".join(lines), encoding="utf8"
        )
    return evidence


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
