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

from core.integrity.hashes import content_hash as _fresh_hash
from research.indicator_engine.algorithm_plan import AlgorithmPlan
from scripts.preregister_t4_equal_plan_comparison import (
    FRESH_ARMS,
    FRESH_MANIFEST_SCHEMA,
    MARKET_HASH,
    SCHEMA,
    digest,
    freeze,
    freeze_fresh_manifest,
    fresh_three_arm_protocol,
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
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--observed", type=Path)
    parser.add_argument("--prior-gpt", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fresh-manifest", type=Path)
    parser.add_argument("--fresh-receipts", type=Path)
    parser.add_argument("--fresh-observations", type=Path)
    parser.add_argument("--expected-manifest-hash")
    parser.add_argument("--expected-receipts-hash")
    parser.add_argument("--expected-observations-hash")
    parser.add_argument("--fresh-output", type=Path)
    args = parser.parse_args()
    if args.fresh_manifest is not None:
        fields = (
            args.fresh_receipts, args.fresh_observations, args.fresh_output,
            args.expected_manifest_hash, args.expected_receipts_hash,
            args.expected_observations_hash,
        )
        if any(v is None for v in fields) or any((
            args.manifest, args.observed, args.prior_gpt, args.output
        )):
            parser.error("fresh scoring requires three independent pinned SHA hashes")
        result = validate_fresh_equal_budget_score(
            json.loads(args.fresh_manifest.read_text(encoding="utf-8")),
            json.loads(args.fresh_receipts.read_text(encoding="utf-8")),
            json.loads(args.fresh_observations.read_text(encoding="utf-8")),
            expected_manifest_hash=args.expected_manifest_hash,
            expected_receipts_hash=args.expected_receipts_hash,
            expected_observations_hash=args.expected_observations_hash,
        )
        target = args.fresh_output
    else:
        if any((args.fresh_receipts, args.fresh_observations, args.fresh_output,
                args.expected_manifest_hash, args.expected_receipts_hash,
                args.expected_observations_hash)):
            parser.error("fresh scoring requires --fresh-manifest")
        if any(v is None for v in (
            args.manifest, args.observed, args.prior_gpt, args.output
        )):
            parser.error("historical scoring requires four legacy arguments")
        result = validate_and_score(
            json.loads(args.manifest.read_text()),
            json.loads(args.observed.read_text()),
            json.loads(args.prior_gpt.read_text()),
        )
        target = args.output
    with target.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    if args.fresh_manifest is not None:
        print("DESCRIPTIVE_ONLY", result["report_hash"])
    else:
        print(
            "VERIFIED", result["report_hash"],
            "evaluations", result["original_plan_evaluations_total"],
        )
        for arm in result["arm_summaries"]:
            print(
                arm["arm"],
                "median return", f"{arm['median_total_return'] * 100:.3f}%",
                "median MDD", f"{arm['median_mdd'] * 100:.3f}%",
                "pass", arm["pass_count"],
                "zero trade", arm["zero_trade_count"],
            )


class FreshComparisonError(ValueError):
    """A new cohort cannot be scored using tampered/unanchored evidence."""


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _value(value: object, *, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FreshComparisonError("missing numeric measured metric")
    number = float(value)
    if not math.isfinite(number) or (low is not None and number < low) or (
        high is not None and number > high
    ):
        raise FreshComparisonError("nonfinite or out-of-bounds measured metric")
    return number


def _anchored(payload: dict[str, Any], key: str, expected: str) -> None:
    if (
        not _valid_sha(expected) or payload.get(key) != expected
        or _fresh_hash({k: v for k, v in payload.items() if k != key}) != expected
    ):
        raise FreshComparisonError(f"{key}: external immutable anchor mismatch")


def _check_costed_fill_trace(row: dict[str, Any]) -> None:
    """Require internally consistent canonical Trade-shaped evidence.

    This cannot prove market prices or canonical replay; it only rejects
    fabricated accounting contradictions before descriptive aggregation.
    """
    held = False
    closed = 0
    paid = 0.0
    previous_time = ""
    fields = {"timestamp", "side", "price", "quantity", "notional", "cost", "symbol"}
    for trade in row["fills"]:
        if not isinstance(trade, dict) or set(trade) != fields:
            raise FreshComparisonError("malformed executed trade trace")
        when = trade["timestamp"]
        side = trade["side"]
        if (
            not isinstance(when, str) or not when or when <= previous_time
            or trade["symbol"] != "QQQ"
            or side not in ("buy", "sell")
        ):
            raise FreshComparisonError("unsupported executed trade provenance or order")
        price = _value(trade["price"], low=0.0000000001)
        qty = _value(trade["quantity"], low=0.0000000001)
        notional = _value(trade["notional"], low=0)
        cost = _value(trade["cost"], low=0)
        if not math.isclose(price * qty, notional, rel_tol=1e-9, abs_tol=1e-6):
            raise FreshComparisonError("executed trade notional inconsistent")
        if (side == "buy" and held) or (side == "sell" and not held):
            raise FreshComparisonError("unpaired executed trade sequence")
        held = side == "buy"
        closed += side == "sell"
        paid += cost
        previous_time = when
    if (
        closed != row["closed_trades"]
        or not math.isclose(paid, row["paid_cost_usd"], rel_tol=1e-9, abs_tol=1e-6)
    ):
        raise FreshComparisonError("executed trade count or paid cost mismatch")


def validate_fresh_equal_budget_score(
    manifest: dict[str, Any],
    receipts: dict[str, Any],
    observations: dict[str, Any],
    *,
    expected_manifest_hash: str,
    expected_receipts_hash: str,
    expected_observations_hash: str,
) -> dict[str, Any]:
    """Descriptive-only v2 scorer: three independently anchored, fresh G1 arms.

    NOTE: a hash-signed user-supplied observation is NOT independent canonical
    replay. Save manifest BEFORE trials and each receipt BEFORE its execution;
    separately commit each SHA to a trusted append-only evidence location.
    """
    try:
        if manifest.get("schema") != FRESH_MANIFEST_SCHEMA:
            raise FreshComparisonError("only the NEW G1 manifest is supported")
        _anchored(manifest, "freeze_hash", expected_manifest_hash)
        protocol = fresh_three_arm_protocol()
        baseline = freeze_fresh_manifest(
            protocol,
            market_hash=manifest["dataset_hash"],
            evaluator_version=manifest["evaluator_version"],
            cost_policy_hash=manifest["cost_policy_hash"],
            feature_policy_hash=manifest["feature_policy_hash"],
            cohort_id=manifest["cohort_id"],
            session_ids=manifest["session_ids"],
            market_start=manifest["market_window"]["start"],
            market_end=manifest["market_window"]["end"],
            source_code_hash=manifest["source_code_hash"],
        )
        if manifest != baseline:
            raise FreshComparisonError("frozen fresh policy contract was modified")
        if not isinstance(receipts, dict) or not isinstance(observations, dict):
            raise FreshComparisonError("submission and observation records required")
        _anchored(receipts, "receipts_hash", expected_receipts_hash)
        _anchored(observations, "observations_hash", expected_observations_hash)
        if (
            receipts.get("schema") != "T4_FRESH_SUBMISSIONS_V2"
            or observations.get("schema") != "T4_FRESH_MEASUREMENTS_V2"
            or receipts.get("manifest_hash") != expected_manifest_hash
            or observations.get("manifest_hash") != expected_manifest_hash
        ):
            raise FreshComparisonError("submitted evidence does not belong to the new G1 study")
        expected_slots = {(arm, i) for arm in FRESH_ARMS for i in range(1, 11)}
        submitted = receipts["rows"]
        measured = observations["rows"]
        if not isinstance(submitted, list) or not isinstance(measured, list) or (
            len(submitted) != len(measured) or len(submitted) != len(expected_slots)
        ):
            raise FreshComparisonError("unequal candidate or S7 observation budget")
        by_slot: dict[tuple[str, int], dict[str, Any]] = {}
        for record in submitted:
            if not isinstance(record, dict):
                raise FreshComparisonError("untyped submitted plan")
            key = (record["arm"], record["slot"])
            if key not in expected_slots or key in by_slot:
                raise FreshComparisonError("duplicate or invalid submitted plan slot")
            _anchored(record, "receipt_hash", record["receipt_hash"])
            if (
                record.get("submitted_before_execution") is not True
                or record.get("session_id") != manifest["session_ids"][record["arm"]]
                or record.get("dataset_hash") != manifest["dataset_hash"]
                or not isinstance(record.get("plan"), dict)
                or not record["plan"].get("plan_id")
                or AlgorithmPlan.model_validate(record["plan"]).model_dump(mode="json")
                != record["plan"]
                or record.get("plan_hash") != _fresh_hash(record["plan"])
                or not _valid_sha(record.get("strategy_hash"))
            ):
                raise FreshComparisonError("unsigned or unmatched strategy/plan submission")
            by_slot[key] = record
        if set(by_slot) != expected_slots:
            raise FreshComparisonError("submitted plan budget is incomplete")

        by_arm: dict[str, list[dict[str, Any]]] = {arm: [] for arm in FRESH_ARMS}
        measured_slots: set[tuple[str, int]] = set()
        for row in measured:
            if not isinstance(row, dict):
                raise FreshComparisonError("untyped measured result")
            key = (row["arm"], row["slot"])
            if key not in expected_slots or key in measured_slots:
                raise FreshComparisonError("duplicate or invalid measured slot")
            measured_slots.add(key)
            _anchored(row, "row_hash", row["row_hash"])
            receipt = by_slot[key]
            if (
                row.get("session_id") != receipt["session_id"]
                or row.get("dataset_hash") != manifest["dataset_hash"]
                or row.get("evaluator_version") != manifest["evaluator_version"]
                or row.get("cost_policy_hash") != manifest["cost_policy_hash"]
                or row.get("plan_hash") != receipt["plan_hash"]
                or row.get("strategy_hash") != receipt["strategy_hash"]
                or not isinstance(row.get("fills"), list)
                or row.get("fill_trace_hash") != _fresh_hash(row["fills"])
                or type(row.get("failed")) is not bool
            ):
                raise FreshComparisonError("costed observation/strategy/checkpoint mismatch")
            if (
                row.get("s7_predicted_direction") not in ("UP", "DOWN", "UNCHANGED", "UNKNOWN")
                or row.get("s7_observed_direction") not in ("UP", "DOWN", "UNCHANGED", "UNKNOWN")
            ):
                raise FreshComparisonError("invalid S7 hypothesis direction")
            _value(row["costed_net_return"], low=-1)
            _value(row["max_drawdown"], low=0, high=1)
            _value(row["paid_cost_usd"], low=0)
            if type(row["closed_trades"]) is not int or row["closed_trades"] < 0:
                raise FreshComparisonError("unverified closed trades count")
            _check_costed_fill_trace(row)
            by_arm[row["arm"]].append(row)
        if measured_slots != expected_slots:
            raise FreshComparisonError("unmeasured generation slot")
        resources = observations["resources"]
        if not isinstance(resources, dict) or set(resources) != set(FRESH_ARMS):
            raise FreshComparisonError("arm resource ledger missing")
        budget = manifest["budget_per_arm"]
        actual_resource_signatures = []
        for arm in FRESH_ARMS:
            usage = resources[arm]
            if not isinstance(usage, dict) or any(
                type(usage.get(k)) is not int or usage[k] < 0
                for k in ("plan_attempts", "s7_trials", "canonical_backtests",
                          "model_calls", "model_input_tokens",
                          "model_output_tokens", "elapsed_ms")
            ):
                raise FreshComparisonError("unverified model/backtest resources")
            if (
                usage["plan_attempts"] != budget["plan_attempts"]
                or usage["s7_trials"] != budget["s7_trials"]
                or usage["canonical_backtests"] != budget["canonical_backtests"]
                or usage["model_calls"] > budget["model_call_ceiling"]
                or usage["model_input_tokens"] + usage["model_output_tokens"]
                > budget["model_token_ceiling"]
            ):
                raise FreshComparisonError("candidate, trial, model or backtest budget bypass")
            actual_resource_signatures.append((
                usage["model_calls"],
                usage["model_input_tokens"] + usage["model_output_tokens"],
            ))
        risk = manifest["risk_gates"]
        summaries: list[dict[str, Any]] = []
        global_fills: set[str] = set()
        for arm in FRESH_ARMS:
            rows = sorted(by_arm[arm], key=lambda r: r["slot"])
            distinct_fills: set[str] = set()
            passed: set[str] = set()
            match = 0
            comparable = 0
            for row in rows:
                fills = row["fill_trace_hash"]
                if row["fills"]:
                    distinct_fills.add(fills)
                    global_fills.add(fills)
                if (
                    row["fills"] and not row["failed"]
                    and row["closed_trades"] >= risk["minimum_closed_trades"]
                    and row["max_drawdown"] <= risk["max_drawdown"]
                    and row["costed_net_return"] > 0
                ):
                    passed.add(fills)
                if row["s7_predicted_direction"] != "UNKNOWN" and (
                    row["s7_observed_direction"] != "UNKNOWN"
                ):
                    comparable += 1
                    match += row["s7_predicted_direction"] == row["s7_observed_direction"]
            summaries.append({
                "arm": arm,
                "sample_size": len(rows),
                "unique_executed_fill_traces": len(distinct_fills),
                "duplicate_fill_trace_count": sum(bool(row["fills"]) for row in rows)
                - len(distinct_fills),
                "risk_gate_passed_unique_signals": len(passed),
                "failed_trials": sum(row["failed"] for row in rows),
                "s7_direction_comparable": comparable,
                "s7_direction_matched": match,
                "s7_direction_match_rate": match / comparable if comparable else None,
                "median_costed_net_return": statistics.median(
                    row["costed_net_return"] for row in rows
                ),
                "median_max_drawdown": statistics.median(
                    row["max_drawdown"] for row in rows
                ),
                "canonical_backtests_declared": resources[arm]["canonical_backtests"],
                "model_calls_declared": resources[arm]["model_calls"],
                "model_tokens_declared": resources[arm]["model_input_tokens"]
                + resources[arm]["model_output_tokens"],
                "elapsed_ms_declared": resources[arm]["elapsed_ms"],
            })
        body: dict[str, Any] = {
            "schema": "T4_FRESH_EQUAL_BUDGET_DESCRIPTIVE_SCORE_V2",
            "status": "DESCRIPTIVE_NOT_INDEPENDENTLY_REPLAYED",
            "protocol_hash": protocol["protocol_hash"],
            "manifest_hash": expected_manifest_hash,
            "receipts_hash": expected_receipts_hash,
            "observations_hash": expected_observations_hash,
            "primary_metric": protocol["selection_metric"],
            "study_cohort_id": manifest["cohort_id"],
            "arm_summaries": summaries,
            "same_market_and_evaluator": True,
            "equal_declared_plan_s7_backtest_budgets": True,
            "actual_model_budget_equalized": len(set(actual_resource_signatures)) == 1,
            "global_distinct_executed_fill_hashes": len(global_fills),
            "number_of_independent_random_seeds": 1,
            "canonical_replay_independently_verified": False,
            "external_commit_timing_independently_verified": False,
            "actual_data_and_model_connection_independently_verified": False,
            "statistical_superiority_established": False,
            "independent_oos_approved": False,
            "broker_executable": False,
            "no_old_cohort_data_reused": True,
            "no_strategy_promoted": True,
        }
        return {**body, "report_hash": _fresh_hash(body)}
    except FreshComparisonError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        raise FreshComparisonError("malformed fresh research evidence") from exc


if __name__ == "__main__":
    main()
