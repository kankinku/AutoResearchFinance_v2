"""Experimental feature-vector bridge: causality and PIT/OOS protections."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine.bridge import prepare_development_replay
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices

START = datetime(2026, 1, 1, 21, tzinfo=timezone.utc)


def _market(
    *,
    zone: DataZone = DataZone.DEVELOPMENT,
    symbol: str = "QQQ",
    future_spike: bool = False,
    as_of: bool = False,
) -> MarketDataSet:
    bars = []
    for i in range(42):
        close = 100.0 + i * 0.5 + (i % 3) * 2
        if future_spike and i == 41:
            close = 9000.0
        bars.append(
            Bar(
                timestamp=START + timedelta(days=i),
                symbol=symbol,
                open=close,
                high=close + 2.0,
                low=close - 2.0,
                close=close,
                volume=100_000.0,
            )
        )
    provenance = MarketSourceProvenance(
        source_id="synthetic-test-not-certified",
        retrieved_at=START + timedelta(days=100),
        revision_policy="as_of" if as_of else "latest",
        universe_policy="single_symbol",
        corporate_action_policy="raw",
        corporate_action_reference=None,
        includes_delisted=False,
    )
    return MarketDataSet(
        version="fixture-v1",
        zone=zone,
        bars=tuple(bars),
        provenance=provenance,
    )


def _approved(tmp_path: Path):
    catalog = ResearchCatalog(tmp_path / "research.sqlite")
    seed_approved_references(catalog)
    for name in ("time_series_momentum", "sma_direction"):
        # The curated TSMOM window is 252 bars, so the replay values
        # will correctly remain warmup None in a 42-bar input.
        signal = catalog.get_indicator(name)
        catalog.verify_and_register(name, verify_signal_on_synthetic_prices(signal))
    hypothesis = compose_hypotheses(
        catalog,
        signal_ids=("time_series_momentum", "sma_direction"),
    )[0]
    return catalog, hypothesis


def test_replay_is_non_executable_and_fully_next_bar_aligned(tmp_path: Path) -> None:
    catalog, hypothesis = _approved(tmp_path)
    data = _market()
    result = prepare_development_replay(catalog, hypothesis, data)
    assert result.status == "NON_PIT_DEVELOPMENT_ONLY"
    assert not result.executable and not result.strategy_ir_compatible
    assert not result.benchmark_independently_verified and not result.sealed_oos_approved
    assert result.execution_not_before[0] == result.timestamps[1]
    assert result.execution_not_before[-1] is None
    assert result.data_hash == data.dataset_hash
    assert result.entry_regime_observations == 0  # warm-up never implies a trade
    assert result == prepare_development_replay(catalog, hypothesis, data)


def test_future_changed_close_never_changes_past_feature_values(tmp_path: Path) -> None:
    catalog, hypothesis = _approved(tmp_path)
    before = prepare_development_replay(catalog, hypothesis, _market())
    after = prepare_development_replay(catalog, hypothesis, _market(future_spike=True))
    assert before.replay_hash != after.replay_hash
    for (a_name, a_values), (b_name, b_values) in zip(before.signals, after.signals, strict=True):
        assert a_name == b_name
        assert a_values[:-1] == b_values[:-1]
    assert after.execution_not_before[-1] is None


def test_rejects_sealed_oos_and_verification_forgery(tmp_path: Path) -> None:
    catalog, hypothesis = _approved(tmp_path)
    with pytest.raises(ResearchCatalogError, match="non-development"):
        prepare_development_replay(catalog, hypothesis, _market(zone=DataZone.SEALED_OOS))
    with pytest.raises(ResearchCatalogError, match="forged"):
        prepare_development_replay(
            catalog, hypothesis.model_copy(update={"identity_hash": "f" * 64}), _market()
        )


def test_rejects_extra_asset_without_pit_universe(tmp_path: Path) -> None:
    catalog, hypothesis = _approved(tmp_path)
    dataset = _market()
    other = Bar(
        timestamp=dataset.bars[-1].timestamp + timedelta(days=1),
        symbol="SPY",
        open=20.0,
        high=22.0,
        low=19.0,
        close=21.0,
        volume=1000.0,
    )
    mixed = MarketDataSet(
        version="mix",
        zone=DataZone.DEVELOPMENT,
        bars=tuple(sorted((*dataset.bars, other), key=lambda bar: (bar.symbol, bar.timestamp))),
    )
    with pytest.raises(ResearchCatalogError, match="cross-asset"):
        prepare_development_replay(catalog, hypothesis, mixed)
