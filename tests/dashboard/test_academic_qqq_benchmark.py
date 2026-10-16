"""QQQ price-only passive benchmark must match the exact DEVELOPMENT dataset.

Not dividend-adjusted / PIT / independently certified benchmark alpha.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.data.contracts import DataZone, MarketSourceProvenance
from core.data.parquet import ParquetDataProvider
from dashboard.academic_benchmark import (
    calculate_qqq_buyhold,
    qqq_buyhold_for_session,
)
from dashboard.academic_monitor import AcademicMonitorReader
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_academic_algorithm_plan import _market


def _synthetic_with_provenance():
    p = MarketSourceProvenance(
        source_id="test-dataset-not-market",
        retrieved_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
        revision_policy="latest",
        universe_policy="single_symbol",
        corporate_action_policy="raw",
        corporate_action_reference=None,
        includes_delisted=False,
    )
    return replace(_market(), provenance=p)


def test_qqq_passive_equity_same_open_and_last_close_costed() -> None:
    market = _synthetic_with_provenance()
    values = calculate_qqq_buyhold(
        market,
        expected_dataset_hash=market.dataset_hash,
    )
    assert values["status"] == "DEVELOPMENT_ONLY"
    assert values["buy_cost_bps"] == pytest.approx(8.0)
    expected = market.bars[-1].close / market.bars[0].open / 1.0008 - 1
    assert values["total_return"] == pytest.approx(expected, abs=1e-12)
    assert values["price_only_gross_total_return"] == pytest.approx(
        market.bars[-1].close / market.bars[0].open - 1
    )
    assert values["final_equity"] == pytest.approx(10_000 * (1 + expected))
    assert values["max_drawdown"] > 0
    assert not values["dividends_included"]
    assert not values["point_in_time_verified"]
    assert not values["independent_benchmark_verified"]
    assert values["no_end_liquidation"] is True


def test_wrong_dataset_hash_and_sealed_market_never_get_benchmark() -> None:
    market = _synthetic_with_provenance()
    assert calculate_qqq_buyhold(
        market,
        expected_dataset_hash="0" * 64,
    ) == {"status": "UNAVAILABLE", "reason": "QQQ_DATASET_HASH_MISMATCH"}
    sealed = replace(market, zone=DataZone.SEALED_OOS)
    blocked = calculate_qqq_buyhold(
        sealed,
        expected_dataset_hash=sealed.dataset_hash,
    )
    assert blocked["status"] == "UNAVAILABLE"
    assert (
        qqq_buyhold_for_session(None, expected_dataset_hash=market.dataset_hash)["status"]
        == "UNAVAILABLE"
    )


def test_monitor_qqq_reference_success_and_session_mismatch(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    root = tmp_path / "state" / "academic-gpt-checkpoints"
    market = _synthetic_with_provenance()
    path = tmp_path / "qqq_input.parquet"
    ParquetDataProvider.write(path, market)
    # The already-started session's dataset has no provenance, therefore
    # the monitored reference hash must fail closed instead of inventing alpha.
    snapshot = AcademicMonitorReader(root, qqq_reference_path=path).snapshot(started["session_id"])
    assert snapshot["buyhold_benchmark"] == {
        "status": "UNAVAILABLE",
        "reason": "QQQ_DATASET_HASH_MISMATCH",
    }
    assert snapshot["best_model_vs_qqq_pp"] is None
    assert snapshot["completed"] == 0


def test_actual_2020_2025_qqq_price_only_hurdle_when_file_present() -> None:
    path = Path("data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet")
    if not path.is_file():
        pytest.skip("Untracked historical QQQ file absent in clean worktree")
    original = ParquetDataProvider.read(path)
    assert original.zone == DataZone.DEVELOPMENT
    result = qqq_buyhold_for_session(path, expected_dataset_hash=original.dataset_hash)
    assert result["status"] == "DEVELOPMENT_ONLY"
    assert result["first_date"] == "2020-01-02"
    assert result["last_date"] == "2025-12-31"
    assert result["trading_bars"] == 1508
    assert result["first_open"] == pytest.approx(214.4)
    assert result["last_close"] == pytest.approx(614.31)
    assert result["total_return"] == pytest.approx(1.8629614964744619)
    assert result["price_only_gross_total_return"] == pytest.approx(1.8652518656716413)
