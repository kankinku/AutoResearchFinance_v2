"""Pinned MIT Bukosabino/ta secondary-output adapter, research-only.

Only 57 explicit source columns in bulk100_manifest.json are executable.
All feature names and family functions are source-manifest whitelisted. Uses
source-default windows as immutable semantics (FeatureSpec.lookback=1 is a
fixed-configuration marker, *not* a tunable window).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from core.features.contracts import FeatureSpec

_SOURCE_SHA = "a890410710a6e483c9ba08da7f3dd5089e4b9dff"
_PTA_SHA = "7c669b033582d53b70aa68b6388796d19ce33979"
_FIELDS = ("open", "high", "low", "close", "volume")
_FAMILIES = frozenset(("volume", "volatility", "trend", "momentum", "others"))


@lru_cache(maxsize=1)
def approved_buk() -> dict[str, dict[str, Any]]:
    meta = json.loads(Path(__file__).with_name("bulk100_manifest.json").read_text())
    if (
        meta["total"] != 100
        or meta["source_shas"]["bukosabino-ta"] != _SOURCE_SHA
        or meta["source_shas"]["pandas-ta-classic"] != _PTA_SHA
        or meta["license"] != "MIT"
    ):
        raise ValueError("bulk-100 pinned source manifest mismatch")
    source = [r for r in meta["entries"] if r["provider"] == "ta"]
    if len(source) != 57 or len({r["name"] for r in source}) != 57:
        raise ValueError("bukosabino whitelist invalid")
    if any(r["category"] not in _FAMILIES or tuple(r["inputs"]) != _FIELDS for r in source):
        raise ValueError("bukosabino input/family mismatch")
    return {str(r["name"]): r for r in source}


def buk_specs() -> tuple[FeatureSpec, ...]:
    origin = f"https://github.com/bukosabino/ta@{_SOURCE_SHA}"
    return tuple(
        FeatureSpec(
            name=name,
            family=str(entry["category"]),
            inputs=_FIELDS,
            calculator="bukosabino_pinned",
            lookback=1,
            parameters={
                "source_column": str(entry["source"]),
                "source_family": str(entry["category"]),
                "window_mode": "source_defaults_fixed",
            },
            formula=f"ta.wrapper::{entry['source']} (pinned defaults)",
            status="REGISTERED",
            source_repositories=(origin,),
            source_licenses=("MIT",),
            data_contract="scalar",
            duplicate_group=name,
            version="ta-a890410-v1",
        )
        for name, entry in sorted(approved_buk().items())
    )


@lru_cache(maxsize=12)
def _family_output(
    family: str,
    rows: tuple[tuple[float | None, ...], ...],
) -> dict[str, tuple[float | None, ...]]:
    import inspect

    import numpy as np
    import pandas as pd  # type: ignore[import-untyped]

    import ta

    if family not in _FAMILIES or len(rows) != len(_FIELDS):
        raise ValueError("unapproved source family")
    source = cast(Callable[..., Any], {
        "volume": ta.add_volume_ta,
        "volatility": ta.add_volatility_ta,
        "trend": ta.add_trend_ta,
        "momentum": ta.add_momentum_ta,
        "others": ta.add_others_ta,
    }[family])
    n = len(rows[0])
    frame = pd.DataFrame(
        {
            name: pd.Series(
                [float(x) if x is not None and math.isfinite(float(x)) else np.nan for x in values],
                dtype="float64",
            )
            for name, values in zip(_FIELDS, rows, strict=True)
        }
    )
    options = {
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "fillna": False,
        "colprefix": "",
    }
    args = {
        key: value for key, value in options.items() if key in inspect.signature(source).parameters
    }
    output = source(frame.copy(), **args)
    if len(output) != n:
        raise ValueError("upstream output length mismatch")
    result: dict[str, tuple[float | None, ...]] = {}
    for column in output.columns:
        if column in _FIELDS:
            continue
        vals = pd.to_numeric(output[column], errors="coerce")
        result[str(column)] = tuple(float(v) if math.isfinite(float(v)) else None for v in vals)
    return result


def calculate_buk(
    spec: FeatureSpec, inputs: Mapping[str, Sequence[float | None]]
) -> tuple[float | None, ...]:
    entry = approved_buk().get(spec.name)
    if (
        entry is None
        or spec.calculator != "bukosabino_pinned"
        or spec.lookback != 1
        or tuple(spec.inputs) != _FIELDS
        or spec.parameters.get("source_column") != entry["source"]
        or spec.parameters.get("source_family") != entry["category"]
        or spec.parameters.get("window_mode") != "source_defaults_fixed"
    ):
        raise ValueError("unapproved Bukosabino source/parameters")
    if any(field not in inputs for field in _FIELDS):
        raise ValueError("missing source input field")
    rows = tuple(tuple(inputs[field]) for field in _FIELDS)
    length = len(rows[0])
    if length < 1 or length > 1_000_000 or any(len(v) != length for v in rows):
        raise ValueError("input series misalignment")
    result = _family_output(str(entry["category"]), rows)
    if str(entry["source"]) not in result:
        raise ValueError("pinned source output missing")
    return result[str(entry["source"])]
