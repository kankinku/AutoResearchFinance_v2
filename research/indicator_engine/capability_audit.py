"""Read-only P0 capability inventory; neither registration nor execution approval.

A catalog flag, successful primitive calculation, and GPT-accessible research
capability are different claims. Only the verified academic provider surface
can be marked end-to-end eligible here, and only for its reviewed market scope.
This audit does not change the provider, trading permissions, or strategy IR.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Literal, TypedDict

from core.data.contracts import DataZone, MarketDataSet
from core.features.calculators import FeatureCalculationError, calculate_feature
from core.features.contracts import FeatureSpec
from core.features.registry import research_feature_specs
from research.indicator_engine.algorithm_plan import build_algorithm_plan_context
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.signals import calculate_signal

CapabilityStatus = Literal["SUPPORTED_AND_EXECUTABLE", "PARTIAL", "MISSING", "BLOCKED_LICENSE"]


class CapabilityRow(TypedDict):
    surface: str
    name: str
    calculator: str
    declared_status: str
    status: CapabilityStatus
    reason: str
    llm_exposed: bool
    calculation_observed: bool


def _row(
    base: Mapping[str, str],
    *,
    status: CapabilityStatus,
    reason: str,
    llm_exposed: bool = False,
    calculation_observed: bool = False,
) -> CapabilityRow:
    return {
        "surface": base["surface"],
        "name": base["name"],
        "calculator": base["calculator"],
        "declared_status": base["declared_status"],
        "status": status,
        "reason": reason,
        "llm_exposed": llm_exposed,
        "calculation_observed": calculation_observed,
    }


def _synthetic_ohlcv() -> dict[str, tuple[float, ...]]:
    close = tuple(100.0 + 0.033 * i + 0.18 * (i % 11) for i in range(560))
    return {
        "close": close,
        "open": tuple(x - 0.22 for x in close),
        "high": tuple(x + 1.0 for x in close),
        "low": tuple(x - 1.0 for x in close),
        "volume": tuple(1000.0 + float(i % 29) for i in range(len(close))),
    }


def _license_blocked(spec: FeatureSpec) -> bool:
    # Conservative hold for explicit non-commercial or rights-restricted
    # code origins; legal permission review can clear a different version.
    return any(
        marker in license_name.lower()
        for license_name in spec.source_licenses
        for marker in ("by-nc", "noncommercial", "all rights reserved", "no license")
    )


def audit_native_capabilities(
    specs: Iterable[FeatureSpec] | None = None,
) -> tuple[CapabilityRow, ...]:
    """Probe primitive paths; never call them 'LLM executable' on this evidence.

    A bar-close synthetic calculation alone doesn't prove StrategyIR binding,
    as-of timing, source permissions, or full historical correctness.
    """
    values = _synthetic_ohlcv()
    rows = []
    for spec in sorted(
        research_feature_specs() if specs is None else specs,
        key=lambda item: item.name,
    ):
        base = {
            "surface": "native_feature_catalog",
            "name": spec.name,
            "calculator": spec.calculator,
            "declared_status": spec.status,
        }
        if _license_blocked(spec):
            rows.append(_row(base, status="BLOCKED_LICENSE", reason="SOURCE_PERMISSION_REVIEW"))
        elif spec.status != "REGISTERED":
            rows.append(_row(base, status="MISSING", reason="NOT_REGISTERED"))
        elif spec.data_contract != "scalar":
            rows.append(_row(base, status="PARTIAL", reason="SPECIALIZED_NOT_BAR_ALIGNED"))
        elif any(field not in values for field in spec.inputs):
            rows.append(_row(base, status="PARTIAL", reason="EXTERNAL_OBSERVATIONS_REQUIRED"))
        else:
            try:
                output = calculate_feature(spec, {field: values[field] for field in spec.inputs})
            except (FeatureCalculationError, ValueError, ArithmeticError) as exc:
                # Explicitly distinguish a missing operator from a failing
                # implementation; neither may be advertised to the GPT.
                kind: CapabilityStatus = (
                    "MISSING" if "unsupported calculator" in str(exc) else "PARTIAL"
                )
                rows.append(_row(base, status=kind, reason="CALCULATION_FAILED"))
                continue
            if len(output) != len(values["close"]) or any(
                x is not None and not math.isfinite(x) for x in output
            ):
                rows.append(_row(base, status="PARTIAL", reason="INVALID_CALCULATION_OUTPUT"))
            elif all(x is None for x in output):
                rows.append(_row(base, status="PARTIAL", reason="NO_OBSERVABLE_OUTPUT"))
            else:
                rows.append(
                    _row(
                        base,
                        status="PARTIAL",
                        reason="NOT_IN_ACADEMIC_PLAN_PROVIDER",
                        calculation_observed=True,
                    )
                )
    return tuple(rows)


def audit_academic_capabilities(
    catalog: ResearchCatalog,
    market: MarketDataSet,
) -> tuple[CapabilityRow, ...]:
    """Evaluate exactly the subset exposed by the current typed GPT provider.

    This is a read-only development surface test; NOT independent PIT/OOS or
    live/broker eligibility. Results are specific to the supplied market.
    """
    if market.zone != DataZone.DEVELOPMENT or not market.bars:
        raise ResearchCatalogError("audit requires nonempty DEVELOPMENT data")
    context = build_algorithm_plan_context(catalog, market)
    exposed = {str(item["indicator_id"]) for item in context["verified_indicators"]}
    bars = market.bars
    source = {
        key: tuple(float(getattr(bar, key)) for bar in bars)
        for key in ("open", "high", "low", "close")
    }
    rows = []
    for candidate in catalog.list_indicators():
        base = {
            "surface": "academic_algorithm_provider",
            "name": candidate.signal_id,
            "calculator": candidate.calculator,
            "declared_status": candidate.status,
        }
        if candidate.signal_id not in exposed:
            rows.append(_row(base, status="PARTIAL", reason="NOT_PROVIDER_ELIGIBLE"))
            continue
        try:
            calculated = calculate_signal(candidate, source)
        except (ValueError, ArithmeticError):
            rows.append(_row(base, status="MISSING", reason="EXPOSED_CALCULATOR_FAILED"))
            continue
        if len(calculated) != len(bars) or not any(
            x is not None and math.isfinite(x) for x in calculated
        ):
            rows.append(_row(base, status="MISSING", reason="NO_VALID_SIGNAL"))
        else:
            rows.append(
                _row(
                    base,
                    status="SUPPORTED_AND_EXECUTABLE",
                    reason="VERIFIED_PROVIDER_DEVELOPMENT_SIGNAL",
                    llm_exposed=True,
                    calculation_observed=True,
                )
            )
    return tuple(rows)
