"""Isolated V3 crossover verification: canonical S2, P2 and S7; no orders.

Donor CompiledAcademicStrategy objects must originate from evidence-verified
research checkout. This layer independently replays their costed signals and
checks genome role/component hashes, not remote-provider attestation or OOS.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from core.backtest.p2_policy import ChildRiskBudget, assess_child_risk
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.controlled_experiments import ControlledExperimentReport
from research.indicator_engine.decision_audit import AcademicDecisionAudit
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.inherited_experiments import compare_inherited_experiments
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy
from research.llm.composite_crossover_v3 import (
    CompositeCandidate,
    VerifiedDonor,
    donor_parent_ids,
)


class CompositeValidationError(ValueError):
    """A genetic experiment is unauditable or fails its declared risk budget."""


@dataclass(frozen=True)
class CompositeValidationResult:
    audit: AcademicDecisionAudit
    p2_review: dict[str, float | int | bool | str]
    s7: ControlledExperimentReport | None
    component_audit_hashes: tuple[str, ...]
    source_genome_hash: str
    dev_only: bool = True
    independent_oos: bool = False
    broker_executable: bool = False


def validate_composite(
    candidate: CompositeCandidate,
    verified_source_compilations: Mapping[str, CompiledAcademicStrategy],
    market: MarketDataSet,
    *,
    budget: ChildRiskBudget,
    diagnosis: dict[str, object] | None = None,
) -> CompositeValidationResult:
    """Costed, independently traced crossover; risk-rejected candidates cannot pass.

    All donors are independently canonical-audited. No user-supplied 'passed'
    result can replace actual fills. This does not commit research generations.
    """
    if market.zone != DataZone.DEVELOPMENT or not candidate.genome_hash:
        raise CompositeValidationError("invalid development-only crossover")
    if (
        content_hash(candidate.provenance) != candidate.genome_hash
        or candidate.strategy.provenance.source_hash != candidate.genome_hash
        or candidate.provenance.get("schema") != "composite-genome-v3"
    ):
        raise CompositeValidationError("crossover lineage provenance mismatch")
    roles = candidate.provenance.get("lineage")
    if not isinstance(roles, list) or set(candidate.donor_roles) != {
        item.get("role") for item in roles if isinstance(item, dict)
    }:
        raise CompositeValidationError("crossover donor role identity mismatch")

    verified_compiled: dict[str, CompiledAcademicStrategy] = {}
    hashes: list[str] = []
    for proof in roles:
        if not isinstance(proof, dict):
            raise CompositeValidationError("invalid donor proof")
        role = proof["role"]
        sha = proof["source_strategy_hash"]
        parent = verified_source_compilations.get(sha)
        if (
            parent is None
            or parent.strategy_hash != sha
            or content_hash(parent.strategy.model_dump(mode="json", by_alias=True)) != sha
            or parent.strategy.strategy_id != proof["source_strategy_id"]
            # The counted source generation may differ from a legacy IR base generation.
        ):
            raise CompositeValidationError("unverified donor strategy identity")
        component: Any = getattr(parent.strategy, role if role != "regime" else "regime_filters")
        if isinstance(component, list):
            serialized: Any = [part.model_dump(mode="json") for part in component]
        else:
            serialized = component.model_dump(mode="json")
        if content_hash(serialized) != proof["component_hash"]:
            raise CompositeValidationError("donor component hash mismatch")
        if role in verified_compiled:
            raise CompositeValidationError("duplicate donor role")
        verified_compiled[role] = parent

    if not {"entry", "exit", "risk"}.issubset(verified_compiled):
        raise CompositeValidationError("missing required donors")
    # Donor hashes alone are not sufficient: verify that the ACTUAL compiled
    # child still contains each independently audited donated component.
    for role in ("entry", "exit", "risk"):
        expected = getattr(verified_compiled[role].strategy, role)
        observed = getattr(candidate.strategy, role)
        if expected != observed:
            raise CompositeValidationError(f"crossover {role} component diverged")
    regime_parent = verified_compiled.get("regime", verified_compiled["entry"])
    if candidate.strategy.regime_filters != regime_parent.strategy.regime_filters:
        raise CompositeValidationError("crossover regime component diverged")
    known_indicators: dict[str, object] = {}
    known_features: dict[str, object] = {}
    for donor in verified_compiled.values():
        for name, spec in donor.strategy.indicators.items():
            if name in known_indicators and known_indicators[name] != spec:
                raise CompositeValidationError("donor indicator alias conflict")
            known_indicators[name] = spec
        for name, feature in donor.strategy.features.items():
            if name in known_features and known_features[name] != feature:
                raise CompositeValidationError("donor feature alias conflict")
            known_features[name] = feature
    if (
        candidate.strategy.indicators != known_indicators
        or candidate.strategy.features != known_features
    ):
        raise CompositeValidationError("crossover feature/indicator component diverged")
    if tuple(dict.fromkeys(p["source_strategy_hash"] for p in roles)) != candidate.source_hashes:
        raise CompositeValidationError("donor set differs from genome")
    expected_parents = donor_parent_ids(tuple(
        VerifiedDonor(
            generation=proof["source_generation"],
            evidence_hash=proof["source_evidence_hash"],
            report_hash=proof["source_report_hash"],
            strategy=verified_compiled[proof["role"]].strategy,
            strategy_hash=proof["source_strategy_hash"],
            replay_verified=True,
        )
        for proof in roles
    ))
    if candidate.strategy.parents != expected_parents:
        raise CompositeValidationError("crossover parent strategy IDs changed")

    entry = verified_compiled["entry"]
    # S2-audit every distinct source against the exact same completed-bar
    # market before merging its independently checked signal vectors.
    union: dict[str, tuple[float | None, ...]] = {}
    source_replay_hashes: list[str] = []
    for parent in verified_compiled.values():
        if parent.dataset_hash != market.dataset_hash:
            raise CompositeValidationError("donor dataset mismatch")
        checked = audit_inherited_decisions(parent, market)
        hashes.append(checked.trace_hash)
        source_replay_hashes.append(parent.replay.replay_hash)
        for alias, series in parent.feature_values.items():
            if alias in union and union[alias] != series:
                raise CompositeValidationError("conflicting donor feature values")
            union[alias] = series
    if set(candidate.strategy.features) != set(union):
        raise CompositeValidationError("crossover feature vectors are not registered")
    from research.indicator_engine.bridge import ResearchSignalReplay

    # Preserve legacy evidence identity if all donors truly used one audited
    # source replay; otherwise derive a new union replay keyed to the genome.
    if all(parent.replay == entry.replay for parent in verified_compiled.values()):
        hypothesis_hash = entry.hypothesis_hash
        replay = entry.replay
        feature_values = entry.feature_values
    else:
        timestamps = tuple(bar.timestamp for bar in market.bars)
        next_bar = timestamps[1:] + (None,)
        hypothesis_hash = content_hash({
            "schema": "composite-replay-v3",
            "genome": candidate.genome_hash,
            "donors": source_replay_hashes,
            "market": market.dataset_hash,
        })
        signals = tuple(sorted(union.items()))
        replay_body = {
            "hypothesis": hypothesis_hash,
            "dataset": market.dataset_hash,
            "signals": signals,
            "decision_timestamps": [t.isoformat() for t in timestamps],
            "earliest_next_bar": [t.isoformat() if t else None for t in next_bar],
            "research_only": True,
        }
        replay = ResearchSignalReplay(
            hypothesis_hash=hypothesis_hash,
            data_hash=market.dataset_hash,
            signals=signals,
            timestamps=timestamps,
            execution_not_before=next_bar,
            entry_regime_observations=0,
            replay_hash=content_hash(replay_body),
        )
        feature_values = dict(signals)
    original = audit_inherited_decisions(entry, market)
    compiled_child = replace(
        entry,
        hypothesis_hash=hypothesis_hash,
        replay=replay,
        feature_values=feature_values,
        strategy=candidate.strategy,
        strategy_hash=content_hash(candidate.strategy.model_dump(mode="json", by_alias=True)),
    )
    child = audit_inherited_decisions(compiled_child, market)
    review = assess_child_risk(
        parent_equity=original.evaluation.equity_curve,
        child_equity=child.evaluation.equity_curve,
        child_closed_trades=len(child.round_trips),
        budget=budget,
    )
    if not review["eligible"]:
        raise CompositeValidationError("crossover risk gate rejected")
    report = (
        compare_inherited_experiments(
            compiled_child, market, diagnosis,
            parent_proof_hash=candidate.genome_hash,
        )
        if diagnosis is not None
        else None
    )
    if report is not None and report.audit_hash != child.trace_hash:
        raise CompositeValidationError("S7 composite audit proof mismatch")
    return CompositeValidationResult(
        audit=child,
        p2_review=review,
        s7=report,
        component_audit_hashes=tuple(hashes),
        source_genome_hash=candidate.genome_hash,
    )
