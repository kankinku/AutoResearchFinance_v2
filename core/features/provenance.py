from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceRecord(BaseModel):
    """Audited provenance for an external indicator source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str = Field(min_length=1)
    commit: str = Field(min_length=7)
    spdx: str = Field(min_length=1)
    implementation_policy: Literal[
        "derived", "independent_reimplementation", "quarantined"
    ]
    excluded_paths: tuple[str, ...] = ()


_SOURCES = (
    SourceRecord(
        repository="marketcalls/pyindicators",
        commit="93503d78db776b50a2777186202cb94c82ea5dc0",
        spdx="MIT",
        implementation_policy="derived",
        excluded_paths=("visual/", "streaming/", "data/"),
    ),
    SourceRecord(
        repository="srlcarlg/srl-python-indicators",
        commit="25e5dfaaa8fa0aba36dc7b24490fdfd5cdffaf29",
        spdx="Apache-2.0",
        implementation_policy="derived",
        excluded_paths=("*.parquet", "plots/"),
    ),
    SourceRecord(
        repository="chironmind/CentaurTechnicalIndicators-Python",
        commit="76ecbe515206206b0268d7ef0cebd9585bb09839",
        spdx="MIT",
        implementation_policy="derived",
        excluded_paths=("target/", "examples/live/"),
    ),
    SourceRecord(
        repository="kshlgrg/pythonpine",
        commit="49dd6f9fad70b76848c1ca2ffedf3d10c4e66f98",
        spdx="AGPL-3.0",
        implementation_policy="independent_reimplementation",
        excluded_paths=("price_fetcher.py", "MetaTrader5", "plotting/"),
    ),
)

_EXCLUDED_SYMBOLS = frozenset(
    {
        "submit_order",
        "place_order",
        "cancel_order",
        "MetaTrader5",
        "requests",
        "download_data",
        "plot",
        "plotly",
    }
)

_SAFE_CALCULATORS = frozenset(
    {
        "sma",
        "ema",
        "rsi",
        "macd",
        "atr",
        "adx",
        "bollinger",
        "vwap",
    }
)


def audited_indicator_sources() -> tuple[SourceRecord, ...]:
    return _SOURCES


def excluded_symbol_names() -> frozenset[str]:
    return _EXCLUDED_SYMBOLS


def registered_import_symbols() -> frozenset[str]:
    """Return calculator symbols admitted to the pure feature engine."""

    return _SAFE_CALCULATORS
