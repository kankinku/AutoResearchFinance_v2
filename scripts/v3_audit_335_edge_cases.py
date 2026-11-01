"""Additional evaluation of non-default OHLCV scenarios and exact signal repeats."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from scripts.v3_audit_335_features import AVAILABLE, synthetic

PATH = Path("docs/operations/quant-v3-335-edge-duplicate-evaluation-20261029.json")


def evaluate() -> dict[str, object]:
    baseline, _ = synthetic()
    n = len(baseline["close"])
    variants: dict[str, dict[str, tuple[float | None, ...]]] = {
        "zero_volume": {k: (0.0,) * n if k == "volume" else v for k, v in baseline.items()},
        "flat_price": {
            "open": (100.0,) * n,
            "high": (100.0,) * n,
            "low": (100.0,) * n,
            "close": (100.0,) * n,
            "volume": (1000.0,) * n,
        },
        "missing_bar": {
            k: tuple(None if j in (170, 171) else x for j, x in enumerate(v))
            for k, v in baseline.items()
        },
    }
    issues: dict[str, list[dict[str, str]]] = {}
    fingerprints: dict[tuple[float | None, ...], list[str]] = defaultdict(list)
    constant = []
    specs = [
        s
        for s in research_feature_specs()
        if s.data_contract == "scalar" and set(s.inputs) <= AVAILABLE
    ]
    for spec in specs:
        data = {key: baseline[key] for key in spec.inputs}
        try:
            result = calculate_feature(spec, data)
            fingerprint = tuple(None if x is None else round(float(x), 8) for x in result)
            if len(set(v for v in fingerprint if v is not None)) > 1:
                fingerprints[fingerprint].append(spec.name)
            else:
                constant.append(spec.name)
        except Exception:
            continue
        for name, variant in variants.items():
            try:
                out = calculate_feature(spec, {key: variant[key] for key in spec.inputs})
                if len(out) != n or any(x is not None and not math.isfinite(x) for x in out):
                    raise ValueError("unaligned or nonfinite value")
            except Exception as exc:
                issues.setdefault(name, []).append(
                    {
                        "name": spec.name,
                        "error": f"{type(exc).__name__}: {exc}"[:250],
                    }
                )
    exact = [sorted(group) for group in fingerprints.values() if len(group) > 1]
    exact.sort(key=lambda group: (-len(group), group))
    summary = {
        "schema": "quant-v3-335-edge-duplicate-audit-v1",
        "eligible_scalar_ohlcv": len(specs),
        "edge_exception_counts": dict(
            sorted((name, len(issues.get(name, []))) for name in variants)
        ),
        "edge_issues": issues,
        "exact_nonconstant_duplicate_groups": exact,
        "exact_nonconstant_duplicate_group_count": len(exact),
        "constant_on_one_synthetic_path": sorted(constant),
        "constant_count": len(constant),
        "caveat": (
            "Exact numerical equality applies only to these 420 synthetic observations and "
            "current default periods, not a proof of mathematical identity; zero-valued "
            "candle patterns may legitimately never trigger on smooth artificial bars."
        ),
    }
    PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "eligible": len(specs),
                "edge_exception_counts": summary["edge_exception_counts"],
                "exact_duplicate_groups": exact,
                "constant_count": len(constant),
            },
            ensure_ascii=False,
        )
    )
    for key, rows in issues.items():
        for row in rows:
            print("ISSUE", key, row["name"], row["error"])
    return summary


if __name__ == "__main__":
    evaluate()
