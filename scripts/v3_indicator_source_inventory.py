"""Reproducible, nonexecuting source manifest and name-level dedup inventory.

Never copies third-party source or executes imported repositories.
Name and synonym matches are candidates for mathematical-equivalence review,
not proof of identical implementations, defaults, or valid signals.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from core.features.registry import research_feature_specs

SOURCES = {
    "pandas-ta-classic": ("MIT", "https://github.com/xgboosted/pandas-ta-classic"),
    "ta-lib": ("BSD-3-Clause", "https://github.com/TA-Lib/ta-lib"),
    "tulipindicators": ("LGPL-3.0", "https://github.com/TulipCharts/tulipindicators"),
    "stock-indicators": ("Apache-2.0", "https://github.com/DaveSkender/Stock.Indicators"),
}
ALIAS = {
    "ao": "awesome_oscillator",
    "chop": "choppiness_index",
    "er": "efficiency_ratio",
    "vhf": "vertical_horizontal_filter",
    "cti": "correlation_trend_indicator",
    "bop": "balance_of_power",
    "coppock": "coppock_curve",
    "copc": "coppock_curve",
    "ce": "chandelier_exit_long",
    "squeeze": "squeeze_on",
    "3blackcrows": "three_black_crows",
    "3whitesoldiers": "three_white_soldiers",
    "darkcloudcover": "dark_cloud_cover",
    "piercing": "piercing_pattern",
    "gravestonedoji": "gravestone_doji",
    "dragonflydoji": "dragonfly_doji",
    "spinningtop": "spinning_top",
    "macdh": "macd_histogram",
    "macds": "macd_signal",
    "kc": "keltner",
    "bbands": "bollinger",
    "ha": "heikin_ashi",
    "natr": "normalized_atr",
    "willr": "williams_r",
    "psar": "parabolic_sar",
    "ui": "ulcer_index",
    "massi": "mass_index",
    "stoch": "stochastic",
    "vosc": "volume_oscillator",
    "mom": "momentum",
    "linreg": "linear_regression",
    "zlema": "zero_lag_ema",
    "midprice": "median_price",
    "typprice": "typical_price",
    "eom": "ease_of_movement",
    "efi": "force_index",
}


def standard(name: str) -> str:
    name = name.removeprefix("cdl_")
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    name = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    # Pattern systems use compact canonical names, not 62 separately copied implementations.
    return ALIAS.get(name, name)


def collect(root: Path) -> dict[str, list[str]]:
    pta = root / "pandas-ta-classic/pandas_ta_classic"
    categories = (
        "candles", "cycles", "math", "momentum", "overlap",
        "performance", "statistics", "trend", "volatility", "volume",
    )
    values = {
        "pandas-ta-classic": sorted({
            f.stem
            for category in categories
            for f in (pta / category).glob("*.py")
            if f.name != "__init__.py" and not f.name.startswith("_")
        }),
        "ta-lib": sorted({
            f.stem[3:].lower()
            for f in (root / "ta-lib/src/ta_func").glob("ta_*.c")
        }),
        "tulipindicators": sorted({
            f.stem for f in (root / "tulipindicators/indicators").glob("*.c")
        }),
        "stock-indicators": sorted({
            f.name.removesuffix(".Catalog.cs")
            for f in (root / "stock-indicators/src/Indicators").rglob("*.Catalog.cs")
        }),
    }
    for source, names in values.items():
        if not names:
            raise ValueError(f"missing inventory: {source}")
    return values


def build(root: Path) -> dict[str, object]:
    from subprocess import check_output

    specs = research_feature_specs()
    existing = {standard(s.name) for s in specs}
    existing.update(standard(alias) for s in specs for alias in s.aliases)
    ported = {
        name for name in existing
        if name in {
            "choppiness_index", "squeeze_on", "chandelier_exit_long",
            "awesome_oscillator", "kst", "coppock_curve", "efficiency_ratio",
            "vertical_horizontal_filter", "correlation_trend_indicator",
            "balance_of_power", "harami", "piercing_pattern", "dark_cloud_cover",
            "three_white_soldiers", "three_black_crows", "spinning_top",
            "dragonfly_doji", "gravestone_doji",
        }
    }
    raw = collect(root)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    manifests = []
    for source, names in sorted(raw.items()):
        location = root / source
        sha = check_output(["git", "-C", str(location), "rev-parse", "HEAD"], text=True).strip()
        manifests.append({
            "source": source, "url": SOURCES[source][1], "license": SOURCES[source][0],
            "sha": sha, "raw_entries": len(names),
        })
        for name in names:
            key = standard(name)
            groups[key].append({"source": source, "source_name": name})
    grouped = []
    for name, occurrences in sorted(groups.items()):
        if name in ported:
            state = "PORTED_VERIFIED_UNIT_TESTS"
        elif name in existing:
            state = "EXISTING_NAME_OR_ALIAS_REVIEW"
        else:
            state = "NEW_NOT_YET_PORTED"
        grouped.append({
            "canonical_candidate": name,
            "status": state,
            "occurrences": occurrences,
        })
    return {
        "schema": "v3-source-indicator-inventory-v1",
        "warning": "Name-level dedup only; implementation/formula/output equivalence not proven.",
        "source_manifest": manifests,
        "registered_before": len(specs) - len(ported),
        "registered_now": len(specs),
        "entries_total": sum(len(names) for names in raw.values()),
        "name_level_candidates": len(grouped),
        "states": {
            kind: sum(row["status"] == kind for row in grouped)
            for kind in ("PORTED_VERIFIED_UNIT_TESTS", "EXISTING_NAME_OR_ALIAS_REVIEW",
                         "NEW_NOT_YET_PORTED")
        },
        "candidates": grouped,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "candidates"}, indent=2))


if __name__ == "__main__":
    main()
