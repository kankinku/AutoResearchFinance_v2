"""Quant V3: actual usability audit for every registered research feature.

Run only against deterministic synthetic developmental OHLCV. This script never
loads live/OOS data, never submits orders, and never mutates the registered catalog.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from core.data.contracts import Bar, MarketDataSet
from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from research.llm.inherited_feature_compiler import _new_feature_vector
from strategy_ir.schema import FeatureRef

OUTPUT = Path("docs/operations/quant-v3-435-feature-usability-audit-20261029.json")
AVAILABLE = {"open", "high", "low", "close", "volume"}


def synthetic(n: int = 420) -> tuple[dict[str, tuple[float, ...]], MarketDataSet]:
    rows = []
    for i in range(n):
        close = 200 + i * 0.045 + math.sin(i / 8.0) * 5 + math.cos(i / 35.0) * 3
        opening = close + 1.2 * math.cos(i / 3.2)
        high = max(close, opening) + 1.1 + 0.7 * abs(math.sin(i / 5.8))
        low = min(close, opening) - 1.2 - 0.6 * abs(math.cos(i / 6.1))
        volume = 1600 + i % 23 * 19 + 350 * abs(math.sin(i / 6.2))
        rows.append(
            Bar(
                datetime(2024, 1, 2, tzinfo=timezone.utc) + timedelta(days=i),
                "QQQ",
                opening,
                high,
                low,
                close,
                volume,
            )
        )
    market = MarketDataSet("synthetic-audit-only-435", "development", tuple(rows))
    return (
        {key: tuple(float(getattr(bar, key)) for bar in market.bars) for key in AVAILABLE},
        market,
    )


def run() -> dict[str, object]:
    start = perf_counter()
    sources, market = synthetic()
    specs = research_feature_specs()
    results: list[dict[str, object]] = []
    for index, spec in enumerate(specs):
        begun = perf_counter()
        entry: dict[str, object] = {
            "name": spec.name,
            "family": spec.family,
            "calculator": spec.calculator,
            "inputs": list(spec.inputs),
            "lookback": spec.lookback,
            "data_contract": spec.data_contract,
            "source_licenses": list(spec.source_licenses),
        }
        if spec.data_contract != "scalar" or any(v not in AVAILABLE for v in spec.inputs):
            entry["status"] = "BLOCKED_EXTERNAL_OR_NONSCALAR_INPUT"
            entry["reason"] = "StrategyIR currently accepts PIT-aligned same-symbol OHLCV only"
            results.append(entry)
            continue
        filtered = {key: sources[key] for key in spec.inputs}
        try:
            full = calculate_feature(spec, filtered)
            if len(full) != len(market.bars):
                raise ValueError(f"length mismatch: {len(full)}")
            if not all(
                v is None or (isinstance(v, (float, int)) and math.isfinite(v)) for v in full
            ):
                raise ValueError("non-finite or non-numeric output")
            nonnull = sum(v is not None for v in full)
            entry["finite_outputs"] = nonnull
            entry["unique_finite_values"] = len(
                set(round(float(v), 9) for v in full if v is not None)
            )
            if not nonnull:
                raise ValueError("no nonmissing values produced")
            prefix = calculate_feature(spec, {k: v[:-1] for k, v in filtered.items()})
            if full[:-1] != prefix:
                raise ValueError("prefix causality changed after future bar append")
            ref = FeatureRef(feature_id=spec.name, lookback=spec.lookback, inputs=spec.inputs)
            bound = _new_feature_vector(ref, market)
            if len(bound) != len(full) or bound != full:
                raise ValueError("StrategyIR vector does not match registered default calculation")
            entry["status"] = "EXECUTABLE_SYNTHETIC_DEFAULT"
            entry["strategy_ir_bound"] = True
            if entry["unique_finite_values"] == 1:
                entry["warning"] = "constant on synthetic test; economic informativeness unproven"
        except Exception as exc:
            entry["status"] = "FAILED_EXECUTION_OR_REPLAY"
            entry["error"] = f"{type(exc).__name__}: {exc}"[:420]
        entry["elapsed_ms"] = round((perf_counter() - begun) * 1000, 1)
        results.append(entry)
        if index % 50 == 0:
            print(f"audit progress {index + 1}/{len(specs)}", flush=True)
    counts = dict(sorted(Counter(row["status"] for row in results).items()))
    summary = {
        "schema": "quant-v3-435-default-execution-audit-v1",
        "synthetic_bars": len(market.bars),
        "registered_total": len(specs),
        "counts": counts,
        "duration_sec": round(perf_counter() - start, 1),
        "caveat": (
            "EXECUTABLE_SYNTHETIC_DEFAULT proves only that registered default can run "
            "with deterministic OHLCV, strict one-bar prefix equality, finite results "
            "and StrategyIR inherited replay. It does not prove source numerical parity, "
            "real-market applicability, PIT external-data readiness, performance, "
            "costs, profitability or sealed OOS behavior."
        ),
        "results": results,
    }
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False))
    for r in results:
        if r["status"] == "FAILED_EXECUTION_OR_REPLAY":
            print("FAIL", r["name"], r["error"])
    return summary


if __name__ == "__main__":
    run()
