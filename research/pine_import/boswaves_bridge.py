"""Development-only feature-vector bridge for the BOSWaves indicator port.

This is not a runtime registry promotion. All values on bar[t] become eligible
for strategy *decisions* only after that bar closes and trade executions cannot
occur before bar[t+1]. Researcher models can inspect this replay explicitly
without granting Pine source execution or broker permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.pine_import.boswaves_ribbon import RibbonParams, compute_ribbon


@dataclass(frozen=True)
class PineIndicatorReplay:
    original: str
    source_sha256: str
    dataset_hash: str
    timestamps: tuple[datetime, ...]
    execution_not_before: tuple[datetime | None, ...]
    signals: tuple[tuple[str, tuple[float | None, ...]], ...]
    replay_hash: str
    status: Literal["DEVELOPMENT_ONLY"] = "DEVELOPMENT_ONLY"
    in_operational_feature_registry: Literal[False] = False
    broker_executable: Literal[False] = False
    strategy_execution_equivalent: Literal[False] = False
    sealed_oos_approved: Literal[False] = False
    tradingview_parity_verified: Literal[False] = False


# SHA-256 of the user's attached original Markdown source, not of a .pine file
# reconstructed from presentation markup.
_BOSWAVES_UPLOAD_SHA256 = (
    "9b8a9fe90a17c488cc6c2f3464e686c1ac0882aee3ab6a338acd3692506760d4"
)


def prepare_boswaves_development_replay(
    dataset: MarketDataSet, *, params: RibbonParams = RibbonParams(),
) -> PineIndicatorReplay:
    """Typed causal signal vectors for opt-in US-equity 1d research.

    The original Pine indicator's visual stop/target drawings are NOT actual
    fills. Only its trend/flip/conviction outputs are exposed as observations.
    This cannot modify a certified StrategyIR or use sealed PIT/OOS data.
    """
    if DataZone(dataset.zone) != DataZone.DEVELOPMENT:
        raise ValueError("BOSWaves research replay requires development dataset")
    if dataset.calendar != "us_equities" or dataset.timeframe != "1d":
        raise ValueError("reviewed BOSWaves bridge supports 1d US-equity bars only")
    if not 40 <= len(dataset.bars) <= 50_000:
        raise ValueError("BOSWaves research replay requires bounded warmup")
    if len({bar.symbol for bar in dataset.bars}) != 1:
        raise ValueError("cross-asset research requires a separate PIT model")
    timestamps = tuple(bar.timestamp for bar in dataset.bars)
    if any(a >= b for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError("non-monotonic signal times")
    output = compute_ribbon(
        tuple(float(bar.high) for bar in dataset.bars),
        tuple(float(bar.low) for bar in dataset.bars),
        tuple(float(bar.close) for bar in dataset.bars),
        params=params,
    )
    signals: tuple[tuple[str, tuple[float | None, ...]], ...] = (
        ("pine.boswaves.bull_flip", tuple(
            float(row.flip == 1) if row.alma is not None and row.slope is not None else None
            for row in output.bars
        )),
        ("pine.boswaves.bear_flip", tuple(
            float(row.flip == -1) if row.alma is not None and row.slope is not None else None
            for row in output.bars
        )),
        ("pine.boswaves.trend", tuple(
            float(row.trend) if row.alma is not None and row.slope is not None else None
            for row in output.bars
        )),
        ("pine.boswaves.conviction", tuple(row.conviction for row in output.bars)),
    )
    next_times = timestamps[1:] + (None,)
    payload = {
        "source_upload_sha256": _BOSWAVES_UPLOAD_SHA256,
        "dataset_hash": dataset.dataset_hash,
        "params": vars(params),
        "timestamps": [t.isoformat() for t in timestamps],
        "execution_not_before": [t.isoformat() if t else None for t in next_times],
        "signals": signals,
    }
    return PineIndicatorReplay(
        original="BOSWaves Trend Target Ribbon Pine v6",
        source_sha256=_BOSWAVES_UPLOAD_SHA256,
        dataset_hash=dataset.dataset_hash,
        timestamps=timestamps,
        execution_not_before=next_times,
        signals=signals,
        replay_hash=content_hash(payload),
    )
