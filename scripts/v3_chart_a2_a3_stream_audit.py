# ruff: noqa: E501  # Audited rule descriptions and URLs remain verbatim.
"""A2 primary-source rule comparison and A3 no-hindsight scalar replay gates.

Read-only OHLCV synthetic probes. No OOS, no orders, no strategy generations.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from core.features.chart_patterns import PATTERNS, calculate_chart_pattern

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"
CHART = ROOT / "core/features/chart_patterns.py"

# Each rule links a concrete checked source URL; proprietary IP code is not reused.
# Status means source comparison, not an official license or market-profit certification.
HARMONIC_GARTLEY = "https://harmonictrader.com/harmonic-patterns/gartley-pattern/"
HARMONIC_BUTTERFLY = "https://harmonictrader.com/harmonic-patterns/butterfly-pattern/"
HARMONIC_BAT = "https://harmonictrader.com/harmonic-patterns/bat-pattern/"
HARMONIC_CRAB = "https://harmonictrader.com/harmonic-patterns/crab-pattern/"
HARMONIC_ORIGIN = "https://harmonictrader.com/harmonicpatternorigin/"
ELLIOTT_IMPULSE = "https://www.elliottwave.com/waveopedia/impulse/"
ELLIOTT_ZIGZAG = "https://www.elliottwave.com/waveopedia/zigzags/"
ELLIOTT_FLAT = "https://www.elliottwave.com/waveopedia/flats/"
ELLIOTT_CORRECTIVE = "https://www.elliottwave.com/waveopedia/corrective-waves/"
REPO_CHART = (
    "https://github.com/kankinku/AutoResearchFinance_v2/blob/"
    "d88b197a7f707dc443ee70b4fd4408f9a3be1d3a/core/features/chart_patterns.py"
)

A2_RULES: dict[str, dict[str, Any]] = {
    "harmonic_gartley": {
        "source_urls": [HARMONIC_GARTLEY, HARMONIC_ORIGIN],
        "reference_constraints": {
            "AB/XA": "0.618, tight ±3% of ratio as source describes",
            "AD/XA": "0.786 retracement",
            "BC/AB": "C retracement approximately 0.382..0.886",
            "CD/BC": "1.13..1.618 extension",
            "CD/AB": "AB=CD or 1.27 AB=CD in PRZ",
            "PRZ": "0.786 XA, BC extension and AB=CD confluence",
        },
        "formula_deltas": {
            "cd_to_bc": {
                "status": "MISSING_SOURCE_GATE",
                "current": "unchecked",
                "source": "1.13..1.618",
            },
            "cd_to_ab": {
                "status": "MISSING_SOURCE_GATE",
                "current": "unchecked",
                "source": "AB=CD/1.27",
            },
            "PRZ": {
                "status": "MISSING_SOURCE_GATE",
                "current": "unchecked",
                "source": "multi-leg confluence",
            },
        },
    },
    "harmonic_butterfly": {
        "source_urls": [HARMONIC_BUTTERFLY],
        "reference_constraints": {
            "AB/XA": "0.786 retracement mandatory",
            "XD/XA": "0.27 beyond X (equivalent 1.27 XA measured from A)",
            "CD/BC": "typically 1.618..2.24 extension",
            "CD/AB": "AB=CD or alternate 1.27/1.618 pattern",
            "PRZ": "XA 1.27 with BC and AB=CD zone confluence",
        },
        "formula_deltas": {
            "cd_to_bc": {
                "status": "TOO_PERMISSIVE",
                "current": ">=1.13",
                "source": "1.618..2.24 typical",
            },
            "cd_to_ab": {
                "status": "MISSING_SOURCE_GATE",
                "current": "unchecked",
                "source": "AB=CD or alternate",
            },
            "PRZ": {
                "status": "MISSING_SOURCE_GATE",
                "current": "unchecked",
                "source": "multi-leg confluence",
            },
        },
    },
    "harmonic_bat": {
        "source_urls": [HARMONIC_BAT],
        "reference_constraints": {
            "AB/XA": "less than 0.618, preferred 0.382 or 0.50",
            "AD/XA": "0.886 retracement",
            "CD/BC": "at least 1.618",
            "PRZ": "0.886 XA with BC extension and AB=CD",
        },
        "formula_deltas": {
            "cd_to_bc": {
                "status": "MISSING_SOURCE_GATE",
                "current": "unchecked",
                "source": ">=1.618",
            },
            "b_range": {
                "status": "RESTRICTIVE_SUBTYPE",
                "current": "0.382..0.50 with ±0.09",
                "source": "B <0.618, typical 0.382/0.50",
            },
        },
    },
    "harmonic_crab": {
        "source_urls": [HARMONIC_CRAB],
        "reference_constraints": {
            "AB/XA": "typically 0.382..0.618",
            "XD/XA": "0.618 beyond X (equivalent XA 1.618 extension)",
            "CD/BC": "extreme 2.618, 3.14, 3.618 source examples",
            "PRZ": "1.618 XA with extreme BC extension",
        },
        "formula_deltas": {
            "cd_to_bc": {
                "status": "MISSING_SOURCE_GATE",
                "current": "unchecked",
                "source": "extreme BC extension",
            },
            "PRZ": {
                "status": "MISSING_SOURCE_GATE",
                "current": "unchecked",
                "source": "multi-leg confluence",
            },
        },
    },
    "elliott_impulse_5": {
        "source_urls": [ELLIOTT_IMPULSE],
        "reference_constraints": {
            "wave_2": "not beyond wave 1 origin",
            "wave_3": "not shortest actionary wave",
            "wave_4": "not into wave 1 price territory for ordinary impulse",
            "substructure": "5-3-5-3-5",
            "count": "five actionary/reactionary alternating waves",
        },
        "formula_deltas": {
            "subwaves": {
                "status": "NOT_VERIFIED",
                "current": "outer 6 pivot extrema only",
                "source": "substructure 5-3-5-3-5",
            },
            "partial_count": {
                "status": "NOT_IMPLEMENTED",
                "current": "full 5 only",
                "source": "intermediate labeling alternatives",
            },
        },
    },
    "elliott_abc": {
        "source_urls": [ELLIOTT_ZIGZAG, ELLIOTT_FLAT],
        "reference_constraints": {
            "zigzag": "A-B-C 5-3-5",
            "flat": "A-B-C 3-3-5, distinct from zigzag",
            "direction": "counter-trend relative to higher degree",
        },
        "formula_deltas": {
            "subwaves": {
                "status": "NOT_VERIFIED",
                "current": "4 outer pivots",
                "source": "5-3-5 vs 3-3-5 depending family",
            },
            "trend_context": {
                "status": "NOT_VERIFIED",
                "current": "no higher-degree context",
                "source": "corrective direction",
            },
        },
    },
    "elliott_wxy": {
        "source_urls": [ELLIOTT_ZIGZAG, ELLIOTT_CORRECTIVE],
        "reference_constraints": {
            "WXY": "two correction groups W and Y, linked by corrective X",
            "subwaves": "corrective group internal structure must be verified",
        },
        "formula_deltas": {
            "structure": {
                "status": "OVERSIMPLIFIED",
                "current": "3 alternating outer ABC zigzag groups",
                "source": "group W and Y connected by X, subwaves needed",
            },
        },
    },
    "elliott_wxyxz": {
        "source_urls": [ELLIOTT_ZIGZAG, ELLIOTT_CORRECTIVE],
        "reference_constraints": {
            "WXYXZ": "three correction groups W/Y/Z separated by two X corrections",
            "subwaves": "corrective group internal structures verified separately",
        },
        "formula_deltas": {
            "structure": {
                "status": "OVERSIMPLIFIED",
                "current": "5 alternating ABC outer groups",
                "source": "two X connectors and proper degree decomposition",
            },
        },
    },
}
for _name in ("double_top", "double_bottom", "head_shoulders", "inverse_head_shoulders"):
    A2_RULES[_name] = {
        "source_urls": [REPO_CHART],
        "reference_constraints": {
            "status": "in-house geometric heuristic, NOT externally validated rule standard",
            "candidate": "swing geometry only",
            "confirmation": "neckline break not implemented",
        },
        "formula_deltas": {
            "neckline": {
                "status": "NOT_IMPLEMENTED",
                "current": "shape event only",
                "source": "pattern confirmation required by A7",
            },
            "invalidation": {
                "status": "NOT_IMPLEMENTED",
                "current": "no lifecycle",
                "source": "separate canceled stage",
            },
        },
    }
A2_RULES["inverse_head_shoulders"]["formula_deltas"]["mirror_symmetry"] = {
    "status": "CONFIRMED_BUG",
    "current": "flat shoulders equal head -> +1",
    "source": "must not assert head dominance with equal-price troughs",
}
assert set(A2_RULES) == set(PATTERNS)


def build_scenarios(
    count: int = 128,
) -> dict[str, dict[str, tuple[float | None, ...]]]:
    """Only deterministic synthetic test bars; none are sealed or real-market data."""
    close = [100.0 + 0.05 * i + 8 * math.sin(i / 3.2) + 2 * math.sin(i / 9.7) for i in range(count)]
    high = [c + 1.35 for c in close]
    low = [c - 1.4 for c in close]
    normal: dict[str, tuple[float | None, ...]] = {
        "high": tuple(high),
        "low": tuple(low),
        "close": tuple(close),
    }
    inverted: dict[str, tuple[float | None, ...]] = {
        "high": tuple(600 - z for z in low),
        "low": tuple(600 - z for z in high),
        "close": tuple(600 - z for z in close),
    }
    stressed: dict[str, list[float | None]] = {
        "high": cast(list[float | None], high.copy()),
        "low": cast(list[float | None], low.copy()),
        "close": cast(list[float | None], close.copy()),
    }
    for j in range(min(12, count)):
        stressed["high"][j] = 100.0
        stressed["low"][j] = 100.0
        stressed["close"][j] = 100.0
    if count > 62:
        stressed["close"][62] = None
    if count > 80:
        stressed["high"][80] = float("nan")
    if count > 95:
        stressed["high"][95] = float(cast(float, stressed["low"][95])) - 2
    return {
        "oscillating": normal,
        "inverted": inverted,
        "flat_missing_invalid": {key: tuple(vals) for key, vals in stressed.items()},
    }


def _confirmation_event_gate(series: dict[str, tuple[float | None, ...]], t: int, c: int) -> bool:
    # Independent basic event-time test, NOT independent pattern rule oracle.
    pivot = t - c
    if pivot < c or t >= len(series["close"]):
        return False
    positions = list(range(pivot - c, t + 1))
    for i in positions:
        h, low_value, close = (series[k][i] for k in ("high", "low", "close"))
        if (
            h is None
            or low_value is None
            or close is None
            or any(not math.isfinite(float(x)) for x in (h, low_value, close))
            or float(h) < float(low_value)
            or not float(low_value) <= float(close) <= float(h)
        ):
            return False
    highs = [float(series["high"][i]) for i in positions]  # type: ignore[arg-type]
    lows = [float(series["low"][i]) for i in positions]  # type: ignore[arg-type]
    high_confirmed = highs[c] == max(highs) and highs.count(highs[c]) == 1
    low_confirmed = lows[c] == min(lows) and lows.count(lows[c]) == 1
    return high_confirmed != low_confirmed


def stream_prefix_gate(
    pattern: str,
    series: dict[str, tuple[float | None, ...]],
    *,
    confirmation_bars: int = 2,
) -> dict[str, Any]:
    """Replay every single bar as if this were a real-time historical run."""
    if pattern not in PATTERNS:
        raise ValueError("unknown chart pattern")
    n = len(series["close"])
    outcome: dict[str, Any] = {
        "bars": n,
        "checkpoints": 0,
        "prefix_mismatches": 0,
        "timestamp_violations": 0,
        "runtime_error": None,
        "nonzero_events": 0,
        "event_times": [],
        "min_eligible_signal_at": 2 * confirmation_bars,
    }
    try:
        full = calculate_chart_pattern(
            series,
            pattern,
            lookback=160,
            confirmation_bars=confirmation_bars,
        )
        for t in range(n):
            prefix = {key: value[: t + 1] for key, value in series.items()}
            observed = calculate_chart_pattern(
                prefix,
                pattern,
                lookback=160,
                confirmation_bars=confirmation_bars,
            )
            outcome["checkpoints"] += 1
            if observed != full[: t + 1]:
                outcome["prefix_mismatches"] += 1
            if full[t] != 0.0:
                outcome["nonzero_events"] += 1
                outcome["event_times"].append(t)
                if t < 2 * confirmation_bars or not _confirmation_event_gate(
                    series, t, confirmation_bars
                ):
                    outcome["timestamp_violations"] += 1
        if any(value not in (-1.0, 0.0, 1.0) for value in full):
            outcome["runtime_error"] = "NON_FINITE_OR_NON_SCALAR_EVENT"
    except (ValueError, KeyError, IndexError, TypeError, ZeroDivisionError) as exc:
        outcome["runtime_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    return outcome


def reproduce(*, strict: bool = True, short: bool = False) -> dict[str, Any]:
    """Only real audit version (strict=True) writes stable JSON/MD evidence."""
    baseline = json.loads(
        (OUT / "quant-v3-chart-A2-formula-source-matrix-20261029.json").read_text()
    )
    proposed = [
        row["name"] for row in baseline["patterns"] if row["status"] == "CANDIDATE_NOT_IMPORTED"
    ]
    rules = []
    for name in PATTERNS:
        cfg = A2_RULES[name]
        rules.append(
            {
                "name": name,
                "research_status": "HEURISTIC_AUDIT_PENDING_SOURCE_PARITY",
                "source_urls": cfg["source_urls"],
                "reference_constraints": cfg["reference_constraints"],
                "formula_deltas": cfg["formula_deltas"],
                "commercial_license_verdict": (
                    "NOT_CLEARED_TRADEMARK_AND_SOURCE_REVIEW_REQUIRED"
                    if name.startswith("harmonic_")
                    else "IN_HOUSE_RULE_NOT_EXTERNAL_LICENSE_GRANT"
                ),
            }
        )
    a2 = {
        "schema": "quant-v3-chart-A2-deep-source-gate-v1",
        "registered_rules": rules,
        "proposed_not_implemented": proposed,
        "counts": {
            "registered_audited": len(rules),
            "deferred_unimplemented": len(proposed),
            "harmonic_require_permission_review": 4,
            "newly_imported": 0,
        },
        "source_code_sha256": hashlib.sha256(CHART.read_bytes()).hexdigest(),
        "notes": [
            "Source web docs verified for specified ratio interpretations; this is a documentary rule audit, not independent computational parity",
            "Harmonic pattern naming/trademark and commercial use may require formal permission. Never assume permission from publicly viewable pages.",
            "Elliott wave correctives require internal 5-3-5 / 3-3-5 subwaves not inferred from outer four pivots.",
            "A3 future-leak gate does not prove correct market pattern labeling or actual trading profitability.",
        ],
    }
    n = 60 if short else 128
    scenarios = {"oscillating": build_scenarios(n)["oscillating"]} if short else build_scenarios(n)
    cohorts: list[dict[str, Any]] = []
    for label, series in scenarios.items():
        signals = {p: stream_prefix_gate(p, series) for p in PATTERNS}
        cohorts.append({"label": label, "bars": n, "patterns": signals})
    total = [row for group in cohorts for row in group["patterns"].values()]
    counts = {
        "regimes": len(cohorts),
        "patterns": len(PATTERNS),
        "prefix_mismatches": sum(item["prefix_mismatches"] for item in total),
        "timestamp_violations": sum(item["timestamp_violations"] for item in total),
        "runtime_errors": sum(item["runtime_error"] is not None for item in total),
        "checkpoints": sum(item["checkpoints"] for item in total),
        "zero_event_pattern_regime_pairs": sum(item["nonzero_events"] == 0 for item in total),
        "total_emitted_events": sum(item["nonzero_events"] for item in total),
    }
    a3 = {
        "schema": "quant-v3-chart-A3-full-streaming-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "chart_branch": "research/v3-chart-audit-20261029",
        "source_code_sha256": a2["source_code_sha256"],
        "pattern_names": list(PATTERNS),
        "confirmation_bars": 2,
        "lookback": 160,
        "regimes": cohorts,
        "summary": counts,
        "gate_scope": "all 12 scalar patterns x full bar-by-bar prefix for 3 synthetic price regimes",
        "not_tested": [
            "real-market price data, trading profit, independent OOS, actual next-open execution",
            "alternative confirmation_bar values and intra-bar execution",
            "named pattern label correctness and full PRZ formulas, known A1 false positives",
        ],
    }
    if strict:
        assert counts["prefix_mismatches"] == 0, counts
        assert counts["timestamp_violations"] == 0, counts
        assert counts["runtime_errors"] == 0, counts
        OUT.joinpath("quant-v3-chart-A2-verified-ratio-rules-20261029.json").write_text(
            json.dumps(a2, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        OUT.joinpath("quant-v3-chart-A3-causal-stream-gate-20261029.json").write_text(
            json.dumps(a3, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        lines = [
            "# Quant V3 A2 수식 정밀검토 · A3 봉 단위 미래참조 검사",
            "",
            f"- 검사 시각: {a3['observed_at_kst']}",
            "- A2: 기존 패턴 12종의 원본 규칙/현재 구현 편차, 미구현 18종 보류를 구별.",
            "- 4종 하모닉: 주요 XA/AB/BC/CD 비율 누락 확인. 원본 공개 페이지에서",
            "  확인한 비율은 법적 사용권 또는 구현 수치 일치 증명이 아니므로 별도",
            "  상업적 이용 검토 전 승인된 제품 기능으로 승격하지 않는다.",
            "- 버터플라이는 X 기준 0.27 XA 초과(=A 기준 1.27 XA)라는",
            "  구현 표현과 공식 표현의 기준점 차이를 해소했다. 실제 결함은",
            "  CD/BC 하한이 너무 완화되고 상한/AB=CD/PRZ 합치기를 미검사하는 점.",
            "- 가틀리는 CD/BC 1.13~1.618과 AB=CD 누락이 확인된 오탐 위험.",
            "- 배트/크랩도 정의를 구성하는 BC 확장을 판정하지 않아 오탐 위험.",
            "- 엘리엇 5파는 바깥 6개 피벗만 검사하여 5-3-5-3-5 내부파 미검증.",
            "- ABC/WXY는 Zigzag와 Flat, 복합 조정 구분이 되지 않음.",
            "",
            "## A3 스트리밍 전체 길이별 재연산 실측",
            "",
            f"- 합성 시나리오: {counts['regimes']}개, 각 {n}봉",
            f"- 차트 계산기: {len(PATTERNS)}개, 전체 접두부 평가 {counts['checkpoints']}회",
            f"- 과거 신호 불일치: {counts['prefix_mismatches']}건",
            f"- 피벗 확정 시점 이전의 신호: {counts['timestamp_violations']}건",
            f"- 계산 예외·비정상 출력: {counts['runtime_errors']}건",
            f"- 패턴·레짐 조합 중 이벤트 0: {counts['zero_event_pattern_regime_pairs']} / {len(total)}",
            f"- 총 이벤트 수: {counts['total_emitted_events']}",
            "",
            "## 범위 한계 및 후속",
            "",
            "- A3은 bar-close 접두부·피벗 우측 확정 시간의 누수 부재를 확인했을 뿐,",
            "  캔들 자체에서 같은 봉 종가를 읽어 미래로 앞당긴 주문 실행이 없다는",
            "  사실까지 독립 테스트한 것은 아니다. StrategyIR next-open 실행은 추가 확인 필요.",
            "- 원본 비율 결함과 역헤드앤숄더 동률 오탐 2건은 기존 XFAIL 보존.",
            "- A2 하모닉 IP/상표·허가 및 추가 후보 18개 수식 오라클은 계속 미완료.",
            "- 다음 실행: A3 개발용 StrategyIR 실제 재생·희귀 양성 종합경로,",
            "  A4 공통 피벗 메타데이터, A5/A7 오류 수정(테스트 선행).",
            "",
            "## 신뢰 가능한 원본 링크",
            "",
            *[
                f"- {url}"
                for url in sorted(
                    {
                        url
                        for cfg in A2_RULES.values()
                        for url in cfg["source_urls"]
                        if not url.startswith("https://github.com/")
                    }
                )
            ],
        ]
        OUT.joinpath("quant-v3-chart-A2-A3-source-causality-report-20261029.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    return a3


if __name__ == "__main__":
    result = reproduce()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
