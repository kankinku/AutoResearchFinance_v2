"""Typed V3 parent-component crossover, research-only and fail-closed.

This does not bypass canonical backtest/S2/P2/S7, certify a donor's origin,
or change the historical StrategyIR schema. The caller must verify each
donor against its immutable stored evidence before constructing a candidate.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from core.integrity.hashes import content_hash
from strategy_ir.schema import StrategyIR


class CrossoverRejected(ValueError):
    """Donor lineage, feature vocabulary, or IR was incompatible."""


@dataclass(frozen=True)
class VerifiedDonor:
    generation: int
    evidence_hash: str
    report_hash: str
    strategy: StrategyIR
    strategy_hash: str
    replay_verified: bool


@dataclass(frozen=True)
class CompositeCandidate:
    strategy: StrategyIR
    genome_hash: str
    source_hashes: tuple[str, ...]
    donor_roles: tuple[str, ...]
    provenance: dict[str, Any]
    # Candidate composition is not approval to trade or read OOS.
    broker_executable: bool = False
    independent_oos_approved: bool = False


def _check_donor(donor: VerifiedDonor) -> None:
    if donor.replay_verified is not True:
        raise CrossoverRejected("donor is missing verified replay")
    if (
        type(donor.generation) is not int
        or donor.generation < 1
        or donor.strategy.generation < 0
        # Historical counted children can retain the BASE StrategyIR generation;
        # the source ledger generation is separately bound by donor evidence.
    ):
        raise CrossoverRejected("donor generation mismatch")
    for digest in (donor.evidence_hash, donor.report_hash, donor.strategy_hash):
        if len(digest) != 64 or any(x not in "0123456789abcdef" for x in digest):
            raise CrossoverRejected("invalid donor lineage hash")
    observed = content_hash(donor.strategy.model_dump(mode="json", by_alias=True))
    if donor.strategy_hash != observed:
        raise CrossoverRejected("donor strategy hash mismatch")


def _merged_definitions(donors: tuple[VerifiedDonor, ...], name: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for donor in donors:
        definitions = getattr(donor.strategy, name)
        for alias, spec in definitions.items():
            if alias in result and result[alias] != spec:
                kind = "indicator" if name == "indicators" else "feature"
                raise CrossoverRejected(f"conflicting {kind} alias: {alias}")
            result[alias] = spec
    return result


def donor_parent_ids(donors: tuple[VerifiedDonor, ...]) -> list[str]:
    """Retain distinct counted ancestors even if historical IR IDs were reused."""
    unique: dict[str, VerifiedDonor] = {}
    for donor in donors:
        unique.setdefault(donor.strategy_hash, donor)
    counts = Counter(d.strategy.strategy_id for d in unique.values())
    return [
        (
            f"{d.strategy.strategy_id}@G{d.generation}-{d.strategy_hash[:12]}"
            if counts[d.strategy.strategy_id] > 1
            else d.strategy.strategy_id
        )
        for d in unique.values()
    ]


def _component_hash(role: str, donor: VerifiedDonor) -> str:
    components: dict[str, Any] = {
        "entry": donor.strategy.entry,
        "exit": donor.strategy.exit,
        "risk": donor.strategy.risk,
        "regime": donor.strategy.regime_filters,
    }
    item = components[role]
    if isinstance(item, list):
        return content_hash([condition.model_dump(mode="json") for condition in item])
    return content_hash(item.model_dump(mode="json"))


def compose(
    *,
    entry: VerifiedDonor,
    exit: VerifiedDonor,
    risk: VerifiedDonor,
    regime: VerifiedDonor | None = None,
) -> CompositeCandidate:
    """Create a canonical executable StrategyIR with auditable donor roles.

    A 2/3-parent genome inherits entry, exit and risk as real strategy fields.
    An optional fourth donor supplies regime filters, but not stateful routing.
    Identifier collisions with different definitions fail closed for now.
    """
    roles = {"entry": entry, "exit": exit, "risk": risk}
    if regime is not None:
        roles["regime"] = regime
    for donor in roles.values():
        _check_donor(donor)
    distinct: dict[str, VerifiedDonor] = {}
    for donor in roles.values():
        distinct.setdefault(donor.strategy_hash, donor)
    if len(distinct) < 2:
        raise CrossoverRejected("crossover requires at least two distinct parents")

    ordered = tuple(distinct.values())
    indicators = _merged_definitions(ordered, "indicators")
    features = _merged_definitions(ordered, "features")
    lineage = [
        {
            "role": role,
            "source_generation": donor.generation,
            "source_strategy_id": donor.strategy.strategy_id,
            "source_strategy_hash": donor.strategy_hash,
            "source_evidence_hash": donor.evidence_hash,
            "source_report_hash": donor.report_hash,
            "component_hash": _component_hash(role, donor),
        }
        for role, donor in roles.items()
    ]
    manifest = {"schema": "composite-genome-v3", "lineage": lineage}
    genome_hash = content_hash(manifest)
    original = entry.strategy.model_dump(mode="json", by_alias=False)
    original.update({
        "strategy_id": "cross_v3_" + genome_hash[:20],
        "family": "research_composite_v3",
        "generation": max(d.generation for d in ordered) + 1,
        "parents": donor_parent_ids(ordered),
        "indicators": {k: v.model_dump(mode="json") for k, v in indicators.items()},
        "features": {k: v.model_dump(mode="json") for k, v in features.items()},
        "entry": entry.strategy.entry.model_dump(mode="json"),
        "exit": exit.strategy.exit.model_dump(mode="json"),
        "risk": risk.strategy.risk.model_dump(mode="json"),
        "regime_filters": [
            c.model_dump(mode="json")
            for c in (regime.strategy if regime is not None else entry.strategy).regime_filters
        ],
        "research": {"mutation": [f"CROSSOVER_V3:{r}" for r in roles]},
        "provenance": {
            "source_type": "research-verified-crossover-v3",
            "source_path": "research.llm.composite_crossover_v3",
            "source_hash": genome_hash,
        },
    })
    candidate = StrategyIR.model_validate(original)
    return CompositeCandidate(
        strategy=candidate,
        genome_hash=genome_hash,
        source_hashes=tuple(d.strategy_hash for d in ordered),
        donor_roles=tuple(roles),
        provenance=manifest,
    )


def mutate_composite(candidate: CompositeCandidate, intent: Any) -> CompositeCandidate:
    """Apply the existing typed ResearchIntent bridge after a verified crossover.

    The emitted composite remains a development research candidate; the caller
    must run canonical S2/P2/S7 before any counted parent promotion.
    """
    from core.features.registry import research_feature_specs
    from research.llm.director import ResearchIntent
    from research.llm.intent_bridge import apply_intent

    if candidate.genome_hash != content_hash(candidate.provenance):
        raise CrossoverRejected("crossover provenance hash mismatch")
    if candidate.strategy.provenance.source_hash != candidate.genome_hash:
        raise CrossoverRejected("crossover strategy provenance mismatch")
    if not isinstance(intent, ResearchIntent):
        raise CrossoverRejected("typed ResearchIntent is required")
    descendant = apply_intent(candidate.strategy, intent, research_feature_specs())
    manifest = {
        "schema": "composite-genome-v3-mutation",
        "base_genome_hash": candidate.genome_hash,
        "donor_lineage": candidate.provenance["lineage"],
        "mutation_intent_hash": content_hash(intent.model_dump(mode="json")),
        "child_strategy_hash": content_hash(descendant.model_dump(mode="json", by_alias=True)),
    }
    genome_hash = content_hash(manifest)
    updated = descendant.model_dump(mode="json", by_alias=False)
    updated["provenance"]["source_hash"] = genome_hash
    strategy = StrategyIR.model_validate(updated)
    return CompositeCandidate(
        strategy=strategy,
        genome_hash=genome_hash,
        source_hashes=candidate.source_hashes,
        donor_roles=candidate.donor_roles,
        provenance=manifest,
    )
