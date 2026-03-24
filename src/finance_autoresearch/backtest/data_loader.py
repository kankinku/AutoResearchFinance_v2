from __future__ import annotations

from collections.abc import Callable
from datetime import time
from pathlib import Path
from typing import TypeAlias

import pandas as pd

MarketKey: TypeAlias = tuple[str, str]
MarketPack: TypeAlias = dict[MarketKey, pd.DataFrame]
MarketDataFetcher: TypeAlias = Callable[[str], pd.DataFrame]

FIXED_MARKET_PACK_KEYS: tuple[MarketKey, ...] = (
    ("QQQ", "1d"),
    ("QQQ", "2h"),
    ("IWM", "1d"),
    ("IWM", "2h"),
    ("BTC-USD", "1d"),
    ("BTC-USD", "2h"),
)
EQUITY_SYMBOLS = frozenset({"QQQ", "IWM"})
REQUIRED_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "symbol",
    "timeframe",
)
RAW_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
MIN_HISTORY_DAYS = {"1d": 1_825, "2h": 540}
FETCH_POLICY = {
    "1d": {"interval": "1d", "period": "10y"},
    "2h": {"interval": "1h", "period": "730d"},
}


def build_market_pack(
    *,
    cache_root: Path | str,
    fetcher: Callable[..., pd.DataFrame] | None = None,
) -> MarketPack:
    resolved_fetcher = fetcher or fetch_market_data
    cache_root_path = Path(cache_root)
    market_pack: MarketPack = {}

    for symbol, timeframe in FIXED_MARKET_PACK_KEYS:
        fetch_policy = FETCH_POLICY[timeframe]
        source = resolved_fetcher(
            symbol,
            interval=fetch_policy["interval"],
            period=fetch_policy["period"],
        )
        raw_frame = _normalize_source_frame(source)
        write_raw_dataset(
            raw_frame,
            symbol=symbol,
            interval=fetch_policy["interval"],
            cache_root=cache_root_path,
        )

        if timeframe == "1d":
            canonical = build_daily_bars(raw_frame, symbol=symbol)
        elif symbol in EQUITY_SYMBOLS:
            canonical = build_equity_2h_bars(raw_frame, symbol=symbol)
        else:
            canonical = build_btc_2h_bars(raw_frame, symbol=symbol)

        write_canonical_dataset(
            canonical,
            symbol=symbol,
            timeframe=timeframe,
            cache_root=cache_root_path,
        )
        market_pack[(symbol, timeframe)] = canonical

    return market_pack


def load_market_pack(*, cache_root: Path | str) -> MarketPack:
    cache_root_path = Path(cache_root)
    market_pack: MarketPack = {}

    for symbol, timeframe in FIXED_MARKET_PACK_KEYS:
        path = canonical_dataset_path(
            symbol=symbol,
            timeframe=timeframe,
            cache_root=cache_root_path,
        )
        if not path.exists():
            raise FileNotFoundError(f"missing canonical dataset: {path}")
        market_pack[(symbol, timeframe)] = pd.read_parquet(path)

    return market_pack


def fetch_market_data(symbol: str, *, interval: str, period: str) -> pd.DataFrame:
    import yfinance as yf

    return yf.download(
        tickers=symbol,
        interval=interval,
        period=period,
        auto_adjust=False,
        actions=False,
        repair=True,
        prepost=False,
        progress=False,
    )


def build_daily_bars(source: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    normalized = _normalize_source_frame(source)
    timestamps = _to_timezone(pd.DatetimeIndex(normalized["timestamp"]), "UTC")
    canonical = normalized.assign(timestamp=timestamps, symbol=symbol, timeframe="1d")
    return _finalize_canonical_frame(canonical)


def build_equity_2h_bars(source: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    intraday = _normalize_source_frame(source)
    timestamps = _to_timezone(pd.DatetimeIndex(intraday["timestamp"]), "America/New_York")
    intraday = intraday.assign(timestamp=timestamps).sort_values("timestamp")

    session_mask = (
        (intraday["timestamp"].dt.dayofweek < 5)
        & (intraday["timestamp"].dt.time >= time(9, 30))
        & (intraday["timestamp"].dt.time <= time(16, 0))
    )
    intraday = intraday.loc[session_mask].reset_index(drop=True)

    rows: list[dict[str, object]] = []
    for _, day_frame in intraday.groupby(intraday["timestamp"].dt.normalize(), sort=True):
        day_frame = day_frame.reset_index(drop=True)
        pair_start = 0
        while pair_start < len(day_frame) - 1:
            first = day_frame.iloc[pair_start]
            second = day_frame.iloc[pair_start + 1]
            if second["timestamp"] - first["timestamp"] == pd.Timedelta(hours=1):
                rows.append(
                    {
                        "timestamp": second["timestamp"].tz_convert("UTC"),
                        "open": first["open"],
                        "high": max(first["high"], second["high"]),
                        "low": min(first["low"], second["low"]),
                        "close": second["close"],
                        "volume": first["volume"] + second["volume"],
                        "symbol": symbol,
                        "timeframe": "2h",
                    }
                )
                pair_start += 2
                continue
            pair_start += 1

    return _canonical_frame_from_rows(rows)


def build_btc_2h_bars(source: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    intraday = _normalize_source_frame(source)
    timestamps = _to_timezone(pd.DatetimeIndex(intraday["timestamp"]), "UTC")
    intraday = intraday.assign(timestamp=timestamps).sort_values("timestamp")

    resampled = (
        intraday.set_index("timestamp")
        .resample("2h", closed="right", label="right")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    canonical = resampled.assign(symbol=symbol, timeframe="2h")
    return _finalize_canonical_frame(canonical)


def write_raw_dataset(
    frame: pd.DataFrame,
    *,
    symbol: str,
    interval: str,
    cache_root: Path | str,
) -> Path:
    path = raw_dataset_path(symbol=symbol, interval=interval, cache_root=cache_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.loc[:, RAW_COLUMNS].to_parquet(path, index=False)
    return path


def write_canonical_dataset(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    cache_root: Path | str,
) -> Path:
    path = canonical_dataset_path(
        symbol=symbol,
        timeframe=timeframe,
        cache_root=cache_root,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def raw_dataset_path(*, symbol: str, interval: str, cache_root: Path | str) -> Path:
    return Path(cache_root) / "data" / "market" / "raw" / f"{symbol}_{interval}.parquet"


def canonical_dataset_path(
    *,
    symbol: str,
    timeframe: str,
    cache_root: Path | str,
) -> Path:
    return (
        Path(cache_root)
        / "data"
        / "market"
        / "canonical"
        / f"{symbol}_{timeframe}.parquet"
    )


def validate_market_pack(market_pack: MarketPack) -> None:
    if tuple(sorted(market_pack.keys())) != tuple(sorted(FIXED_MARKET_PACK_KEYS)):
        raise ValueError("market pack keys do not match the fixed canonical combinations")

    for symbol, timeframe in FIXED_MARKET_PACK_KEYS:
        validate_canonical_frame(
            market_pack[(symbol, timeframe)],
            symbol=symbol,
            timeframe=timeframe,
        )


def validate_canonical_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
) -> None:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"missing required canonical columns: {missing_columns}")

    timestamps = pd.DatetimeIndex(frame["timestamp"])
    if timestamps.tz is None or str(timestamps.tz) != "UTC":
        raise ValueError("canonical timestamps must be timezone-aware UTC")

    if not timestamps.is_monotonic_increasing:
        raise ValueError("canonical timestamps must be sorted ascending")

    if timestamps.has_duplicates:
        raise ValueError("canonical timestamps must be unique per symbol/timeframe")

    if frame.empty:
        raise ValueError("canonical frame must not be empty")

    if not frame["symbol"].eq(symbol).all():
        raise ValueError("canonical symbol column does not match the expected symbol")

    if not frame["timeframe"].eq(timeframe).all():
        raise ValueError("canonical timeframe column does not match the expected timeframe")

    history_window = timestamps.max() - timestamps.min()
    if history_window < pd.Timedelta(days=MIN_HISTORY_DAYS[timeframe]):
        raise ValueError(
            f"{symbol} {timeframe} requires at least {MIN_HISTORY_DAYS[timeframe]} days of history"
        )


def _normalize_source_frame(source: pd.DataFrame) -> pd.DataFrame:
    normalized = source.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = normalized.columns.get_level_values(0)

    if "timestamp" not in normalized.columns:
        normalized = normalized.reset_index()

    rename_map = {
        "Datetime": "timestamp",
        "Date": "timestamp",
        "index": "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    normalized = normalized.rename(columns=rename_map)

    missing_source_columns = [
        column for column in RAW_COLUMNS if column not in normalized.columns
    ]
    if missing_source_columns:
        raise ValueError(f"missing source columns: {missing_source_columns}")

    normalized = normalized.loc[:, RAW_COLUMNS].copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"])
    return normalized.sort_values("timestamp").reset_index(drop=True)


def _to_timezone(index: pd.DatetimeIndex, timezone_name: str) -> pd.DatetimeIndex:
    if index.tz is None:
        return index.tz_localize(timezone_name)
    return index.tz_convert(timezone_name)


def _canonical_frame_from_rows(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    return _finalize_canonical_frame(pd.DataFrame(rows))


def _finalize_canonical_frame(frame: pd.DataFrame) -> pd.DataFrame:
    canonical = frame.loc[:, REQUIRED_COLUMNS].copy()
    canonical["timestamp"] = _to_timezone(pd.DatetimeIndex(canonical["timestamp"]), "UTC")
    return canonical.sort_values("timestamp").reset_index(drop=True)
