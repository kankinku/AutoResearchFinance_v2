"""Development-only indicator replay, strictly isolated from the StrategyIR executor.

Provides a causal feature-vector interoperability boundary, NOT an executable
StrategyIR or evidence of PIT validity, benchmark alpha or trade profitability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.models import ResearchHypothesis
from research.indicator_engine.signals import calculate_signal


@dataclass(frozen=True)
class ResearchSignalReplay:
    hypothesis_hash: str
    data_hash: str
    signals: tuple[tuple[str, tuple[float | None, ...]], ...]
    timestamps: tuple[datetime, ...]
    execution_not_before: tuple[datetime | None, ...]
    entry_regime_observations: int
    replay_hash: str
    status: Literal["NON_PIT_DEVELOPMENT_ONLY"] = "NON_PIT_DEVELOPMENT_ONLY"
    executable: Literal[False] = False
    strategy_ir_compatible: Literal[False] = False
    benchmark_independently_verified: Literal[False] = False
    sealed_oos_approved: Literal[False] = False


def prepare_development_replay(
    catalog: ResearchCatalog,
    hypothesis: ResearchHypothesis,
    dataset: MarketDataSet,
) -> ResearchSignalReplay:
    """Replay math on completed development bars; never simulate PnL or orders."""
    if dataset.zone != DataZone.DEVELOPMENT:
        raise ResearchCatalogError("non-development data is sealed from feature exploration")
    if dataset.timeframe != "1d" or dataset.calendar != "us_equities":
        raise ResearchCatalogError("only US-equity daily data supported by reviewed signals")
    if not 2 <= len(dataset.bars) <= 1_000_000:
        raise ResearchCatalogError("need 2-1000000 completed daily bars")
    if len({bar.symbol for bar in dataset.bars}) != 1:
        raise ResearchCatalogError("cross-asset series require a PIT multi-asset compiler")

    valid = compose_hypotheses(
        catalog,
        signal_ids=hypothesis.signal_ids,
        max_results=100,
    )
    if hypothesis not in valid:
        raise ResearchCatalogError("forged or stale composition identity")

    timestamps = tuple(bar.timestamp for bar in dataset.bars)
    available_next = timestamps[1:] + (None,)
    inputs = {
        field: tuple(float(getattr(bar, field)) for bar in dataset.bars)
        for field in ("open", "high", "low", "close")
    }
    signals = tuple(
        (signal_id, calculate_signal(catalog.get_indicator(signal_id), inputs))
        for signal_id in hypothesis.signal_ids
    )
    result_map = dict(signals)
    entry = hypothesis.signal_ids[hypothesis.roles.index("entry")]
    regime = hypothesis.signal_ids[hypothesis.roles.index("regime")]
    # A research signal is observed at close[t] and cannot be traded in bar[t].
    # No execution time is assigned for the last bar.
    triggers = 0
    for i in range(len(dataset.bars) - 1):
        entry_value = result_map[entry][i]
        regime_value = result_map[regime][i]
        if (
            entry_value is not None
            and entry_value > 0
            and regime_value is not None
            and regime_value > 0
        ):
            triggers += 1
    body = {
        "hypothesis": hypothesis.identity_hash,
        "dataset": dataset.dataset_hash,
        "signals": signals,
        "decision_timestamps": [t.isoformat() for t in timestamps],
        "earliest_next_bar": [t.isoformat() if t else None for t in available_next],
        "research_only": True,
    }
    return ResearchSignalReplay(
        hypothesis_hash=hypothesis.identity_hash,
        data_hash=dataset.dataset_hash,
        signals=signals,
        timestamps=timestamps,
        execution_not_before=available_next,
        entry_regime_observations=triggers,
        replay_hash=content_hash(body),
    )
