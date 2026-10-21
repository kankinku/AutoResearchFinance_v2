# ruff: noqa: E501  # Preserve original typed diagnosis explanations as audit strings.
"""Bounded, deterministic, evidence-grounded research controller.

No OpenAI API/agent calls here: this is *not* independently GPT-authored per generation.
Uses canonical GPT checkpoint API with a GPT-designed fixed rule search policy;
never trades, calls OOS, changes authentication, or weakens core gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.engine import _regime_allows, _rules_match
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from research.indicator_engine.experiment_preflight import static_noop_hypotheses
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.llm.diagnostic_research import (
    DiagnosisContractError,
    DiagnosticResponse,
    approve_diagnostic_plan,
    build_diagnostic_context,
)
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state/moon-http/fresh-20261021"
SESSION = (STATE / "session-id.txt").read_text(encoding="utf-8").strip()
PROGRESS = STATE / "additional-50-progress.jsonl"
CONTROLLER = "DETERMINISTIC_GPT_DESIGNED_POLICY_NOT_PER_GENERATION_LLM"


def event(data: dict[str, Any]) -> None:
    with PROGRESS.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"at": datetime.now(timezone.utc).isoformat(), **data},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        f.flush()


def rule(left: str, *, val: float = 0.5, op: str = "greater_than") -> dict:
    return {"op": op, "left": left, "value": val}


ENTRIES = [
    None,
    ("ema_direction_20", 0.5),
    ("previous_range_breakout", 0.5),
    ("range_low_reclaim_20", 0.5),
    ("sma_pullback_20", 0.5),
    ("sma_direction", 0.5),
    ("plan_vote_score", 0.25),
    ("plan_vote_score", 0.5),
    ("plan_vote_score", 0.75),
    ("dual_sma_trend_50", 0.5),
]
EXITS = [
    ("plan_vote_score", 0.25),
    ("plan_vote_score", 0.5),
    ("plan_vote_score", 0.75),
    ("plan_vote_score", 0.0),
    ("plan_vote_score", 1.0),
    ("ema_direction_20", 0.5),
    ("dual_sma_trend_50", 0.5),
    ("sma_direction", 0.5),
    ("previous_range_breakout", 0.5),
    ("range_low_reclaim_20", 0.5),
    ("plan_entry", 0.5),
    ("sma_pullback_20", 0.5),
]


def designs():
    # First compare single exit/entry mechanisms, then paired counterfactuals.
    for e in EXITS:
        yield [
            {
                "op": "REPLACE_RULE",
                "path": "exit.conditions.0",
                "condition": rule(e[0], val=e[1], op="less_equal"),
            }
        ]
    for v in ENTRIES:
        if v:
            yield [
                {"op": "ADD_RULE", "path": "entry.conditions", "condition": rule(v[0], val=v[1])}
            ]
    for v in ENTRIES:
        if not v:
            continue
        for e in EXITS:
            yield [
                {"op": "ADD_RULE", "path": "entry.conditions", "condition": rule(v[0], val=v[1])},
                {
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": rule(e[0], val=e[1], op="less_equal"),
                },
            ]
    for entry in ENTRIES:
        if not entry:
            continue
        for e in EXITS:
            yield [
                {
                    "op": "REPLACE_RULE",
                    "path": "entry.conditions.1",
                    "condition": rule(entry[0], val=entry[1]),
                },
                {
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": rule(e[0], val=e[1], op="less_equal"),
                },
            ]

    # V2 recovery of G115 exhausted pool: unlike the original generator that
    # only ADDED entry gates (often producing the exact same entry signal), this
    # compares different entry mechanisms while holding the second filter and
    # exit constant. The same complete 1508-bar signal dedup, >=30 closed-trade
    # gate, net-cost audit and S7 are kept. These are bounded candidate families,
    # NOT independent LLM reasoning or evidence of causal improvement.
    entry_mechanisms = (
        ("ema_direction_20", 0.5),
        ("previous_range_breakout", 0.5),
        ("range_low_reclaim_20", 0.5),
        ("sma_pullback_20", 0.5),
        ("sma_direction", 0.5),
        ("dual_sma_trend_50", 0.5),
        ("plan_vote_score", 0.25),
        ("plan_vote_score", 0.5),
        ("plan_vote_score", 0.75),
        ("plan_branch_index", 1.5),
    )
    for path in ("entry.conditions.0", "entry.conditions.1"):
        for feat, threshold in entry_mechanisms:
            yield [{"op": "REPLACE_RULE", "path": path, "condition": rule(feat, val=threshold)}]
    # Contrast an alternate entry definition and exit mechanism together.
    for feat, threshold in entry_mechanisms:
        for xfeat, xval in EXITS:
            yield [
                {
                    "op": "REPLACE_RULE",
                    "path": "entry.conditions.0",
                    "condition": rule(feat, val=threshold),
                },
                {
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": rule(xfeat, val=xval, op="less_equal"),
                },
            ]
    # Alter the second entry gate instead of always stacking additional gates.
    for feat, threshold in entry_mechanisms:
        for xfeat, xval in EXITS:
            yield [
                {
                    "op": "REPLACE_RULE",
                    "path": "entry.conditions.1",
                    "condition": rule(feat, val=threshold),
                },
                {
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": rule(xfeat, val=xval, op="less_equal"),
                },
            ]
    # If two-condition AND keeps exhausting all eligible unique signals, test
    # rule disjunction explicitly rather than silently relaxing the trade gate.
    for logic in ("OR",):
        yield [{"op": "CHANGE_AND_OR", "path": "entry.logic", "logic": logic}]
        for feat, threshold in entry_mechanisms:
            yield [
                {"op": "CHANGE_AND_OR", "path": "entry.logic", "logic": logic},
                {
                    "op": "REPLACE_RULE",
                    "path": "entry.conditions.0",
                    "condition": rule(feat, val=threshold),
                },
            ]

    # G158 recovery: the last static 1–2 operation pool was measured and
    # exhausted. Explore pairwise entry-regime combinations with explicitly
    # different AND/OR semantics and cost-tested exits. These remain actual
    # signal-changing controlled experiments, not synthetic performance.
    # Candidate operations are enumerated deterministically and deduplicated
    # against all history before a new generation can be committed.
    from itertools import product

    for logic in ("OR", "AND"):
        for first, second, exit_spec in product(entry_mechanisms, entry_mechanisms, EXITS):
            if first == second:
                continue
            for exit_direction in ("less_equal", "greater_than"):
                yield [
                    {"op": "CHANGE_AND_OR", "path": "entry.logic", "logic": logic},
                    {
                        "op": "REPLACE_RULE",
                        "path": "entry.conditions.0",
                        "condition": rule(first[0], val=first[1]),
                    },
                    {
                        "op": "REPLACE_RULE",
                        "path": "entry.conditions.1",
                        "condition": rule(second[0], val=second[1]),
                    },
                    {
                        "op": "REPLACE_RULE",
                        "path": "exit.conditions.0",
                        "condition": rule(exit_spec[0], val=exit_spec[1], op=exit_direction),
                    },
                ]


def get_done_attempts() -> set[str]:
    ret = set()
    if PROGRESS.is_file():
        for line in PROGRESS.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                if item.get("kind") in ("plan_rejected", "plan_submitted"):
                    ret.add(item["signature"])
            except (ValueError, KeyError):
                pass
    return ret


def diagnosis(c: dict, *, generation: int, parent: dict, applied_ops: list[dict]) -> dict:
    obs = c["observations"]
    if obs.get("loss_cases"):
        sample = obs["loss_cases"][0]
        ids = [sample["trade_id"], sample["entry_decision_id"]]
        entry = sample.get("entry_indicator_values", {})
        exit = sample.get("exit_indicator_values", {})
        fact = f"largest sampled losing trade net PnL ${sample['net_pnl']:.2f}, entry vote ${entry.get('plan_vote_score')}, exit vote ${exit.get('plan_vote_score')}."
        # Contrast with alternative (none of the directional predictions are proven).
        applied_exit = next(
            (
                o.get("condition")
                for o in applied_ops
                if o["op"] == "REPLACE_RULE" and o["path"] == "exit.conditions.0"
            ),
            None,
        )
        # Never submit the very same controlled rule as a hypothesis (atomicity).
        candidate_exit = (
            0.25
            if (
                applied_exit is None
                or applied_exit.get("left") != "plan_vote_score"
                or float(applied_exit.get("value", -1)) != 0.25
            )
            else 0.5
        )
        hyp_op = {
            "op": "REPLACE_RULE",
            "path": "exit.conditions.0",
            "condition": rule("plan_vote_score", val=candidate_exit, op="less_equal"),
        }
        metric = "max_drawdown"
        direction = "DECREASE"
        mechanism = "Entry-to-exit vote deterioration may represent whipsaw versus true regime reversal; a changed score exit threshold could reduce peak-to-trough losses in weak sessions."
        alternative = "A threshold shift could trap positions in drawdowns or prematurely close profitable rallies and worsen net return even if costs decrease."
    elif obs.get("non_execution_decision_samples"):
        sample = obs["non_execution_decision_samples"][0]
        ids = [sample["decision_id"]]
        fact = (
            f"no fill; sampled decision {sample['decision_id']} action {sample['decision_action']}."
        )
        hyp_op = {"op": "REMOVE_RULE", "path": "entry.conditions.1"}
        metric = "trade_count"
        direction = "INCREASE"
        mechanism = "A strict entry gate may block every execution; relaxing a secondary entry condition could permit enough fills for meaningful evaluation."
        alternative = "Permitting more fills can add fees and false entries without economically useful return."
    else:
        x = obs.get("execution_samples", [])
        if not x:
            raise RuntimeError("NO_REFERENCABLE_OBSERVATIONS")
        sample = x[0]
        ids = [sample["decision_id"]]
        fact = f"sampled executed decision {sample['decision_id']}."
        hyp_op = {
            "op": "REPLACE_RULE",
            "path": "exit.conditions.0",
            "condition": rule("plan_vote_score", val=0.25, op="less_equal"),
        }
        metric = "total_return"
        direction = "INCREASE"
        mechanism = "Observed executable signals suggest exit timing could change profit capture; adjusting the vote-score exit threshold may reduce avoidable churn."
        alternative = "Longer holding can increase adverse excursion, and development sample feedback is not independent validation."
    metrics = c["metrics"]
    return {
        "context_hash": c["context_hash"],
        "audit_hash": c["audit_hash"],
        "strategy_hash": c["strategy_hash"],
        "dataset_hash": c["dataset_hash"],
        "summary": (
            f"G{generation} rule-policy review (not independent per-generation GPT model call): "
            f"costed return={metrics['total_return']:.4%}, "
            f"MDD={metrics['max_drawdown']:.4%}, "
            f"closed trades={metrics['trade_count']}, "
            f"exposure={metrics['exposure']:.4%}; {fact} "
            "Contrasting the selected parent remains development-only, not causal or OOS."
        ),
        "hypotheses": [
            {
                "hypothesis_id": f"g{generation}_exit_or_entry_counterfactual",
                "observed_ids": ids,
                "mechanism": mechanism,
                "alternative": alternative,
                "expected_metric": metric,
                "predicted_direction": direction,
                "test_design": "RULE_STRUCTURE",
                "control": "PARENT_UNCHANGED",
                "next_intent": {
                    "mode": "structure",
                    "parent_ids": [c["algorithm_parent_id"]],
                    "operations": [hyp_op],
                    "rationale": (
                        f"G{generation} one-rule controlled development counterfactual "
                        "against unchanged selected parent; inspect actual fills, MDD, "
                        "return, costs. No independent causality claim."
                    ),
                },
            }
        ],
    }


def main(max_new: int):
    assert 1 <= max_new <= 100
    service = AcademicMCPCheckpointService(project_root=ROOT, state_dir=STATE / "research")
    result = service.get({"session_id": SESSION})
    target = result["requested_generations"]
    assert 3 <= result["completed_generations"] < target <= 1000
    assert result["completed_generations"] >= 3
    assert result["orders_enabled"] is False and result["independent_oos_approved"] is False
    assert (
        result["dataset_hash"] == "f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e"
    )
    successes = 0
    tested = get_done_attempts()
    while successes < max_new and result["completed_generations"] < target:
        assert result["checkpoint_phase"] == "AWAITING_PLAN"
        g = result["completed_generations"] + 1
        c = result["model_context"]
        parent = c["inherited_parent_strategy_id"]
        parent_hash = c["inherited_parent_strategy_hash"]
        prev = result["history"][-1]["evidence_hash"]
        if not c["counted_parent_inheritance_ready"]:
            raise RuntimeError("NO_VERIFIED_PARENT_G" + str(g))
        candidate = None
        staged = None
        # A strict costed fill change against the selected parent is NOT enough:
        # an identical effective entry/exit vector may already be counted in
        # another generation. Preflight against the entire immutable history.
        with service._connect() as db:
            _, catalog, dataset, current = service._state(db, SESSION)
            selected_compiled, _, _ = service._selected_ir(catalog, dataset, current)
        previous_effective = {h.get("effective_signal_hash") for h in result["history"]}
        values = {k: list(v) for k, v in selected_compiled.feature_values.items()}
        feedback_active = getattr(service, "precommit_child_risk_budget", None) is not None
        feedback_holder = [c.get("precommit_rejection_feedback")] if feedback_active else []
        if feedback_active:
            if not feedback_holder[0] or feedback_holder[0].get("schema") != "p2-risk-feedback-v1":
                raise RuntimeError("UNVERIFIED_P2_REJECTION_FEEDBACK")
            from research.llm.precommit_rejection_feedback import (
                iter_feedback_adjusted_designs,
            )

            candidates_iter = iter_feedback_adjusted_designs(list(designs()), feedback_holder)
        else:
            candidates_iter = designs()
        for ops in candidates_iter:
            # Avoid repeating a failed or successful candidate on the same parent.
            digest = hashlib.sha256(
                json.dumps([parent_hash, ops], sort_keys=True).encode()
            ).hexdigest()
            if digest in tested:
                continue
            tested.add(digest)
            intent = {
                "mode": "structure",
                "parent_ids": [parent],
                "operations": ops,
                "rationale": (
                    f"G{g} adaptive continuation from measured G{g - 1} evidence: "
                    f"parent_hash={parent_hash}, evidence={prev}. "
                    "Test a single exit timing/entry selectivity mechanism or paired "
                    "gate under unchanged QQQ DEVELOPMENT dataset and costs; "
                    "rule catalogue is GPT-designed deterministic policy, NOT an "
                    "independent live GPT reasoning call for this generation."
                ),
            }
            try:
                trial = ResearchIntent.model_validate(intent)
                derived = apply_intent(selected_compiled.strategy, trial, research_feature_specs())
                active = {
                    "dataset_hash": dataset.dataset_hash,
                    "entry": tuple(
                        _rules_match(derived.entry.conditions, derived.entry.logic, values, i)
                        for i in range(len(dataset.bars))
                    ),
                    "exit": tuple(
                        _rules_match(derived.exit.conditions, derived.exit.logic, values, i)
                        for i in range(len(dataset.bars))
                    ),
                    "regime": tuple(
                        _regime_allows(derived, values, i) for i in range(len(dataset.bars))
                    ),
                }
                eff = content_hash(active)
                if eff in previous_effective:
                    event(
                        {
                            "kind": "plan_rejected",
                            "generation": g,
                            "signature": digest,
                            "error_type": "PRECHECK_DUPLICATE_EFFECTIVE_SIGNALS",
                        }
                    )
                    continue
                compiled = replace(
                    selected_compiled,
                    strategy=derived,
                    strategy_hash=content_hash(derived.model_dump(mode="json", by_alias=True)),
                )
                measured = audit_inherited_decisions(compiled, dataset).llm_packet["metrics"]
                if measured["trade_count"] < 30:
                    event(
                        {
                            "kind": "plan_rejected",
                            "generation": g,
                            "signature": digest,
                            "error_type": "INSUFFICIENT_CLOSED_TRADES_FOR_REVIEW",
                            "observed_trades": measured["trade_count"],
                        }
                    )
                    continue
                staged = service.submit_plan(
                    {
                        "session_id": SESSION,
                        "checkpoint_token": result["checkpoint_token"],
                        "plan": intent,
                        "require_execution_change": True,
                    }
                )
                assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
            except (ValueError, RuntimeError) as exc:
                rejection_type = (
                    "P2_PRECOMMIT_RISK_REJECTED"
                    if str(exc).startswith("P2_PRECOMMIT_RISK_REJECTED:")
                    else type(exc).__name__
                )
                event(
                    {
                        "kind": "plan_rejected",
                        "generation": g,
                        "signature": digest,
                        "error_type": rejection_type,
                        "error": str(exc)[:220],
                    }
                )
                if rejection_type == "P2_PRECOMMIT_RISK_REJECTED" and feedback_active:
                    updated = service.get({"session_id": SESSION})
                    if (
                        updated["checkpoint_phase"] != "AWAITING_PLAN"
                        or updated["checkpoint_token"] != result["checkpoint_token"]
                        or updated["completed_generations"] != result["completed_generations"]
                    ):
                        raise RuntimeError("P2_REJECTION_CHANGED_CHECKPOINT") from exc
                    new_feedback = updated["model_context"]["precommit_rejection_feedback"]
                    if new_feedback["rejection_count"] <= feedback_holder[0]["rejection_count"]:
                        raise RuntimeError("P2_REJECTION_NOT_RECORDED") from exc
                    feedback_holder[0] = new_feedback
                    event(
                        {
                            "kind": "risk_feedback_adaptation",
                            "generation": g,
                            "rejection_count": new_feedback["rejection_count"],
                            "absolute_mdd_failures": new_feedback["absolute_mdd_failures"],
                            "relative_mdd_failures": new_feedback["relative_mdd_failures"],
                            "trade_count_failures": new_feedback["trade_count_failures"],
                            "hypothesis": new_feedback["hypothesis"],
                            "proposed_domain_order": new_feedback["proposed_domain_order"],
                            "evidence_digest": new_feedback["evidence_digest"],
                            "controller": "DETERMINISTIC_SIGNED_EVIDENCE_GUIDANCE_NOT_GPT",
                        }
                    )
                continue
            except Exception as exc:
                # Catch only known, pre-commit validation errors; unexpected errors should stop.
                from research.indicator_engine.catalog import ResearchCatalogError

                if isinstance(exc, ResearchCatalogError):
                    event(
                        {
                            "kind": "plan_rejected",
                            "generation": g,
                            "signature": digest,
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:220],
                        }
                    )
                    continue
                raise
            candidate = intent
            event(
                {
                    "kind": "plan_submitted",
                    "generation": g,
                    "signature": digest,
                    "parent_hash": parent_hash,
                    "operations": ops,
                    "metrics": staged["model_context"]["metrics"],
                    "s2_preflight": staged["model_context"]
                    .get("s2_execution_preflight", {})
                    .get("status"),
                }
            )
            break
        if staged is None or candidate is None:
            raise RuntimeError("EXHAUSTED_TYPED_PLAN_POOL_G" + str(g))
        dc = staged["model_context"]
        diagnose = diagnosis(dc, generation=g, parent=c, applied_ops=candidate["operations"])
        # Preflight the semantic mutation BEFORE irreversibly claiming diagnosis.
        # A duplicate diagnosis would interrupt the gateway and require
        # operator-only recovery, so fail closed rather than submit it.
        with service._connect() as db:
            row, catalog, dataset, current = service._state(db, SESSION)
            pending = json.loads(row["plan_json"])
            _, compiled, _ = service._materialize_inherited(catalog, dataset, current, pending)
        audit = audit_inherited_decisions(compiled, dataset)
        trusted = build_diagnostic_context(audit, compiled.strategy)
        validated = False
        alternatives = [
            {
                "op": "REPLACE_RULE",
                "path": "exit.conditions.0",
                "condition": rule("plan_vote_score", val=v, op="less_equal"),
            }
            for v in (0.25, 0.5, 0.75, 0.0, 1.0)
        ]
        alternatives += [
            {
                "op": "REPLACE_RULE",
                "path": "exit.conditions.0",
                "condition": rule(left, val=0.5, op="less_equal"),
            }
            for left in ("ema_direction_20", "sma_direction", "dual_sma_trend_50", "plan_entry")
        ]
        if dc["observations"].get("non_execution_decision_samples"):
            alternatives += [{"op": "REMOVE_RULE", "path": "entry.conditions.1"}]
        # Try initially evidence-directed hypothesis, then bounded alternatives.
        initial = diagnose["hypotheses"][0]["next_intent"]["operations"][0]
        alternatives = [initial] + alternatives
        for hyp_op in alternatives:
            diagnose["hypotheses"][0]["next_intent"]["operations"] = [hyp_op]
            # Mechanism language reflects the exact alternative being tested.
            diagnose["hypotheses"][0]["mechanism"] = (
                "Measured losing or non-execution cases motivate a controlled "
                "single-rule experiment changing the exit or secondary entry "
                "gate; the impact on fills, net return and drawdown is uncertain."
            )
            try:
                typed = DiagnosticResponse.model_validate(diagnose)
                if static_noop_hypotheses(compiled.strategy, typed):
                    continue
                approve_diagnostic_plan(audit, compiled.strategy, trusted, diagnose)
                validated = True
                break
            except (DiagnosisContractError, ValueError):
                continue
        if not validated:
            event({"kind": "diagnosis_preflight_blocked", "generation": g})
            raise RuntimeError("NO_UNCHANGED_FREE_DIAGNOSTIC_G" + str(g))
        try:
            out = service.submit_diagnosis(
                {
                    "session_id": SESSION,
                    "checkpoint_token": staged["checkpoint_token"],
                    "diagnosis": diagnose,
                    "require_signal_change": True,
                }
            )
        except Exception as exc:
            event(
                {
                    "kind": "diagnosis_failed",
                    "generation": g,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:450],
                    "phase": "MAY_STILL_BE_AWAITING_DIAGNOSIS_OR_INTERRUPTED",
                }
            )
            raise
        assert out["completed_generations"] == g
        assert out["history"][-1]["previous_evidence_hash"] == prev
        assert out["orders_enabled"] is False
        assert out.get("controlled_experiments_automatically_evaluated") is True
        x = out["history"][-1]
        e = out["latest_controlled_experiments"]
        assert e["original_generation_evidence_hash"] == x["evidence_hash"]
        event(
            {
                "kind": "generation_committed",
                "generation": g,
                "evidence_hash": x["evidence_hash"],
                "parent_evidence_hash": prev,
                "strategy_hash": x["strategy_hash"],
                "metrics": x["metrics"],
                "s7_report_hash": e.get("report_hash"),
                "s7": (
                    {"experiment_count": len(e.get("experiments", [])), "status": e.get("status")}
                ),
            }
        )
        print(
            json.dumps(
                {
                    "g": g,
                    "r": round(x["metrics"]["total_return"] * 100, 2),
                    "mdd": round(x["metrics"]["max_drawdown"] * 100, 2),
                    "trades": x["metrics"]["trade_count"],
                    "evidence": x["evidence_hash"][:12],
                    "status": out["status"],
                }
            ),
            flush=True,
        )
        successes += 1
        result = out
    print(
        "SUMMARY",
        json.dumps(
            {
                "completed": result["completed_generations"],
                "requested": result["requested_generations"],
                "processed_this_invocation": successes,
                "controller": CONTROLLER,
                "status": result["status"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-new", type=int, default=5)
    opts = ap.parse_args()
    try:
        main(opts.max_new)
    except Exception as ex:
        event(
            {"kind": "controller_halted", "error_type": type(ex).__name__, "error": str(ex)[:500]}
        )
        traceback.print_exc()
        raise
