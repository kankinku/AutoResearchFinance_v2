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
    active_signals = {
        "dataset_hash": market.dataset_hash,
        "entry": tuple(
            _rules_match(
                compiled.strategy.entry.conditions,
                compiled.strategy.entry.logic,
                values,
                i,
            ) for i in range(len(market.bars))
        ),
        "exit": tuple(
            _rules_match(
                compiled.strategy.exit.conditions,
                compiled.strategy.exit.logic,
                values,
                i,
            ) for i in range(len(market.bars))
        ),
        "regime": tuple(
            _regime_allows(compiled.strategy, values, i)
            for i in range(len(market.bars))
        ),
    }
    return content_hash(active_signals)
