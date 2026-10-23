"""Canonical inherited entry/exit/regime vector identity.

Used identically at *precommit* and counted-generation commit to prevent
a duplicate signal signature from consuming an expensive diagnosis checkpoint.
This does NOT replace the final immutable genealogy or costed S2 audit.
"""

from __future__ import annotations

from core.backtest.engine import _regime_allows, _rules_match
from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy


def inherited_effective_signal_hash(
    compiled: CompiledAcademicStrategy,
    market: MarketDataSet,
) -> str:
    if compiled.dataset_hash != market.dataset_hash:
        raise ValueError("inherited effective signal dataset mismatch")
    values = {key: list(val) for key, val in compiled.feature_values.items()}
    if not values or any(len(v) != len(market.bars) for v in values.values()):
        raise ValueError("inherited feature vectors missing or unaligned")
    # The v1 inherited academic replay is pinned to precomputed, signed
    # features. Merely declaring a new registered FeatureRef does NOT compute
    # its series; never pass a missing alias into the protected backtest engine.
    # A future feature-aware replay compiler must bind and hash the new vector
    # before the full S2/S7 audit can accept it.
    conditions = (
        *compiled.strategy.entry.conditions,
        *compiled.strategy.exit.conditions,
        *compiled.strategy.regime_filters,
    )
    feature_names = set(compiled.strategy.features)
    used_names = {c.left for c in conditions} | {c.right for c in conditions if c.right is not None}
    if feature_names != set(values) or not used_names <= set(values):
        raise ValueError(
            "INHERITED_FEATURE_BINDING_MISSING: selected feature was not "
            "compiled and hash-bound into this inherited academic replay"
        )
    active_signals: dict[str, object] = {
        "dataset_hash": market.dataset_hash,
        "entry": tuple(
            _rules_match(
                compiled.strategy.entry.conditions,
                compiled.strategy.entry.logic,
                values,
                i,
            )
            for i in range(len(market.bars))
        ),
        "exit": tuple(
            _rules_match(
                compiled.strategy.exit.conditions,
                compiled.strategy.exit.logic,
                values,
                i,
            )
            for i in range(len(market.bars))
        ),
        "regime": tuple(
            _regime_allows(compiled.strategy, values, i) for i in range(len(market.bars))
        ),
    }
    # Legacy 100%-cash strategies retain their exact historical identity.
    # Non-default exposure is an economically executed mutation: a 75% size
    # changes actual positions, costs and equity even with the same binary
    # entry/exit signals. It must not be mistakenly deduplicated as unchanged.
    size = compiled.strategy.risk.position_size_pct
    if size != 100:
        active_signals["position_size_pct"] = size
    return content_hash(active_signals)
