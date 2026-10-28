"""Reproducible disposition of the 330 names inventoried after the second batch.

This is a source-name audit, NOT proof that all unrelated algorithms have been ported.
Pandas TA's pinned manifest is the only additional executable implementation
added in this phase. Remaining TA-Lib / C# / LGPL candidates stay unregistered.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


def compact(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def audit(prior: dict[str, Any], port: dict[str, Any], root: Path) -> dict[str, Any]:
    entries = {str(e["source"]): e for e in port["entries"]}
    semantic_overlap = dict(port["excluded_semantic_overlap"])
    failed = {r["name"]: r["reason"] for r in port["failed_probe"]}

    additional_ports = {
        "ac": "talib_ac",
        "adr": "talib_adr",
        "imi": "talib_imi",
        "rogerssatchell": "talib_rogers_satchell",
        "rvol": "talib_rvol",
        "alligator": "stock_alligator_jaw",
        "elder_ray": "stock_elder_bull",
        "starc_bands": "stock_starc_upper",
        "ibs": "talib_ibs",
        "si": "talib_si",
        "asi": "talib_asi",
        "frama": "talib_frama",
        "gator": "stock_gator_upper",
        "pmo": "stock_pmo",
        "roc_wb": "stock_roc_wb_upper",
        "fcb": "stock_fcb_upper",
        "std_dev_channels": "stock_stddev_channel_upper_now",
    }

    existing_patterns = {
        "doji",
        "inside",
        "engulfing",
        "hammer",
        "shootingstar",
        "eveningstar",
        "morningstar",
        "threeblackcrows",
        "threewhitesoldiers",
        "marubozu",
        "hangingman",
        "invertedhammer",
        "belthold",
        "haramicross",
        "matchinglow",
        "highwave",
        "longleggeddoji",
        "threeinside",
        "darkcloudcover",
        "piercing",
        "gravestonedoji",
        "dragonflydoji",
        "spinningtop",
    }
    registered_candles = {compact(source[4:]) for source in entries if source.startswith("cdl_")}
    duplicate_indicators = {
        "ad",
        "adosc",
        "adx",
        "adxr",
        "ao",
        "awesome",
        "alma",
        "avgprice",
        "atr",
        "atrstop",
        "bop",
        "bollinger",
        "chandelier",
        "chop",
        "cmou",
        "cmo",
        "correlation",
        "cumsum",
        "donchian",
        "emv",
        "eom",
        "fractal",
        "hvol",
        "httrendline",
        "kst",
        "lag",
        "linearreg",
        "ln",
        "logreturn",
        "ma",
        "macdext",
        "macdfix",
        "crsi",  # Existing Quant connors_rsi: same Connors RSI family, no duplicate promotion.
        "mama",
        "mass",
        "medprice",
        "midpoint",
        "mmar",
        "natr",
        "percentrank",
        "percentb",
        "pivots",
        "roc",
        "rocp",
        "rocr",
        "rocr100",
        "rma",
        "sar",
        "sarext",
        "smma",
        "sqrt",
        "stc",
        "stddev",
        "stochf",
        "stochrsi",
        "supertrend",
        "t3",
        "tr",
        "trima",
        "ultimate",
        "uo",
        "volatility",
        "volatilitystop",
        "wilder",
        "wilders",
        "vosc",
        "zlema",
    }
    math_terms = {
        "abs",
        "acos",
        "add",
        "asin",
        "atan",
        "ceil",
        "cos",
        "cosh",
        "crossany",
        "crossover",
        "div",
        "exp",
        "floor",
        "ln",
        "log10",
        "max",
        "maxindex",
        "min",
        "minindex",
        "minmax",
        "minmaxindex",
        "mult",
        "mul",
        "npabs",
        "npround",
        "round",
        "sin",
        "sinh",
        "sqrt",
        "sub",
        "sum",
        "tan",
        "tanh",
        "todeg",
        "torad",
        "trunc",
        "rollingmax",
        "rollingmin",
        "rollingsum",
        "median",
        "stderr",
        "variance",
        "stdev",
        "stddev",
    }
    extra_data = {
        "beta",
        "correl",
        "prs",
        "correlation",
        "relativevolume",
    }
    noncausal = {"zigzag", "rollingpivots", "fractal", "fractals", "ichimoku"}
    own = Path(root, "pandas_ta_classic")
    records = []
    for item in prior["candidates"]:
        if item["status"] != "NEW_NOT_YET_PORTED":
            continue
        occur = item["occurrences"]
        refs = {r["source"]: r["source_name"] for r in occur}
        panda = refs.get("pandas-ta-classic")
        ta_lib = refs.get("ta-lib")
        stock = refs.get("stock-indicators")
        tulip = refs.get("tulipindicators")
        name = item["canonical_candidate"]

        if name in additional_ports:
            state = "PORTED_VERIFIED_INDEPENDENT_FORMULA"
            reason = "Pinned TA-Lib C / Stock C# math independently ported and tested"
            new_name = additional_ports[name]
        elif panda in entries:
            state = "PORTED_VERIFIED_SOURCE_ADAPTER"
            reason = "Pinned MIT source; aligned numeric source output and prefix audit"
            new_name = "pta_" + panda
        elif panda in semantic_overlap:
            state = "EXCLUDED_SEMANTIC_OVERLAP"
            reason = semantic_overlap[panda]
            new_name = None
        elif panda in failed:
            state = "QUARANTINED_PROBE_FAILURE"
            reason = str(failed[panda])
            new_name = None
        elif panda and (own / "math" / (panda + ".py")).is_file():
            state = "EXCLUDED_MATH_OPERATOR"
            reason = "Generic mathematical transformer, not a separately verified trading feature"
            new_name = None
        elif compact(name) in math_terms:
            state = "EXCLUDED_MATH_OPERATOR"
            reason = "Generic math operator or rolling reducer, not a standalone indicator"
            new_name = None
        elif (panda and compact(panda.replace("cdl_", "")) in existing_patterns) or (
            ta_lib and ta_lib.startswith("cdl") and compact(ta_lib[3:]) in existing_patterns
        ):
            state = "EXCLUDED_KNOWN_PATTERN_FAMILY"
            reason = "Already represented by native/first two batch pattern family"
            new_name = None
        elif ta_lib and ta_lib.startswith("cdl") and compact(ta_lib[3:]) in registered_candles:
            state = "EXCLUDED_DUPLICATE_CANDLE_SOURCE"
            reason = (
                "Equivalent named TA-Lib candle family already backed by pinned MIT implementation"
            )
            new_name = None
        elif (
            (panda and compact(panda) in duplicate_indicators)
            or (stock and compact(stock) in duplicate_indicators)
            or (ta_lib and compact(ta_lib) in duplicate_indicators)
        ):
            state = "EXCLUDED_KNOWN_INDICATOR_FAMILY"
            reason = "Indicator family already represented; numerical parity pending"
            new_name = None
        elif compact(name) in extra_data or (panda and panda in extra_data):
            state = "BLOCKED_EXTERNAL_ASOF_INPUTS"
            reason = "Additional benchmark/cross-asset point-in-time inputs unavailable"
            new_name = None
        elif compact(name) in noncausal:
            state = "QUARANTINED_POTENTIAL_LOOKAHEAD"
            reason = (
                "Repainting/forward-looking risk requires separately locked causal specification"
            )
            new_name = None
        elif panda and any(
            (own / folder / (panda + ".py")).exists()
            for folder in (
                "candles",
                "cycles",
                "momentum",
                "overlap",
                "statistics",
                "trend",
                "volatility",
                "volume",
            )
        ):
            state = "PENDING_PANDAS_SOURCE_ADAPTER_REVIEW"
            reason = "Source exists but probe did not demonstrate safe aligned calculation"
            new_name = None
        elif ta_lib:
            state = "PENDING_TALIB_C_SOURCE_PORT"
            reason = "C function needs API/output parity and causal adapter"
            new_name = None
        elif stock:
            state = "PENDING_CSHARP_SOURCE_PORT"
            reason = ".NET indicator not yet ported/tested in Python research engine"
            new_name = None
        elif tulip:
            state = "PENDING_LGPL_COMPLIANCE_OR_FALLBACK"
            reason = "LGPL license and Python parity review required"
            new_name = None
        else:
            state = "PENDING_UNRESOLVED_SOURCE"
            reason = "No verified causal same-symbol adapter"
            new_name = None
        records.append(
            {
                "canonical_candidate": name,
                "state": state,
                "reason": reason,
                "registered_name": new_name,
                "sources": occur,
            }
        )
    if len(records) != 330:
        raise ValueError(f"expected full 330-name audit, got {len(records)}")
    states = dict(sorted(Counter(r["state"] for r in records).items()))
    return {
        "schema": "quant-v3-330-source-candidate-disposition-v1",
        "prior_source_name_candidates": len(records),
        "registered_new_source_candidate_groups": (
            states.get("PORTED_VERIFIED_SOURCE_ADAPTER", 0)
            + states.get("PORTED_VERIFIED_INDEPENDENT_FORMULA", 0)
        ),
        "registered_new_feature_outputs": len(port["entries"]) + 12 + 13,
        "remaining_eligible_not_proven": sum(
            n for k, n in states.items() if k.startswith("PENDING_")
        ),
        "warning": (
            "Semantic family duplicates are conservative exclusion decisions, "
            "not a proof of byte-for-byte formula equivalence. "
            "The remaining PENDING and QUARANTINED names are not active Quant features."
        ),
        "source_shas": prior["source_manifest"],
        "states": states,
        "dispositions": records,
    }


def main() -> None:
    source = Path("docs/operations/quant-v3-opensource-indicator-candidates-batch2-20261028.json")
    manifest = Path("core/features/pandas_ta_manifest.json")
    result = audit(json.loads(source.read_text()), json.loads(manifest.read_text()), Path("."))
    output = Path("docs/operations/quant-v3-330-source-full-disposition-20261028.json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "dispositions"}, indent=2))


if __name__ == "__main__":
    main()
