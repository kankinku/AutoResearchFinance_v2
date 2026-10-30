"""Guided filter threshold calibration from predesignated *training-only* bars.

Advisory only: emits condition values and observed entry-gate selectivity,
NEVER runs OOS, modifies any strategy or optimizes on final returns.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from core.backtest.engine import _feature_values, _indicator_values, _regime_allows, _rules_match
from core.data.contracts import DataZone, MarketDataSet
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from orchestration.evaluation_runner import _market_feature_inputs
from strategy_ir.schema import FeatureRef, StrategyIR


def suggest_training_thresholds(
    *,
    parent: StrategyIR,
    dataset: MarketDataSet,
    feature_id: str,
    op: str = "greater_than",
) -> dict[str, Any]:
    if dataset.zone is not DataZone.DEVELOPMENT:
        raise PermissionError("threshold calibration must use development data")
    if op not in {"greater_than", "less_than"}:
        raise ValueError("threshold suggestions require greater_than or less_than")
    specs = {s.name: s for s in research_feature_specs()}
    if feature_id not in specs or specs[feature_id].status != "REGISTERED":
        raise ValueError("threshold calibration requires a registered feature")
    spec = specs[feature_id]
    if spec.timeframe != "1d" or any(
        x not in {"open", "high", "low", "close", "volume"} for x in spec.inputs
    ):
        raise ValueError("threshold calibration requires daily in-dataset OHLCV inputs")
    alias = "calibrated_" + feature_id
    if alias in parent.indicators or alias in parent.features:
        raise ValueError("calibration alias collision")
    # Selection pre-committed to first 60% of bar history; not tuned on tail OOS.
    training_end = int(len(dataset.bars) * 0.6)
    if training_end < max(50, spec.lookback + 20):
        raise ValueError("insufficient training-only bars for feature lookback")
    # Evaluate on the sliced training dataset to physically prevent access to
    # subsequent evaluation bars (not merely mask full-period data).
    train = (
        dataset.model_copy(update={"bars": dataset.bars[:training_end]})
        if hasattr(dataset, "model_copy")
        else None
    )
    if train is None:
        from dataclasses import replace

        train = replace(dataset, bars=dataset.bars[:training_end])
    ref = FeatureRef(
        feature_id=feature_id,
        timeframe="1d",
        lag_bars=0,
        lookback=spec.lookback,
        inputs=spec.inputs,
        parameters=dict(spec.parameters),
    )
    candidate = parent.model_copy(update={"features": {**parent.features, alias: ref}})
    feature_specs = {s.name: s for s in research_feature_specs()}
    native = _indicator_values(train, parent)
    measured = _feature_values(train, candidate, None, feature_specs, _market_feature_inputs(train))
    native.update(measured)
    active = [
        i
        for i in range(training_end)
        if _rules_match(parent.entry.conditions, parent.entry.logic, native, i)
        and _regime_allows(parent, native, i)
    ]
    observed = sorted(
        float(native[alias][i])
        for i in active
        if native[alias][i] is not None and isfinite(float(native[alias][i]))
    )
    if len(observed) < 15:
        raise ValueError("insufficient eligible entry observations to calibrate")
    proposals = []
    for q in (0.2, 0.35, 0.5, 0.65, 0.8):
        pos = int((len(observed) - 1) * q)
        threshold = observed[pos]
        passing = (
            sum(x > threshold for x in observed)
            if op == "greater_than"
            else sum(x < threshold for x in observed)
        )
        if 0.10 <= passing / len(observed) <= 0.90:
            if any(abs(p["threshold"] - threshold) <= 1e-12 for p in proposals):
                continue
            proposals.append(
                {
                    "train_quantile": q,
                    "threshold": threshold,
                    "train_baseline_entry_observations": len(observed),
                    "train_filter_passes": passing,
                    "train_pass_fraction": round(passing / len(observed), 6),
                    "condition": {"op": op, "left": alias, "value": threshold, "enabled": True},
                }
            )
    return {
        "feature_id": feature_id,
        "alias": alias,
        "feature_selection": {
            "alias": alias,
            "feature_id": feature_id,
            "inputs": list(spec.inputs),
            "timeframe": "1d",
            "lag_bars": 0,
            "lookback": spec.lookback,
            "parameters": dict(spec.parameters),
        },
        "source_kind": "TRAINING_ONLY_ENTRY_GATED_QUANTILE_ADVISORY",
        "training_bars": training_end,
        "total_development_bars": len(dataset.bars),
        "dataset_hash": dataset.dataset_hash,
        "training_evidence_hash": content_hash(
            {
                "dataset": dataset.dataset_hash,
                "parent": parent.model_dump(mode="json", by_alias=True),
                "feature_id": feature_id,
                "op": op,
                "train_end": training_end,
                "observed": observed,
            }
        ),
        "suggestions": proposals,
        "note": (
            "No return optimization, only training-period selectivity; 40% holdback "
            "and sealed OOS not used for thresholds. Actual changed fills and policy "
            "gates must be checked separately."
        ),
    }
