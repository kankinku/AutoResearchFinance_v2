"""Read-only academic VERIFIED signal vs generic calculator parity experiment.

Synthetic completed candles are deliberately *not* paper replication, PIT
backtesting, live eligibility or model/provider research evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from application.quant_feature_bridge_audit import _read_signals
from research.indicator_engine.feature_parity_bridge import verify_feature_signal_parity
from research.indicator_engine.models import IndicatorCandidate


def _synthetic() -> dict[str, tuple[float, ...]]:
    close = tuple(100.0 + i * 0.04 + (i % 17) * 0.13 for i in range(630))
    return {
        "open": tuple(x + (0.08 if i % 2 else -0.05) for i, x in enumerate(close)),
        "high": tuple(x + 1.0 for x in close),
        "low": tuple(x - 1.0 for x in close),
        "close": close,
    }


def audit(catalog: Path) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    verified = sorted(
        (
            IndicatorCandidate.model_validate(payload)
            for payload in _read_signals(catalog).values()
            if payload["status"] == "VERIFIED"
        ),
        key=lambda c: c.signal_id,
    )
    for candidate in verified:
        try:
            evidence = verify_feature_signal_parity(candidate, _synthetic())
        except ValueError as exc:
            pairs.append(
                {
                    "academic_signal_id": candidate.signal_id,
                    "status": "NOT_EQUIVALENCE_VERIFIED",
                    "reason": str(exc),
                }
            )
        else:
            pairs.append(
                {
                    "academic_signal_id": candidate.signal_id,
                    "status": "SYNTHETIC_EQUIVALENCE_VERIFIED_NOT_PROMOTED",
                    "evidence": evidence,
                }
            )
    return {
        "schema": "quant-feature-semantic-parity-report-v1",
        "academic_verified_catalog_count": len(verified),
        "synthetic_parity_pass": sum(x["status"].startswith("SYNTHETIC_") for x in pairs),
        "untested_or_not_equivalent": sum(not x["status"].startswith("SYNTHETIC_") for x in pairs),
        "no_automatic_catalog_promotion": True,
        "orders_enabled": False,
        "independent_oos_approved": False,
        "model_calls": 0,
        "results": pairs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.catalog)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
