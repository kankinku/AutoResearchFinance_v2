# ruff: noqa: E501  # Preserve long audit evidence strings and literal source URLs.
"""Reproduce Chart V3 A0-A2 *research-only* audit from frozen worktree checkouts.

Run from the independent chart-pattern Git worktree. No production writes,
OOS reads, trading, or modified-code execution. Writes JSON/Markdown reports.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.features.calculators import calculate_feature
from core.features.catalog import semantic_feature_id
from core.features.chart_patterns import (
    PATTERNS,
    ConfirmedPivot,
    classical_shape,
    harmonic_xabcd,
)
from core.features.contracts import FeatureSpec
from core.features.registry import research_feature_specs
from scripts.v3_audit_335_features import synthetic

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path("/shared/moon-workspace/AutoResearchFinance_v3-track1-strategy-20261027")
OUT = ROOT / "docs/operations"
AVAIL = {"open", "high", "low", "close", "volume"}


def git(*args: str, root: Path = ROOT) -> str:
    cp = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return cp.stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name: str, data: dict[str, Any]) -> None:
    (OUT / name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def mkpoints(values: list[float]) -> list[ConfirmedPivot]:
    return [
        ConfirmedPivot(i, float(v), "low" if i % 2 == 0 else "high", i + 2)
        for i, v in enumerate(values)
    ]


def signals_for(
    names: list[FeatureSpec], sample: dict[str, tuple[float, ...]]
) -> dict[str, dict[str, Any]]:
    outcome = {}
    for spec in names:
        try:
            vector = calculate_feature(spec, {field: sample[field] for field in spec.inputs})
            finite = all(v is None or math.isfinite(v) for v in vector)
            outcome[spec.name] = {
                "length_ok": len(vector) == len(sample["close"]),
                "finite": finite,
                "observed_values": sum(v is not None for v in vector),
                "nonzero_events": sum(v is not None and v != 0.0 for v in vector),
                "unique_observed_values": len({v for v in vector if v is not None}),
                "prefix_last_bar_equal": vector[:-1]
                == calculate_feature(spec, {key: sample[key][:-1] for key in spec.inputs}),
                "output_signature_sha256": hashlib.sha256(
                    json.dumps(vector, allow_nan=False, separators=(",", ":")).encode()
                ).hexdigest(),
            }
        except Exception as exc:
            outcome[spec.name] = {
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            }
    return outcome


def build() -> dict[str, Any]:
    specs = research_feature_specs()
    names = {s.name for s in specs}
    assert len(specs) == len(names) == 447
    chart_names = ["chart_" + x for x in PATTERNS]
    assert len(chart_names) == 12 and set(chart_names) <= names

    bulk = json.loads((LOCAL / "core/features/bulk40_manifest.json").read_text())
    local_pinned = json.loads((LOCAL / "core/features/pandas_ta_manifest.json").read_text())
    chart_pinned = json.loads((ROOT / "core/features/pandas_ta_manifest.json").read_text())
    local_specs = json.loads(
        subprocess.run(
            [
                "/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/.venv/bin/python",
                "-c",
                "import json; from core.features.registry import research_feature_specs; "
                "print(json.dumps([s.name for s in research_feature_specs()]))",
            ],
            cwd=LOCAL,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    new40 = {r["name"] for r in bulk["entries"]}
    assert len(new40) == 40 and new40 <= set(local_specs)
    assert set(chart_names).isdisjoint(new40)
    a0: dict[str, Any] = {
        "schema": "quant-v3-chart-A0-baseline-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "chart_branch": {
            "branch": git("branch", "--show-current"),
            "sha": git("rev-parse", "HEAD"),
            "registered": len(specs),
            "conditional_ohlcv_eligible": sum(
                s.data_contract == "scalar" and set(s.inputs) <= AVAIL for s in specs
            ),
            "chart_patterns": len(chart_names),
            "new_names": sorted(chart_names),
            "working_tree_status_before_audit": "",
            "pandas_ta_pinned_entries": len(chart_pinned["entries"]),
            "source_sha": chart_pinned["source_sha"],
        },
        "local_bulk40": {
            "branch": git("branch", "--show-current", root=LOCAL),
            "sha": git("rev-parse", "HEAD", root=LOCAL),
            "registered": len(local_specs),
            "new_candidates": 40,
            "new_names": sorted(new40),
            "staged_or_uncommitted_paths": [
                "core/features/pandas_ta_manifest.json",
                "core/features/pandas_ta_pinned.py",
                "core/features/bulk40_manifest.json",
                "tests/core/test_v3_selected_bulk40.py",
            ],
            "dirty_paths_observed": git("status", "--porcelain=v1", root=LOCAL).splitlines(),
            "file_hash_sha256": {
                name: sha256(LOCAL / name)
                for name in (
                    "core/features/pandas_ta_manifest.json",
                    "core/features/pandas_ta_pinned.py",
                    "core/features/bulk40_manifest.json",
                    "tests/core/test_v3_selected_bulk40.py",
                )
            },
            "pandas_ta_pinned_entries": len(local_pinned["entries"]),
        },
        "cross_branch_merge": "NOT_DONE",
        "potential_union_if_no_additional_collision": 487,
        "union_value_is_approved_or_tested": False,
        "frozen_baseline_registered": 435,
        "protected_operations": {
            "live_orders": "NOT_RUN",
            "sealed_OOS": "NOT_READ",
            "research_generation": "NOT_RUN",
            "production_main": "UNCHANGED",
            "existing_research_ledger": "UNCHANGED",
        },
    }
    write("quant-v3-chart-A0-baseline-20261029.json", a0)

    source, _ = synthetic(480)
    eligible = [s for s in specs if s.data_contract == "scalar" and set(s.inputs) <= AVAIL]
    runtime = signals_for(eligible, source)
    inverted = {
        "open": tuple(750 - x for x in source["open"]),
        "high": tuple(750 - x for x in source["low"]),
        "low": tuple(750 - x for x in source["high"]),
        "close": tuple(750 - x for x in source["close"]),
        "volume": tuple(x * (1 + i % 5 / 20) for i, x in enumerate(source["volume"])),
    }
    chart = [s for s in specs if s.name.startswith("chart_")]
    chart_reverse = signals_for(chart, inverted)

    ids: dict[str, list[str]] = defaultdict(list)
    sigs: dict[str, list[str]] = defaultdict(list)
    rows = []
    for spec in specs:
        eligible_flag = spec in eligible
        sem = semantic_feature_id(spec)
        ids[sem].append(spec.name)
        observed = runtime.get(spec.name)
        if observed and "output_signature_sha256" in observed:
            sigs[observed["output_signature_sha256"]].append(spec.name)
        rows.append(
            {
                "name": spec.name,
                "family": spec.family,
                "status": spec.status,
                "inputs": list(spec.inputs),
                "calculator": spec.calculator,
                "parameters": spec.parameters,
                "lookback": spec.lookback,
                "timeframe": spec.timeframe,
                "lag_bars": spec.lag_bars,
                "formula": spec.formula,
                "output_name": spec.output_name,
                "data_contract": spec.data_contract,
                "aliases": list(spec.aliases),
                "source_repositories": list(spec.source_repositories),
                "source_licenses": list(spec.source_licenses),
                "semantic_id": sem,
                "same_symbol_ohlcv_eligible": eligible_flag,
                "observed_synthetic_480": observed or "BLOCKED_EXTERNAL_OR_SPECIAL",
                "indicator_is_independent_math_formula": "UNVERIFIED",
                "family_chart_prefix": spec.name.startswith("chart_"),
                "source_is_officially_verified": False,
            }
        )
    a1_findings: list[dict[str, Any]] = [
        {
            "id": "A1-F01",
            "severity": "P1",
            "path": "core/features/chart_patterns.py",
            "function": "classical_shape",
            "detail": "inverse_head_shoulders false positive with equal head/shoulder lows: [100,110,100,110,100] returns +1; mirrored normal H&S returns 0",
            "reproduced": True,
            "expected": 0,
            "observed": classical_shape(
                mkpoints([100, 110, 100, 110, 100]), "inverse_head_shoulders"
            ),
            "stage": "A7",
        },
        {
            "id": "A1-F02",
            "severity": "P1",
            "path": "core/features/chart_patterns.py",
            "function": "harmonic_xabcd",
            "detail": "Gartley CD/BC projection constraint absent; test [100,120,107.64,112.4,104.28] ratio 1.70588 while illustrative reference ceiling 1.618",
            "reproduced": True,
            "expected": 0,
            "observed": harmonic_xabcd(
                mkpoints([100, 120, 107.64, 112.4, 104.28]), "harmonic_gartley"
            ),
            "stage": "A5",
        },
        {
            "id": "A1-F03",
            "severity": "P2",
            "path": "core/features/chart_patterns.py",
            "function": "impulse_five",
            "detail": "Only full six pivots, no developing wave 1-4 candidate, alternative counts or subwave decomposition",
            "reproduced": "CODE_INSPECTED",
            "stage": "A6",
        },
        {
            "id": "A1-F04",
            "severity": "P2",
            "path": "core/features/chart_patterns.py",
            "function": "complex_correction",
            "detail": "WXY and WXYXZ only alternating ABC zigzag groups, not full Elliott complex corrections",
            "reproduced": "CODE_INSPECTED",
            "stage": "A6",
        },
        {
            "id": "A1-F05",
            "severity": "P2",
            "path": "core/features/chart_patterns.py",
            "function": "calculate_chart_pattern",
            "detail": "Single +1/0/-1 event, no candidate/confirmed/invalidation separation, no timestamp sidecar",
            "reproduced": "CODE_INSPECTED",
            "stage": "A4/A8",
        },
        {
            "id": "A1-F06",
            "severity": "P2",
            "path": "core/features/chart_patterns.py",
            "function": "calculate_chart_pattern",
            "detail": "confirmation_bars=2 and minimum_swing=0.015 common to all patterns: sensitivity, false-positive and lag not calibrated",
            "reproduced": "CODE_INSPECTED",
            "stage": "A3/A4",
        },
        {
            "id": "A1-F07",
            "severity": "P2",
            "path": "tests/core/test_v3_causal_chart_patterns.py",
            "function": "test_every_pattern_has_registered_inherited_scalar_and_is_prefix_stable",
            "detail": "No positive end-to-end OHLC path per pattern; finite/causal only, possible always-zero default features",
            "reproduced": "CODE_INSPECTED",
            "stage": "A9",
        },
        {
            "id": "A1-F08",
            "severity": "P2",
            "path": "core/features/chart_patterns.py",
            "function": "classical_shape",
            "detail": "Double top/shoulders use geometric shape only; neckline confirmation and invalidation events absent",
            "reproduced": "CODE_INSPECTED",
            "stage": "A7",
        },
    ]
    for f in a1_findings:
        if f["id"] in ("A1-F01", "A1-F02"):
            assert f["observed"] == 1
    a1: dict[str, Any] = {
        "schema": "quant-v3-chart-A1-feature-audit-v1",
        "reference_branch": a0["chart_branch"]["branch"],
        "reference_commit": a0["chart_branch"]["sha"],
        "feature_rows": rows,
        "counts": {
            "registered": len(specs),
            "conditional_ohlcv_eligible": len(eligible),
            "specialized_or_external": len(specs) - len(eligible),
            "chart_scalar_features": len(chart),
            "runtime_exceptions": sum("error_type" in x for x in runtime.values()),
            "nonfinite_or_alignment_or_prefix_failures": sum(
                not (x.get("finite") and x.get("length_ok") and x.get("prefix_last_bar_equal"))
                for x in runtime.values()
            ),
            "chart_features_without_events_on_480bar_synthetic": [
                key
                for key in sorted(runtime)
                if key.startswith("chart_") and runtime[key].get("nonzero_events") == 0
            ],
            "chart_features_without_events_on_inverted_480bar_synthetic": [
                key
                for key in sorted(chart_reverse)
                if chart_reverse[key].get("nonzero_events") == 0
            ],
            "registered_with_declared_source_license": sum(bool(s.source_licenses) for s in specs),
        },
        "semantic_duplicate_id_groups": [group for group in ids.values() if len(group) > 1],
        "same_480bar_numeric_vector_groups": [group for group in sigs.values() if len(group) > 1],
        "chart_reverse_regime": chart_reverse,
        "findings": a1_findings,
        "caveats": [
            "One 480-bar deterministic synthetic path, plus inverted path only for chart patterns: no proof of broad market reliability",
            "Observed identical output vector is NOT algebraic identity. Similar-name variants may differ in formula/warmup/params",
            "Registration is not a full source numeric parity or license clearance",
            "Lookback and signal calculation were not evaluated on sealed 2026 OOS; actual research generations not run",
        ],
    }
    write("quant-v3-chart-A1-feature-audit-20261029.json", a1)

    references = [
        {
            "source": "Elliott Wave International Waveopedia",
            "url": "https://www.elliottwave.com/waveopedia/impulse/",
            "type": "reference, not copied code",
            "license_note": "citation only",
        },
        {
            "source": "International Federation of Technical Analysts, Elliott Wave",
            "url": "https://www.ifta.org/assets/docs/d_ifta_update_vol21-iss3.pdf",
            "type": "reference, not copied code",
            "license_note": "citation only",
        },
        {
            "source": "Harmonic Trader, pattern taxonomy",
            "url": "https://harmonictrader.com/harmonic-patterns/",
            "type": "reference, not copied code",
            "license_note": "trademark & commercial usage review needed",
        },
        {
            "source": "Harmonic Trader, Butterfly pattern",
            "url": "https://harmonictrader.com/harmonic-patterns/butterfly-pattern/",
            "type": "reference, not copied code",
            "license_note": "Butterfly trademark/commercial licensing caution; never copy code",
        },
        {
            "source": "Titan FX XABCD ratio overview",
            "url": "https://research.titanfx.com/technical-analysis/fibonacci/what-is-harmonic-patterns",
            "type": "comparison, not authoritative original code",
            "license_note": "citation only",
        },
    ]
    existing_rules = {
        "elliott_impulse_5": (
            "6 pivots; wave 2 retracement and wave 3 shortest, wave 4 no overlap",
            "subwaves, interim counts, invalidation, diagonals excluded",
            "IFTA/elliottwave.com",
        ),
        "elliott_abc": (
            "4 pivots; B 0.236-1.05, C/A 0.618-1.90, zigzag-style",
            "flat/triangle/running variants missing",
            "IFTA",
        ),
        "elliott_wxy": (
            "10 pivots; alternating 3 ABC zigzag units",
            "no internal X type/staging/alternate corrections",
            "IFTA",
        ),
        "elliott_wxyxz": (
            "16 pivots; alternating 5 ABC zigzag units",
            "no alternate ABC/flat/triangle subdivisions",
            "IFTA",
        ),
        "harmonic_butterfly": (
            "B/XA ~0.786, D projection beyond X by 0.27 XA, CD/BC >=1.13",
            "AB=CD minimum and per-leg PRZ crossing absent; commercial IP review",
            "harmonictrader.com",
        ),
        "harmonic_gartley": (
            "B/XA ~0.618, AD/XA ~0.786",
            "CD/BC 1.13-1.618 missing, PRZ confluence missing",
            "Titan FX",
        ),
        "harmonic_bat": ("B/XA ~0.382-0.5, AD/XA ~0.886", "CD/BC projection missing", "Titan FX"),
        "harmonic_crab": (
            "B/XA ~0.382-0.618, D beyond X by ~0.618 XA",
            "CD/BC 2.24-3.618 missing",
            "Titan FX",
        ),
        "double_top": (
            "equal peaks within 3.5%; trough depth >=2.5%",
            "neckline break confirmation missing",
            "independent geometric heuristic",
        ),
        "double_bottom": (
            "equal troughs within 3.5%; middle height >=2.5%",
            "neckline break confirmation missing",
            "independent geometric heuristic",
        ),
        "head_shoulders": (
            "5 pivots; head > 1.03 * shoulder peak, similar shoulders",
            "neckline break and volume confirmation missing",
            "independent geometric heuristic",
        ),
        "inverse_head_shoulders": (
            "mirror transform direction -1; wrong head comparison with negative numbers",
            "false positive A1-F01; need correction",
            "independent geometric heuristic",
        ),
    }
    proposed = {
        "harmonic_deep_crab": "needs origin ratios and multi-leg oracle",
        "harmonic_alternate_bat": "needs origin ratios and multi-leg oracle",
        "harmonic_shark": "different multi-swing order; cannot repurpose XABCD",
        "harmonic_cypher": "needs source-specific ratio/licensing verification",
        "harmonic_5_0": "needs source and AB=CD-style confluence validation",
        "harmonic_abcd": "AB=CD and BC/CD extensions; no distinct current detector",
        "elliott_leading_diagonal": "can overlap wave1/4; different inner subdivision rules",
        "elliott_ending_diagonal": "special overlapping diagonal; not standard impulse",
        "elliott_flat_regular": "ABC subwave topology 3-3-5; distinguish zigzag",
        "elliott_flat_expanded": "B exceeds A start; C exceeds A end, own oracle",
        "elliott_flat_running": "B exceeds A start; C shortfalls, own oracle",
        "elliott_triangle": "ABCDE contracting/expanding; 5 swing groups not simple ABC",
        "elliott_double_zigzag": "WXY with distinct internal structure; avoid formula alias",
        "elliott_triple_zigzag": "WXYXZ with distinct structure; avoid formula alias",
        "classical_triangle": "must define converging slopes and breakout confirmation",
        "classical_wedge": "separate trend continuation vs reversal; breakout confirmation",
        "classical_flag": "pole and channel with duration/volume conditions",
        "classical_pennant": "pole and converging sides; validate breakout without future look",
    }
    ptn: list[dict[str, Any]] = []
    for name in PATTERNS:
        rules, gaps, citation = existing_rules[name]
        ptn.append(
            {
                "name": name,
                "status": "REGISTERED_HEURISTIC",
                "rules": rules,
                "code_source": "core/features/chart_patterns.py",
                "reference": citation,
                "missing_formula_or_contract": gaps,
                "required_evidence": "source formula matrix, positive/negative oracle, prefix/decision_time, quantitative output coverage",
                "risk": "IP/TRADEMARK/COMMERCIAL_LICENSE_REVIEW"
                if "harmonic_" in name
                else "CAUSALITY/HEURISTIC_NOT_VALIDATED",
                "next_stage": "A5"
                if name.startswith("harmonic")
                else "A6"
                if name.startswith("elliott")
                else "A7",
            }
        )
    for name, problem in proposed.items():
        ptn.append(
            {
                "name": name,
                "status": "CANDIDATE_NOT_IMPORTED",
                "rules": "NOT_VERIFIED_OR_IMPLEMENTED",
                "code_source": None,
                "reference": "source review pending",
                "missing_formula_or_contract": problem,
                "required_evidence": "full public source rule oracle, independent safe implementation, non-hindsight recognition and license clearance before import",
                "risk": "IP_REVIEW_REQUIRED"
                if name.startswith("harmonic")
                else "FUTURE_LEAKAGE_AND_FORMULA_REVIEW_REQUIRED",
                "next_stage": "A5"
                if name.startswith("harmonic")
                else "A6"
                if name.startswith("elliott")
                else "A7",
            }
        )
    a2 = {
        "schema": "quant-v3-chart-A2-source-formula-matrix-v1",
        "source_references": references,
        "patterns": ptn,
        "counts": {
            "registered_heuristic": len(PATTERNS),
            "unimplemented_research_candidates": len(proposed),
            "candidate_count_is_independent_math_count": False,
        },
        "verified_defects": [
            {
                "id": "A2-F01",
                "pattern": "harmonic_gartley",
                "observed_ratio_cd_over_bc": abs(112.4 - 104.28) / abs(107.64 - 112.4),
                "formula_constraint_status": "MISSING",
                "source": references[-1]["url"],
            },
            {
                "id": "A2-F02",
                "pattern": "inverse_head_shoulders",
                "input": [100, 110, 100, 110, 100],
                "expected": 0,
                "observed": 1,
                "source": "core/features/chart_patterns.py",
            },
        ],
        "restrictions": [
            "Harmonic pattern labels and specific implementations may have trademark/commercial use restrictions; do not copy proprietary code",
            "These references establish a comparison review, not per-candidate implementation parity or permission",
            "No new candidate may become registered without fixed source/evidence/license and deterministic causal oracle",
        ],
    }
    write("quant-v3-chart-A2-formula-source-matrix-20261029.json", a2)
    report = f"""# Quant V3 · 차트·엘리엇 A0~A2 전수조사 1차 실측 보고

- 시점: {a0["observed_at_kst"]}
- 기준 HEAD: `{a0["chart_branch"]["sha"]}` / 분리 브랜치 `{a0["chart_branch"]["branch"]}`.
- **A0 확인**: Moon 접속 복구; 별도 clean worktree 확보. 기존 +40개는 원래 브랜치에서 커밋 전 **등록 {a0["local_bulk40"]["registered"]}개, 신규 40개** 상태 보존. Chart 브랜치는 **{len(specs)}개 / 동일종목 OHLCV 후보 {len(eligible)}개 / 외부·전문 입력 {len(specs) - len(eligible)}개**, Chart 12개. 현재 **+40 / +12 미병합**. 예상 조합 487은 검증된 실제 개수가 아님.
- **A1 FeatureSpec 목록 검사**: **{len(rows)}개 모든 등록 feature 행을 JSON에 기록**(이름·계열·계산기·입력·기간·출력·수식·소스·라이선스·실행 관찰). 합성 480봉 개발용 데이터에서 {len(eligible)}개 계산 및 1바 prefix 확인. 예외 {a1["counts"]["runtime_exceptions"]}개, 비유한/길이/접두부 위반 {a1["counts"]["nonfinite_or_alignment_or_prefix_failures"]}개.
- Chart 12개 중 합성 경로에서 이벤트 0건: {len(a1["counts"]["chart_features_without_events_on_480bar_synthetic"])}개; 반전 추세 480봉에서 0건: {len(a1["counts"]["chart_features_without_events_on_inverted_480bar_synthetic"])}개. *한두 합성 경로 이벤트 부재는 수학적으로 영구 불능 증명이 아님*. 실제 시장 이벤트 빈도/OOS 수익은 미검증.
- 정확히 같은 480봉 계산 결과를 보인 feature 그룹: {len(a1["same_480bar_numeric_vector_groups"])}개 (수학적 완전 동등성 **아님**).
- **A2 원문/오픈소스 규칙 후보**: 현재 12개 + 아직 구현되지 않은 18개 = **30개 행별 공식·근거·미지원·라이선스 상태**. 소스 참고문헌 5건을 명시하되 원본 코드 복제·적법성 인증을 주장하지 않음.

## 재현된 결함 (핵심)

1. **A1-F01 / P1** 역헤드앤숄더: `[100, 110, 100, 110, 100]`처럼 어깨·머리 가격이 같아야 무효인데 실제 +1 반환. 반대 방향 헤드앤숄더는 동일한 동치 구조에서 0 반환하여 수평 뒤집기 대칭성 위반. 원인: 음수 좌표로 뒤집고 `c > max(a,e)*1.03` 검증. **A7 필수 수정**.
2. **A1-F02 / P1** 가틀리: XABCD `[100,120,107.64,112.4,104.28]`에서 `CD/BC = {abs(112.4 - 104.28) / abs(107.64 - 112.4):.6f}`; 참고 기준의 CD/BC 상한 1.618을 넘지만 계산기가 +1 반환. B/XA와 AD/XA만 확인. **A5 비율 매트릭스/PRZ 필수 수정**.
3. 1~5파 완성 후 탐지만 지원(A6), ABC/WXY 복합 유형 제한(A6), 피벗 확정/후보/무효화를 0/±1로 압축(A4/A8), 공통 고정 민감도(A4), 넥라인 돌파 불검사(A7), 전체 end-to-end 양성 OHLC 패턴 fixture 부재(A9).

## 현재 의미와 차단 조건

- **전수조사의 대상 범위(등록 447개 + 로컬40 후보 + 패턴후보18)를 분류했지만**, 외부 원전별 세부 수식 검증·전략 가치 증명은 아직 끝나지 않은 A2 후속 과제다.
- 구체 원본 조건/라이선스가 충족되기 전 신규 후보 18개를 추가 등록하지 않는다. 하모닉 상표/상업적 사용 제한은 별도 확인이 필요하다.
- **Moon 공식 release 검증: VALIDATION_FAILED** — `uv run --locked --extra dev ruff check .` 호출이 `uv: command not found` (exit 127)로 중단. 별도 venv에서 수행한 Ruff/pytest/scoped mypy PASS와 구분.
- 실제 StrategyIR 실거래 활용 금지, 2026 sealed OOS 비접근, 원래 연구 기록/계보·OAuth·MCP URL·orders OFF 무변경.
- **다음:** A2 원식별기별 ratio/validator oracle 채우기 → A3 시점별 prefix/no future 데이터 누수 정밀 감사 → A4 공통 pivot API 수정. P1 오탐 2건 교정은 먼저 별도 테스트/소스 버전으로 진행하고 전체 회귀 후 승격.

## 근거 파일

- A0: `docs/operations/quant-v3-chart-A0-baseline-20261029.json`
- A1: `docs/operations/quant-v3-chart-A1-feature-audit-20261029.json`
- A2: `docs/operations/quant-v3-chart-A2-formula-source-matrix-20261029.json`
- 코드 수정 없음; 자동 재현: `python scripts/v3_chart_a0_a2_audit.py`; 독립 테스트: `pytest -q tests/core/test_v3_chart_a0_a2_audit.py`.
"""
    (OUT / "quant-v3-chart-A0-A2-first-audit-20261029.md").write_text(report, encoding="utf-8")
    return {
        "chart_registered": len(specs),
        "eligible": len(eligible),
        "runtime_failures": a1["counts"]["runtime_exceptions"],
        "prefix_or_nan": a1["counts"]["nonfinite_or_alignment_or_prefix_failures"],
        "chart_event_zero": len(a1["counts"]["chart_features_without_events_on_480bar_synthetic"]),
        "inverted_chart_event_zero": len(
            a1["counts"]["chart_features_without_events_on_inverted_480bar_synthetic"]
        ),
        "source_candidate_rows": len(ptn),
        "duplicates_480bar_vector_groups": len(a1["same_480bar_numeric_vector_groups"]),
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
