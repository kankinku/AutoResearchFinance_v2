"""New G1 score must bind three external hash anchors and actual fill identity."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import AlgorithmPlan
from scripts.preregister_t4_equal_plan_comparison import (
    freeze_fresh_manifest,
    fresh_three_arm_protocol,
    local_plan,
)
from scripts.score_t4_equal_plan_comparison import (
    FreshComparisonError,
    validate_fresh_equal_budget_score,
)

ARMS = ("GPT_S7_S8", "FIXED_RULE", "RANDOM_SEEDED")


def _seal(body: dict, name: str) -> dict:
    return {**body, name: content_hash(body)}


def _inputs() -> tuple[dict, dict, dict, str, str, str]:
    manifest = freeze_fresh_manifest(
        fresh_three_arm_protocol(),
        market_hash="1" * 64, evaluator_version="quant-improved-evaluator-20261110",
        cost_policy_hash="2" * 64, feature_policy_hash="3" * 64,
        cohort_id="fresh-g1-validation",
        market_start="2021-01-01", market_end="2025-12-31",
        source_code_hash="4" * 64,
        session_ids={"GPT_S7_S8": "a" * 32, "FIXED_RULE": "b" * 32, "RANDOM_SEEDED": "c" * 32},
    )
    receipts = []
    observations = []
    for arm in ARMS:
        for slot in range(1, 11):
            plan = local_plan(slot)
            plan["plan_id"] = f"new_{arm.lower()}_{slot}"
            plan = AlgorithmPlan.model_validate(plan).model_dump(mode="json")
            strategy_hash = content_hash({"strategy": arm, "slot": slot})
            rec = _seal({
                "arm": arm, "slot": slot, "session_id": manifest["session_ids"][arm],
                "plan": plan, "plan_hash": content_hash(plan),
                "strategy_hash": strategy_hash, "dataset_hash": manifest["dataset_hash"],
                "submitted_before_execution": True,
            }, "receipt_hash")
            receipts.append(rec)
            # Fully typed synthetic executed-fill snapshots; not live market data.
            times = [
                (datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(
                    days=i + (1 if slot == 2 else slot) * 100
                ))
                .isoformat()
                for i in range(70)
            ]
            fills = [
                {"timestamp": stamp, "side": "buy" if i % 2 == 0 else "sell",
                 "price": 100.0, "quantity": 1.0, "notional": 100.0,
                 "cost": 1.0, "symbol": "QQQ"}
                for i, stamp in enumerate(times)
            ]
            # Different StrategyIR/plan hashes but identical executed fills.
            observations.append(_seal({
                "arm": arm, "slot": slot, "session_id": manifest["session_ids"][arm],
                "dataset_hash": manifest["dataset_hash"],
                "cost_policy_hash": manifest["cost_policy_hash"],
                "evaluator_version": manifest["evaluator_version"],
                "plan_hash": rec["plan_hash"], "strategy_hash": strategy_hash,
                "fills": fills, "fill_trace_hash": content_hash(fills),
                "costed_net_return": 0.1, "max_drawdown": 0.12,
                "closed_trades": 35, "paid_cost_usd": 70.0,
                "s7_predicted_direction": "UP",
                "s7_observed_direction": "UP" if slot % 2 == 0 else "DOWN",
                "failed": False,
            }, "row_hash"))
    receipt_body = {"schema": "T4_FRESH_SUBMISSIONS_V2", "manifest_hash": manifest["freeze_hash"],
                    "rows": receipts}
    observation_body = {
        "schema": "T4_FRESH_MEASUREMENTS_V2", "manifest_hash": manifest["freeze_hash"],
        "rows": observations,
        "resources": {
            arm: {"plan_attempts": 10, "s7_trials": 10, "canonical_backtests": 20,
                  "model_calls": 20 if arm == "GPT_S7_S8" else 0,
                  "model_input_tokens": 10000 if arm == "GPT_S7_S8" else 0,
                  "model_output_tokens": 5000 if arm == "GPT_S7_S8" else 0,
                  "elapsed_ms": 80000 if arm == "GPT_S7_S8" else 5000}
            for arm in ARMS
        },
    }
    r = _seal(receipt_body, "receipts_hash")
    o = _seal(observation_body, "observations_hash")
    return manifest, r, o, manifest["freeze_hash"], r["receipts_hash"], o["observations_hash"]


def _score(items):
    m, r, o, mm, rr, oo = items
    return validate_fresh_equal_budget_score(
        m, r, o, expected_manifest_hash=mm,
        expected_receipts_hash=rr, expected_observations_hash=oo,
    )


def test_fresh_three_arm_descriptive_score_never_claims_live_alpha() -> None:
    score = _score(_inputs())
    assert score["status"] == "DESCRIPTIVE_NOT_INDEPENDENTLY_REPLAYED"
    assert score["actual_model_budget_equalized"] is False
    assert score["statistical_superiority_established"] is False
    assert score["independent_oos_approved"] is False
    assert score["canonical_replay_independently_verified"] is False
    assert score["primary_metric"] == "UNIQUE_COSTED_FILL_TRACE_WITH_RISK_GATES"
    assert score["report_hash"] == content_hash({
        k: v for k, v in score.items() if k != "report_hash"
    })
    assert len(score["arm_summaries"]) == 3
    for summary in score["arm_summaries"]:
        assert summary["sample_size"] == 10
        assert summary["unique_executed_fill_traces"] == 9
        assert summary["duplicate_fill_trace_count"] == 1
        assert summary["risk_gate_passed_unique_signals"] == 9
        assert summary["s7_direction_match_rate"] == 0.5
        assert summary["canonical_backtests_declared"] == 20


@pytest.mark.parametrize("mutate", [
    "manifest_data", "manifest_budget", "manifest_evaluator", "observed_return",
    "observed_fill", "observed_strategy", "receipt_plan", "receipt_strategy",
    "observed_resign", "receipt_resign", "missing_arm", "duplicated_slot",
    "wrong_dataset", "budget_bypass", "model_token_excess", "nonfinite_metric",
    "uncounted_hypothesis", "resign_manifest", "changed_market_window",
    "changed_source_code",
])
def test_fresh_score_rejects_mutated_or_budget_overridden_evidence(mutate: str) -> None:
    inputs = list(deepcopy(_inputs()))
    m, r, o = inputs[:3]
    if mutate == "manifest_data":
        m["dataset_hash"] = "f" * 64
    elif mutate == "manifest_budget":
        m["budget_per_arm"]["canonical_backtests"] = 4
    elif mutate == "manifest_evaluator":
        m["evaluator_version"] = "legacy"
    elif mutate == "observed_return":
        o["rows"][0]["costed_net_return"] += 20
    elif mutate == "observed_fill":
        o["rows"][0]["fills"][0]["quantity"] += 1
    elif mutate == "observed_strategy":
        o["rows"][0]["strategy_hash"] = "f" * 64
    elif mutate == "receipt_plan":
        r["rows"][0]["plan"]["plan_id"] = "changed"
    elif mutate == "receipt_strategy":
        r["rows"][0]["strategy_hash"] = "f" * 64
    elif mutate == "observed_resign":
        o["rows"][0]["costed_net_return"] = 0.9
        o["rows"][0] = _seal({
            k: v for k, v in o["rows"][0].items() if k != "row_hash"
        }, "row_hash")
        o.update(_seal({
            k: v for k, v in o.items() if k != "observations_hash"
        }, "observations_hash"))
    elif mutate == "receipt_resign":
        r["rows"][0]["plan"]["plan_id"] = "changed"
        r["rows"][0]["plan_hash"] = content_hash(r["rows"][0]["plan"])
        r["rows"][0] = _seal({
            k: v for k, v in r["rows"][0].items() if k != "receipt_hash"
        }, "receipt_hash")
        r.update(_seal({k: v for k, v in r.items() if k != "receipts_hash"}, "receipts_hash"))
    elif mutate == "missing_arm":
        o["rows"] = [x for x in o["rows"] if x["arm"] != "RANDOM_SEEDED"]
    elif mutate == "duplicated_slot":
        o["rows"][1]["slot"] = 1
    elif mutate == "wrong_dataset":
        o["rows"][0]["dataset_hash"] = "f" * 64
    elif mutate == "budget_bypass":
        o["resources"]["FIXED_RULE"]["canonical_backtests"] = 19
    elif mutate == "model_token_excess":
        o["resources"]["GPT_S7_S8"]["model_input_tokens"] = 999999
    elif mutate == "nonfinite_metric":
        o["rows"][0]["max_drawdown"] = float("nan")
    elif mutate == "uncounted_hypothesis":
        o["rows"][0]["s7_observed_direction"] = "FAKE_WIN"
    elif mutate == "changed_market_window":
        m["market_window"]["end"] = "2023-12-31"
    elif mutate == "changed_source_code":
        m["source_code_hash"] = "f" * 64
    elif mutate == "resign_manifest":
        m["dataset_hash"] = "f" * 64
        m["freeze_hash"] = content_hash({k: v for k, v in m.items() if k != "freeze_hash"})
    with pytest.raises(FreshComparisonError):
        _score(inputs)


def test_new_score_cli_requires_all_external_anchors_and_never_overwrites(
    tmp_path, monkeypatch,
) -> None:
    import json
    import sys

    from scripts.score_t4_equal_plan_comparison import main

    m, r, o, mm, rr, oo = _inputs()
    files = [tmp_path / name for name in ("manifest.json", "receipts.json", "observed.json")]
    for path, payload in zip(files, (m, r, o), strict=True):
        path.write_text(json.dumps(payload))
    dest = tmp_path / "score.json"
    argv = [
        "score", "--fresh-manifest", str(files[0]),
        "--fresh-receipts", str(files[1]),
        "--fresh-observations", str(files[2]),
        "--expected-manifest-hash", mm,
        "--expected-receipts-hash", rr,
        "--expected-observations-hash", oo,
        "--fresh-output", str(dest),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert json.loads(dest.read_text()) == _score((m, r, o, mm, rr, oo))
    with pytest.raises(FileExistsError):
        main()

    # Externally anchored receipts never accept a changed result after submission.
    dest.unlink()
    changed = json.loads(files[2].read_text())
    changed["rows"][0]["max_drawdown"] = 0.99
    files[2].write_text(json.dumps(changed))
    with pytest.raises(FreshComparisonError):
        main()
    assert not dest.exists()



@pytest.mark.parametrize("alteration", ["cost", "closed_count", "overlapping_buys"])
def test_even_resealed_costed_execution_trace_must_be_self_consistent(
    alteration: str,
) -> None:
    m, r, o, mm, rr, _ = deepcopy(_inputs())
    trial = o["rows"][0]
    if alteration == "cost":
        trial["paid_cost_usd"] = 0.0
    elif alteration == "closed_count":
        trial["closed_trades"] = 60
    else:
        trial["fills"][1]["side"] = "buy"
    trial["fill_trace_hash"] = content_hash(trial["fills"])
    o["rows"][0] = _seal({
        key: value for key, value in trial.items() if key != "row_hash"
    }, "row_hash")
    o = _seal({key: value for key, value in o.items() if key != "observations_hash"},
              "observations_hash")
    with pytest.raises(FreshComparisonError):
        _score((m, r, o, mm, rr, o["observations_hash"]))


def test_same_fills_in_multiple_arms_are_not_globally_new_signals() -> None:
    scored = _score(_inputs())
    # Each arm has the same synthetic executed traces despite distinct plans.
    assert scored["global_distinct_executed_fill_hashes"] == 9
    assert sum(
        arm["unique_executed_fill_traces"] for arm in scored["arm_summaries"]
    ) == 27


def test_costed_risk_gate_excludes_one_over_drawdown_even_if_receipts_reanchored() -> None:
    m, r, o, mm, rr, _ = deepcopy(_inputs())
    trial = o["rows"][2]
    trial["max_drawdown"] = 0.9
    o["rows"][2] = _seal({
        key: value for key, value in trial.items() if key != "row_hash"
    }, "row_hash")
    o = _seal({key: value for key, value in o.items() if key != "observations_hash"},
              "observations_hash")
    report = _score((m, r, o, mm, rr, o["observations_hash"]))
    arm = next(x for x in report["arm_summaries"] if x["arm"] == "GPT_S7_S8")
    assert arm["risk_gate_passed_unique_signals"] == 8
    assert report["statistical_superiority_established"] is False
