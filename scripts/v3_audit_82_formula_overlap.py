"""Evidence-oriented 82 candidate formula-family audit.

A source function sharing a common trading name isn't proof of equal output:
declare explicit mathematical equivalences separately from family/parameter
variants, and retain the actual pinned source locations and numerical evidence.
This audit changes neither FeatureSpec registry nor trading/data boundaries.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from core.features.calculators import calculate_feature
from core.features.pandas_ta_pinned import _callable
from core.features.registry import research_feature_specs
from scripts.v3_audit_335_features import synthetic

ROOT = Path("docs/operations/quant-v3-max-additional-pandas-source-capacity-20261029.json")
OUTPUT = Path("docs/operations/quant-v3-82-formula-overlap-audit-20261029.json")
CATEGORIES = {
    "ALGEBRAIC_DUPLICATE": (
        "Identical named formula after matching source period, or algebraic affine "
        "version; no new independent research feature"
    ),
    "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION": (
        "Existing named mathematical indicator family; parameter, initialization, "
        "or implementation differs and numerical parity is not implied"
    ),
    "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY": (
        "Additional band/line/input-specific transform or state channel, not a new "
        "independent formula family"
    ),
    "UNREPRESENTED_FORMULA": (
        "Not found as its own named formula in the 435-feature scalar catalog; new "
        "feature candidate, still subject to production readiness and cross-source "
        "exact formula audit"
    ),
}
MATCH: dict[str, tuple[str, str, str]] = {
    # source: classification, baseline target, formula/semantic basis
    "ht_dcperiod": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "dominant_cycle",
        (
            "Hilbert-transform dominant-cycle period; existing dominant_cycle is a "
            "simplified cycle estimator"
        ),
    ),
    "ht_dcphase": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "hilbert_phase",
        "Hilbert dominant-cycle phase; existing hilbert_phase uses atan2 of price movement",
    ),
    "cdl_doji": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "doji",
        "Candle body vs historical range-based threshold, rather than simple same-bar threshold",
    ),
    "cdl_engulfing": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "engulfing",
        "Signed bullish/bearish engulfing versus current one-sided simplified pattern",
    ),
    "cdl_harami": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "harami",
        "TA candle body/range threshold and direction versus current harami signature",
    ),
    "cdl_highwave": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "high_wave",
        "Doji-like small body plus two long shadows; existing high_wave candle family",
    ),
    "cdl_inside": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "inside_bar",
        "Inside bar direction/color and scalar vs existing 0/1 inside-bar detection",
    ),
    "cdl_longleggeddoji": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "long_legged_doji",
        "Doji body and long-shadow criteria, candle setting dependent",
    ),
    "cdl_matchinglow": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "matching_low",
        "Pattern of two bearish candles with nearly equal lows of body/close",
    ),
    "cdl_pattern": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "spinning_top",
        "Output index 52 spinning-top candlestick pattern already named in catalog",
    ),
    "cdl_z": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "zscore",
        (
            "Rolling zscore of four OHLC legs (open, high, low, close), existing scalar "
            "uses close alone"
        ),
    ),
    "ha": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "heikin_ashi",
        (
            "HA_open recursive; HA_high=max(high,HA_open,HA_close); "
            "HA_low=min(low,HA_open,HA_close), existing HA_close component"
        ),
    ),
    "bias": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "bias_ratio",
        "BIAS = close/MA(close)-1; bias_ratio family already present",
    ),
    "brar": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "brar_ar",
        "AR and BR from open-high/low and previous-close ranges; brar_ar and brar_br both exist",
    ),
    "cg": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "center_of_gravity",
        "Negative weighted rolling close sum divided by rolling close sum; sign and warmup differ",
    ),
    "coppock": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "coppock_curve",
        "WMA of summed two rate-of-change paths; registered Coppock family",
    ),
    "cti": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "correlation_trend_indicator",
        "Pearson R of closes vs linear time trend; CTI already represented",
    ),
    "er": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "efficiency_ratio",
        "Kaufman efficiency ratio abs net change/sum(abs close differences)",
    ),
    "kdj": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "kdj_j",
        "K,D,J of stochastic oscillator; J already present and K,D are associated lines",
    ),
    "lrsi": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "laguerre_rsi",
        "Four-filter Laguerre stage RSI; registered laguerre_rsi currently simplified",
    ),
    "mom": (
        "ALGEBRAIC_DUPLICATE",
        "momentum",
        "MOM = close[t] - close[t-n], exactly native momentum at same n",
    ),
    "pgo": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "pretty_good_oscillator",
        "PGO = (close-SMA) / EMA(ATR), same named oscillator",
    ),
    "psl": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "psychological_line",
        "Percent-positive/negative closes sign sum vs psychological_line",
    ),
    "rocp": ("ALGEBRAIC_DUPLICATE", "returns", "ROCP = close/close[n]-1 = native returns"),
    "rocr": ("ALGEBRAIC_DUPLICATE", "returns", "ROCR = close/close[n] = native returns + 1"),
    "rocr100": (
        "ALGEBRAIC_DUPLICATE",
        "returns",
        "ROCR100 = 100*close/close[n] = 100*(native returns+1)",
    ),
    "squeeze": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "squeeze_on",
        "Squeeze release OFF boolean complements existing squeeze_on and bands",
    ),
    "stoch": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "stochastic",
        "Slow stochastic %D signal-line from smoothed %K; existing main stochastic output",
    ),
    "willr": (
        "ALGEBRAIC_DUPLICATE",
        "williams_r",
        "WILLIAMS %R = 100*((close-lowest)/(highest-lowest)-1)",
    ),
    "ht_trendline": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "hilbert_trendline",
        "Hilbert-transform trendline differs from existing EMA approximation",
    ),
    "linreg": (
        "ALGEBRAIC_DUPLICATE",
        "linear_regression",
        (
            "Ordinary least-squares line endpoint; identical registered linear_regression "
            "with same period"
        ),
    ),
    "mcgd": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "mcginley",
        "McGinley Dynamic adaptive recursion; depends on seed/ratio floor details",
    ),
    "midpoint": (
        "UNREPRESENTED_FORMULA",
        "",
        "(rolling max(close,n)+rolling min(close,n))/2, no named same-close-window midpoint scalar",
    ),
    "mmar": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "guppy_mma",
        "Five separately exposed EMA lines at multiple periods of Moving Average Rainbow",
    ),
    "rma": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "rsi.wilder",
        (
            "Wilder EMA alpha=1/n smoothing; existing smoothing primitive used within RSI "
            "but not direct standalone output"
        ),
    ),
    "wcp": (
        "UNREPRESENTED_FORMULA",
        "",
        "Weighted closing price (high+low+2*close)/4; differs from typical price HLC3 and OHLC4",
    ),
    "drawdown": (
        "UNREPRESENTED_FORMULA",
        "",
        (
            "Three wealth/price running-peak drawdown measures: peak-close, 1-close/peak "
            "and log(peak/close); portfolio max drawdown metric is not bar-level catalog "
            "scalar"
        ),
    ),
    "log_return": (
        "ALGEBRAIC_DUPLICATE",
        "log_returns",
        "LOGRET_n = log(close[t]/close[t-n]), same input n as native log_returns",
    ),
    "kurtosis": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "rolling_kurtosis",
        (
            "Fourth standardized central moment; pandas computes sample/excess "
            "conventions, native often population moment"
        ),
    ),
    "skew": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "rolling_skewness",
        "Third standardized central moment, sample vs population normalization",
    ),
    "stderr": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "standard_deviation",
        (
            "Standard error = sample standard deviation/sqrt(window length), derived from "
            "existing stdev"
        ),
    ),
    "stdev": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "standard_deviation",
        "Rolling sample std(ddof=1) vs native population std(ddof=0)",
    ),
    "variance": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "standard_deviation",
        "Variance = square of sample stdev; directly derived from stdev with ddof agreement",
    ),
    "adxr": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "dmi_adx",
        "ADXR = (ADX[t]+ADX[t-period])/2 smoothed follow-up to existing ADX",
    ),
    "chop": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "choppiness_index",
        "Choppiness index log(sum ATR / high-low span)/log(n)",
    ),
    "psar": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "parabolic_sar",
        (
            "PSAR long, short, acceleration factor and reversal state; registered "
            "parabolic_sar scalar and Buk split markers"
        ),
    ),
    "sarext": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "parabolic_sar",
        "Extended acceleration factors of SAR, same family different acceleration/initialization",
    ),
    "vhf": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "vertical_horizontal_filter",
        "(rolling max(close)-min(close))/sum(abs successive close changes), same VHF family",
    ),
    "accbands": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "acceleration_band_upper",
        "Acceleration band lower or upper from low/high*(1±(high-low)/(high+low)) and MA",
    ),
    "ce": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "chandelier_exit_long",
        "Chandelier long HH-N*ATR and short LL+N*ATR, one existing side",
    ),
    "hvol": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "historical_volatility",
        "Std of one-bar log returns times sqrt(annualization), source percent and ddof adjust",
    ),
    "kc": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "buk_volatility_kcl",
        (
            "Keltner lower/upper bands; existing registered Bukosabino kcl/kch, source "
            "uses range smoothing"
        ),
    ),
    "massi": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "mass_index",
        "Mass Index double EMA of (high-low), two distinct fast and slow periods",
    ),
    "natr": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "normalized_atr",
        "Normalized ATR = 100*ATR/close; possible parameter and unit conventions differ",
    ),
    "thermo": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "thermometer",
        (
            "Thermometer moving average and change-state side signal, original "
            "thermometer raw already registered"
        ),
    ),
    "ad": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "adl",
        (
            "With open_ given, AD uses (close-open)*volume/(high-low); "
            "absent open it uses (2*close-high-low)*volume/(high-low) "
            "identical to native ADL"
        ),
    ),
    "adosc": (
        "UNREPRESENTED_FORMULA",
        "",
        (
            "Chaikin Accumulation/Distribution Oscillator = EMA_fast(ADL)-EMA_slow(ADL); "
            "different from Chaikin Volatility"
        ),
    ),
    "efi": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "force_index",
        "Force Index (close-change)*volume then smoothed MA; native scalar uses raw force index",
    ),
    "emv": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "ease_of_movement",
        "One-bar ease of movement midpoint distance*(high-low)/volume with scale divisor",
    ),
    "eom": (
        "ADDITIONAL_OUTPUT_OF_EXISTING_FAMILY",
        "ease_of_movement",
        "Smoothed SMA of ease of movement; same raw source family",
    ),
    "vosc": (
        "EXISTING_FAMILY_DIFFERENT_IMPLEMENTATION",
        "volume_oscillator",
        "100*(SMA(volume,fast)-SMA(volume,slow))/SMA(volume,slow), existing EMA-spread variant",
    ),
}
ALGEBRAIC_MODES = {
    "mom": "identity",
    "rocp": "identity",
    "rocr": "plus_one",
    "rocr100": "plus_one_times_100",
    "log_return": "identity",
    "linreg": "identity",
    "willr": "identity",
    "bias": "identity",
    "brar": "identity",
    "cti": "identity",
    "er": "identity",
    "kdj": "identity",
    "stdev": "identity",
    "chop": "identity",
    "vhf": "identity",
}
# Other source outputs have close family names, but this whitelist is only for
# numerically and algebraically confirmed identities on two market regimes.
PROVEN_MORE = frozenset(
    {
        "bias:0",
        "brar:0",
        "brar:1",
        "cti:0",
        "er:0",
        "kdj:2",
        "stdev:0",
        "chop:0",
        "vhf:0",
    }
)
OUTPUT_TARGET = {"brar:1": "brar_br"}


def normalized(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def overlap82():
    all_entries = json.loads(ROOT.read_text())["approved"]
    specs = research_feature_specs()

    def direct(entry):
        key = normalized(entry["source"])
        return [
            s.name
            for s in specs
            if normalized(s.name) == key
            or (s.name.startswith("pta_") and normalized(s.name[4:]) == key)
            or (s.name.startswith("buk_") and normalized(s.name[4:].split("_")[-1]) == key)
        ]

    removed = [x for x in all_entries if direct(x)]
    remaining = [x for x in all_entries if not direct(x)]
    assert len(all_entries) == 145 and len(removed) == 63 and len(remaining) == 82
    return remaining, specs


def source_callable(cat: str, name: str):
    method, signature = _callable(name, cat == "candles")
    return method, signature


def get_source_output(entry, data):
    source = entry["source"]
    func, names = source_callable(entry["category"], source)
    kwargs = {}
    for key in ("open_", "open", "high", "low", "close", "volume"):
        source_key = "open" if key in ("open", "open_") else key
        if key in names:
            kwargs[key] = pd.Series(data[source_key], dtype="float64")
    if "length" in names:
        kwargs["length"] = 20
    if "offset" in names:
        kwargs["offset"] = 0
    for key in ("talib", "lookahead", "centered"):
        if key in names:
            kwargs[key] = False
    output = func(**kwargs)
    if isinstance(output, pd.DataFrame):
        output = output.iloc[:, entry["index"]]
    return np.asarray(pd.to_numeric(output, errors="coerce"), dtype=float)


def numerical_checks(entries, specs):
    test_data, _ = synthetic(480)
    spec_by_name = {s.name: s for s in specs}
    by_source = {}
    for e in entries:
        by_source.setdefault(e["source"], []).append(e)
    evidence = {}
    for source, rows in sorted(by_source.items()):
        try:
            for entry in rows:
                out = get_source_output(entry, test_data)
                config = MATCH[source]
                target = OUTPUT_TARGET.get(source + ":" + str(entry["index"]), config[1])
                ev = {
                    "compared_to": target,
                    "same_period_n": 20,
                    "overlapping_finite": 0,
                    "raw_exact_max_abs_error": None,
                    "match_mode": None,
                }
                if target and target in spec_by_name:
                    spec = spec_by_name[target]
                    adjusted = (
                        spec.model_copy(update={"lookback": 20})
                        if spec.calculator not in {"bukosabino_pinned", "pandas_ta_pinned"}
                        else spec
                    )
                    native = np.asarray(
                        [
                            np.nan if v is None else float(v)
                            for v in calculate_feature(
                                adjusted, {k: test_data[k] for k in adjusted.inputs}
                            )
                        ]
                    )
                    if len(native) == len(out):
                        mode = ALGEBRAIC_MODES.get(source, "identity")
                        expected = {
                            "identity": native,
                            "plus_one": native + 1,
                            "plus_one_times_100": 100 * (native + 1),
                        }[mode]
                        overlap = np.isfinite(out) & np.isfinite(expected)
                        ev["overlapping_finite"] = int(overlap.sum())
                        if overlap.any():
                            ev["raw_exact_max_abs_error"] = float(
                                np.max(np.abs(out[overlap] - expected[overlap]))
                            )
                        if overlap.sum() >= 200 and np.allclose(
                            out[overlap], expected[overlap], rtol=1e-9, atol=1e-8
                        ):
                            ev["match_mode"] = mode
                evidence[source + ":" + str(entry["index"])] = ev
        except Exception as exc:
            for entry in rows:
                evidence[source + ":" + str(entry["index"])] = {
                    "error": type(exc).__name__ + ": " + str(exc)[:150]
                }
    return evidence


def run():
    remaining, specs = overlap82()
    numeric = numerical_checks(remaining, specs)
    records = []
    for entry in remaining:
        source = str(entry["source"])
        key = source + ":" + str(entry["index"])
        status, target, reason = MATCH[source]
        if key in PROVEN_MORE:
            status = "ALGEBRAIC_DUPLICATE"
            target = OUTPUT_TARGET.get(key, target)
            reason += "; verified source and existing formula coincide after period alignment"
        module = Path("pandas_ta_classic") / entry["category"] / (source + ".py")
        src_lines = module.read_text().splitlines()
        definition_line = next(
            (i + 1 for i, ln in enumerate(src_lines) if ln.startswith("def " + source + "(")), None
        )
        key = source + ":" + str(entry["index"])
        ev = numeric[key]
        if status == "ALGEBRAIC_DUPLICATE":
            if ev.get("match_mode") != ALGEBRAIC_MODES[source]:
                raise AssertionError(f"algebraic duplicate reference failed: {key}: {ev}")
        target_spec = next((s for s in specs if s.name == target), None) if target else None
        records.append(
            {
                "candidate": key,
                "category": entry["category"],
                "index": entry["index"],
                "existing_catalog_formula": target_spec.formula
                if target_spec is not None
                else None,
                "existing_catalog_calculator": target_spec.calculator
                if target_spec is not None
                else None,
                "existing_catalog_default_lookback": (
                    target_spec.lookback if target_spec is not None else None
                ),
                "existing_catalog_inputs": (
                    list(target_spec.inputs) if target_spec is not None else None
                ),
                "source": source,
                "source_output_index": entry["index"],
                "output_label": entry["label"],
                "source_path": str(module),
                "source_definition_line": definition_line,
                "source_sha": "7c669b033582d53b70aa68b6388796d19ce33979",
                "formula_disposition": status,
                "existing_comparison_target": target or None,
                "formula_evidence": reason,
                "numeric_reference_480": ev,
                "novel_independent_formula_certified": False,
            }
        )
    assert len(records) == 82 and len({x["candidate"] for x in records}) == 82
    counts = dict(sorted(Counter(x["formula_disposition"] for x in records).items()))
    output = {
        "schema": "quant-v3-82-formula-overlap-audit-v1",
        "registered_current": 435,  # immutable baseline at time of source audit
        "prior_numerical_candidates": 145,
        "excluded_prior_direct_name_match": 63,
        "evaluated_remaining": len(records),
        "counts": counts,
        "caveat": (
            "All 82 manually mapped to source-specific formulas and existing catalog "
            "names. ALGEBRAIC_DUPLICATE validated against native at same period on 480 "
            "synthetic bars, with <=1e-8 residual. EXISTING_FAMILY and "
            "ADDITIONAL_OUTPUT are formula-semantic classifications, not a proof of "
            "exact numeric equality. UNREPRESENTED means no named same-formula scalar "
            "in 435 names; not a proof of globally new mathematics. Differences can "
            "come from lookback, seeds, ddof and plotting. No registry changes."
        ),
        "items": records,
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "items"}, ensure_ascii=False))
    print(
        "NUMERIC_MATCHES",
        [
            (r["candidate"], r["numeric_reference_480"].get("raw_exact_max_abs_error"))
            for r in records
            if r["formula_disposition"] == "ALGEBRAIC_DUPLICATE"
        ],
    )
    return output


if __name__ == "__main__":
    run()
