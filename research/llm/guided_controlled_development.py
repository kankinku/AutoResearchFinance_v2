"""S7-compatible, source-bound Guided parent/child controlled DEVELOPMENT replay.

Only bars preceding the earliest time-fold test are physically available to
this evaluator. This is observational feedback, NOT causal, production, OOS,
or a substitute for the original academic S7 protocol.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from typing import Any

from core.backtest.engine import BacktestEngine, BacktestRequest, Trade
from core.data.contracts import DataZone, MarketDataSet
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from evaluation.metrics import calculate_metrics
from experiments.identity import semantic_strategy_hash
from orchestration.evaluation_runner import _market_feature_inputs
from orchestration.pipeline import GenerationPipeline
from research.llm.guided_research_feedback import check_proposal
from strategy_ir.schema import StrategyIR


def _training_cutoff(attempt: dict, dataset: MarketDataSet) -> int:
    selected=attempt.get("train_only_selection")
    if not isinstance(selected,dict) or selected.get("sealed_oos_evaluated") is not False:
        raise ValueError("CONTROL_TRAINING_SELECTION_UNAVAILABLE")
    folds=selected.get("folds")
    if not isinstance(folds,list) or not folds:
        raise ValueError("CONTROL_TRAINING_FOLDS_MISSING")
    limits=[]
    for f in folds:
        if not isinstance(f,dict) or not isinstance(f.get("train_end_at"),str) or not isinstance(f.get("test_start_at"),str):
            raise ValueError("CONTROL_INVALID_FOLD_CUTOFF")
        start=datetime.fromisoformat(f["test_start_at"])
        cutoff=datetime.fromisoformat(f["train_end_at"])
        if cutoff>=start or cutoff.tzinfo is None or start.tzinfo is None:
            raise ValueError("CONTROL_TRAIN_FOLDS_OVERLAP")
        limits.append(cutoff)
    first=min(limits)
    count=sum(b.timestamp<=first for b in dataset.bars)
    if count<12 or count>=len(dataset.bars):
        raise ValueError("CONTROL_TRAIN_BARS_OUTSIDE_BUDGET")
    if any(b.timestamp>first for b in dataset.bars[:count]):
        raise ValueError("CONTROL_TRAINING_BARS_UNSORTED")
    return count


def _events(trades: tuple[Trade,...]) -> dict[tuple[str,str,str],Trade]:
    result={}
    for t in trades:
        key=(t.timestamp,t.side,t.symbol)
        if key in result:
            raise ValueError("CONTROL_DUPLICATE_EXECUTION_EVENT")
        result[key]=t
    return result


def controlled_training_comparison(*, proposal:dict[str,Any], proposal_hash:str,
                                   attempt:dict[str,Any], market:MarketDataSet,
                                   expected_run_id:str) -> dict[str,Any]:
    """Replay fixed parent and each child with identical fees/prices on train bars."""
    if market.zone is not DataZone.DEVELOPMENT:
        raise PermissionError("CONTROL_DEVELOPMENT_ONLY")
    check_proposal(proposal,expected_hash=proposal_hash)
    if (proposal.get("run_id")!=expected_run_id or attempt.get("research_run_id")!=expected_run_id
        or proposal.get("dataset_hash")!=market.dataset_hash or attempt.get("status")!="COMPLETED"
        or attempt.get("verification") is not None):
        raise ValueError("CONTROL_RUN_OR_DATASET_EVIDENCE_MISMATCH")
    original=proposal.get("parent_strategy_ir")
    if not isinstance(original,dict):
        raise ValueError("CONTROL_MISSING_PARENT_IR")
    parent=StrategyIR.model_validate(original)
    if semantic_strategy_hash(parent)!=proposal.get("parent_semantic_hash"):
        raise ValueError("CONTROL_PARENT_HASH_MISMATCH")
    candidates=attempt.get("candidates")
    if (not isinstance(candidates,list)
        or {x.get("semantic_strategy_hash") for x in candidates}
        != {c.get("semantic_strategy_hash") for c in proposal["candidates"]}
        or len(candidates)!=len(proposal["candidates"])):
        raise ValueError("CONTROL_CHILD_EVIDENCE_MISMATCH")
    bars=_training_cutoff(attempt,market)
    train=replace(market,bars=market.bars[:bars])
    engine=BacktestEngine()
    features={s.name:s for s in research_feature_specs()}
    inputs=_market_feature_inputs(train)
    cost=GenerationPipeline().cost_model
    def run(strategy:StrategyIR):
        r=engine.run(BacktestRequest(
            run_id="guided-training-paired-replay",
            strategy_hash=semantic_strategy_hash(strategy),dataset=train,
            initial_cash=100_000.0,strategy=strategy,
            cost_model=cost,feature_specs=features,feature_inputs=inputs,
        ))
        if r.exit_status!="SUCCEEDED" or r.data_hash!=train.dataset_hash or len(r.equity_curve)!=bars:
            raise ValueError("CONTROL_ENGINE_RESULT_UNVERIFIED")
        return r
    original_run=run(parent)
    pre=_events(original_run.trades)
    parent_metrics=calculate_metrics(original_run.equity_curve,(),periods_per_year=252)
    comparisons=[]
    for item in proposal["candidates"]:
        child=StrategyIR.model_validate(item["strategy_ir"])
        after=run(child)
        post=_events(after.trades)
        common=pre.keys()&post.keys()
        added=post.keys()-pre.keys()
        removed=pre.keys()-post.keys()
        resized=sum(pre[k].quantity!=post[k].quantity or pre[k].cost!=post[k].cost for k in common)
        if not (added or removed or resized):
            kind="UNCHANGED_EXECUTION_EVENTS"
        elif added or removed:
            kind="SIGNAL_TIMING_CHANGED"
        else:
            kind="EXECUTION_SIZE_OR_COST_CHANGED"
        child_metrics=calculate_metrics(after.equity_curve,(),periods_per_year=252)
        boundaries=[(bars-1)*i//4 for i in range(5)]
        windows=[]
        for start,end in zip(boundaries[:-1],boundaries[1:],strict=True):
            a=calculate_metrics(original_run.equity_curve[start:end+1],(),periods_per_year=252)
            b=calculate_metrics(after.equity_curve[start:end+1],(),periods_per_year=252)
            windows.append({
                "start_at":train.bars[start].timestamp.isoformat(),
                "end_at":train.bars[end].timestamp.isoformat(),
                "parent_return":a.total_return,"child_return":b.total_return,
                "net_return_delta":b.total_return-a.total_return,
                "parent_mdd":a.max_drawdown,"child_mdd":b.max_drawdown,
                "scope":"REUSED_TRAINING_ONLY_NOT_INDEPENDENT_HOLDOUT",
            })
        prior_cost=sum(t.cost for t in original_run.trades)
        child_cost=sum(t.cost for t in after.trades)
        cmp={
            "semantic_strategy_hash":item["semantic_strategy_hash"],
            "parent_total_return":parent_metrics.total_return,
            "child_total_return":child_metrics.total_return,
            "net_total_return_delta":child_metrics.total_return-parent_metrics.total_return,
            "parent_mdd":parent_metrics.max_drawdown,
            "child_mdd":child_metrics.max_drawdown,
            "parent_closed_trades":sum(t.side=="sell" for t in original_run.trades),
            "child_closed_trades":sum(t.side=="sell" for t in after.trades),
            "parent_fill_count":len(original_run.trades),
            "child_fill_count":len(after.trades),
            "parent_execution_trace_hash":content_hash([asdict(t) for t in original_run.trades]),
            "child_execution_trace_hash":content_hash([asdict(t) for t in after.trades]),
            "parent_costs":prior_cost,"child_costs":child_cost,
            "added_events":len(added),"removed_events":len(removed),
            "resized_or_recosted_events":resized,
            "execution_change_kind":kind,
            "development_windows":windows,
            "result_observation":("PARENT_CHILD_TRAIN_NET_GAIN" if child_metrics.total_return>parent_metrics.total_return+1e-9
                                  else "PARENT_CHILD_TRAIN_NET_LOSS" if child_metrics.total_return<parent_metrics.total_return-1e-9
                                  else "NO_TRAIN_NET_DIFFERENCE"),
            "causal_status":"NOT_ESTABLISHED",
        }
        comparisons.append(cmp)
    donor_comparison=None
    cross=proposal.get("crossover_proof")
    if cross is not None:
        donor_strategy=StrategyIR.model_validate(proposal["crossover_donor_strategy_ir"])
        donor_run=run(donor_strategy)
        donor_metrics=calculate_metrics(donor_run.equity_curve,(),periods_per_year=252)
        donor_event=_events(donor_run.trades)
        donor_comparison=[]
        for item in proposal["candidates"]:
            child=StrategyIR.model_validate(item["strategy_ir"])
            result=run(child)
            child_metrics=calculate_metrics(result.equity_curve,(),periods_per_year=252)
            child_event=_events(result.trades)
            donor_comparison.append({
                "child_semantic_strategy_hash":item["semantic_strategy_hash"],
                "donor_semantic_strategy_hash":cross["donor_semantic_hash"],
                "donor_run_id":cross["donor_run_id"],
                "donor_training_return":donor_metrics.total_return,
                "child_training_return":child_metrics.total_return,
                "net_return_delta_vs_donor":child_metrics.total_return-donor_metrics.total_return,
                "donor_training_mdd":donor_metrics.max_drawdown,
                "child_training_mdd":child_metrics.max_drawdown,
                "donor_fill_count":len(donor_run.trades),
                "child_fill_count":len(result.trades),
                "donor_costs":sum(x.cost for x in donor_run.trades),
                "child_costs":sum(x.cost for x in result.trades),
                "added_events_vs_donor":len(child_event.keys()-donor_event.keys()),
                "removed_events_vs_donor":len(donor_event.keys()-child_event.keys()),
                "donor_execution_trace_hash":content_hash([asdict(x) for x in donor_run.trades]),
                "child_execution_trace_hash":content_hash([asdict(x) for x in result.trades]),
                "causal_status":"NOT_ESTABLISHED",
                "development_only_not_oos":True,
            })
    report={
        "schema":"guided-paired-training-control-v1",
        "run_id":expected_run_id,"proposal_hash":proposal_hash,
        "original_dataset_hash":market.dataset_hash,
        "training_dataset_hash":train.dataset_hash,
        "training_bars":bars,
        "training_end_at":train.bars[-1].timestamp.isoformat(),
        "first_excluded_bar_at":market.bars[bars].timestamp.isoformat(),
        "training_selection_upstream_verified":attempt["train_only_selection"].get("upstream_selection_verified") is True,
        "fee_policy":"CANONICAL_GENERATION_PIPELINE_COST_MODEL",
        "comparisons":comparisons,
        "crossover_donor_comparisons":donor_comparison,
        "validation_fold_tests_used":False,"sealed_oos_evaluated":False,
        "production_promotion":False,"orders_enabled":False,
        "causal_status":"NOT_ESTABLISHED",
        "original_diagnostic_proof": "PROPOSAL_AND_ATTEMPT_IMMUTABLE_EVIDENCE_BOUND",
    }
    report["report_hash"]=content_hash(report)
    return report
