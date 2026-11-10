"""Isolated Track2 diagnostic prototype. NEVER a strategy, order, or OOS access.

Warnings depend only on already available registered features.
Event labels and accuracy metrics are computed offline, after observations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from math import isfinite
from statistics import mean, median, pstdev
from typing import Literal

from core.features.calculators import calculate_feature
from core.features.registry import default_feature_registry
from core.integrity.hashes import content_hash


class EventStudyError(ValueError):
    """Reject unsafe or unreviewed event-research inputs."""


EventKind = Literal["CRASH", "REBOUND", "VOL_SPIKE"]


@dataclass(frozen=True)
class EventStudy:
    """Explicit example settings, not user-approved market thresholds."""

    kind: EventKind
    label_window: int
    threshold: float
    min_lead_bars: int
    max_lead_bars: int
    warning_budget_per_year: int
    alert_score_threshold: float
    cooldown_bars: int
    min_confirmed_events: int

    def __post_init__(self) -> None:
        if self.kind not in {"CRASH", "REBOUND", "VOL_SPIKE"}:
            raise EventStudyError("invalid event type")
        integers = (
            self.label_window, self.min_lead_bars, self.max_lead_bars,
            self.warning_budget_per_year, self.cooldown_bars, self.min_confirmed_events,
        )
        if any(type(x) is not int for x in integers):
            raise EventStudyError("integer event-study parameters required")
        if (
            self.label_window < 1 or self.min_lead_bars < 1
            or self.max_lead_bars < self.min_lead_bars
            or self.warning_budget_per_year < 1 or self.cooldown_bars < 0
            or self.min_confirmed_events < 1
        ):
            raise EventStudyError("invalid event study horizon, warning budget or cooldown")
        if (
            type(self.threshold) not in {float, int}
            or not isfinite(float(self.threshold))
            or self.threshold <= 0
            or (self.kind in {"CRASH", "REBOUND"} and self.threshold >= 1)
            or type(self.alert_score_threshold) not in {float, int}
            or not isfinite(float(self.alert_score_threshold))
            or self.alert_score_threshold < 0
        ):
            raise EventStudyError("positive finite event magnitude and score cutoff required")


def _validate_prices(prices: Sequence[float]) -> None:
    if any(
        type(p) not in {float, int} or not isfinite(float(p)) or p <= 0
        for p in prices
    ):
        raise EventStudyError("strictly positive finite close prices required")


def _daily_returns(prices: Sequence[float]) -> tuple[float, ...]:
    return tuple(prices[i] / prices[i - 1] - 1 for i in range(1, len(prices)))


def label_event_onsets(prices: Sequence[float], study: EventStudy) -> tuple[int, ...]:
    """Ex-post event onset indices; never feed these labels into the signal."""
    _validate_prices(prices)
    window = study.label_window
    returns = _daily_returns(prices)

    def crossed(i: int) -> bool:
        if i < (2 * window if study.kind != "CRASH" else window):
            return False
        if study.kind == "CRASH":
            return prices[i] / prices[i - window] - 1 <= -study.threshold
        if study.kind == "REBOUND":
            # Rebound after a declining, completed preceding window.
            return (
                prices[i] / prices[i - window] - 1 >= study.threshold
                and prices[i - window] < prices[i - 2 * window]
            )
        # Std deviation of last window returns vs previous-window baseline.
        # This is a RETROSPECTIVE event label, never a predictor.
        if window < 2:
            return False
        current = returns[i - window : i]
        previous = returns[i - 2 * window : i - window]
        base = pstdev(previous)
        return base > 0 and pstdev(current) / base >= study.threshold

    selected: list[int] = []
    was_crossed = False
    for index in range(len(prices)):
        event = crossed(index)
        if event and not was_crossed:
            selected.append(index)
        was_crossed = event
    return tuple(selected)


def historical_risk_scores(
    prices: Sequence[float],
    study: EventStudy,
) -> tuple[float | None, ...]:
    """Causal risk score from existing REGISTERED 20-bar QQQ returns."""
    _validate_prices(prices)
    spec = default_feature_registry().get("qqq_returns")
    if spec.status != "REGISTERED" or spec.calculator != "returns":
        raise EventStudyError("pre-approved registered return feature unavailable")
    raw = calculate_feature(spec, {"QQQ.close": tuple(float(p) for p in prices)})
    if study.kind in {"CRASH", "REBOUND"}:
        # Prior decline is a heuristic precursor, NOT a claimed prediction.
        return tuple(None if r is None else max(0.0, -r) for r in raw)
    return tuple(None if r is None else abs(r) for r in raw)


def select_budgeted_warnings(
    scores: Sequence[float | None],
    days: Sequence[date],
    *,
    threshold: float,
    budget: int,
    cooldown: int,
) -> tuple[int, ...]:
    """Online chronological budget; NEVER rank a full future year retrospectively."""
    if (
        len(scores) != len(days) or type(budget) is not int or budget < 1
        or type(cooldown) is not int or cooldown < 0
        or not isfinite(threshold) or threshold < 0
    ):
        raise EventStudyError("invalid warning budget")
    previous: date | None = None
    for day, value in zip(days, scores, strict=True):
        if not isinstance(day, date) or (previous is not None and day <= previous):
            raise EventStudyError("time indices must be strictly increasing dates")
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (float, int))
            or not isfinite(value)
        ):
            raise EventStudyError("finite warning score required")
        previous = day
    chosen: list[int] = []
    used_by_year: dict[int, int] = {}
    for i, (day, value) in enumerate(zip(days, scores, strict=True)):
        if value is None or value < threshold or used_by_year.get(day.year, 0) >= budget:
            continue
        if chosen and i - chosen[-1] <= cooldown:
            continue
        chosen.append(i)
        used_by_year[day.year] = used_by_year.get(day.year, 0) + 1
    return tuple(chosen)


def average_precision(
    scores: Sequence[float], labels: Sequence[bool]
) -> float | None:
    """Threshold/tie-group average precision, not trapezoidal ROC AUC."""
    if len(scores) != len(labels) or not scores:
        raise EventStudyError("nonempty equal-sized scores and labels required")
    if any(not isfinite(float(x)) for x in scores):
        raise EventStudyError("finite ranked scores required")
    if any(type(x) is not bool for x in labels):
        raise EventStudyError("binary labels required")
    positive = sum(labels)
    if positive == 0:
        return None
    ranked = sorted(zip(scores, labels, strict=True), key=lambda x: x[0], reverse=True)
    retrieved = true_positive = 0
    ap = 0.0
    pos = 0
    while pos < len(ranked):
        score = ranked[pos][0]
        group = []
        while pos < len(ranked) and ranked[pos][0] == score:
            group.append(ranked[pos][1])
            pos += 1
        retrieved += len(group)
        found = sum(group)
        true_positive += found
        ap += found / positive * true_positive / retrieved
    return ap


def _warning_stats(
    indices: tuple[int, ...], labels_onsets: tuple[int, ...],
    study: EventStudy, eligible_count: int,
) -> dict[str, float | int | tuple[int, ...] | None]:
    unmatched = set(labels_onsets)
    hits = 0
    leads: list[int] = []
    for issue in indices:
        candidate = min((
            j for j in unmatched
            if issue + study.min_lead_bars <= j <= issue + study.max_lead_bars
        ), default=None)
        if candidate is not None:
            unmatched.remove(candidate)
            hits += 1
            leads.append(candidate - issue)
    false = len(indices) - hits
    return {
        "warning_count": len(indices),
        "matched_event_count": hits,
        "false_warning_count": false,
        "precision": hits / len(indices) if indices else None,
        "event_recall": hits / len(labels_onsets) if labels_onsets else None,
        "confirmed_lead_times_bars": tuple(leads),
        "median_confirmed_lead_bars": median(leads) if leads else None,
        "mean_confirmed_lead_bars": mean(leads) if leads else None,
        "false_warnings_per_252_eligible_bars": (
            false * 252.0 / eligible_count if eligible_count else None
        ),
    }


def require_purged_train_test_boundary(
    train_last_issue_index: int, test_first_issue_index: int, study: EventStudy,
) -> None:
    """Prevent a train label horizon from reaching a held-out test fold.

    This verifies one boundary only; it DOES NOT establish a complete
    purged walk-forward experiment or independent OOS provenance.
    """
    if (
        type(train_last_issue_index) is not int
        or type(test_first_issue_index) is not int
        or train_last_issue_index < 0
        or test_first_issue_index <= train_last_issue_index
        or train_last_issue_index + study.max_lead_bars >= test_first_issue_index
    ):
        raise EventStudyError("purged walk-forward needs an embargo after label horizon")


def evaluate_development_events(
    prices: Sequence[float],
    days: Sequence[date],
    study: EventStudy,
    *,
    data_zone: object = "development",
) -> dict[str, object]:
    """Research diagnostic ONLY; never accesses broker, sealed OOS or Track1."""
    if data_zone != "development":
        raise EventStudyError("Track2 research accepts development data only")
    _validate_prices(prices)
    if len(prices) != len(days) or any(
        not isinstance(d, date) or (i and d <= days[i - 1])
        for i, d in enumerate(days)
    ):
        raise EventStudyError("strictly ordered daily timestamps required")
    feature = default_feature_registry().get("qqq_returns")
    risk = historical_risk_scores(prices, study)
    onsets = label_event_onsets(prices, study)
    # No scores within the last lookahead window may be scored: censored.
    opportunities = tuple(
        i for i, value in enumerate(risk[:max(0, len(risk) - study.max_lead_bars)])
        if value is not None
    )
    if not opportunities:
        raise EventStudyError("not enough history for a censored event evaluation")
    warnings = select_budgeted_warnings(
        tuple(risk[i] for i in opportunities),
        tuple(days[i] for i in opportunities),
        threshold=study.alert_score_threshold,
        budget=study.warning_budget_per_year,
        cooldown=study.cooldown_bars,
    )
    warnings = tuple(opportunities[j] for j in warnings)
    baseline_always = select_budgeted_warnings(
        (1.0,) * len(opportunities),
        tuple(days[i] for i in opportunities),
        threshold=0.0, budget=study.warning_budget_per_year,
        cooldown=study.cooldown_bars,
    )
    baseline_always = tuple(opportunities[j] for j in baseline_always)
    actionable = tuple(
        j for j in onsets
        if any(i + study.min_lead_bars <= j <= i + study.max_lead_bars
               for i in opportunities)
    )
    future_labels = tuple(
        any(i + study.min_lead_bars <= j <= i + study.max_lead_bars
            for j in actionable)
        for i in opportunities
    )
    good = len(actionable) >= study.min_confirmed_events and any(
        not y for y in future_labels
    )
    score_values = tuple(float(v) for i in opportunities if (v := risk[i]) is not None)
    ap = average_precision(score_values, future_labels) if good else None
    data_hash = content_hash({
        "dates": [d.isoformat() for d in days],
        "closes": [float(p) for p in prices],
    })
    protocol_hash = content_hash(asdict(study))
    alert_records = [
        {
            "issued_at_index": i, "issued_at_date": days[i].isoformat(),
            "score_available_at": days[i].isoformat(),
            "score": risk[i], "protocol_hash": protocol_hash,
            "warning_reason": "REGISTERED_QQQ_RETURNS_20_BAR",
            "feature_semantic_id": feature.canonical_id,
            "observed_prefix_hash": content_hash({
                "dates": [d.isoformat() for d in days[:i + 1]],
                "closes": [float(p) for p in prices[:i + 1]],
            }),
        }
        for i in warnings
    ]
    body: dict[str, object] = {
        "schema": "TRACK2_EVENT_DIAGNOSTIC_V1",
        "status": "SYNTHETIC_OR_UNVERIFIED_DEVELOPMENT_ONLY"
        if good else "BLOCKED_INSUFFICIENT_EVENTS",
        "event_kind": study.kind,
        "protocol_hash": protocol_hash,
        "data_content_hash": data_hash,
        "registered_feature": feature.name,
        "registered_feature_semantic_id": feature.canonical_id,
        "event_count": len(actionable),
        "eligible_opportunities": len(opportunities),
        "right_censored_from_index": opportunities[-1] + 1,
        "base_rate_by_opportunity": sum(future_labels) / len(future_labels),
        "pr_auc": ap,
        "pr_auc_benchmark_constant": (
            sum(future_labels) / len(future_labels) if good else None
        ),
        "warnings": alert_records,
        "detector": _warning_stats(warnings, actionable, study, len(opportunities)),
        "no_warning": _warning_stats((), actionable, study, len(opportunities)),
        "always_warning": _warning_stats(
            baseline_always, actionable, study, len(opportunities)
        ),
        "label_visibility": "OFFLINE_EX_POST",
        "scores_available_at": "BAR_CLOSE_ONLY",
        "warning_score_future_ranked": False,
        "warning_budget_per_calendar_year": study.warning_budget_per_year,
        "warnings_are_trading_orders": False,
        "track1_research_access": False,
        "no_sealed_oos_read": True,
        "independent_oos_approved": False,
        "broker_executable": False,
        "evidence_origin_attested": False,
        "causal_status": "NOT_ESTABLISHED",
        "economic_superiority_established": False,
        "brier_score": None,
        "calibration_status": "NOT_CALIBRATED_NO_PROSPECTIVE_PROBABILITY",
        "purged_walk_forward_validated": False,
        "champion_candidate_selected": False,
        "evaluation_type": "RETROSPECTIVE_EVENT_DIAGNOSTIC_NOT_PROSPECTIVE",
    }
    return {**body, "report_hash": content_hash(body)}
