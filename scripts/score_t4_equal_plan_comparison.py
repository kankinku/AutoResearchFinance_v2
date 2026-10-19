"""Verify identities and score preregistered three-arm T4 development study.

No runtime backtesting, provider call, sealed/OOS read, strategy promotion, or
unverified statistical inference. All metrics are rechecked against MCP
immutable generation checkpoint payloads saved under the experiment evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

from research.indicator_engine.algorithm_plan import AlgorithmPlan
from scripts.preregister_t4_equal_plan_comparison import (
    MARKET_HASH,
    SCHEMA,
    digest,
    freeze,
)

SCHEMA_RESULT = "T4_THREE_ARM_DEVELOPMENT_COMPARISON_V1"
ARMS = ("GPT_RECORDED", "RANDOM", "LOCAL")


class ThreeArmComparisonError(ValueError):
    pass


def _safe_number(v: object) -> float | None:
    if v is None:
        return None
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise ThreeArmComparisonError("invalid performance metric type")
    result = float(v)
    if not math.isfinite(result):
        raise ThreeArmComparisonError("nonfinite performance metric")
    return result


def validate_and_score(
    manifest: dict[str, Any],
    observed: dict[str, Any],
    earlier: dict[str, Any],
) -> dict[str, Any]:
    if manifest != json.loads(json.dumps(freeze(earlier), ensure_ascii=False)):
        raise ThreeArmComparisonError("manifest differs from frozen preregistration")
    if (
        manifest["freeze_hash"] != digest({k: v for k, v in manifest.items() if k != "freeze_hash"})
        or manifest["schema"] != SCHEMA
    ):
        raise ThreeArmComparisonError("frozen plan tampering")
    if observed.get("schema") != "T4_THREE_ARM_MATCHED_PLAN_RECORDED_EVIDENCE_V1":
        raise ThreeArmComparisonError("unrecognized observation evidence schema")
    sessions = observed.get("data")
    if not isinstance(sessions, list) or {s["arm"] for s in sessions} != set(ARMS):
        raise ThreeArmComparisonError("control arm imbalance")
    by_arm = {session["arm"]: session for session in sessions}
    if len(by_arm) != 3:
        raise ThreeArmComparisonError("duplicate arm sessions")

    ratings: list[dict[str, Any]] = []
    all_trials: list[dict[str, Any]] = []
    for arm in ARMS:
        session = by_arm[arm]
        rows = session["history"]
        if (
            session["status"] != "COMPLETED"
            or session["completed_generations"] != 10
            or session["requested_generations"] != 10
            or session["final_report"]["proposed_hypotheses"] != 10
            or session["final_report"]["tested_hypotheses"] != 10
            or session["orders_enabled"] is not False
            or session["independent_oos_approved"] is not False
            or session["dataset_hash"] != MARKET_HASH
            or len(rows) != manifest["arm_size"]
        ):
            raise ThreeArmComparisonError(f"{arm}: scope/budget/market mismatch")
        if arm == "GPT_RECORDED" and session["session_id"] != manifest["source_gpt_session"]:
            raise ThreeArmComparisonError("historical GPT session mismatch")
        if arm != "GPT_RECORDED" and session["session_id"] == manifest["source_gpt_session"]:
            raise ThreeArmComparisonError("control unexpectedly points to GPT session")

        returns: list[float] = []
        mdds: list[float] = []
        sharpe: list[float | None] = []
        counts: list[float] = []
        exposures: list[float] = []
        unique: set[str] = set()
        for i, (row, plan) in enumerate(zip(rows, manifest["plans"][arm], strict=True)):
            if (
                row["generation"] != i + 1
                or row["algorithm_plan"] != plan
                or row["dataset_hash"] != MARKET_HASH
                or (i > 0 and row["previous_evidence_hash"] != rows[i - 1]["evidence_hash"])
                or not isinstance(row["evidence_hash"], str)
                or len(row["evidence_hash"]) != 64
                or len(row["hypothesis_ids"]) != 1
                or len(row["experiments"]) != 1
                or row["hypothesis_ids"][0] != row["experiments"][0]["hypothesis_id"]
                or AlgorithmPlan.model_validate(row["algorithm_plan"]).model_dump(mode="json")
                != plan
            ):
                raise ThreeArmComparisonError(
                    f"{arm}: plan, evidence chain or hypothesis mismatch G{i + 1}"
                )
            if (
                arm == "GPT_RECORDED"
                and row["evidence_hash"] != manifest["gpt_source_generation_evidence_hashes"][i]
            ):
                raise ThreeArmComparisonError("GPT evidence changed after initial observation")
            if row["algorithm_semantic_hash"] in unique:
                raise ThreeArmComparisonError("duplicate semantic algorithm within arm")
            unique.add(row["algorithm_semantic_hash"])
            m = row["metrics"]
            ret = _safe_number(m["total_return"])
            dd = _safe_number(m["max_drawdown"])
            expo = _safe_number(m["exposure"])
            trade = _safe_number(m["trade_count"])
            shp = _safe_number(m["sharpe"])
            if any(x is None for x in (ret, dd, expo, trade)):
                raise ThreeArmComparisonError("missing required measured metrics")
            assert ret is not None and dd is not None and expo is not None and trade is not None
            if dd < 0 or dd > 1 or expo < 0 or expo > 1 or trade < 0 or int(trade) != trade:
                raise ThreeArmComparisonError("invalid risk or trade metrics")
            returns.append(ret)
            mdds.append(dd)
            exposures.append(expo)
            counts.append(trade)
            sharpe.append(shp)
            all_trials.append(
                {
                    "arm": arm,
                    "slot": i + 1,
                    "plan_id": plan["plan_id"],
                    "plan_sha256": digest(plan),
                    "semantic_hash": row["algorithm_semantic_hash"],
                    "checkpoint_evidence_hash": row["evidence_hash"],
                    "metrics": m,
                    "passes_preregistered_gates": (
                        ret > 0 and dd <= 0.20 and trade >= 10 and shp is not None and shp > 0.50
                    ),
                }
            )
        pass_count = sum(x["passes_preregistered_gates"] for x in all_trials if x["arm"] == arm)
        ratings.append(
            {
                "arm": arm,
                "count": len(rows),
                "mean_total_return": statistics.mean(returns),
                "median_total_return": statistics.median(returns),
                "median_mdd": statistics.median(mdds),
                "median_sharpe_valid_only": statistics.median(s for s in sharpe if s is not None)
                if any(s is not None for s in sharpe)
                else None,
                "valid_sharpe_count": sum(s is not None for s in sharpe),
                "median_exposure": statistics.median(exposures),
                "median_closed_trades": statistics.median(counts),
                "pass_count": pass_count,
                "zero_trade_count": sum(n == 0 for n in counts),
                "best_development_return": max(returns),
                "worst_development_return": min(returns),
            }
        )

    # No winner selection from hindsight. The original, preregistered
    # primary metric is displayed without a significance/superiority claim.
    body = {
        "schema": SCHEMA_RESULT,
        "freeze_hash": manifest["freeze_hash"],
        "dataset_hash": MARKET_HASH,
        "arm_evaluations_equal": True,
        "original_plan_evaluations_total": 30,
        "controlled_s7_trials_total": 30,
        "scoring_preset": manifest["scoring_preset"],
        "arm_summaries": ratings,
        "trials": all_trials,
        "retrospective_gpt_outcomes_known_before_control_freeze": True,
        "candidate_grammar_common_but_selection_distributions_not_equated": True,
        "model_adaptive_vs_outcome_blind_controls": True,
        "gpt_token_and_elapsed_budget_equalized": False,
        "independent_pit_oos_approved": False,
        "statistical_model_superiority_established": False,
        "broker_executable": False,
        "no_strategy_promoted": True,
        "limitations": (
            "GPT historical plans were outcome-informed, whereas random/local controls "
            "were outcome-blind. Fixed grammar, indicator universe and 10+10 test "
            "counts do not equalize search distributions, inference time, model "
            "tokens, or prospectivity. Same reused QQQ RAW development data. "
            "S7 control probes use a common fixed entry >0.99 threshold, "
            "whereas GPT selected differing experiments; compare first-plan "
            "metrics as primary, not S7 diagnostic effectiveness."
        ),
    }
    return {**body, "report_hash": digest(body)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--observed", required=True, type=Path)
    parser.add_argument("--prior-gpt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = validate_and_score(
        json.loads(args.manifest.read_text()),
        json.loads(args.observed.read_text()),
        json.loads(args.prior_gpt.read_text()),
    )
    with args.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(
        "VERIFIED", result["report_hash"], "evaluations", result["original_plan_evaluations_total"]
    )
    for arm in result["arm_summaries"]:
        print(
            arm["arm"],
            "median return",
            f"{arm['median_total_return'] * 100:.3f}%",
            "median MDD",
            f"{arm['median_mdd'] * 100:.3f}%",
            "pass",
            arm["pass_count"],
            "zero trade",
            arm["zero_trade_count"],
        )


if __name__ == "__main__":
    main()
