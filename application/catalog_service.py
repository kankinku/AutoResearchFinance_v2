from __future__ import annotations

from collections import Counter

from core.features.registry import research_feature_specs
from research.indicator_engine.capability_audit import audit_native_capabilities


class FeatureCatalogService:
    """Project research features without conflating registration with execution."""

    def research_features(self) -> list[dict[str, object]]:
        """Preserve the existing six-key feature listing for MCP compatibility."""
        return [
            {
                "name": spec.name,
                "family": spec.family,
                "inputs": list(spec.inputs),
                "calculator": spec.calculator,
                "lookback": spec.lookback,
                "timeframe": spec.timeframe,
            }
            for spec in research_feature_specs()
        ]

    def capability_summary(self) -> dict[str, object]:
        """Read-only bounded caveats for the GPT, not execution authorization."""
        rows = audit_native_capabilities()
        reasons = Counter(row["reason"] for row in rows)
        return {
            "source": "SYNTHETIC_OHLCV_PRIMITIVE_AUDIT_ONLY",
            "registered_count": len(rows),
            "observed_scalar_calculation_count": sum(row["calculation_observed"] for row in rows),
            "reasons": dict(sorted(reasons.items())),
            "not_bar_aligned": [
                row["name"] for row in rows if row["reason"] == "SPECIALIZED_NOT_BAR_ALIGNED"
            ],
            "no_observable_output_on_probe": [
                row["name"] for row in rows if row["reason"] == "NO_OBSERVABLE_OUTPUT"
            ],
            "usage_policy": (
                "Registered is not proof of executable feature or usable signal. "
                "Specialized features need a separately verified bar adapter; "
                "external series require as-of data; no Pine/source-specific preference."
            ),
        }
