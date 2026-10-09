"""Fail closed on corrupt OHLCV values before evaluating a strategy."""
from __future__ import annotations

from datetime import datetime, timezone
from math import inf, nan

import pytest

from core.data.contracts import Bar, DataContractError, MarketDataSet


@pytest.mark.parametrize("invalid", [nan, inf, -inf])
@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
def test_bar_rejects_nonfinite_market_value(field: str, invalid: float) -> None:
    values = {"open": 100.0, "high": 105.0, "low": 95.0, "close": 101.0, "volume": 1000.0}
    values[field] = invalid
    with pytest.raises(DataContractError, match="finite"):
        Bar(datetime(2024, 1, 1, tzinfo=timezone.utc), "TEST", **values)


def test_data_contract_keeps_legitimate_zero_volume() -> None:
    bar = Bar(datetime(2024, 1, 1, tzinfo=timezone.utc), "TEST", 100, 105, 95, 100, 0)
    dataset = MarketDataSet("zero-volume", "development", (bar,))
    assert dataset.bars[0].volume == 0
