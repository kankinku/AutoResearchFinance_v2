"""EXPLICIT SYNTHETIC 100 checkpoint test. No LLM API, historical G150, live data or orders."""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
from research.llm.checkpoint_autopilot import AcademicCheckpointAutopilot
from tests.research.test_academic_algorithm_plan import _market, _plan
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

ROOT = Path(os.environ.get("QUANT100_SYNTHETIC_TEST_ROOT", "/tmp/quant100-isolated-20261110"))
NAMES = [
    "time_series_momentum", "previous_range_breakout", "sma_pullback_20",
    "dual_sma_trend_50", "ema_direction_20", "range_low_reclaim_20",
]


def write_x(path: Path, obj: object) -> None:
    with path.open("x", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def service() -> AcademicMCPCheckpointService:
    return AcademicMCPCheckpointService(project_root=ROOT / "project", state_dir=ROOT / "state")


def initialize() -> None:
    if ROOT.exists():
        raise RuntimeError("Refuse to overwrite an existing stress-test root")
    ROOT.mkdir(mode=0o700, parents=True)
    (ROOT / "project" / "data").mkdir(parents=True)
    m = _market()
    ParquetDataProvider.write(ROOT / "project" / "data" / "study.parquet", m)
    svc = service()
    catalog = svc._catalog("s6-v2")
    rng = random.Random(20261110)
    plans: list[dict] = []
    unique: set[str] = set()
    attempts = 0
    for _attempt in range(2500):
        if len(plans) == 100:
            break
        draft = _plan().model_dump(mode="json")
        draft["plan_id"] = f"synthetic_distinct_{len(plans) + 1:03d}"
        for case in draft["cases"]:
            a, b = rng.sample(NAMES, 2)
            w = rng.uniform(0.15, 0.85)
            case["votes"] = [
                {"indicator_id": a, "weight": w},
                {"indicator_id": b, "weight": 1 - w},
            ]
            case["min_score"] = rng.choice((0.2, 0.3, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9))
            case["when"]["threshold"] = rng.uniform(0.00000005, 0.00035)
        typed = AlgorithmPlan.model_validate(draft)
        compiled = compile_algorithm_plan(catalog, typed, m)
        key = content_hash({
            "entry": compiled.compiled.feature_values["plan_entry"],
            "regime": compiled.compiled.feature_values["plan_regime"],
        })
        if key not in unique:
            unique.add(key)
            plans.append(draft)
        attempts += 1
    if len(plans) != 100:
        raise AssertionError(
            f"unable to preselect 100 distinct synthetic effective signals: {len(plans)}"
        )
    write_x(ROOT / "preselected_plans.json", plans)
    begun = svc.start({"data_path": "data/study.parquet", "generations": 100})
    state = svc.get({"session_id": begun["session_id"]})
    assert state["completed_generations"] == 0 and state["orders_enabled"] is False
    write_x(ROOT / "session.json", {
        "session_id": begun["session_id"],
        "requested_generations": 100,
        "data_origin": "SYNTHETIC_TESTS_ONLY",
        "plan_generation": "PRESELECTED_FROM_SYNTHETIC_DATA_NOT_GPT",
        "market_hash": m.dataset_hash,
        "plan_set_hash": content_hash(plans),
        "expected_order_permission": False,
        "actual_gpt_calls": 0,
        "candidates_screened": attempts,
    })
    print(json.dumps({"event": "INIT", "session": begun["session_id"],
        "synthetic_candidates_screened": attempts, "unique_effective_signals": len(plans),
        "status": state["status"], "research_only": True,
        "actual_gpt_calls": 0}, ensure_ascii=False), flush=True)


class SyntheticPlanProvider:
    def __init__(self, *, fail_generation: int | None = None):
        self.plans = json.loads((ROOT / "preselected_plans.json").read_text())
        self.fail_generation = fail_generation
        self.current_generation = None
        self.plan_calls = 0
        self.diagnosis_calls = 0

    def propose(self, context: dict) -> dict:
        if context.get("output_contract") == "AlgorithmPlan":
            generation = context["generation"]
            self.plan_calls += 1
            self.current_generation = generation
            return self.plans[generation - 1]
        self.diagnosis_calls += 1
        if self.fail_generation and self.current_generation == self.fail_generation:
            self.fail_generation = None
            raise RuntimeError("SIMULATED_PROVIDER_DISCONNECT_IN_DIAGNOSIS")
        observations = context["observations"]
        if observations["execution_samples"]:
            return ScriptedResearcher().propose(context)
        # Real zero-fill cycles legitimately contain no executed trades.
        # Cite a signed non-executing decision, never invent a fake trade ID.
        anchor = observations["non_execution_decision_samples"][0]
        return {
            "context_hash": context["context_hash"],
            "audit_hash": context["audit_hash"],
            "strategy_hash": context["strategy_hash"],
            "dataset_hash": context["dataset_hash"],
            "summary": (
                "No fills occurred; propose a predeclared one-rule ablation "
                "against the unchanged control."
            ),
            "hypotheses": [{
                "hypothesis_id": "zero_fill_rule_test",
                "observed_ids": [anchor["decision_id"]],
                "mechanism": "The existing risk or entry gate prevented a trade from executing.",
                "alternative": (
                    "The entry gate may be irrelevant because the indicator stayed flat."
                ),
                "expected_metric": "trade_count",
                "predicted_direction": "INCREASE",
                "test_design": "RULE_STRUCTURE",
                "control": "PARENT_UNCHANGED",
                "next_intent": {
                    "mode": "structure",
                    "parent_ids": [context["algorithm_parent_id"]],
                    "operations": [{
                        "op": "REPLACE_RULE", "path": "entry.conditions.0",
                        "condition": {
                            "left": "plan_vote_score", "op": "greater_than", "value": 0.2,
                        },
                    }],
                    "rationale": (
                        "Measure one changed entry gate against the unchanged "
                        "development control."
                    ),
                },
            }],
        }


def run(batch: int, *, fail_generation: int | None = None) -> int:
    sid = json.loads((ROOT / "session.json").read_text())["session_id"]
    svc = service()
    before = svc.get({"session_id": sid})
    current = int(before["completed_generations"])
    if current == 100:
        print(json.dumps({"event": "ALREADY_COMPLETE", "generations": 100}), flush=True)
        return 0
    provider = SyntheticPlanProvider(fail_generation=fail_generation)
    start = time.monotonic()
    try:
        result = AcademicCheckpointAutopilot(svc, provider).run(
            sid, max_generations=min(batch, 100 - current),
        )
    except BaseException as exc:
        after = svc.get({"session_id": sid})
        print(json.dumps({
            "event": "CHECKPOINT_INTERRUPTION", "mode": "SYNTHETIC_NOT_REAL_GPT",
            "error_type": type(exc).__name__,
            "error": str(exc)[:320],
            "before": current,
            "completed": after["completed_generations"],
            "phase": after["checkpoint_phase"],
            "status": after["status"],
            "submitted_new_plans": provider.plan_calls,
            "submitted_diagnoses": provider.diagnosis_calls,
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "orders_enabled": after["orders_enabled"],
        }, ensure_ascii=False), flush=True)
        # We expect a genuine failing exit from a deliberate provider disconnect.
        return 12
    state = svc.get({"session_id": sid})
    assert state["completed_generations"] == result["completed_generations"]
    assert state["orders_enabled"] is False and state["independent_oos_approved"] is False
    assert len(state["history"]) == result["completed_generations"]
    assert len({h["evidence_hash"] for h in state["history"]}) == len(state["history"])
    print(json.dumps({
        "event": "BATCH_COMPLETED", "mode": "SYNTHETIC_NOT_REAL_GPT",
        "before": current, "completed": state["completed_generations"],
        "new": result["advanced_generations_this_call"],
        "plans_in_this_process": provider.plan_calls,
        "diagnoses_in_this_process": provider.diagnosis_calls,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "status": result["status"], "phase": state["checkpoint_phase"],
        "observed_S7_measurements": result["measured_hypotheses_read_or_executed"],
        "actual_gpt_calls": 0, "orders_enabled": False,
    }, ensure_ascii=False), flush=True)
    return 0


def audit() -> None:
    sid = json.loads((ROOT / "session.json").read_text())["session_id"]
    svc = service()
    state = svc.get({"session_id": sid})
    history = state["history"]
    n = state["completed_generations"]
    hash_fields = ["evidence_hash", "algorithm_semantic_hash", "effective_signal_hash"]
    uniqueness = {name: len(set(row[name] for row in history)) for name in hash_fields}
    proof_count = 0
    for i in range(1, n + 1):
        receipt = svc.evaluate_experiments({"session_id": sid, "generation": i})
        assert receipt["original_generation_evidence_hash"] == history[i-1]["evidence_hash"]
        proof_count += 1
    runner_provider = SyntheticPlanProvider()
    replay = AcademicCheckpointAutopilot(svc, runner_provider).run(sid, max_generations=2)
    assert replay["advanced_generations_this_call"] == 0
    assert runner_provider.plan_calls == runner_provider.diagnosis_calls == 0
    full = bool(n == 100 and state["status"] == "COMPLETED"
        and all(value == 100 for value in uniqueness.values())
        and proof_count == 100
        and state["orders_enabled"] is False
        and state["independent_oos_approved"] is False
        and replay["external_model_proposals_this_call"] == 0)
    output = {
        "schema": "QUANT_100_GENERATION_SYNTHETIC_CHECKPOINT_STRESS_V1",
        "test_only": True,
        "actual_gpt_calls": 0,
        "live_market_data_used": False,
        "generation_target": 100,
        "completed": n,
        "status": state["status"],
        "checkpoint_phase": state["checkpoint_phase"],
        "history_hashes": uniqueness,
        "verified_S7_generations": proof_count,
        "postcompletion_replay_new_generations": replay["advanced_generations_this_call"],
        "orders_enabled": state["orders_enabled"],
        "independent_oos_approved": state["independent_oos_approved"],
        "test_acceptance_pass": full,
        "assessment": "SYNTHETIC_EXECUTION_ONLY_NOT_REAL_GPT" if full else "INCOMPLETE",
    }
    write_x(ROOT / "final_audit.json", output)
    print(json.dumps({"event": "FINAL_AUDIT", **output}, ensure_ascii=False), flush=True)
    if not full:
        raise AssertionError("synthetic checkpoint stress did not meet the 100-generation contract")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("init", "run", "audit"))
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--fail-generation", type=int)
    args = ap.parse_args()
    if args.action == "init":
        initialize()
    elif args.action == "run":
        raise SystemExit(run(args.batch, fail_generation=args.fail_generation))
    else:
        audit()
