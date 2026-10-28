"""Reusable, read-only 100-output cohort gate for autonomous feature research.

Checks overlap with every preexisting feature on synthetic data, complete
prefix causality at multiple cutoffs, and inherited StrategyIR scalar binding.
No seals, broker access, OOS, market feeds, or generational mutation.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from research.llm.inherited_feature_compiler import _new_feature_vector
from scripts.v3_audit_435_features import synthetic
from strategy_ir.schema import FeatureRef

MANIFEST = Path("core/features/bulk100_manifest.json")
OUTPUT = Path("docs/operations/quant-v3-bulk100-cohort-gate-20261029.json")


def _fingerprint(values: tuple[float | None, ...]) -> str:
    line = ";".join("N" if v is None else f"{v:.7f}" for v in values)
    return hashlib.sha256(line.encode()).hexdigest()


def run() -> dict[str, object]:
    evidence = json.loads(MANIFEST.read_text())
    selected = {item["name"] for item in evidence["entries"]}
    specs = research_feature_specs()
    assert len(selected) == 100 and len(specs) == 435
    raw, market = synthetic(480)
    fingerprints: dict[str, str] = {}
    for spec in specs:
        if (
            spec.name in selected
            or spec.data_contract != "scalar"
            or any(field not in raw for field in spec.inputs)
        ):
            continue
        source = {field: raw[field] for field in spec.inputs}
        values = calculate_feature(spec, source)
        fingerprints[_fingerprint(values)] = spec.name
    rows: list[dict[str, object]] = []
    for spec in specs:
        if spec.name not in selected:
            continue
        status = "VERIFIED_DISTINCT_DEFAULT"
        why = ""
        nonnull = 0
        try:
            source = {field: raw[field] for field in spec.inputs}
            values = calculate_feature(spec, source)
            nonnull = sum(v is not None for v in values)
            if (
                len(values) != 480
                or nonnull < 10
                or any(x is not None and not math.isfinite(x) for x in values)
            ):
                raise ValueError("invalid scalar or missing source output")
            distinct_values = {round(x, 7) for x in values if x is not None}
            if len(distinct_values) <= 1:
                raise ValueError("constant source output on evaluation path")
            signature = _fingerprint(values)
            if signature in fingerprints:
                raise ValueError(f"duplicate synthetic signal: {fingerprints[signature]}")
            fingerprints[signature] = spec.name
            for cutoff in (140, 280, 420, 479):
                sub = calculate_feature(
                    spec, {field: series[:cutoff] for field, series in source.items()}
                )
                if sub != values[:cutoff]:
                    raise ValueError(f"prefix mismatch at bar {cutoff}")
            ref = FeatureRef(feature_id=spec.name, lookback=spec.lookback, inputs=spec.inputs)
            if _new_feature_vector(ref, market) != values:
                raise ValueError("StrategyIR inherited replay mismatch")
        except Exception as exc:
            status = "REJECTED"
            why = f"{type(exc).__name__}: {exc}"[:210]
        rows.append(
            {
                "name": spec.name,
                "status": status,
                "nonmissing": nonnull,
                "reason": why,
                "lookback": spec.lookback,
            }
        )
    verified = sum(row["status"] == "VERIFIED_DISTINCT_DEFAULT" for row in rows)
    answer = {
        "schema": "quant-v3-bulk100-cohort-gate-v1",
        "registered_total": len(specs),
        "new_cohort_size": len(rows),
        "verified_new_distinct_default_outputs": verified,
        "rejected_count": len(rows) - verified,
        "previous_registered_count": len(specs) - len(rows),
        "external_or_special_inputs_not_checked": 26,
        "source_shas": evidence["source_shas"],
        "screening_scope": (
            "Single 480-bar deterministic developmental synthetic market; unique output "
            "signatures on that path, not mathematical formula uniqueness or "
            "independent OOS/profitability proof. Four bar-prefix lengths tested."
        ),
        "rows": rows,
    }
    OUTPUT.write_text(json.dumps(answer, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: value for key, value in answer.items() if key != "rows"}))
    for row in rows:
        if row["status"] != "VERIFIED_DISTINCT_DEFAULT":
            print("REJECT", row["name"], row["reason"])
    return answer


if __name__ == "__main__":
    run()
