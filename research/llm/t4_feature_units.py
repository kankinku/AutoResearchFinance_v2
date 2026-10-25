"""Verified feature-unit advice and conservative rejection for T4 model plans.

Only include domains justified by the actual registered canonical calculator.
Schaff Trend Cycle is calculated using _percentile(_macd(...)), returning
a fraction in [0, 1]. No model-generated or historical market thresholds are
used to select entry/exit policies here.
"""

from __future__ import annotations

from typing import Any

from core.features.registry import research_feature_specs
from strategy_ir.schema import StrategyIR


class FeatureUnitMismatch(ValueError):
    """An explicitly registered feature has a provably out-of-range cutoff."""


_KNOWN_DOMAINS: dict[str, dict[str, Any]] = {
    "schaff_trend_cycle": {
        "calculator": "schaff_trend_cycle",
        "value_range": [0.0, 1.0],
        "scale": "normalized_fraction",
        "derivation": (
            "schaff_trend_cycle uses percentile(macd, lookback) "
            "in the canonical calculator"
        ),
    },
}


def verified_feature_unit_guidance() -> dict[str, Any]:
    """Model-facing documentation, never a substitute for actual execution."""
    installed = {f.name: f for f in research_feature_specs() if f.status == "REGISTERED"}
    verified = {
        name: {**info, "canonical_feature_id": installed[name].canonical_id}
        for name, info in sorted(_KNOWN_DOMAINS.items())
        if name in installed and installed[name].calculator == info["calculator"]
    }
    return {
        "schema": "t4-feature-unit-guidance-v1",
        "registered_feature_units": verified,
        "unlisted_feature_policy": "UNKNOWN_DO_NOT_ASSUME",
        "scope": "REGISTERED_CALCULATOR_DEFINITION_NOT_MARKET_OOS",
        "instruction": (
            "Choose numeric condition thresholds using the registered feature's "
            "actual scale, not the conventional name's quoted scale. "
            "For unknown ranges, inspect the calculator before proposing a cutoff."
        ),
    }


def verify_feature_condition_ranges(strategy: StrategyIR) -> None:
    """Reject only provably out-of-domain numeric cutoffs on known features.

    Preserve legacy rules, unknown domains, cross-series comparisons and all
    thresholds inside the documented inclusive range. Does not claim optimal
    cutoffs or independent economic validity.
    """
    unit_info = verified_feature_unit_guidance()["registered_feature_units"]
    for section, conditions in (
        ("entry", strategy.entry.conditions),
        ("exit", strategy.exit.conditions),
        ("regime_filters", strategy.regime_filters),
    ):
        for condition in conditions:
            if condition.enabled is False or condition.right is not None:
                continue
            reference = strategy.features.get(condition.left)
            if reference is None:
                continue
            feature = unit_info.get(reference.feature_id)
            if feature is None:
                continue
            value = condition.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            low, high = feature["value_range"]
            if value < low or value > high:
                raise FeatureUnitMismatch(
                    f"FEATURE_THRESHOLD_OUTSIDE_DOMAIN: {section}.{condition.left} "
                    f"uses cutoff {value:g} but registered {reference.feature_id} "
                    f"emits {feature['scale']} in [{low:g}, {high:g}]; "
                    "revise threshold using the same plan checkpoint token"
                )


def require_nonempty_executions(audit: Any, *, required: bool = True) -> None:
    """Opt-in T4 *planning* quality preflight based on actual S2 closed trades.

    This does not change legacy/past generation acceptance nor the S7 gate;
    authors can elect to repair an inactive candidate at the SAME plan token.
    """
    if required and (not audit.fills or not audit.round_trips):
        raise ValueError(
            "NO_EXECUTED_TRADES_PRECOMMIT: costed S2 replay contains no "
            "closed trades; revise plan using the same checkpoint token"
        )
