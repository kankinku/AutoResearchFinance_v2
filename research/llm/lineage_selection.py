"""Conservative selection of S7-verified *development* successor parents.

This selects an input for further counted research, not OOS approval. Caller
must fully replay each candidate's immutable source, StrategyIR, fills and cost
model before setting replay_verified=True; labels or checksums alone are not proof.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any

from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy


class LineageSelectionError(ValueError):
    """Malformed/tampered candidate must never influence next generation."""


def _finite(row: Mapping[str, Any], key: str) -> float:
    val = row.get(key)
    if isinstance(val, bool) or not isinstance(val, (float, int)) or not isfinite(val):
        raise LineageSelectionError(f"nonfinite successor parent metric: {key}")
    return float(val)


def _valid_hash(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def choose_development_parent(
    candidates: Sequence[Mapping[str, Any]],
    *,
    min_closed_trades: int = 30,
    max_drawdown_multiplier: float = 1.25,
) -> dict[str, Any] | None:
    """Deterministic return-first choice with explicit risk, diversity, QQQ context.

    Hard gates filter invalid/degenerate results; QQQ-relative performance is
    *reported*, not required. Ex-post QQQ allocations are NOT usable as trading
    forecasts. The same development window is reused: statistical discovery
    and independent validation remain outstanding.
    """
    if not 1 <= min_closed_trades <= 1000 or not 1 <= max_drawdown_multiplier <= 2:
        raise LineageSelectionError("invalid parent selection policy")
    eligible: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        for name in (
            "source_evidence_hash",
            "lineage_report_hash",
            "successor_strategy_hash",
            "strategy_equity_hash",
        ):
            if not _valid_hash(row.get(name)):
                raise LineageSelectionError(f"invalid successor identity: {name}")
        digest = str(row["lineage_report_hash"])
        if digest in seen:
            raise LineageSelectionError("duplicate lineage report in parent pool")
        seen.add(digest)
        generation = row.get("source_generation")
        if type(generation) is not int or not 1 <= generation <= 100:
            raise LineageSelectionError("invalid source generation")
        ret = _finite(row, "successor_total_return")
        child_ret = _finite(row, "child_total_return")
        dd = _finite(row, "successor_max_drawdown")
        child_dd = _finite(row, "child_max_drawdown")
        exposure = _finite(row, "successor_market_exposure")
        qqq = _finite(row, "qqq_buy_and_hold_return")
        proxy = _finite(row, "qqq_exposure_matched_return")
        trades = row.get("successor_closed_trades")
        if type(trades) is not int or trades < 0 or trades > 1_000_000:
            raise LineageSelectionError("invalid counted closed trades")
        if (
            row.get("replay_verified") is not True
            or row.get("independent_oos_approved") is not False
            or row.get("broker_executable") is not False
            or not 0 <= dd <= 1
            or not 0 <= child_dd <= 1
            or not 0 <= exposure <= 1
            or ret <= -1
            or child_ret <= -1
            or qqq <= -1
            or proxy <= -1
        ):
            continue
        if (
            trades < min_closed_trades
            or exposure < 0.05
            or ret <= child_ret + 1e-12
            or dd > max(child_dd * max_drawdown_multiplier, 0.02)
        ):
            continue
        body = {
            "schema": "p0-3b-selected-development-parent-v1",
            "status": "PARENT_SELECTED_NOT_COUNTED",
            "source_generation": generation,
            "source_evidence_hash": str(row["source_evidence_hash"]),
            "lineage_report_hash": digest,
            "successor_strategy_hash": str(row["successor_strategy_hash"]),
            "strategy_equity_hash": str(row["strategy_equity_hash"]),
            "parent_quality": {
                "total_return": ret,
                "max_drawdown": dd,
                "closed_trades": trades,
                "market_exposure": exposure,
                "qqq_buy_and_hold_return": qqq,
                "qqq_exposure_matched_return": proxy,
            },
            "relative_qqq_bh_pp": 100 * (ret - qqq),
            "relative_exposure_proxy_pp": 100 * (ret - proxy),
            "selection_basis": "REPLAYED_COSTED_DEVELOPMENT_RETURN_WITH_MDD_TRADE_EXPOSURE_GATES",
            "comparators": "QQQ_COSTED_AND_POST_HOC_EXPOSURE_PROXY_NOT_FORWARD_TRADABLE",
            "independent_oos_approved": False,
            "broker_executable": False,
            "counted_generation_incremented": False,
        }
        if row.get("source_kind") == "COUNTED_S7_CHILD":
            for name in ("hypothesis_id", "source_report_hash"):
                if not row.get(name) or (
                    name == "source_report_hash" and not _valid_hash(row[name])
                ):
                    raise LineageSelectionError("counted S7 child origin incomplete")
            body.update(
                {
                    "source_kind": "COUNTED_S7_CHILD",
                    "hypothesis_id": str(row["hypothesis_id"]),
                    "source_report_hash": str(row["source_report_hash"]),
                }
            )
        eligible.append({**body, "selection_hash": content_hash(body)})
    if not eligible:
        return None
    eligible.sort(
        key=lambda x: (
            -x["parent_quality"]["total_return"],
            x["parent_quality"]["max_drawdown"],
            -x["parent_quality"]["closed_trades"],
            abs(x["parent_quality"]["market_exposure"] - 0.35),
            x["successor_strategy_hash"],
        )
    )
    return eligible[0]


def replay_lineage_candidate(
    catalog: ResearchCatalog,
    market: MarketDataSet,
    original: dict[str, Any],
    stored_experiment: dict[str, Any],
    stored_lineage: dict[str, Any],
) -> dict[str, Any]:
    """Reconstruct the actual child->successor from S7 and re-check every fill.

    Does not use metrics claimed by GPT or a sidecar as ground truth.
    This is read-only and never advances a counted generation.
    """
    from dataclasses import replace

    from core.features.registry import research_feature_specs
    from evaluation.metrics import calculate_metrics
    from research.indicator_engine.algorithm_plan import (
        AlgorithmPlan,
        compile_algorithm_plan,
    )
    from research.indicator_engine.development_benchmark import (
        compare_qqq_development_benchmarks,
    )
    from research.indicator_engine.strategy_adapter import evaluate_compiled_development
    from research.llm.director import ResearchIntent
    from research.llm.intent_bridge import apply_intent
    from research.llm.lineage_replay import verified_child_successor

    if (
        stored_lineage.get("source_evidence_hash") != original.get("evidence_hash")
        or stored_lineage.get("source_generation") != original.get("generation")
        or stored_lineage.get("report_hash")
        != content_hash({k: v for k, v in stored_lineage.items() if k != "report_hash"})
    ):
        raise LineageSelectionError("lineage origin or sidecar hash mismatch")
    hid = stored_lineage.get("hypothesis_id")
    if not isinstance(hid, str):
        raise LineageSelectionError("lineage hypothesis identity missing")
    proposals = [item for item in original["experiments"] if item["hypothesis_id"] == hid]
    if len(proposals) != 1:
        raise LineageSelectionError("lineage hypothesis is absent or duplicated")
    expected = verified_child_successor(
        catalog,
        market,
        original,
        stored_experiment,
        hypothesis_id=hid,
        expected_child_strategy_hash=stored_lineage["reproduced_child_strategy_hash"],
        continuation_intent=stored_lineage["continuation_intent"],
    )
    if json.loads(json.dumps(expected, sort_keys=True)) != json.loads(
        json.dumps(stored_lineage, sort_keys=True)
    ):
        raise LineageSelectionError("lineage cannot be exactly replayed")
    plan = AlgorithmPlan.model_validate(original["algorithm_plan"])
    base = compile_algorithm_plan(catalog, plan, market)
    child = apply_intent(
        base.compiled.strategy,
        ResearchIntent.model_validate(proposals[0]["proposed_intent"]),
        research_feature_specs(),
    )
    successor = apply_intent(
        child,
        ResearchIntent.model_validate(stored_lineage["continuation_intent"]),
        research_feature_specs(),
    )
    digest = content_hash(successor.model_dump(mode="json", by_alias=True))
    if digest != expected["successor_strategy_hash"]:
        raise LineageSelectionError("reconstructed promoted StrategyIR hash mismatch")
    outcome = evaluate_compiled_development(
        replace(base.compiled, strategy=successor, strategy_hash=digest), market
    )
    if (
        outcome.equity_hash != expected["successor_equity_hash"]
        or abs(outcome.final_equity - expected["successor_final_equity"]) > 1e-6
        or outcome.trades_count != expected["successor_fills"]
        or abs(outcome.total_paid_costs - expected["successor_costs"]) > 1e-6
    ):
        raise LineageSelectionError("promoted StrategyIR cost or fills replay mismatch")
    # Count actual closed pairs, not fills / 2 or a model's reported trades.
    open_position = False
    closed = 0
    by_time = {}
    for trade in outcome.trades:
        if trade.side == "buy" and not open_position:
            open_position = True
        elif trade.side == "sell" and open_position:
            open_position = False
            closed += 1
        else:
            raise LineageSelectionError("unpaired inherited execution trace")
        by_time[trade.timestamp] = open_position
    held = False
    exposure_days = 0
    for bar in market.bars:
        held = by_time.get(bar.timestamp.isoformat(), held)
        exposure_days += int(held)
    exposure = exposure_days / len(market.bars)
    benchmarks = compare_qqq_development_benchmarks(
        market,
        strategy_equity_curve=outcome.equity_curve,
        realized_exposure=exposure,
    )
    metrics = calculate_metrics(outcome.equity_curve, (), periods_per_year=252)
    if (
        abs(metrics.total_return - expected["successor_total_return"]) > 1e-9
        or abs(metrics.max_drawdown - expected["successor_max_drawdown"]) > 1e-9
    ):
        raise LineageSelectionError("counted candidate metrics do not replay")
    return {
        "source_generation": original["generation"],
        "source_evidence_hash": original["evidence_hash"],
        "lineage_report_hash": expected["report_hash"],
        "successor_strategy_hash": digest,
        "strategy_equity_hash": outcome.equity_hash,
        "child_total_return": expected["child_total_return"],
        "child_max_drawdown": expected["child_max_drawdown"],
        "successor_total_return": metrics.total_return,
        "successor_max_drawdown": metrics.max_drawdown,
        "successor_closed_trades": closed,
        "successor_market_exposure": exposure,
        "qqq_buy_and_hold_return": benchmarks["qqq_costed_buy_and_hold"]["total_return"],
        "qqq_exposure_matched_return": benchmarks["qqq_fixed_initial_allocation_proxy"][
            "total_return"
        ],
        "replay_verified": True,
        "independent_oos_approved": False,
        "broker_executable": False,
    }


def compile_replayed_successor(
    catalog: ResearchCatalog,
    market: MarketDataSet,
    original: dict[str, Any],
    stored_experiment: dict[str, Any],
    stored_lineage: dict[str, Any],
) -> CompiledAcademicStrategy:
    """Return the exact IR after whole lineage and fill replay, never proxy IR."""
    from dataclasses import replace

    from core.features.registry import research_feature_specs
    from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
    from research.llm.director import ResearchIntent
    from research.llm.intent_bridge import apply_intent

    verified = replay_lineage_candidate(
        catalog, market, original, stored_experiment, stored_lineage
    )
    base = compile_algorithm_plan(
        catalog, AlgorithmPlan.model_validate(original["algorithm_plan"]), market
    ).compiled
    matching = [
        x for x in original["experiments"] if x["hypothesis_id"] == stored_lineage["hypothesis_id"]
    ]
    if len(matching) != 1:
        raise LineageSelectionError("invalid inherited source hypothesis")
    child = apply_intent(
        base.strategy,
        ResearchIntent.model_validate(matching[0]["proposed_intent"]),
        research_feature_specs(),
    )
    successor = apply_intent(
        child,
        ResearchIntent.model_validate(stored_lineage["continuation_intent"]),
        research_feature_specs(),
    )
    digest = content_hash(successor.model_dump(mode="json", by_alias=True))
    if digest != verified["successor_strategy_hash"]:
        raise LineageSelectionError("source StrategyIR identity mismatch")
    return replace(base, strategy=successor, strategy_hash=digest)


def replay_counted_s7_child(
    catalog: ResearchCatalog,
    market: MarketDataSet,
    original: dict[str, Any],
    stored_experiment: dict[str, Any],
    parent: CompiledAcademicStrategy,
    hypothesis_id: str,
) -> tuple[dict[str, Any], CompiledAcademicStrategy]:
    """Replay a counted S7 child, binding decision audit, fees and report bytes.

    The parent's sealed cycle evidence and the S7 sidecar must already have
    passed their persistent hash chains; we independently reconstruct both.
    """
    from dataclasses import asdict, replace

    from core.features.registry import research_feature_specs
    from evaluation.metrics import calculate_metrics
    from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
    from research.indicator_engine.inherited_experiments import compare_inherited_experiments
    from research.indicator_engine.strategy_adapter import evaluate_compiled_development
    from research.llm.director import ResearchIntent
    from research.llm.intent_bridge import apply_intent

    if (
        original.get("inherited_strategy_ir") is None
        or original.get("strategy_hash") != parent.strategy_hash
        or original.get("dataset_hash") != market.dataset_hash
        or stored_experiment.get("original_generation_evidence_hash")
        != original.get("evidence_hash")
        or stored_experiment.get("study_scope") != "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
        or stored_experiment.get("record_hash")
        != content_hash({k: v for k, v in stored_experiment.items() if k != "record_hash"})
    ):
        raise LineageSelectionError("counted S7 source evidence integrity mismatch")
    report = stored_experiment["report"]
    if (
        report.get("broker_executable") is not False
        or report.get("out_of_sample_approved") is not False
        or report.get("causal_status") != "NOT_ESTABLISHED"
        or report.get("dataset_hash") != market.dataset_hash
        or report.get("audit_hash") != original.get("audit_hash")
    ):
        raise LineageSelectionError("counted S7 report identity mismatch")
    proposals = [e for e in original["experiments"] if e.get("hypothesis_id") == hypothesis_id]
    outcomes = [e for e in report["experiments"] if e.get("hypothesis_id") == hypothesis_id]
    if len(proposals) != 1 or len(outcomes) != 1:
        raise LineageSelectionError("counted S7 hypothesis missing or duplicated")
    diagnostic = {
        "context_hash": original["diagnostic_context_hash"],
        "audit_hash": original["audit_hash"],
        "strategy_hash": original["strategy_hash"],
        "dataset_hash": original["dataset_hash"],
        "summary": original["analysis_summary"],
        "hypotheses": [
            {
                "hypothesis_id": row["hypothesis_id"],
                "observed_ids": row["observed_ids"],
                "mechanism": row["mechanism"],
                "alternative": row["alternative"],
                "expected_metric": row["expected_metric"],
                "predicted_direction": row["predicted_direction"],
                "test_design": row["test_design"],
                "control": row["control"],
                "next_intent": row["proposed_intent"],
            }
            for row in original["experiments"]
        ],
    }
    replay = compare_inherited_experiments(
        parent,
        market,
        diagnostic,
        parent_proof_hash=original["inherited_parent"]["parent_selection_hash"],
    )
    if json.loads(json.dumps(asdict(replay))) != report:
        raise LineageSelectionError("counted S7 full report replay mismatch")
    if (
        outcomes[0]["status"] in ("NO_OBSERVED_EFFECT", "DEGENERATE_INACTIVE_CHILD")
        or outcomes[0]["same_fill_trace"] is True
    ):
        # Research memory still retains it, but it is not a better parent.
        raise IneligibleCountedChild("counted S7 child has no effective trading change")
    intent = ResearchIntent.model_validate(proposals[0]["proposed_intent"])
    child_ir = apply_intent(parent.strategy, intent, research_feature_specs())
    digest = content_hash(child_ir.model_dump(mode="json", by_alias=True))
    if digest != outcomes[0]["child_strategy_hash"]:
        raise LineageSelectionError("counted S7 child hash mismatch")
    compiled = replace(parent, strategy=child_ir, strategy_hash=digest)
    child = evaluate_compiled_development(compiled, market)
    if (
        abs(child.final_equity - outcomes[0]["child_final_equity"]) > 1e-6
        or child.trades_count != outcomes[0]["child_fill_count"]
        or abs(child.total_paid_costs - outcomes[0]["execution_delta"]["child_costs"]) > 1e-6
        or parent.strategy_hash == digest
    ):
        raise LineageSelectionError("counted S7 child fills/equity/cost mismatch")
    parent_metrics = calculate_metrics(
        audit_inherited_decisions(parent, market).evaluation.equity_curve,
        (),
        periods_per_year=252,
    )
    child_metrics = calculate_metrics(child.equity_curve, (), periods_per_year=252)
    closed = 0
    held = False
    timeline = {}
    for trade in child.trades:
        if trade.side == "buy" and not held:
            held = True
        elif trade.side == "sell" and held:
            held = False
            closed += 1
        else:
            raise LineageSelectionError("counted S7 child unpaired fill")
        timeline[trade.timestamp] = held
    exposed = 0
    held = False
    for bar in market.bars:
        held = timeline.get(bar.timestamp.isoformat(), held)
        exposed += int(held)
    exposure = exposed / len(market.bars)
    from research.indicator_engine.development_benchmark import (
        compare_qqq_development_benchmarks,
    )

    benchmarks = compare_qqq_development_benchmarks(
        market,
        strategy_equity_curve=child.equity_curve,
        realized_exposure=exposure,
    )
    lineage_body = {
        "schema": "counted-s7-child-origin-v1",
        "source_generation": original["generation"],
        "source_evidence_hash": original["evidence_hash"],
        "source_report_hash": stored_experiment["record_hash"],
        "hypothesis_id": hypothesis_id,
        "child_strategy_hash": digest,
    }
    return {
        "source_kind": "COUNTED_S7_CHILD",
        "source_generation": original["generation"],
        "source_evidence_hash": original["evidence_hash"],
        "source_report_hash": stored_experiment["record_hash"],
        "hypothesis_id": hypothesis_id,
        "lineage_report_hash": content_hash(lineage_body),
        "successor_strategy_hash": digest,
        "strategy_equity_hash": child.equity_hash,
        "child_total_return": parent_metrics.total_return,
        "child_max_drawdown": parent_metrics.max_drawdown,
        "successor_total_return": child_metrics.total_return,
        "successor_max_drawdown": child_metrics.max_drawdown,
        "successor_closed_trades": closed,
        "successor_market_exposure": exposure,
        "qqq_buy_and_hold_return": benchmarks["qqq_costed_buy_and_hold"]["total_return"],
        "qqq_exposure_matched_return": benchmarks["qqq_fixed_initial_allocation_proxy"][
            "total_return"
        ],
        "replay_verified": True,
        "independent_oos_approved": False,
        "broker_executable": False,
    }, compiled


class IneligibleCountedChild(ValueError):
    """Expected S7 non-improvement: record rejection, not fake promotion."""
