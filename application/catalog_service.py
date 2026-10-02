from __future__ import annotations

from core.features.registry import research_feature_specs


class FeatureCatalogService:
    """Project the research feature registry for command and MCP consumers."""

    def research_features(self) -> list[dict[str, object]]:
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
