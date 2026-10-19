"""F1: read-only, development-only profiles of *audited* feature observations.

Only feature values observed by the canonical decision audit are profiled.
No registry promotion, future feature engineering, claims about true positives,
causal attribution, model training, strategy execution or trading permissions.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from math import isclose, isfinite
from typing import Any

from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.decision_audit import AcademicDecisionAudit
from research.indicator_engine.signals import calculate_signal
from research.llm.loss_attribution import LossAttributionError, _checked
from research.llm.trade_cohort_review import _entry_regime


class FeatureProfileError(ValueError):
    """Untrusted market/audit observations must not become research advice."""


def build_feature_evidence_profiles(
    audit: AcademicDecisionAudit,
    market: MarketDataSet,
    feature_ids: tuple[str, ...],
    *,
    min_per_outcome: int = 5,
    threshold: float = 0.5,
    max_examples: int = 12,
    _verified_vectors: dict[str, tuple[float | None, ...]] | None = None,
    _verified_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize actual pre-entry observations, not counterfactual feature utility.

    WIN/LOSS and holding-time labels are retrospective and NEVER signal inputs.
    A high win/loss rate conditional on a recorded feature is not proof that
    imposing a new filter improves whole-portfolio costed equity.
    """
    if (
        type(feature_ids) is not tuple
        or not 1 <= len(feature_ids) <= 5
        or any(type(name) is not str or not name or len(name) > 100 for name in feature_ids)
        or len(set(feature_ids)) != len(feature_ids)
        or type(min_per_outcome) is not int
        or not 1 <= min_per_outcome <= 100
        or type(max_examples) is not int
        or not 1 <= max_examples <= 30
        or type(threshold) not in (int, float)
        or not isfinite(threshold)
    ):
        raise FeatureProfileError("invalid bounded F1 profile request")
    try:
        _checked(audit, market)
    except (LossAttributionError, ValueError) as exc:
        raise FeatureProfileError("unverified audit/market evidence") from exc
    if len(audit.round_trips) > 5000:
        raise FeatureProfileError("unbounded trade observations")
    snapshots = [dict(d.indicator_values) for d in audit.decisions]
    available = set(snapshots[0])
    if any(set(row) != available for row in snapshots):
        raise FeatureProfileError("unaligned audit signal observations")
    if _verified_vectors is not None:
        if (
            _verified_metadata is None
            or set(_verified_vectors) != set(_verified_metadata)
            or set(_verified_vectors) != set(feature_ids)
        ):
            raise FeatureProfileError("invalid verified-source identity")
        for name, vector in _verified_vectors.items():
            if len(vector) != len(snapshots):
                raise FeatureProfileError("verified vector is not bar aligned")
            for row, value in zip(snapshots, vector, strict=True):
                if name in row:
                    recorded = row[name]
                    if (recorded is None) != (value is None) or (
                        recorded is not None
                        and value is not None
                        and not isclose(recorded, value, rel_tol=1e-9, abs_tol=1e-12)
                    ):
                        raise FeatureProfileError("verified calculation mismatches audit")
                else:
                    row[name] = value
        available |= set(_verified_vectors)
    if not set(feature_ids) <= available:
        raise FeatureProfileError("feature not present in audited or verified observations")
    if any(
        value is not None and (type(value) not in (float, int) or not isfinite(value))
        for row in snapshots
        for value in row.values()
    ):
        raise FeatureProfileError("invalid signed feature observation")
    by_id = {d.decision_id: d for d in audit.decisions}
    if len(by_id) != len(audit.decisions):
        raise FeatureProfileError("duplicate source decision identity")

    outcomes: list[tuple[str, str, str, str, str, str, float]] = []
    for closed in audit.round_trips:
        entry = by_id.get(closed.entry_fill.decision_id)
        if entry is None or entry.action != "REQUEST_ENTRY":
            raise FeatureProfileError("missing executed entry decision")
        if not entry.signal_time < closed.entry_fill.execution_time:
            raise FeatureProfileError("feature not available before execution")
        trend, vol = _entry_regime(market, entry.bar_index)
        kind = "WIN" if closed.net_pnl > 0 else "LOSS" if closed.net_pnl < 0 else "FLAT"
        outcomes.append(
            (
                kind,
                closed.trade_id,
                entry.decision_id,
                entry.signal_time.isoformat(),
                closed.entry_fill.execution_time.isoformat(),
                trend + "/" + vol,
                closed.net_pnl,
            )
        )

    def _positive(v: float | None) -> bool:
        assert v is not None
        return v > threshold

    profiles: list[dict[str, Any]] = []
    for name in feature_ids:
        vals = [row[name] for row in snapshots]
        observed = [float(x) for x in vals if x is not None]
        is_binary = all(x in (0.0, 1.0) for x in observed)
        transitions = (
            sum(
                _positive(vals[k]) != _positive(vals[k - 1])
                for k in range(1, len(vals))
                if vals[k] is not None and vals[k - 1] is not None
            )
            if is_binary
            else None
        )
        outcome_counts: Counter[str] = Counter()
        signal_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
        cohort_counts: dict[str, Counter[str]] = defaultdict(Counter)
        regime_signal_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        examples: list[dict[str, Any]] = []
        for kind, trade_id, did, signal_time, execution_time, regime, pnl in outcomes:
            value = snapshots[by_id[did].bar_index][name]
            outcome_counts[kind] += 1
            cohort_counts[regime][kind] += 1
            signal_state = (
                "MISSING"
                if value is None
                else "POSITIVE"
                if is_binary and value > threshold
                else "NON_POSITIVE"
                if is_binary
                else "CONTINUOUS"
            )
            signal_outcomes[signal_state][kind] += 1
            regime_signal_counts[(regime, signal_state)][kind] += 1
            if len(examples) < max_examples and (kind != "FLAT"):
                examples.append(
                    {
                        "outcome": kind,
                        "trade_id": trade_id,
                        "source_decision_id": did,
                        "signal_time": signal_time,
                        "first_fill_time": execution_time,
                        "observed_value": value,
                        "net_pnl_after_costs": pnl,
                        "entry_regime": regime,
                    }
                )
        no_entry = [
            d for d in audit.decisions if d.action in ("NO_ENTRY_SIGNAL", "FILTERED_REGIME")
        ]
        no_entry_examples = [
            {
                "decision_id": d.decision_id,
                "signal_time": d.signal_time.isoformat(),
                "action": d.action,
                "observed_value": snapshots[d.bar_index][name],
            }
            for d in no_entry[:max_examples]
        ]
        regimes = [
            {
                "regime": regime,
                "wins": counter["WIN"],
                "losses": counter["LOSS"],
                "flats": counter["FLAT"],
                "insufficient_for_inference": (
                    counter["WIN"] < min_per_outcome or counter["LOSS"] < min_per_outcome
                ),
            }
            for regime, counter in sorted(cohort_counts.items())
        ]
        conditional = [
            {
                "regime": regime,
                "observed_signal_state": state,
                "wins": counts["WIN"],
                "losses": counts["LOSS"],
                "flats": counts["FLAT"],
                "insufficient_for_inference": (
                    counts["WIN"] < min_per_outcome or counts["LOSS"] < min_per_outcome
                ),
            }
            for (regime, state), counts in sorted(regime_signal_counts.items())
        ]
        counts = {
            "winning_entry_count": outcome_counts["WIN"],
            "losing_entry_count": outcome_counts["LOSS"],
            "flat_entry_count": outcome_counts["FLAT"],
        }
        body: dict[str, Any] = {
            "feature_id": name,
            "source_strategy_hash": audit.evaluation.strategy_hash,
            "source_audit_hash": audit.trace_hash,
            "dataset_hash": market.dataset_hash,
            "symbol": audit.decisions[0].symbol,
            "timeframe": market.timeframe,
            "source_vector_hash": content_hash(vals),
            "formula_provenance_status": (
                "VERIFIED_ACADEMIC_CALCULATOR_REFERENCE"
                if _verified_metadata is not None
                else "AUDIT_VECTOR_ONLY"
            ),
            "formula_metadata": (
                _verified_metadata[name] if _verified_metadata is not None else None
            ),
            "role_claim": "UNSPECIFIED_OBSERVED_SIGNAL",
            "signal_asof": "BAR_CLOSE_BEFORE_NEXT_OPEN",
            "signal_observation_count": len(observed),
            "missing_count": len(vals) - len(observed),
            "binary_signal": is_binary,
            "binary_threshold": threshold if is_binary else None,
            "binary_transition_count": transitions,
            "entry_outcomes_by_observed_signal": [
                {
                    "signal_state": state,
                    "wins": counts["WIN"],
                    "losses": counts["LOSS"],
                    "flats": counts["FLAT"],
                    "insufficient_for_inference": (
                        counts["WIN"] < min_per_outcome or counts["LOSS"] < min_per_outcome
                    ),
                }
                for state, counts in sorted(signal_outcomes.items())
            ],
            "signal_conditioned_regime_counts": conditional,
            "observed_mean": sum(observed) / len(observed) if observed else None,
            "observed_min": min(observed) if observed else None,
            "observed_max": max(observed) if observed else None,
            "no_entry_decision_count": len(no_entry),
            "no_entry_decision_examples": no_entry_examples,
            **counts,
            "regime_counts": regimes,
            "regime_observations": examples,
            "evidence_status": (
                "OBSERVED_NON_CAUSAL"
                if outcome_counts["WIN"] >= min_per_outcome
                and outcome_counts["LOSS"] >= min_per_outcome
                else "OBSERVED_INSUFFICIENT_SAMPLE"
            ),
            "advantages_not_proven": True,
            "limitations_not_proven": True,
            "outcomes_are_ex_post_labels": True,
            "not_a_feature_selection_score": True,
            "independent_oos_approved": False,
            "broker_executable": False,
        }
        profiles.append({**body, "profile_hash": content_hash(body)})

    # Pairwise agreement is descriptive ONLY for binary audited signals.
    agreement = []
    for i, a in enumerate(profiles):
        for b in profiles[i + 1 :]:
            x = [v[a["feature_id"]] for v in snapshots]
            y = [v[b["feature_id"]] for v in snapshots]
            overlap = [(u, v) for u, v in zip(x, y, strict=True) if u is not None and v is not None]
            agreement.append(
                {
                    "left": a["feature_id"],
                    "right": b["feature_id"],
                    "overlap_count": len(overlap),
                    "binary_signal_agreement": (
                        sum(u == v for u, v in overlap) / len(overlap)
                        if a["binary_signal"] and b["binary_signal"] and overlap
                        else None
                    ),
                    "incremental_information_not_established": True,
                }
            )
    report = {
        "schema": "feature-evidence-profile-f1-v1",
        "source_audit_hash": audit.trace_hash,
        "strategy_hash": audit.evaluation.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "coverage_scope": (
            "VERIFIED_ACADEMIC_REFERENCE_AND_AUDITED_OUTCOMES"
            if _verified_vectors is not None
            else "AUDITED_REPLAY_SIGNALS_ONLY"
        ),
        "profiles": profiles,
        "pairwise_observation_agreement": agreement,
        "validation_scope": "REUSED_DEVELOPMENT_ONLY",
        "causal_status": "NOT_ESTABLISHED",
        "point_in_time_verified": False,
        "independent_oos_approved": False,
        "broker_executable": False,
    }
    return {**report, "evidence_hash": content_hash(report)}


def build_verified_catalog_feature_profiles(
    catalog: ResearchCatalog,
    audit: AcademicDecisionAudit,
    market: MarketDataSet,
    feature_ids: tuple[str, ...],
    *,
    min_per_outcome: int = 5,
    max_examples: int = 8,
) -> dict[str, Any]:
    """Profile 1-5 *verified* academic OHLCV calculators against audited entries.

    Values are derived only from completed data bars. Their formula identity is
    stored separately from the audit's signed decision values; this analysis
    cannot change any entry or execution in the original canonical backtest.
    """
    if (
        type(feature_ids) is not tuple
        or not 1 <= len(feature_ids) <= 5
        or len(set(feature_ids)) != len(feature_ids)
        or any(type(name) is not str or not name for name in feature_ids)
        or market.timeframe != "1d"
        or len({bar.symbol for bar in market.bars}) != 1
    ):
        raise FeatureProfileError("invalid verified-feature scope")
    raw = {
        name: tuple(float(getattr(bar, name)) for bar in market.bars)
        for name in ("open", "high", "low", "close", "volume")
    }
    calculated: dict[str, tuple[float | None, ...]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for name in feature_ids:
        try:
            signal = catalog.get_indicator(name)
        except (ResearchCatalogError, ValueError) as exc:
            raise FeatureProfileError("feature absent from verified catalog") from exc
        if signal.status != "VERIFIED" or signal.scope != "single_asset":
            raise FeatureProfileError("unverified or unsupported indicator cannot be profiled")
        try:
            vector = calculate_signal(signal, raw)
            # Prefix checks prove the *chosen signal* is not affected by future
            # bars at representative dates; they do not verify vendor PIT as-of.
            check_indices = sorted(
                {0, min(signal.lookback, len(vector) - 1), len(vector) // 2, len(vector) - 1}
            )
            for i in check_indices:
                prefix = {
                    field: series[: i + 1]
                    for field, series in raw.items()
                    if field in signal.required_fields
                }
                if calculate_signal(signal, prefix)[i] != vector[i]:
                    raise FeatureProfileError("catalog calculator uses future data")
        except (ValueError, ArithmeticError) as exc:
            raise FeatureProfileError("invalid causal academic calculation") from exc
        calculated[name] = vector
        metadata[name] = {
            "candidate_hash": content_hash(signal.model_dump(mode="json")),
            "calculator": signal.calculator,
            "lookback": signal.lookback,
            "required_fields": signal.required_fields,
            "formula": signal.formula,
            "verification_scope": "SYNTHETIC_REFERENCE_VERIFIED_NOT_INDEPENDENT_PIT",
            "license_attested": False,
        }
    return build_feature_evidence_profiles(
        audit,
        market,
        feature_ids,
        min_per_outcome=min_per_outcome,
        max_examples=max_examples,
        _verified_vectors=calculated,
        _verified_metadata=metadata,
    )
