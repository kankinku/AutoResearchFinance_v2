"""Bridge the real feature calculator to pinned policy receipts (development only)."""

from __future__ import annotations

from core.data.contracts import MarketDataSet
from core.features.calculators import calculate_feature
from core.features.contracts import FeatureSpec
from core.features.registry import FeatureRegistry
from strategy_ir.feature_receipt import compile_with_trusted_receipt_lookup
from strategy_ir.policy_decision import PolicyDecision
from strategy_ir.policy_program import PolicySwitch
from strategy_ir.receipt_manifest import PinnedReceiptManifest


def compile_calculated_policy(
    dataset: MarketDataSet,
    program: PolicySwitch,
    registry: FeatureRegistry,
    manifest: PinnedReceiptManifest,
) -> tuple[PolicyDecision, ...]:
    """Calculate actual OHLCV features; refuse inputs without pinned review receipts.

    Prefix agreement is a local anti-lookahead check, not independent PIT proof.
    """
    if dataset.zone != "development":
        raise ValueError("development data required")
    bars = dataset.bars
    features: dict[str, tuple[float | None, ...]] = {}
    for feature_id in sorted({item.feature for item in program.predicates}):
        spec: FeatureSpec = registry.get(feature_id)
        if spec.status != "REGISTERED" or spec.name != feature_id:
            raise ValueError("canonical registered feature required")
        if (
            spec.timeframe != "1d"
            or spec.lag_bars
            or any(name not in {"open", "high", "low", "close", "volume"} for name in spec.inputs)
        ):
            raise ValueError("unsupported unaligned or external feature inputs")
        series = {name: tuple(float(getattr(bar, name)) for bar in bars) for name in spec.inputs}
        calculated = calculate_feature(spec, series)
        if len(calculated) != len(bars):
            raise ValueError("feature alignment mismatch")
        # Verify every prefix using the actual production calculator. Limit to
        # development slices; higher-cost exhaustive historical proof is separate.
        for end in range(1, len(bars) + 1):
            prefix = calculate_feature(
                spec, {name: values[:end] for name, values in series.items()}
            )
            if prefix != calculated[:end]:
                raise ValueError("feature used future bars")
        features[feature_id] = calculated
    return compile_with_trusted_receipt_lookup(dataset, program, features, lookup=manifest.lookup)
