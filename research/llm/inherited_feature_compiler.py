"""Replay-bind newly selected registered scalar features in inherited GPT research.

Existing parent vectors and the protected S2/backtester remain unchanged. For
new or modified registered features, compute causal development-only series,
bind an immutable replay hash, and use next-open execution. Never make up an
unknown feature series or silently substitute the old parent replay.
"""

from __future__ import annotations

from dataclasses import replace
from math import isfinite

from core.backtest.engine import _regime_allows, _rules_match
from core.data.contracts import DataZone, MarketDataSet
from core.features.calculators import FeatureCalculationError, calculate_feature
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from research.indicator_engine.bridge import ResearchSignalReplay
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy
from strategy_ir.schema import FeatureRef, StrategyIR


class InheritedFeatureBindingError(ValueError):
    """Missing/unreviewed features cannot enter the inherited replay."""


def _new_feature_vector(ref: FeatureRef, market: MarketDataSet) -> tuple[float | None, ...]:
    if ref.timeframe != "1d" or ref.lag_bars > 252:
        raise InheritedFeatureBindingError(
            "INHERITED_FEATURE_UNSUPPORTED_TIMEFRAME: daily bounded replay required"
        )
    specs = {spec.name: spec for spec in research_feature_specs()}
    feature = specs.get(ref.feature_id)
    if feature is None:
        feature = next(
            (spec for spec in specs.values() if ref.feature_id in spec.aliases),
            None,
        )
    if feature is None or feature.status != "REGISTERED" or feature.data_contract != "scalar":
        raise InheritedFeatureBindingError(
            "INHERITED_FEATURE_NOT_EXECUTABLE: unreviewed feature calculator"
        )
    if any(
        term in license_name.lower()
        for license_name in feature.source_licenses
        for term in ("by-nc", "noncommercial", "all rights reserved", "no license")
    ):
        raise InheritedFeatureBindingError(
            "INHERITED_FEATURE_NOT_EXECUTABLE: source permission review required"
        )
    inputs = ref.inputs or feature.inputs
    if (
        not inputs
        or any(key not in {"open", "high", "low", "close", "volume"} for key in inputs)
        or len(inputs) != len(set(inputs))
    ):
        raise InheritedFeatureBindingError(
            "INHERITED_FEATURE_INPUT_UNAVAILABLE: PIT-aligned same-symbol OHLCV only"
        )
    lookback = ref.lookback or feature.lookback
    if not 1 <= lookback <= 252 or len(market.bars) <= lookback:
        raise InheritedFeatureBindingError(
            "INHERITED_FEATURE_INVALID_LOOKBACK: bounded history required"
        )
    params = {**feature.parameters, **ref.parameters}
    checked = feature.model_copy(
        update={"inputs": tuple(inputs), "lookback": lookback, "parameters": params}
    )
    values = {key: tuple(float(getattr(bar, key)) for bar in market.bars) for key in inputs}
    try:
        computed = calculate_feature(checked, values)
    except (FeatureCalculationError, ValueError, IndexError, TypeError) as exc:
        raise InheritedFeatureBindingError(
            "INHERITED_FEATURE_NOT_EXECUTABLE: reviewed indicator calculation failed"
        ) from exc
    if len(computed) != len(market.bars) or any(
        value is not None and (not isinstance(value, (int, float)) or not isfinite(value))
        for value in computed
    ):
        raise InheritedFeatureBindingError(
            "INHERITED_FEATURE_NOT_EXECUTABLE: invalid indicator series"
        )
    # Bar[t] is only observed at close[t]. A feature lag shifts *backwards*
    # in the decision window, never toward a future bar.
    lag = ref.lag_bars
    return (None,) * lag + tuple(computed[: len(computed) - lag] if lag else computed)


def bind_inherited_features(
    parent: CompiledAcademicStrategy,
    child: StrategyIR,
    market: MarketDataSet,
) -> CompiledAcademicStrategy:
    """Compile effective vectors for one inherited mutation, replaying full S2."""
    if (
        market.zone != DataZone.DEVELOPMENT
        or market.timeframe != "1d"
        or market.calendar != "us_equities"
        or market.dataset_hash != parent.dataset_hash
        or len({bar.symbol for bar in market.bars}) != 1
    ):
        raise InheritedFeatureBindingError(
            "INHERITED_FEATURE_DATA_SCOPE: sealed/OOS or wrong data denied"
        )
    digest = content_hash(child.model_dump(mode="json", by_alias=True))
    old = parent.strategy.features
    changed = {
        alias for alias, ref in child.features.items() if alias not in old or ref != old[alias]
    }
    removed = set(old) - set(child.features)
    if not changed and not removed:
        return replace(parent, strategy=child, strategy_hash=digest)
    vectors = {
        alias: series
        for alias, series in parent.feature_values.items()
        if alias in child.features and alias not in changed
    }
    for alias in sorted(changed):
        vectors[alias] = _new_feature_vector(child.features[alias], market)
    if set(vectors) != set(child.features):
        raise InheritedFeatureBindingError(
            "INHERITED_FEATURE_BINDING_MISSING: incomplete replay source vectors"
        )
    stamps = tuple(bar.timestamp for bar in market.bars)
    next_stamps = stamps[1:] + (None,)
    signals = tuple(sorted(vectors.items()))
    hypothesis = content_hash(
        {
            "schema": "inherited-feature-rebind-v1",
            "parent_hypothesis_hash": parent.hypothesis_hash,
            "child_strategy_hash": digest,
            "dataset_hash": market.dataset_hash,
            "feature_refs": {
                alias: feature.model_dump(mode="json")
                for alias, feature in sorted(child.features.items())
            },
            "signal_digest": content_hash(signals),
        }
    )
    body = {
        "hypothesis": hypothesis,
        "dataset": market.dataset_hash,
        "signals": signals,
        "decision_timestamps": [t.isoformat() for t in stamps],
        "earliest_next_bar": [t.isoformat() if t else None for t in next_stamps],
        "research_only": True,
    }
    decoded = {name: list(series) for name, series in vectors.items()}
    observed_entries = sum(
        _rules_match(child.entry.conditions, child.entry.logic, decoded, t)
        and _regime_allows(child, decoded, t)
        for t in range(len(market.bars) - 1)
    )
    replay = ResearchSignalReplay(
        hypothesis_hash=hypothesis,
        data_hash=market.dataset_hash,
        signals=signals,
        timestamps=stamps,
        execution_not_before=next_stamps,
        entry_regime_observations=observed_entries,
        replay_hash=content_hash(body),
    )
    return replace(
        parent,
        hypothesis_hash=hypothesis,
        replay=replay,
        strategy=child,
        strategy_hash=digest,
        feature_values=vectors,
    )
