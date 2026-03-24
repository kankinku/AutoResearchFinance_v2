from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from finance_autoresearch.backtest.data_loader import (
    FIXED_MARKET_PACK_KEYS,
    build_btc_2h_bars,
    build_equity_2h_bars,
    build_market_pack,
    load_market_pack,
    validate_canonical_frame,
)


def make_ohlcv_frame(index: pd.DatetimeIndex, *, start: float = 100.0) -> pd.DataFrame:
    values = list(range(len(index)))
    return pd.DataFrame(
        {
            "Open": [start + value for value in values],
            "High": [start + value + 1.0 for value in values],
            "Low": [start + value - 1.0 for value in values],
            "Close": [start + value + 0.5 for value in values],
            "Volume": [1_000 + value for value in values],
        },
        index=index,
    )


def test_build_market_pack_writes_raw_and_canonical_datasets(tmp_path: Path) -> None:
    daily_index = pd.date_range("2026-03-20", periods=3, freq="D", tz="UTC")
    equity_intraday_index = pd.DatetimeIndex(
        [
            "2026-03-23 10:30:00",
            "2026-03-23 11:30:00",
            "2026-03-23 12:30:00",
            "2026-03-23 13:30:00",
            "2026-03-23 14:30:00",
        ],
        tz="America/New_York",
    )
    crypto_intraday_index = pd.DatetimeIndex(
        [
            "2026-03-23 01:00:00+00:00",
            "2026-03-23 02:00:00+00:00",
            "2026-03-23 03:00:00+00:00",
            "2026-03-23 04:00:00+00:00",
        ]
    )

    fetch_map = {
        ("QQQ", "1d"): make_ohlcv_frame(daily_index, start=100.0),
        ("QQQ", "1h"): make_ohlcv_frame(equity_intraday_index, start=200.0),
        ("IWM", "1d"): make_ohlcv_frame(daily_index, start=300.0),
        ("IWM", "1h"): make_ohlcv_frame(equity_intraday_index, start=400.0),
        ("BTC-USD", "1d"): make_ohlcv_frame(daily_index, start=500.0),
        ("BTC-USD", "1h"): make_ohlcv_frame(crypto_intraday_index, start=600.0),
    }

    def fetcher(symbol: str, *, interval: str, period: str) -> pd.DataFrame:
        assert period in {"10y", "730d"}
        return fetch_map[(symbol, interval)].copy()

    result = build_market_pack(cache_root=tmp_path, fetcher=fetcher)
    reloaded = load_market_pack(cache_root=tmp_path)

    assert tuple(sorted(result.keys())) == tuple(sorted(FIXED_MARKET_PACK_KEYS))
    assert tuple(sorted(reloaded.keys())) == tuple(sorted(FIXED_MARKET_PACK_KEYS))

    raw_dir = tmp_path / "data" / "market" / "raw"
    assert sorted(path.name for path in raw_dir.glob("*.parquet")) == [
        "BTC-USD_1d.parquet",
        "BTC-USD_1h.parquet",
        "IWM_1d.parquet",
        "IWM_1h.parquet",
        "QQQ_1d.parquet",
        "QQQ_1h.parquet",
    ]

    canonical_dir = tmp_path / "data" / "market" / "canonical"
    assert sorted(path.name for path in canonical_dir.glob("*.parquet")) == [
        "BTC-USD_1d.parquet",
        "BTC-USD_2h.parquet",
        "IWM_1d.parquet",
        "IWM_2h.parquet",
        "QQQ_1d.parquet",
        "QQQ_2h.parquet",
    ]

    for key in FIXED_MARKET_PACK_KEYS:
        assert reloaded[key].equals(result[key])


def test_equity_2h_bars_use_second_source_bar_close_timestamp() -> None:
    hourly_index = pd.DatetimeIndex(
        [
            "2026-03-23 10:30:00",
            "2026-03-23 11:30:00",
            "2026-03-23 12:30:00",
            "2026-03-23 13:30:00",
            "2026-03-23 14:30:00",
        ],
        tz="America/New_York",
    )
    source = make_ohlcv_frame(hourly_index, start=100.0)

    canonical = build_equity_2h_bars(source, symbol="QQQ")

    assert canonical["timestamp"].tolist() == [
        pd.Timestamp("2026-03-23 15:30:00+00:00"),
        pd.Timestamp("2026-03-23 17:30:00+00:00"),
    ]
    assert canonical["open"].tolist() == [100.0, 102.0]
    assert canonical["close"].tolist() == [101.5, 103.5]
    assert canonical["volume"].tolist() == [2_001, 2_005]
    assert canonical["symbol"].tolist() == ["QQQ", "QQQ"]
    assert canonical["timeframe"].tolist() == ["2h", "2h"]


def test_btc_2h_bars_are_right_labeled_utc_buckets() -> None:
    hourly_index = pd.DatetimeIndex(
        [
            "2026-03-23 01:00:00+00:00",
            "2026-03-23 02:00:00+00:00",
            "2026-03-23 03:00:00+00:00",
            "2026-03-23 04:00:00+00:00",
        ]
    )
    source = make_ohlcv_frame(hourly_index, start=10.0)

    canonical = build_btc_2h_bars(source, symbol="BTC-USD")

    assert canonical["timestamp"].tolist() == [
        pd.Timestamp("2026-03-23 02:00:00+00:00"),
        pd.Timestamp("2026-03-23 04:00:00+00:00"),
    ]
    assert canonical["open"].tolist() == [10.0, 12.0]
    assert canonical["close"].tolist() == [11.5, 13.5]
    assert canonical["volume"].tolist() == [2_001, 2_005]
    assert canonical["symbol"].tolist() == ["BTC-USD", "BTC-USD"]
    assert canonical["timeframe"].tolist() == ["2h", "2h"]


def test_validate_canonical_frame_rejects_duplicate_timestamps() -> None:
    duplicate_timestamps = pd.DatetimeIndex(
        [
            "2020-01-01 00:00:00+00:00",
            "2020-01-01 00:00:00+00:00",
            "2026-01-01 00:00:00+00:00",
        ]
    )
    duplicate_frame = pd.DataFrame(
        {
            "timestamp": duplicate_timestamps,
            "open": [1.0, 2.0, 3.0],
            "high": [2.0, 3.0, 4.0],
            "low": [0.5, 1.5, 2.5],
            "close": [1.5, 2.5, 3.5],
            "volume": [100.0, 200.0, 300.0],
            "symbol": ["QQQ", "QQQ", "QQQ"],
            "timeframe": ["1d", "1d", "1d"],
        }
    )

    with pytest.raises(ValueError, match="unique"):
        validate_canonical_frame(duplicate_frame, symbol="QQQ", timeframe="1d")


def test_validate_canonical_frame_requires_minimum_history_window() -> None:
    timestamps = pd.to_datetime(
        [
            "2020-01-01 00:00:00+00:00",
            "2024-12-29 00:00:00+00:00",
        ]
    )
    short_frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [1.0, 2.0],
            "high": [2.0, 3.0],
            "low": [0.5, 1.5],
            "close": [1.5, 2.5],
            "volume": [100.0, 200.0],
            "symbol": ["QQQ", "QQQ"],
            "timeframe": ["1d", "1d"],
        }
    )

    with pytest.raises(ValueError, match="requires at least 1825 days"):
        validate_canonical_frame(short_frame, symbol="QQQ", timeframe="1d")
