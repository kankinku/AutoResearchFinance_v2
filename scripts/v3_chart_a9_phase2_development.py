# ruff: noqa: E501  # Preserve audit strings and machine-linked findings.
"""A9 phase2: read-only non-PIT QQQ DEVELOPMENT chart indicator audit.

Fixed, fingerprinted input. Never opens 2026 sealed OOS or production state.
No data-dependent retuning, PnL, or future signal access; metrics are descriptive.
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

from core.data.contracts import Bar, DataContractError, DataZone, MarketDataSet
from core.features.calculators import calculate_feature
from core.features.chart_patterns import PATTERNS
from core.features.classical_lifecycle import CLASSICAL_PATTERNS, calculate_classical_events
from core.features.registry import research_feature_specs
from research.chart_pattern_bridge import (
    calculate_chart_research,
    chart_research_feature_specs,
    overlay_payload,
)
from research.llm.inherited_feature_compiler import (
    InheritedFeatureBindingError,
    _new_feature_vector,
)
from strategy_ir.schema import FeatureRef

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"
DEV_ROOT = Path("/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021")
DATA = DEV_ROOT / ("data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet")
ORIGIN = DEV_ROOT / "data/market/public_yahoo_qqq/snapshot-origin.json"
DATA_SHA256 = "94e1f5f118e6dc14d25dc95b654fcfd485f07bce251fb1c8a16d1843df638037"
CORP_EVENT_SPLIT_BAR = 84
DATE_START, DATE_END = "2020-01-02", "2025-12-31"


def load_development_market() -> tuple[MarketDataSet, dict[str, Any]]:
    """Reject changed/non-development inputs, no fallback or remote access."""
    import pandas as pd  # type: ignore[import-untyped]

    if not DATA.is_file() or not ORIGIN.is_file():
        raise FileNotFoundError("frozen read-only QQQ development input is unavailable")
    sha = hashlib.sha256(DATA.read_bytes()).hexdigest()
    if sha != DATA_SHA256:
        raise ValueError("frozen development data bytes have changed")
    manifest = json.loads(ORIGIN.read_text(encoding="utf8"))
    if (
        manifest["parquet_sha256"] != sha
        or manifest["classification"] != "NON_PIT_DEVELOPMENT_ONLY"
        or manifest["vendor_confirmed"] is not False
        or manifest["bars"] != 1508
        or manifest["start"] != DATE_START
        or manifest["end"] != DATE_END
        or manifest["orders_enabled"] is not False
    ):
        raise ValueError("development provenance contract mismatch")
    frame = pd.read_parquet(DATA)
    if list(frame.columns) != ["timestamp", "symbol", "open", "high", "low", "close", "volume"]:
        raise ValueError("unexpected OHLCV parquet schema")
    if len(frame) != 1508:
        raise ValueError("development row count not frozen")
    bars = tuple(
        Bar(
            timestamp=datetime.fromisoformat(str(row.timestamp)),
            symbol=str(row.symbol),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in frame.itertuples(index=False)
    )
    if not bars or {b.symbol for b in bars} != {"QQQ"}:
        raise ValueError("development QQQ symbol mismatch")
    if bars[0].timestamp.date().isoformat() != DATE_START:
        raise ValueError("development first date mismatch")
    if bars[-1].timestamp.date().isoformat() != DATE_END:
        raise ValueError("development last date mismatch")
    if any(b.timestamp.year >= 2026 for b in bars):
        raise ValueError("unexpected sealed/OOS bar in development input")
    market = MarketDataSet(
        version="public-yahoo-qqq-2020-2025-raw-nonpit",
        zone=DataZone.DEVELOPMENT,
        bars=bars,
    )
    return market, {
        "source_kind": "PUBLIC_YAHOO_QQQ_FROZEN",
        "pit_status": "NON_PIT_DEVELOPMENT_ONLY",
        "provider_confirmed": False,
        "window": [DATE_START, DATE_END],
        "source_row_count": len(bars),
        "parquet_sha256": sha,
        "dataset_frozen_manifest_hash": manifest["dataset_hash"],
        "dataset_loaded_contract_hash": market.dataset_hash,
        "manifest_verified": True,
        "protected_2026_OOS_accessed": False,
    }


def _market_vectors(market: MarketDataSet) -> dict[str, tuple[float, ...]]:
    return {
        key: tuple(float(getattr(bar, key)) for bar in market.bars)
        for key in ("high", "low", "close")
    }


def summarize_development(market: MarketDataSet) -> dict[str, Any]:
    """All 44 opt-in channels, time-prefix, FeatureRef, and overlay alignment."""
    if market.zone != DataZone.DEVELOPMENT:
        raise PermissionError("research-only development market required")
    if len(market.bars) != 1508 or any(b.timestamp.year >= 2026 for b in market.bars):
        raise ValueError("unexpected time scope for frozen development audit")
    default = research_feature_specs()
    optional = research_feature_specs(chart_research_opt_in=True)
    specs = chart_research_feature_specs()
    assert len(default) == 487 and len(optional) == 531 and len(specs) == 44
    source = _market_vectors(market)
    n = len(market.bars)
    outputs: dict[str, tuple[float, ...]] = {}
    rows: list[dict[str, Any]] = []
    timings: list[float] = []
    ref_mismatches = 0
    protected_gate_rejections = 0
    for spec in specs:
        family = str(spec.parameters["pattern_name"])
        channel = str(spec.parameters["channel"])
        start = perf_counter()
        values = calculate_feature(spec, source)
        timings.append((perf_counter() - start) * 1000)
        if len(values) != n or not all(v is not None and math.isfinite(v) for v in values):
            raise ValueError("A8 real development emitted unaligned or nonfinite vector")
        results = tuple(float(v) for v in values)
        outputs[spec.name] = results
        ref = FeatureRef(feature_id=spec.name, timeframe="1d")
        try:
            _new_feature_vector(ref, market)
        except InheritedFeatureBindingError:
            protected_gate_rejections += 1
        else:
            raise AssertionError("research channel accessible without explicit opt-in")
        aligned = _new_feature_vector(ref, market, allow_chart_research=True)
        if aligned != results:
            ref_mismatches += 1
        zeros = sum(x == 0 for x in results)
        rows.append(
            {
                "feature": spec.name,
                "family": family,
                "channel": channel,
                "source_canonical_id": spec.canonical_id,
                "version": spec.version,
                "output_hash": hashlib.sha256(
                    json.dumps(results, separators=(",", ":")).encode()
                ).hexdigest(),
                "count_bars": n,
                "count_zero": zeros,
                "count_nonzero": n - zeros,
                "zero_fraction": zeros / n,
                "nonfinite": 0,
                "events_per_1000_bars": (
                    round((n - zeros) * 1000 / n, 4) if channel == "detected" else None
                ),
            }
        )
    if ref_mismatches or protected_gate_rejections != 44:
        raise AssertionError("development StrategyIR FeatureRef parity/opt-in violation")

    # A8 sends a complete confirmed bar t only to next bar t+1, never t.
    checkpoints = (256, 640, 1000, n)
    prefix_checks = 0
    prefix_mismatches = 0
    for cutoff in checkpoints:
        partial = {key: series[:cutoff] for key, series in source.items()}
        for spec in specs:
            observed = calculate_feature(spec, partial)
            original = outputs[spec.name][:cutoff]
            prefix_checks += 1
            if observed != original:
                prefix_mismatches += 1

    evidence: list[dict[str, Any]] = []
    families: list[dict[str, Any]] = []
    years = sorted({b.timestamp.year for b in market.bars})
    for name in PATTERNS:
        pulse_name = f"chart_research_{name}_detected"
        pulse = outputs[pulse_name]
        indices = [t for t, v in enumerate(pulse) if v != 0]
        year_counts = {
            str(y): sum(market.bars[t].timestamp.year == y for t in indices) for y in years
        }
        families.append(
            {
                "family": name,
                "event_count": len(indices),
                "per_1000_bars": round(len(indices) * 1000 / n, 4),
                "year_counts": year_counts,
                "zero_signal_bars": n - len(indices),
                "first_observed_date": (
                    market.bars[indices[0]].timestamp.date().isoformat() if indices else None
                ),
                "interpretation": (
                    "CLASSICAL_CLOSE_CONFIRMED"
                    if name in CLASSICAL_PATTERNS
                    else "OUTER_GEOMETRY_ONLY"
                ),
            }
        )
    overlay = overlay_payload(
        market,
        patterns=tuple(PATTERNS),
        allow_research=True,
        data_kind="RESEARCH_DEVELOPMENT",
    )
    if overlay["dataset_hash"] != market.dataset_hash or not overlay["overlay_hash"]:
        raise AssertionError("overlay dataset/provenance mismatch")
    overlay_violations = 0
    lifecycle_counts: Counter[str] = Counter()
    delays: list[int] = []
    classical_count = 0
    for name in CLASSICAL_PATTERNS:
        events = calculate_classical_events(source, name)
        lifecycle_counts.update(e.stage for e in events)
        classical_count += len(events)
        last_candidate: dict[str, int] = {}
        for event in events:
            if event.stage == "CANDIDATE":
                last_candidate[event.pattern_id] = event.known_at
            if event.stage == "CONFIRMED" and event.pattern_id in last_candidate:
                delays.append(event.known_at - last_candidate[event.pattern_id])
            matched = [
                x
                for x in overlay["events"]
                if x["event_id"] == event.event_id and x["name"] == name
            ]
            if len(matched) != 1:
                overlay_violations += 1
            if event.stage == "CONFIRMED":
                pulse = outputs[f"chart_research_{name}_detected"]
                if pulse[event.known_at] != float(event.direction):
                    overlay_violations += 1
    for event in overlay["events"]:
        t = int(event["known_at"])
        if (
            int(event["event_at"]) != t
            or int(event["eligible_from"]) != t + 1
            or t < int(event["last_pivot_index"])
            or t >= n
        ):
            overlay_violations += 1
        if event["name"] not in CLASSICAL_PATTERNS:
            pulse = outputs[f"chart_research_{event['name']}_detected"]
            if float(event["direction"]) != pulse[t]:
                overlay_violations += 1
        if len(evidence) < 36:
            evidence.append(
                {
                    "family": event["name"],
                    "stage": event["stage"],
                    "known_at": t,
                    "last_pivot_index": event["last_pivot_index"],
                    "eligible_from": event["eligible_from"],
                    "date": market.bars[t].timestamp.date().isoformat(),
                }
            )
    if prefix_mismatches or overlay_violations:
        raise AssertionError("A9 development prefix or overlay time violation")
    sorted_time = sorted(timings)
    return {
        "channels": rows,
        "families": families,
        "prefix_checks": prefix_checks,
        "prefix_mismatches": prefix_mismatches,
        "overlay_violations": overlay_violations,
        "source_ref_parity_mismatches": ref_mismatches,
        "default_off_rejections": protected_gate_rejections,
        "overlay_hash": overlay["overlay_hash"],
        "selected_event_evidence": evidence,
        "overlay_event_count": len(overlay["events"]),
        "classical_event_count": classical_count,
        "classical_stage_counts": dict(lifecycle_counts),
        "classical_candidate_to_confirmation_lags": delays,
        "all_zero_channels": sum(r["count_nonzero"] == 0 for r in rows),
        "all_zero_detected_families": sorted(
            r["family"] for r in families if r["event_count"] == 0
        ),
        "runtime_median_ms": sorted_time[len(sorted_time) // 2],
        "runtime_p95_ms": sorted_time[min(len(sorted_time) - 1, int(len(sorted_time) * 0.95))],
        "development_bar_count": n,
        "passed": True,
    }


def metamorphic_probes() -> dict[str, Any]:
    """Adverse synthetic transformations. No market-data modifications."""
    n = 160
    flat = {key: (100.0,) * n for key in ("high", "low", "close")}
    flat_count = sum(
        sum(v != 0 for v in calculate_chart_research(p, "detected", flat)) for p in PATTERNS
    )
    if flat_count:
        raise AssertionError("flat series generated a confirmed chart pattern")
    # Constant tied highs/lows are invalid turning points, not patterns.
    tied = {
        key: tuple(100.0 if i % 2 == 0 else 110.0 for i in range(n))
        for key in ("high", "low", "close")
    }
    tied_count = sum(
        sum(v != 0 for v in calculate_chart_research(p, "detected", tied)) for p in PATTERNS
    )
    base_close = [120.0 + 7.0 * math.sin(i / 6) for i in range(n)]
    base = {
        "high": tuple(c + 0.5 for c in base_close),
        "low": tuple(c - 0.5 for c in base_close),
        "close": tuple(base_close),
    }
    missing: dict[str, list[float | None]] = {k: list(v) for k, v in base.items()}
    missing["high"][82] = None
    missing_checks = 0
    missing_mismatch = 0
    for pattern in PATTERNS:
        result = calculate_chart_research(pattern, "detected", missing)
        for cut in (81, 82, 83, 100, n):
            seen = calculate_chart_research(
                pattern, "detected", {k: v[:cut] for k, v in missing.items()}
            )
            missing_checks += 1
            if result[:cut] != seen:
                missing_mismatch += 1
    scale = {key: tuple(v * 2.0 for v in series) for key, series in base.items()}
    original_signals = {p: calculate_chart_research(p, "detected", base) for p in PATTERNS}
    scaled_signals = {p: calculate_chart_research(p, "detected", scale) for p in PATTERNS}
    scale_diff = sum(
        x != y
        for name in PATTERNS
        for x, y in zip(original_signals[name], scaled_signals[name], strict=True)
    )
    split = {
        key: tuple(v if i < CORP_EVENT_SPLIT_BAR else v * 0.5 for i, v in enumerate(series))
        for key, series in base.items()
    }
    split_outputs = [calculate_chart_research(pattern, "detected", split) for pattern in PATTERNS]
    split_signal_count = sum(x != 0 for values in split_outputs for x in values)
    spike = {key: list(values) for key, values in base.items()}
    for key in ("high", "low", "close"):
        spike[key][91] += 90.0
    spike_outputs = [calculate_chart_research(pattern, "detected", spike) for pattern in PATTERNS]
    spike_finite = all(math.isfinite(v) for values in spike_outputs for v in values)
    high_low_rejected = False
    try:
        Bar(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            symbol="TEST",
            open=100.0,
            high=99.0,
            low=100.0,
            close=100.0,
            volume=1000.0,
        )
    except DataContractError:
        high_low_rejected = True
    if missing_mismatch:
        raise AssertionError("missing-bar prefix recomputation is not causal")
    return {
        "flat_prices": {"detected_signals": flat_count, "bars": n},
        "tied_pivots": {"detected_signals": tied_count, "bars": n},
        "missing_bar": {
            "missing_field": "high",
            "missing_at": 82,
            "prefix_checks": missing_checks,
            "lookahead_errors": missing_mismatch,
        },
        "scaled_prices": {
            "scale": 2.0,
            "input_bar_count": n,
            "detected_mismatches": scale_diff,
        },
        "split_bar": CORP_EVENT_SPLIT_BAR,
        "split_like_adjustment": {
            "explicitly_non_pit": True,
            "abrupt_price_halving": True,
            "detected_signal_count": split_signal_count,
            "corporate_action_asof_proved": False,
        },
        "single_spike": {
            "spike_bar": 91,
            "spike_amount": 90.0,
            "finite_outputs": spike_finite,
        },
        "invalid_high_low": {"rejected": high_low_rejected},
    }


def run_audit(*, save: bool = True) -> dict[str, Any]:
    market, identity = load_development_market()
    measurements = summarize_development(market)
    probes = metamorphic_probes()
    if not probes["invalid_high_low"]["rejected"] or not probes["single_spike"]["finite_outputs"]:
        raise AssertionError("synthetic stress did not meet safety bounds")
    report = {
        "schema": "quant-v3-chart-A9-phase2-development-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "scope": "READ_ONLY_NON_PIT_DEVELOPMENT_NO_OOS",
        "stage_id": "A9_PHASE2",
        "question_ids": ["Q05", "Q10", "Q11", "Q12", "Q18"],
        "input": identity,
        "summary": {
            "channels_evaluated": len(measurements["channels"]),
            "families_evaluated": len(measurements["families"]),
            "all_zero_channels": measurements["all_zero_channels"],
            "all_zero_detected_families": measurements["all_zero_detected_families"],
            "prefix_checks": measurements["prefix_checks"],
            "prefix_mismatches": measurements["prefix_mismatches"],
            "overlay_violations": measurements["overlay_violations"],
            "feature_ref_parity_mismatches": measurements["source_ref_parity_mismatches"],
            "default_off_rejections": measurements["default_off_rejections"],
            "overlay_event_count": measurements["overlay_event_count"],
            "classical_stage_counts": measurements["classical_stage_counts"],
            "classical_confirmation_lags_bars": measurements[
                "classical_candidate_to_confirmation_lags"
            ],
            "runtime_median_ms": measurements["runtime_median_ms"],
            "runtime_p95_ms": measurements["runtime_p95_ms"],
        },
        "family_metrics": measurements["families"],
        "channel_metrics": measurements["channels"],
        "synthetic_adverse_cases": probes,
        "overlay_hash": measurements["overlay_hash"],
        "selected_event_evidence": measurements["selected_event_evidence"],
        "real_market_precision": None,
        "real_market_recall": None,
        "profitability": None,
        "release_authorized": False,
        "protected_paths_modified": False,
        "sealed_2026_OOS_accessed": False,
        "validation": {
            "same_symbol_development_1508": "PASS",
            "data_sha256_and_origin_manifest": "PASS",
            "FeatureRef_default_off_and_opt_in_parity": "PASS",
            "44_channels_and_overlay_prefix_time": "PASS",
            "raw_source_time_provenance": "NON_PIT_NOT_INDEPENDENTLY_VERIFIED",
            "actual_label_precision_recall": "BLOCKED_LABELS_UNAVAILABLE",
            "next_open_execution_parent_replay": "NOT_RUN",
            "2026_holdout": "NOT_ACCESSED",
            "release_ci": "NOT_RUN",
            "full_A9": "INCOMPLETE",
        },
    }
    if save:
        (OUT / "quant-v3-chart-A9-phase2-development-audit-20261029.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf8",
        )
        lines = [
            "# Quant V3 A9 2차 · QQQ 실제 개발기간(비PIT) 차트 패턴 검증",
            "",
            "**범위:** 2020-01-02~2025-12-31 QQQ 1508봉, public Yahoo 개발용 frozen snapshot.",
            "**상태:** A9 부분 수행. 실제 정답 라벨·외부 시점별 원본·거래 경제성·최종 릴리스 미확인.",
            f"- 원본 SHA256: `{identity['parquet_sha256']}`, 읽기 전용·manifest hash 교차 검증.",
            "- 2026 봉인 OOS 미접근; 운영·G원장·실주문 설정 변경 없음.",
            "- 기본 487개 / 선택형 44개: 직접 계산 + FeatureRef 패리티",
            f"  오류 {measurements['source_ref_parity_mismatches']}, 기본 OFF 접근 거부",
            f"  {measurements['default_off_rejections']}/44.",
            f"- 전체 44개 채널의 1508봉 prefix 감사 {measurements['prefix_checks']}회:",
            f"  과거값 변경 {measurements['prefix_mismatches']}, 차트 이벤트 시각 위반",
            f"  {measurements['overlay_violations']}.",
            f"- 0값만인 채널 {measurements['all_zero_channels']}/44;",
            "  이 수치는 '패턴이 없거나 비활성'이라는 뜻이지 정확도 아님.",
            f"- 실제 개발기간 오버레이 이벤트 {measurements['overlay_event_count']}건,",
            f"  고전 후보/확정/무효/만료: {measurements['classical_stage_counts']}.",
            f"- 합성 오류/가격 스케일 경계 검증: missing prefix {probes['missing_bar']['prefix_checks']}회",
            f"  및 mismatch {probes['missing_bar']['lookahead_errors']}; 동률 신호",
            f"  {probes['tied_pivots']['detected_signals']};",
            f"  2배 가격 스케일 차이 {probes['scaled_prices']['detected_mismatches']}.",
            "- 급등락·주식분할 유사 가격 급변은 합성 시험일 뿐 실제 기업행동 as-of 검증 아님.",
            "",
            "## 패턴별 관측 빈도 (개발 데이터, 시장 정답 라벨 아님)",
            "",
            "| 패턴 | 신호 건수 | 1,000봉당 | 최초 관측 |",
            "|---|---:|---:|---|",
            *[
                f"| {r['family']} | {r['event_count']} | {r['per_1000_bars']:.1f} | {r['first_observed_date'] or '-'} |"
                for r in measurements["families"]
            ],
            "",
            "## 다음 단계 및 명시적 차단",
            "",
            "- 실제 주가에서 그 패턴이 정답이라는 독립 라벨이 없으므로",
            "  precision·recall·거짓양성률 수치는 **미산정**.",
            "- 2020~2025 snapshot은 현재 수집된 non-PIT이며 원본 당시 정보 가용성",
            "  또는 기업행동 시점 대응이 보증되지 않음. 복수 자료 공급자 교차 검증 필요.",
            "- 기존 G 부모 StrategyIR 완결 replay, 체결비용·PnL, 메모리 부하 및",
            "  전체 CI 승인 전까지 A9는 INCOMPLETE, 신호 자동 전략 승격 금지.",
            "- V05→T4→V01–V04→V06→V07 상위 개발 승인 순서를 변경하지 않음.",
        ]
        (OUT / "quant-v3-chart-A9-phase2-development-report-20261029.md").write_text(
            "\n".join(lines) + "\n", encoding="utf8"
        )
    return report


if __name__ == "__main__":
    output = run_audit()
    print(
        json.dumps(
            {
                "scope": output["scope"],
                "summary": output["summary"],
                "family_metrics": output["family_metrics"],
                "edge_cases": output["synthetic_adverse_cases"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
