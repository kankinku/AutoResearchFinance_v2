"""Opt-in research-only selection of externally VERIFIED inherited parent candidates.

This is an ex-post robustness sidecar, NOT an OOS promotion gate. It leaves
the existing counted parent selection unchanged until the academic checkpoint
workflow explicitly opts in, replays each candidate's full evidence, and
records the resulting selection receipt. It does not write to either ledger.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from math import isfinite
from statistics import median
from typing import Any, Literal, cast

from core.integrity.hashes import content_hash
from research.indicator_engine.inherited_historical_robustness import InheritedRobustnessReport


class GeneralizationParentError(ValueError):
    """Missing, mixed or tampered source evidence blocks research selection."""


@dataclass(frozen=True)
class ParentRobustnessReview:
    source_generation: int
    strategy_hash: str
    source_evidence_hash: str
    effective_signal_hash: str
    full_audit_hash: str
    full_development_return: float
    full_development_mdd: float
    total_annual_completed_trades: int
    annual_periods: int
    worst_year_return: float
    worst_year_excess_vs_qqq: float
    median_year_excess_vs_qqq: float
    worst_year_mdd: float
    positive_years: int
    outperform_qqq_years: int
    year_set: tuple[int, ...]
    report_hash: str


@dataclass(frozen=True)
class GeneralizationParentChoice:
    chosen_generation: int
    chosen_strategy_hash: str
    lane_names: tuple[str, ...]
    lane_generations: tuple[int, ...]
    candidate_reviews: tuple[ParentRobustnessReview, ...]
    frontier_generations: tuple[int, ...]
    selection_hash: str
    status: Literal["EX_POST_DEVELOPMENT_SELECTION_ONLY"] = (
        "EX_POST_DEVELOPMENT_SELECTION_ONLY"
    )
    independent_oos_approved: Literal[False] = False
    broker_executable: Literal[False] = False
    candidate_promotable: Literal[False] = False


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _numeric(value: object, name: str) -> float:
    if type(value) not in (int, float):
        raise GeneralizationParentError(f"non-numeric {name}")
    number = float(cast(int | float, value))
    if not isfinite(number):
        raise GeneralizationParentError(f"non-finite {name}")
    return number


def _review(
    candidate: Mapping[str, Any], report: InheritedRobustnessReport
) -> ParentRobustnessReview:
    expected_digest = content_hash({
        "schema": "audited-inherited-ir-historical-v1",
        "full_audit_hash": report.full_audit_hash,
        "source_evidence_hash": report.source_evidence_hash,
        "source_data_hash": report.development_hash,
        "years": [x.year for x in report.periods],
        "periods": [asdict(x) for x in report.periods],
        "cutoff": report.cutoff_date,
        "oos_approved": False,
    })
    if (
        candidate.get("replay_verified") is not True
        or candidate.get("source_kind") != "COUNTED_GENERATION"
        or candidate.get("independent_oos_approved") is not False
        or candidate.get("broker_executable") is not False
        or report.status != "INHERITED_IR_EX_POST_DEVELOPMENT_ONLY"
        or report.independent_oos_approved is not False
        or report.broker_executable is not False
        or report.candidate_promotable is not False
        or candidate.get("successor_strategy_hash") != report.strategy_hash
        or candidate.get("source_evidence_hash") != report.source_evidence_hash
        or candidate.get("audit_hash") != report.full_audit_hash
        or not _valid_sha(report.report_hash)
        or not _valid_sha(report.development_hash)
        or report.report_hash != expected_digest
    ):
        raise GeneralizationParentError("parent provenance or OOS safety boundary mismatch")
    gen = candidate.get("source_generation")
    if type(gen) is not int or gen < 1:
        raise GeneralizationParentError("invalid counted candidate generation")
    signal = candidate.get("effective_signal_hash")
    if not isinstance(signal, str) or not signal:
        raise GeneralizationParentError("candidate has no effective signal")
    quality = candidate.get("parent_quality")
    if not isinstance(quality, dict):
        raise GeneralizationParentError("missing full-run parent quality")
    total = _numeric(quality.get("total_return"), "total_return")
    drawdown = _numeric(quality.get("max_drawdown"), "max_drawdown")
    if total <= -1 or not 0 <= drawdown <= 1:
        raise GeneralizationParentError("invalid full-run return/drawdown")
    periods = report.periods
    if len(periods) < 3:
        raise GeneralizationParentError("need three or more full historical years")
    years = tuple(period.year for period in periods)
    if years != tuple(sorted(set(years))):
        raise GeneralizationParentError("invalid annual observation order")
    if (
        any(period.year_end_coverage != "YEAR_END_OBSERVED" for period in periods)
        or any(period.trading_bars < 100 for period in periods)
    ):
        raise GeneralizationParentError("incomplete annual development window")
    excess = []
    actual = []
    md = []
    total_closings = 0
    for row in periods:
        if (
            row.initial_cash != 10_000
            or row.first_holdout_equity != row.initial_cash
            or row.completed_trades < 0
            or row.fill_count < row.completed_trades
            or row.trading_bars > 300
            or not _valid_sha(row.evaluation_hash)
            or not _valid_sha(row.benchmark_hash)
        ):
            raise GeneralizationParentError("invalid per-year cost/position evidence")
        ret = _numeric(row.total_return, "annual_return")
        qqq = _numeric(row.market_qqq_costed_return, "annual_benchmark")
        worst_mdd = _numeric(row.max_drawdown, "annual_drawdown")
        diff = _numeric(row.excess_costed_return, "excess")
        if (
            ret <= -1 or qqq <= -1 or not 0 <= worst_mdd <= 1
            or abs(diff - (ret - qqq)) > 1e-9
        ):
            raise GeneralizationParentError("annual metric / benchmark reconciliation failed")
        actual.append(ret)
        excess.append(diff)
        md.append(worst_mdd)
        total_closings += row.completed_trades
    if total_closings < 10:
        # This is a comparability diagnostic, not a claim of statistical
        # confidence: even 10 trades over five years can be very uncertain.
        raise GeneralizationParentError("insufficient completed annual trades")
    return ParentRobustnessReview(
        source_generation=gen,
        strategy_hash=report.strategy_hash,
        source_evidence_hash=report.source_evidence_hash,
        effective_signal_hash=signal,
        full_audit_hash=report.full_audit_hash,
        full_development_return=total,
        full_development_mdd=drawdown,
        total_annual_completed_trades=total_closings,
        annual_periods=len(periods),
        worst_year_return=min(actual),
        worst_year_excess_vs_qqq=min(excess),
        median_year_excess_vs_qqq=float(median(excess)),
        worst_year_mdd=max(md),
        positive_years=sum(r > 0 for r in actual),
        outperform_qqq_years=sum(r > 0 for r in excess),
        year_set=years,
        report_hash=report.report_hash,
    )


def _dominates(other: ParentRobustnessReview, current: ParentRobustnessReview) -> bool:
    other_values = (
        other.full_development_return,
        -other.full_development_mdd,
        other.worst_year_excess_vs_qqq,
        -other.worst_year_mdd,
    )
    current_values = (
        current.full_development_return,
        -current.full_development_mdd,
        current.worst_year_excess_vs_qqq,
        -current.worst_year_mdd,
    )
    return all(a >= b for a, b in zip(other_values, current_values, strict=True)) and any(
        a > b for a, b in zip(other_values, current_values, strict=True)
    )


def select_generalization_parent(
    candidates: Sequence[Mapping[str, Any]],
    reports: Mapping[str, InheritedRobustnessReport],
    *,
    next_generation: int,
) -> GeneralizationParentChoice:
    """Rotate audited growth/defense/consistency lanes on shared ex-post years.

    The caller supplies only counted parents after full canonical audit and
    chain verification. The report hash and strategy/evidence identities must
    match, but third-party evidence authenticity is NOT granted here.
    """
    if type(next_generation) is not int or next_generation < 2:
        raise GeneralizationParentError("invalid next generation")
    if not candidates:
        raise GeneralizationParentError("no verified candidate to select")
    reviews = []
    seen_signals: set[str] = set()
    for candidate in candidates:
        key = candidate.get("successor_strategy_hash")
        if not isinstance(key, str) or key not in reports:
            raise GeneralizationParentError("missing audited annual report")
        review = _review(candidate, reports[key])
        if review.effective_signal_hash in seen_signals:
            raise GeneralizationParentError("duplicate effective candidate signals")
        seen_signals.add(review.effective_signal_hash)
        reviews.append(review)
    baseline_years = reviews[0].year_set
    baseline_data = reports[reviews[0].strategy_hash].development_hash
    baseline_cutoff = reports[reviews[0].strategy_hash].cutoff_date
    if any(
        rev.year_set != baseline_years
        or reports[rev.strategy_hash].development_hash != baseline_data
        or reports[rev.strategy_hash].cutoff_date != baseline_cutoff
        for rev in reviews
    ):
        raise GeneralizationParentError("incomparable development years or market dataset")
    reviews.sort(key=lambda p: (p.source_generation, p.strategy_hash))
    frontier = [
        a for a in reviews
        if not any(_dominates(b, a) for b in reviews if b is not a)
    ]
    # Strictly deterministic ties, so equal-score runs don't change parents.
    lanes = (
        ("GROWTH", sorted(frontier, key=lambda x: (
            -x.full_development_return, x.full_development_mdd, x.source_generation))),
        ("DOWNSIDE", sorted(frontier, key=lambda x: (
            x.worst_year_mdd, -x.worst_year_excess_vs_qqq, x.source_generation))),
        ("CONSISTENCY", sorted(frontier, key=lambda x: (
            -x.worst_year_excess_vs_qqq, -x.median_year_excess_vs_qqq,
            -x.full_development_return, x.source_generation))),
    )
    picked: list[tuple[str, ParentRobustnessReview]] = []
    seen: set[str] = set()
    for name, ranked in lanes:
        for row in ranked:
            if row.effective_signal_hash not in seen:
                seen.add(row.effective_signal_hash)
                # When a better consistency candidate is already retained
                # in the growth/defense lane, the next distinct strategy is a
                # DIVERSITY allocation, NOT evidence of superior consistency.
                actual_lane = name if row is ranked[0] else "PARETO_DIVERSITY"
                picked.append((actual_lane, row))
                break
    selected = picked[(next_generation - 1) % len(picked)][1]
    body = {
        "schema": "counted-inherited-ex-post-parent-comparison-v1",
        "next_generation": next_generation,
        "dataset_hash": baseline_data,
        "cutoff": baseline_cutoff,
        "year_set": baseline_years,
        "chosen_generation": selected.source_generation,
        "chosen_strategy_hash": selected.strategy_hash,
        "lanes": [(name, row.source_generation) for name, row in picked],
        "frontier_generations": [r.source_generation for r in frontier],
        "candidate_reviews": [asdict(r) for r in reviews],
        "oos_approved": False,
    }
    return GeneralizationParentChoice(
        chosen_generation=selected.source_generation,
        chosen_strategy_hash=selected.strategy_hash,
        lane_names=tuple(n for n, _ in picked),
        lane_generations=tuple(r.source_generation for _, r in picked),
        candidate_reviews=tuple(reviews),
        frontier_generations=tuple(r.source_generation for r in frontier),
        selection_hash=content_hash(body),
    )
