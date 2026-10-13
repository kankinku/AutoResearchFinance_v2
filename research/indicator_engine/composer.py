"""Build non-executable, bounded research hypotheses from eligible signals only.

This never emits StrategyIR / executable orders. Translation to existing
canonical StrategyIR requires an independent adapter + evaluation gate.
"""

from __future__ import annotations

from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.models import IndicatorCandidate, ResearchHypothesis


def compose_hypotheses(
    catalog: ResearchCatalog,
    *,
    signal_ids: tuple[str, ...],
    max_results: int = 100,
) -> tuple[ResearchHypothesis, ...]:
    if not 1 <= max_results <= 10_000:
        raise ValueError("max_results must be between 1 and 10000")
    if not 1 <= len(signal_ids) <= 256:
        raise ValueError("signal_ids must have 1-256 entries")
    if len(set(signal_ids)) != len(signal_ids):
        raise ValueError("repeated source IDs cannot be combined")

    choices: list[IndicatorCandidate] = []
    for name in sorted(signal_ids):
        signal = catalog.get_indicator(name)
        if signal.status != "VERIFIED":
            raise ResearchCatalogError("unverified indicator cannot enter composer")
        if signal.scope != "single_asset" or signal.execution_delay_bars < 1:
            raise ResearchCatalogError("missing aligned, next-bar-safe research capability")
        choices.append(signal)

    by_role = {
        role: sorted((s for s in choices if s.role == role), key=lambda s: s.signal_id)
        for role in ("entry", "regime", "risk")
    }
    results: dict[str, ResearchHypothesis] = {}
    # Require the entry and market-regime signals to have independent roles.
    # Risk overlay is optional; never permit two correlated 'entry' signals
    # masquerading as diversification.
    for entry in by_role["entry"]:
        for regime in by_role["regime"]:
            for risk in (None, *by_role["risk"]):
                members = (entry, regime) if risk is None else (entry, regime, risk)
                identities = tuple(item.signal_id for item in members)
                roles = tuple(item.role for item in members)
                identity_hash = content_hash(
                    {
                        "signal_ids": identities,
                        "roles": roles,
                        "scope": "single_asset",
                        "execution_delay_bars": 1,
                        "version": 1,
                    }
                )
                results[identity_hash] = ResearchHypothesis(
                    signal_ids=identities, roles=roles, identity_hash=identity_hash
                )
                if len(results) >= max_results:
                    return tuple(results[key] for key in sorted(results))
    return tuple(results[key] for key in sorted(results))
