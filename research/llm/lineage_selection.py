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


class LineageSelectionError(ValueError):
    """Malformed/tampered candidate must never influence next generation."""


def _finite(row: Mapping[str, Any], key: str) -> float:
    val = row.get(key)
    if isinstance(val, bool) or not isinstance(val, (float, int)) or not isfinite(val):
        raise LineageSelectionError(f"nonfinite successor parent metric: {key}")
    return float(val)


def _valid_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
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
            "source_evidence_hash", "lineage_report_hash",
            "successor_strategy_hash", "strategy_equity_hash",
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
            or ret <= -1 or child_ret <= -1 or qqq <= -1 or proxy <= -1
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
        eligible.append({**body, "selection_hash": content_hash(body)})
    if not eligible:
        return None
    eligible.sort(key=lambda x: (
        -x["parent_quality"]["total_return"],
        x["parent_quality"]["max_drawdown"],
        -x["parent_quality"]["closed_trades"],
        abs(x["parent_quality"]["market_exposure"] - 0.35),
        x["successor_strategy_hash"],
    ))
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
        or stored_lineage.get("report_hash") != content_hash({
            k: v for k, v in stored_lineage.items() if k != "report_hash"
        })
    ):
        raise LineageSelectionError("lineage origin or sidecar hash mismatch")
    hid = stored_lineage.get("hypothesis_id")
    if not isinstance(hid, str):
        raise LineageSelectionError("lineage hypothesis identity missing")
    proposals = [
        item for item in original["experiments"] if item["hypothesis_id"] == hid
    ]
    if len(proposals) != 1:
        raise LineageSelectionError("lineage hypothesis is absent or duplicated")
    expected = verified_child_successor(
        catalog, market, original, stored_experiment,
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
        "qqq_exposure_matched_return": benchmarks[
            "qqq_fixed_initial_allocation_proxy"
        ]["total_return"],
        "replay_verified": True,
        "independent_oos_approved": False,
        "broker_executable": False,
    }
