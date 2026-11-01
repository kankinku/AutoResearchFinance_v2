"""A10 staged only: audit isolation and source-verified 40 indicator merger.

Do not mutate user worktrees, historical A0-A9 artifacts, G records,
protected data, 2026 OOS, OAuth/MCP or live order configuration.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.features.calculators import calculate_feature
from core.features.pandas_ta_pinned import _approved
from core.features.registry import research_feature_specs
from research.chart_pattern_bridge import chart_research_feature_specs
from research.llm.inherited_feature_compiler import _new_feature_vector
from scripts.v3_audit_335_features import synthetic
from strategy_ir.schema import FeatureRef

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"
A0 = OUT / "quant-v3-chart-A0-baseline-20261029.json"
REGISTRY_SNAPSHOT = ROOT / "tests/core/fixtures/v3_chart_a10_premerge_registry_20261029.json"
SOURCE_40 = ROOT / "core/features/bulk40_manifest.json"
DIRTY = Path("/shared/moon-workspace/AutoResearchFinance_v3-track1-strategy-20261027")


def _identities(specs: Any) -> dict[str, dict[str, object]]:
    return {
        p.name: {
            "canonical_id": p.canonical_id,
            "version": p.version,
            "calculator": p.calculator,
            "inputs": list(p.inputs),
            "lookback": p.lookback,
        }
        for p in specs
    }


def verify_a10(*, save: bool = True) -> dict[str, Any]:
    snap = json.loads(REGISTRY_SNAPSHOT.read_text())
    proof = json.loads(A0.read_text())
    source_hashes: dict[str, str] = proof["local_bulk40"]["file_hash_sha256"]
    actual_originals: dict[str, str] = {}
    for rel, expected in sorted(source_hashes.items()):
        if not (DIRTY / rel).exists():
            raise FileNotFoundError(f"original uncommitted source unavailable: {rel}")
        actual = hashlib.sha256((DIRTY / rel).read_bytes()).hexdigest()
        if actual != expected:
            raise AssertionError(f"uncommitted source changed: {rel}")
        actual_originals[rel] = actual
        if rel != "tests/core/test_v3_selected_bulk40.py":
            current = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
            if current != actual:
                raise AssertionError(f"source file changed while copying: {rel}")
    cohort = json.loads(SOURCE_40.read_text())
    assert cohort["source_license"] == "MIT"
    assert cohort["source_sha"] == "7c669b033582d53b70aa68b6388796d19ce33979"
    assert cohort["baseline_registered"] == 435  # source's historical baseline
    assert cohort["expected_after_registered"] == 475  # source's historical projection
    selected = cohort["entries"]
    assert len(selected) == 40
    names = {row["name"] for row in selected}
    assert len(names) == 40
    source_counts = Counter(row["formula_disposition"] for row in selected)
    assert source_counts == {
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY": 34,
        "UNREPRESENTED_FORMULA": 6,
    }
    assert len(_approved()) == 179
    existing = _identities(research_feature_specs())
    opted = _identities(research_feature_specs(chart_research_opt_in=True))
    before, before_opt = snap["base"], snap["optin"]
    assert len(before) == 447 and len(before_opt) == 491
    assert len(existing) == 487 and len(opted) == 531
    assert len(chart_research_feature_specs()) == 44
    assert set(existing) == set(before) | names
    assert set(opted) == set(before_opt) | names
    assert {k: existing[k] for k in before} == before
    assert {k: opted[k] for k in before_opt} == before_opt
    assert names.isdisjoint(before_opt)

    overlap = json.loads((OUT / "quant-v3-82-formula-overlap-audit-20261029.json").read_text())
    selected_audit = {
        row["candidate"]: row
        for row in overlap["items"]
        if row["formula_disposition"]
        in {"ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY", "UNREPRESENTED_FORMULA"}
    }
    assert set(selected_audit) == {row["audit_candidate"] for row in selected}
    raw, market = synthetic(480)
    specs_by_name = {s.name: s for s in research_feature_specs()}
    channels: list[dict[str, Any]] = []
    prefix_checks = 0
    replay_checks = 0
    for row in sorted(selected, key=lambda obj: str(obj["name"])):
        name = row["name"]
        spec = specs_by_name[name]
        if spec.source_licenses != ("MIT",):
            raise AssertionError("license did not survive integration")
        if spec.parameters["source_name"] != row["source"]:
            raise AssertionError("pinned source implementation changed")
        if spec.parameters["output_index"] != row["output_index"]:
            raise AssertionError("pinned output index changed")
        inputs = {key: raw[key] for key in spec.inputs}
        values = calculate_feature(spec, inputs)
        if len(values) != 480 or not all(v is None or math.isfinite(v) for v in values):
            raise AssertionError("nonfinite/nonbar output")
        observed = len({round(float(v), 7) for v in values if v is not None})
        if observed <= 1:
            raise AssertionError(f"constant or unavailable source output: {name}")
        for cutoff in (140, 280, 420, 479):
            earlier = calculate_feature(
                spec, {key: series[:cutoff] for key, series in inputs.items()}
            )
            if tuple(values[:cutoff]) != earlier:
                raise AssertionError(f"future data contaminated {name} at {cutoff}")
            prefix_checks += 1
        ref = FeatureRef(
            feature_id=name, timeframe="1d", lookback=spec.lookback, inputs=spec.inputs
        )
        if _new_feature_vector(ref, market) != values:
            raise AssertionError(f"inherited source mismatch for {name}")
        replay_checks += 1
        channels.append(
            {
                "name": name,
                "family": str(row["source"]),
                "formula_disposition": str(row["formula_disposition"]),
                "canonical_id": spec.canonical_id,
                "input_fields": list(spec.inputs),
                "output_index": row["output_index"],
                "lookback": spec.lookback,
                "observed_distinct_values": observed,
                "nonmissing_count": sum(v is not None for v in values),
                "source_sha256": source_hashes["core/features/pandas_ta_manifest.json"],
                "synthetic_vector_sha256": hashlib.sha256(
                    json.dumps(values, separators=(",", ":"), allow_nan=False).encode()
                ).hexdigest(),
                "prefix_checks": 4,
                "inherited_replay_equal": True,
            }
        )
    assert len(channels) == 40 and prefix_checks == 160 and replay_checks == 40

    body: dict[str, Any] = {
        "schema": "quant-v3-chart-A10-bulk40-staged-integration-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "scope": "A10_STAGING_BRANCH_NO_MAIN_NO_OOS",
        "stage": "A10",
        "question_ids": ["Q05", "Q10", "Q11", "Q12", "Q18"],
        "integration_branch": "research/v3-chart-a10-bulk40-integration-20261029",
        "base_branch": "research/v3-chart-audit-20261029",
        "counts": {
            "prior_base": 447,
            "integrated_base": 487,
            "prior_chart_optin": 491,
            "integrated_chart_optin": 531,
            "new_channels": 40,
        },
        "source_files_verified": len(actual_originals),
        "original_dirty_source_hashes": actual_originals,
        "source_provenance": {
            "sha": cohort["source_sha"],
            "license": cohort["source_license"],
            "formula_dispositions": dict(source_counts),
            "source_manifest_base_count": 435,
            "source_manifest_after_count": 475,
        },
        "registry_premerge_snapshot_sha256": snap["payload_sha256"],
        "name_collisions": [],
        "legacy_canonical_changed": [],
        "synthetic_samples": 480,
        "full_source_oracle_40": "TESTED_BY_tests/core/test_v3_selected_bulk40.py",
        "prefix_checks": prefix_checks,
        "prefix_mismatches": 0,
        "strategyir_replay_checks": replay_checks,
        "strategyir_replay_mismatches": 0,
        "channel_metrics": channels,
        "historical_A0_A9_evidence_untouched": True,
        "original_dirty_worktree_untouched": True,
        "main_merged": False,
        "release_authorized": False,
        "sealed_2026_OOS_accessed": False,
        "limitations": [
            "40 scalar channels: 34 additional outputs + 6 formulas; "
            "NOT 40 independent mathematical inventions",
            "Existing prior tests and provenance unchanged; "
            "catalog in separate research worktree only",
            "Source upstream MIT license and SHA pinned; predictive performance not established",
            "Historical 447/491 evidence from A0-A9 is preserved and not retroactively updated",
            "A9 market precision and autonomous G replay unverified; 2026 OOS remains sealed",
            "Release gate and integration PR require review before any protected main merge",
        ],
    }
    if save:
        (OUT / "quant-v3-chart-A10-integration-acceptance-20261029.json").write_text(
            json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf8",
        )
        lines = [
            "# Quant V3 A10 · 별도 브랜치 40개 소스 출력 통합 감사",
            "",
            "**상태:** 연구용 통합 브랜치에만 반영. 운영 main/2026 OOS/실거래 변경 없음.",
            f"- 원본 미커밋 소스 파일 해시 확인: {len(actual_originals)}/4 PASS.",
            "- 등록: 기존 447 → 487; 차트 opt-in 기존 491 → 531.",
            "- Cohort 유형: 추가 출력 채널 34 + 신규 수식 채널 6.",
            "- 기존 447 및 chart research 44 FeatureSpec 식별자·등록 의미 보존.",
            f"- 40개×4개 절단 시점 = {prefix_checks}개 봉별 인과성 검사 오류 0.",
            f"- 40개 typed FeatureRef replay 일치 {replay_checks}/40.",
            "- Pandas-TA Classic MIT 소스 7c669b0 고정. 파라미터 임의 변경 거부.",
            "- 과거 A0–A9의 정량 증거/원본 SHA는 그대로 보존. 435→475",
            "  수치는 기존 원본 작업 브랜치 기준이며 차트 12를 합친 현재 단계는",
            "  447→487이므로 서로 다른 기준을 혼동하지 않음.",
            "",
            "## 범위·실사용 미검증",
            "",
            "- 기존 40 미커밋 원본을 고치거나 Git에 Push하지 않음.",
            "- 본 통합은 40개의 고유한 신규 투자 전략이나 독립 알파를 뜻하지 않음.",
            "- V05→T4→V01~V04→V06→V07 상위 개발 순서 유지.",
            "- 실제 자율 연구 세대/G 평가, 수익·거래비용, 2026 독립 OOS 미실행.",
            "- 공식 release CI의 uv 미설치 문제 해소 및 코드 리뷰 전 main 병합 금지.",
            "",
            "## 증거",
            "",
            "- core/features/bulk40_manifest.json (원본 바이트 동일).",
            "- tests/core/test_v3_selected_bulk40.py (역사적 435→475 단언만",
            "  현재 447→487로 보정한 테스트 복사본).",
            "- tests/core/fixtures/v3_chart_a10_premerge_registry_20261029.json.",
            "- tests/core/test_v3_chart_a10_bulk40_integration.py.",
            "- scripts/v3_chart_a10_validate.py.",
        ]
        (OUT / "quant-v3-chart-A10-integration-report-20261029.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf8",
        )
    return body


if __name__ == "__main__":
    evidence = verify_a10()
    print(
        json.dumps(
            {
                "counts": evidence["counts"],
                "source_files_verified": evidence["source_files_verified"],
                "prefix_checks": evidence["prefix_checks"],
                "strategyir_replay_checks": evidence["strategyir_replay_checks"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
