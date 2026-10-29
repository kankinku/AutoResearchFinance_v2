"""A12 versioned addendum: repair the execution boundary without revising A11 evidence.

This scripted development-only re-run reads a temporary G452 SQLite snapshot.
It does NOT create GPT generations, use OOS, modify the original A11 report,
or change the canonical core engine/operating deployment.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash
from scripts.v3_chart_a11_g68_preregistered import read_prereg, run_a11

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "docs/operations"
ORIGINAL_A11 = OPERATIONS / "quant-v3-chart-A11-G68-diagnostic-results-20261029.json"
ADDENDUM = OPERATIONS / "quant-v3-chart-A12-lag-control-addendum-20261029.json"
ADDENDUM_MD = OPERATIONS / "quant-v3-chart-A12-lag-control-report-20261029.md"


def run_a12(*, save: bool = True) -> dict[str, Any]:
    historical_bytes = ORIGINAL_A11.read_bytes()
    old: dict[str, Any] = json.loads(historical_bytes)
    original_hash = sha256(historical_bytes).hexdigest()
    if (
        old["blocked_arm_count"] != 1
        or old["valid_costed_arm_count"] != 5
        or old["scope"] != "A11_PHASE1_SCRIPTED_DEVELOPMENT_NOT_AUTONOMOUS_GPT"
    ):
        raise ValueError("A12 requires the immutable original blocked A11 outcome")
    prior = {row["arm"]: row for row in old["candidate_arms"]}
    assert prior["B4_DELAYED_CONTROL"]["status"] == "BLOCKED_DOUBLE_LAG_PROVENANCE"
    fresh = run_a11(save=False)  # Uses original locked six-arm manifest and temp RO SQLite backup.
    current = {row["arm"]: row for row in fresh["candidate_arms"]}
    locked = read_prereg()
    if (
        fresh["preregistration_hash"] != old["preregistration_hash"]
        or fresh["preregistration_hash"] != locked["freeze_hash"]
        or fresh["parent_source"] != old["parent_source"]
        or fresh["valid_costed_arm_count"] != 6
        or fresh["blocked_arm_count"] != 0
    ):
        raise ValueError("A12 preregistration, parent lineage or six-arm budget drift")
    for name, previous in prior.items():
        if name == "B4_DELAYED_CONTROL":
            continue
        if current[name] != previous:
            raise ValueError(f"A12 non-control arm changed: {name}")
    b4 = current["B4_DELAYED_CONTROL"]
    if (
        b4["status"] != "VALID_COSTED_DEVELOPMENT_REPLAY"
        or b4["closed_trades"] < 1
        or b4["counted_as_valid_evaluation"] is not True
    ):
        raise ValueError("A12 B4 independent audit not complete")
    report: dict[str, Any] = {
        "schema": "quant-v3-A12-lag-control-replay-addendum-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "scope": "A12_SUPPLEMENT_NONPIT_DEVELOPMENT_ONLY",
        "preregistration_hash": fresh["preregistration_hash"],
        "original_A11_file_sha256": original_hash,
        "original_A11_result_content_hash": old["result_content_hash"],
        "source_G68_strategy_sha": fresh["parent_source"]["parent_strategy_sha"],
        "development_dataset_sha": fresh["parent_source"]["parent_dataset_hash"],
        "five_preregistered_costed_arms_bitwise_unchanged": True,
        "new_valid_B4_only": True,
        "all_six_replay_audit_costed_after_repair": True,
        "new_b4_report_is_separate_not_retroactively_preregistered": True,
        "lag_bridge": (
            "Research replay contains effective lagged decision series; "
            "protected core applies FeatureRef lag once to supplied raw. "
            "Research-only adapter reconstructs raw inputs before execution."
        ),
        "B4": {
            **b4,
            "research_feature_ref_lag_bars": 35,
            "negative_control": True,
        },
        "original_A11_report_modified": False,
        "preregistration_modified": False,
        "operating_main_merged": False,
        "original_ledger_modified": False,
        "gpt_calls_performed": 0,
        "new_counted_generations": 0,
        "independent_OOS_accessed": False,
        "orders_enabled": False,
        "strategy_promotion": False,
        "alpha_improvement_proved": False,
        "statistical_significance_established": False,
        "data_warning": "reused 2020-2025 non-PIT development bars, not unseen test data",
        "replay_limitation": (
            "single-scripted-control only; full GPT/random population not performed"
        ),
    }
    report["result_content_hash"] = content_hash({
        key: value for key, value in report.items()
        if key not in ("observed_at_kst", "result_content_hash")
    })
    if ORIGINAL_A11.read_bytes() != historical_bytes:
        raise ValueError("original historical A11 file changed during supplemental read")
    if save:
        ADDENDUM.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ADDENDUM_MD.write_text(
            "# Quant V3 A12 — A11 지연 대조군 연구용 재생 보완 보고\n\n"
            "원본 A11 기록은 그대로 보존하고 동일 사전등록 실험군 B4만 복구해 별도 판정합니다.\n\n"
            f"- B4(고전 double-bottom + 35봉 지연): 누적 {b4['total_return'] * 100:+.2f}%, "
            f"MDD {b4['max_drawdown'] * 100:.2f}%, 완료 {b4['closed_trades']}건, "
            f"비용 {b4['trading_costs']:.2f}.\n"
            f"- 기존 B0/B1/B2/B3/B40 다섯 실험 결과: 기존과 정확히 일치.\n"
            f"- 원본 A11 원장 결과 hash: `{old['result_content_hash']}`. "
            f"사전등록 hash: `{locked['freeze_hash']}`.\n"
            "- 전부 재사용한 비PIT 개발 데이터이고 새로운 GPT 세대 0, 봉인 OOS 0, 주문 0.\n"
            "- A11 당시 B4 실패 기록은 역사적 사실로 남고, 이번 결과는 후속 코드 "
            "버그 수정을 적용한 별도 보완 검증이므로 "
            "사전등록 원 실험의 완전성으로 소급하지 않습니다.\n"
            "- 정식 통합/배포, 전체 A11 통계적 유의성, 독립 검증은 미완료입니다.\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    result = run_a12()
    row = result["B4"]
    print(json.dumps({
        "scope": result["scope"],
        "B4_return_pct": round(row["total_return"] * 100, 3),
        "B4_mdd_pct": round(row["max_drawdown"] * 100, 3),
        "B4_closed_trades": row["closed_trades"],
        "unchanged_other_five": result["five_preregistered_costed_arms_bitwise_unchanged"],
    }, ensure_ascii=False))
