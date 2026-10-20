"""Two Pine semantic ports -> existing *typed expression* research engine.

This does NOT register unverified Pine features in operational FeatureRegistry.
It allows a GPT-authored, schema-validated *research expression* to consume
source-derived, completed-bar observations from both original indicators.
Original source semantics still need TradingView parity review (P5).
No strategy generation, broker orders, operational MCP change, or OOS access.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.expression_ir import (
    MAX_BARS,
    Expression,
    ValueType,
    compile_expression,
    evaluate_expression,
)
from research.pine_import.boswaves_bridge import prepare_boswaves_development_replay
from research.pine_import.shaakuni_bridge import prepare_shaakuni_development_replay

# Deliberately no runtime registration: candidates are P2/P3 semantic prototypes.
# Exact IDs come from the actual causal-vector bridges, not LLM assertions.
PINE_RESEARCH_SOURCES: dict[str, str] = {
    "boswaves_trend": "pine.boswaves.trend",
    "boswaves_bull_flip": "pine.boswaves.bull_flip",
    "boswaves_bear_flip": "pine.boswaves.bear_flip",
    "boswaves_conviction": "pine.boswaves.conviction",
    "shaakuni_bull_ob_confirmed": "pine.shaakuni.bull_ob_confirmed",
    "shaakuni_bear_ob_confirmed": "pine.shaakuni.bear_ob_confirmed",
    "shaakuni_fresh_bull_ob_count": "pine.shaakuni.fresh_bull_ob_count",
    "shaakuni_fresh_bear_ob_count": "pine.shaakuni.fresh_bear_ob_count",
}
_PINE_SOURCE_TYPES: dict[str, ValueType] = {
    name: "number" for name in PINE_RESEARCH_SOURCES
}


@dataclass(frozen=True)
class PineExpressionStudy:
    market_hash: str
    algorithm_hash: str
    evidence_hash: str
    timestamps: tuple[datetime, ...]
    next_bar_timestamps: tuple[datetime | None, ...]
    source_replays: tuple[str, ...]
    source_replay_hashes: tuple[tuple[str, str], ...]
    signals: tuple[bool | None, ...]
    status: Literal["RESEARCH_PROTOTYPE_ONLY"] = "RESEARCH_PROTOTYPE_ONLY"
    operationally_registered: Literal[False] = False
    tradingview_parity_verified: Literal[False] = False
    broker_executable: Literal[False] = False
    out_of_sample_approved: Literal[False] = False


def compose_pine_research_expression(
    market: MarketDataSet,
    expression: Expression | Mapping[str, object],
) -> PineExpressionStudy:
    """Evaluate arbitrary bounded Boolean formulas across the two Pine ports.

    Uses the existing P1-1 typed compiler and evaluator rather than a second
    Pine-specific parser. Source numbers are read only after completed bar
    close[t], so an execution cannot be authorized before bar[t+1].
    """
    if market.zone != DataZone.DEVELOPMENT:
        raise ValueError("Pine study requires development zone, not sealed OOS")
    if market.timeframe != "1d" or market.calendar != "us_equities":
        raise ValueError("reviewed study requires 1d US-equity development data")
    if not 40 <= len(market.bars) <= MAX_BARS:
        raise ValueError("unbounded study or insufficient indicator warmup")

    compiled = compile_expression(expression, _PINE_SOURCE_TYPES)
    if compiled.result_type != "boolean":
        raise ValueError("Pine study signal must be a Boolean typed expression")

    bos = prepare_boswaves_development_replay(market)
    sha = prepare_shaakuni_development_replay(market)
    if not (
        bos.dataset_hash == sha.dataset_hash == market.dataset_hash
        and bos.timestamps == sha.timestamps
        and bos.execution_not_before == sha.execution_not_before
    ):
        raise ValueError("source identity or timestamp alignment mismatch")

    available = {**dict(bos.signals), **dict(sha.signals)}
    # The compiler tracks only used source names; no other indicator is made
    # available, and unknown IDs are rejected rather than silently approximated.
    sources = {
        name: available[PINE_RESEARCH_SOURCES[name]]
        for name, _ in compiled.source_types
    }
    raw = evaluate_expression(compiled, sources, bar_count=len(market.bars))
    if any(value is not None and type(value) is not bool for value in raw):
        raise ValueError("compiled signal returned unexpected non-boolean data")
    values: tuple[bool | None, ...] = tuple(
        bool(value) if value is not None else None for value in raw
    )
    replays = (("boswaves", bos.replay_hash), ("shaakuni", sha.evidence_hash))
    proof = content_hash({
        "market": market.dataset_hash,
        "expression": compiled.definition_hash,
        "source_replay_hashes": replays,
        "values": values,
        "execution_not_before": [
            instant.isoformat() if instant else None
            for instant in bos.execution_not_before
        ],
        "contract": "PINE_STAGED_RESEARCH_ONLY_NO_ORDERS_v1",
    })
    return PineExpressionStudy(
        market_hash=market.dataset_hash,
        algorithm_hash=compiled.definition_hash,
        evidence_hash=proof,
        timestamps=bos.timestamps,
        next_bar_timestamps=bos.execution_not_before,
        source_replays=("boswaves", "shaakuni"),
        source_replay_hashes=replays,
        signals=values,
    )
