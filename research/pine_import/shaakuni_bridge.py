"""Typed causal replay of Shaakuni completed levels and confirmed OB observations.

This adapter is not a FeatureRegistry promotion, an executable StrategyIR,
or parity evidence for Pine's historical/live-panel drawings.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.pine_import.shaakuni_order_blocks import (
    ShaakuniParams,
    compute_shaakuni,
)


@dataclass(frozen=True)
class ShaakuniStudyReplay:
    source_upload_sha256: str
    dataset_hash: str
    timestamps: tuple[datetime, ...]
    execution_not_before: tuple[datetime | None, ...]
    signals: tuple[tuple[str, tuple[float | None, ...]], ...]
    evidence_hash: str
    status: Literal["NON_PIT_DEVELOPMENT_ONLY"] = "NON_PIT_DEVELOPMENT_ONLY"
    source_license: Literal["MPL-2.0"] = "MPL-2.0"
    in_operational_feature_registry: Literal[False] = False
    strategy_ir_compatible: Literal[False] = False
    broker_executable: Literal[False] = False
    independent_oos_approved: Literal[False] = False
    tradingview_parity_verified: Literal[False] = False


_SOURCE_UPLOAD = "54dabcd62a87df46e0b248ef290ccf3f1346d4b2f5f49ec72b6c68148e703f78"


def prepare_shaakuni_development_replay(
    dataset: MarketDataSet,
    *,
    params: ShaakuniParams | None = None,
) -> ShaakuniStudyReplay:
    """No next-day or future OB knowledge on prior close-bar observations."""
    if params is None:
        params = ShaakuniParams()
    if dataset.zone != DataZone.DEVELOPMENT:
        raise ValueError("Shaakuni research forbids nondevelopment market data")
    if dataset.calendar != "us_equities" or dataset.timeframe != "1d":
        raise ValueError("reviewed research is limited to US-equities daily market")
    if not 40 <= len(dataset.bars) <= 50_000:
        raise ValueError("missing warmup or unbounded source")
    if len({bar.symbol for bar in dataset.bars}) != 1:
        raise ValueError("mixed instruments require PIT audit")
    times = tuple(bar.timestamp for bar in dataset.bars)
    study = compute_shaakuni(
        times,
        tuple(float(bar.open) for bar in dataset.bars),
        tuple(float(bar.high) for bar in dataset.bars),
        tuple(float(bar.low) for bar in dataset.bars),
        tuple(float(bar.close) for bar in dataset.bars),
        params,
    )
    signals: tuple[tuple[str, tuple[float | None, ...]], ...] = (
        ("pine.shaakuni.pdh", tuple(b.levels.previous_day_high for b in study.bars)),
        ("pine.shaakuni.pdl", tuple(b.levels.previous_day_low for b in study.bars)),
        ("pine.shaakuni.pwh", tuple(b.levels.previous_week_high for b in study.bars)),
        ("pine.shaakuni.pwl", tuple(b.levels.previous_week_low for b in study.bars)),
        ("pine.shaakuni.bull_ob_confirmed", tuple(
            float(bool(b.created_bull_ids)) for b in study.bars
        )),
        ("pine.shaakuni.bear_ob_confirmed", tuple(
            float(bool(b.created_bear_ids)) for b in study.bars
        )),
        ("pine.shaakuni.fresh_bull_ob_count", tuple(
            float(b.fresh_bull) for b in study.bars
        )),
        ("pine.shaakuni.fresh_bear_ob_count", tuple(
            float(b.fresh_bear) for b in study.bars
        )),
        ("pine.shaakuni.ob_mitigation_count", tuple(
            float(len(b.mitigated_ids)) for b in study.bars
        )),
    )
    next_time = times[1:] + (None,)
    body = {
        "source_upload": _SOURCE_UPLOAD,
        "market": dataset.dataset_hash,
        "params": vars(params),
        "timestamps": [t.isoformat() for t in times],
        "next_bar": [t.isoformat() if t else None for t in next_time],
        "signals": signals,
        "execution_banned": True,
    }
    return ShaakuniStudyReplay(
        source_upload_sha256=_SOURCE_UPLOAD,
        dataset_hash=dataset.dataset_hash,
        timestamps=times,
        execution_not_before=next_time,
        signals=signals,
        evidence_hash=content_hash(body),
    )
