"""Pinned MIT Pandas-TA feature adapter for pre-verified, causal source candidates.

Feature IDs are fixed by checked-in manifest; no arbitrary function names,
symbol lookups, parameter-origin swaps, or code expressions are admitted.
Vendored upstream 7c669b0 is immutable within the research branch.
"""

from __future__ import annotations

import importlib
import inspect
import json
import math
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.features.contracts import FeatureSpec


@lru_cache(maxsize=1)
def _approved() -> dict[str, dict[str, Any]]:
    path = Path(__file__).with_name("pandas_ta_manifest.json")
    body = json.loads(path.read_text(encoding="utf-8"))
    if body["source_sha"] != "7c669b033582d53b70aa68b6388796d19ce33979" or body["license"] != "MIT":
        raise ValueError("pinned source manifest provenance mismatch")
    mapping = {entry["name"]: entry for entry in body["entries"]}
    if len(mapping) != len(body["entries"]):
        raise ValueError("source manifest duplicate identity")
    return mapping


def pinned_specs() -> tuple[FeatureSpec, ...]:
    body = _approved()
    source = (
        "https://github.com/xgboosted/pandas-ta-classic@7c669b033582d53b70aa68b6388796d19ce33979"
    )
    return tuple(
        FeatureSpec(
            name=key,
            family=str(entry["category"]),
            inputs=tuple(entry["inputs"]),
            calculator="pandas_ta_pinned",
            lookback=int(entry["lookback"]),
            parameters={
                "source_name": str(entry["source"]),
                "output_index": int(entry["output_index"]),
            },
            formula=f"pandas_ta_classic::{entry['source']}::{entry['output_index']}",
            status="REGISTERED",
            source_repositories=(source,),
            source_licenses=("MIT",),
            data_contract="scalar",
            duplicate_group=key,
            version="pta-7c669b0-v1",
        )
        for key, entry in sorted(body.items())
    )


@lru_cache(maxsize=128)
def _callable(source: str, is_candle: bool) -> tuple[Any, frozenset[str]]:
    if is_candle:
        module = importlib.import_module(f"pandas_ta_classic.candles.{source}")
        method = getattr(module, source)
    else:
        module = importlib.import_module("pandas_ta_classic")
        method = getattr(module, source)
    return method, frozenset(inspect.signature(method).parameters)


def calculate_pinned(
    spec: FeatureSpec, inputs: Mapping[str, Sequence[float | None]]
) -> tuple[float | None, ...]:
    """Return source series only, bar-aligned and with nonfinite outputs withheld.

    Every point t is derived only from input bars <=t; the platform's existing
    next-open decision gate is unchanged. This never touches external data.
    """
    entry = _approved().get(spec.name)
    if (
        entry is None
        or spec.parameters.get("source_name") != entry["source"]
        or spec.parameters.get("output_index") != entry["output_index"]
        or tuple(entry["inputs"]) != tuple(spec.inputs)
        or spec.lookback < 1
        or spec.lookback > 252
    ):
        raise ValueError("unapproved pinned upstream feature parameters")
    n = len(next(iter(inputs.values())))
    if n == 0 or n > 1_000_000 or any(len(v) != n for v in inputs.values()):
        raise ValueError("misaligned input size")
    try:
        import numpy as np
        import pandas as pd  # type: ignore[import-untyped]

        source = str(entry["source"])
        method, args = _callable(source, source.startswith("cdl_"))
        kwargs: dict[str, Any] = {}
        for field in ("open", "high", "low", "close", "volume"):
            source_key = "open_" if field == "open" else field
            if field in inputs and source_key in args:
                kwargs[source_key] = pd.Series(
                    [np.nan if value is None else float(value) for value in inputs[field]],
                    dtype="float64",
                )
        if "length" in args:
            kwargs["length"] = int(spec.lookback)
        if "offset" in args:
            kwargs["offset"] = 0
        if "talib" in args:
            kwargs["talib"] = False
        if "lookahead" in args:
            kwargs["lookahead"] = False
        if "centered" in args:
            kwargs["centered"] = False
        output = method(**kwargs)
        if output is None:
            return (None,) * n
        if isinstance(output, pd.DataFrame):
            idx = int(entry["output_index"])
            if idx >= output.shape[1]:
                raise ValueError("upstream output index missing")
            output = output.iloc[:, idx]
        if not isinstance(output, pd.Series) or len(output) != n:
            raise ValueError("unverified non-bar-aligned source output")
        data = pd.to_numeric(output, errors="coerce")
        result = tuple(
            float(value) if value is not None and math.isfinite(float(value)) else None
            for value in data
        )
        return result
    except (KeyError, TypeError, ValueError, ArithmeticError, IndexError) as exc:
        raise ValueError(f"pinned upstream feature failed: {spec.name}") from exc
