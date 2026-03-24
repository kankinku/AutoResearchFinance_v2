from __future__ import annotations

import pandas as pd

from finance_autoresearch.strategy.indicator_registry import ema


def classify_ema200_regime(close: pd.Series) -> pd.Series:
    ema200 = ema(close, 200)
    return pd.Series(
        data=["bull" if price > trend else "bear" for price, trend in zip(close, ema200)],
        index=close.index,
        dtype="object",
    )


def is_bull(close: pd.Series) -> pd.Series:
    return classify_ema200_regime(close).eq("bull")


def is_bear(close: pd.Series) -> pd.Series:
    return classify_ema200_regime(close).eq("bear")
