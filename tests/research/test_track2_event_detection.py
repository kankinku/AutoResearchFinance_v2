"""Track2 only: no old G150, no live data, no OOS promotion, no trading."""

import math
from datetime import date, timedelta

import pytest

from core.integrity.hashes import content_hash
from research.indicator_engine.track2_event_detection import (
    EventStudy,
    EventStudyError,
    average_precision,
    evaluate_development_events,
    historical_risk_scores,
    label_event_onsets,
    select_budgeted_warnings,
)


def calendar(n: int, *, start: date = date(2022, 1, 1)) -> tuple[date, ...]:
    return tuple(start + timedelta(days=i) for i in range(n))


def study(kind: str = "CRASH", **overrides) -> EventStudy:
    opts = dict(
        kind=kind, label_window=2, threshold=0.1,
        min_lead_bars=1, max_lead_bars=4,
        warning_budget_per_year=2, alert_score_threshold=0.04,
        cooldown_bars=2, min_confirmed_events=2,
    )
    opts.update(overrides)
    return EventStudy(**opts)


def test_label_crash_rebound_and_volatility_spike_as_confirmed_onsets():
    prices = (100.0, 105.0, 110.0, 90.0, 78.0, 99.0, 102.0, 103.0)
    crashed = label_event_onsets(prices, study("CRASH", label_window=1, threshold=0.1))
    assert 3 in crashed
    assert 4 not in crashed  # same episode, no double-counting
    bounced = label_event_onsets(prices, study("REBOUND", label_window=1, threshold=0.1))
    assert 5 in bounced
    assert 4 not in label_event_onsets(
        (100.0, 101.0, 102.0, 103.0, 120.0),
        study("REBOUND", label_window=1, threshold=0.1),
    )  # prior-window drawdown is required
    spike_prices = (100.0, 101.0, 99.0, 100.0, 101.0, 99.0, 105.0, 95.0)
    spikes = label_event_onsets(
        spike_prices, study("VOL_SPIKE", label_window=2, threshold=2.0)
    )
    assert spikes
    assert all(0 <= i < len(spike_prices) for i in spikes)


@pytest.mark.parametrize("bad", [
    {"kind": "OTHER"}, {"threshold": -1}, {"label_window": 0},
    {"min_lead_bars": 0}, {"max_lead_bars": 0},
    {"min_lead_bars": 5, "max_lead_bars": 4},
    {"warning_budget_per_year": 0}, {"cooldown_bars": -1},
    {"alert_score_threshold": float("nan")}, {"min_confirmed_events": 0},
])
def test_invalid_study_parameters_fail_closed(bad):
    with pytest.raises(EventStudyError):
        study(**bad)


def test_registered_feature_scores_are_strictly_causal_under_tail_changes():
    prices = tuple(100 + i * 0.2 for i in range(55))
    changed = prices[:50] + (300.0, 5.0, 3.0, 900.0, 50.0)
    for kind in ("CRASH", "REBOUND", "VOL_SPIKE"):
        earlier = historical_risk_scores(prices[:50], study(kind))
        larger = historical_risk_scores(changed, study(kind))
        assert earlier == larger[:50]
        assert all(x is None or math.isfinite(x) for x in larger)


def test_event_labels_are_ex_post_only_and_warning_scores_never_use_them():
    prices = tuple([100.0] * 35 + [110.0] * 25)
    risk = historical_risk_scores(prices, study("REBOUND"))
    # Change the entire right half; past scores stay identical.
    other = tuple([100.0] * 35 + [5.0] * 25)
    assert risk[:35] == historical_risk_scores(other, study("REBOUND"))[:35]


def test_warning_budget_and_cooldown_never_inspect_future_scores():
    days = calendar(50)
    scores = tuple([1.0] * 50)
    first = select_budgeted_warnings(scores, days, threshold=0.0, budget=2, cooldown=3)
    second = select_budgeted_warnings(scores[:35], days[:35], threshold=0.0, budget=2, cooldown=3)
    assert first == second
    assert len(first) == 2
    assert first[1] - first[0] > 3


def test_no_warning_and_always_warning_baselines_share_the_same_budget():
    days = calendar(75)
    empty = select_budgeted_warnings((0.0,) * 75, days, threshold=1.0, budget=3, cooldown=0)
    always = select_budgeted_warnings((1.0,) * 75, days, threshold=0.0, budget=3, cooldown=0)
    assert empty == ()
    assert len(always) == 3


def test_tied_scores_are_not_sorted_with_hidden_future_label_information():
    assert average_precision((1.0, 1.0, 1.0, 1.0), (True, False, True, False)) == 0.5
    assert average_precision((0.9, 0.8, 0.2, 0.1), (True, True, False, False)) == 1.0
    assert average_precision((0.1, 0.2), (False, False)) is None


def test_scored_report_is_blocked_when_event_base_rate_is_insufficient():
    days = calendar(60)
    close = tuple(float(100 + i) for i in range(60))
    report = evaluate_development_events(close, days, study("CRASH"))
    assert report["status"] == "BLOCKED_INSUFFICIENT_EVENTS"
    assert report["event_count"] == 0
    assert report["pr_auc"] is None
    assert report["no_warning"]["warning_count"] == 0
    assert report["always_warning"]["warning_count"] <= 2
    assert report["independent_oos_approved"] is False
    assert report["broker_executable"] is False
    assert report["evidence_origin_attested"] is False
    assert report["report_hash"] == content_hash({
        k: v for k, v in report.items() if k != "report_hash"
    })


@pytest.mark.parametrize("zone", ["sealed_oos", "validation", "development ", "", 1])
def test_rejects_undeclared_or_forbidden_data_zone(zone):
    with pytest.raises(EventStudyError, match="development"):
        evaluate_development_events(
            (100.0,) * 40, calendar(40), study(), data_zone=zone
        )


@pytest.mark.parametrize("prices, dates", [
    ((100.0, 102.0, 0.0), calendar(3)),
    ((100.0, float("nan"), 102.0), calendar(3)),
    ((100.0,) * 3, (date(2021, 1, 1),) * 3),
    ((100.0,) * 3, calendar(2)),
])
def test_bad_time_order_or_nonfinite_prices_rejected(prices, dates):
    with pytest.raises(EventStudyError):
        evaluate_development_events(prices, dates, study())


def test_right_censor_never_counts_events_after_the_last_observation():
    days = calendar(38)
    prices = tuple([100.0] * 32 + [90.0, 80.0, 90.0, 120.0, 60.0, 50.0])
    report = evaluate_development_events(prices, days, study("CRASH", min_confirmed_events=1))
    assert report["eligible_opportunities"] <= 38 - 4 - 20
    assert all(
        alert["issued_at_index"] + 4 < len(prices)
        for alert in report["warnings"]
    )


def test_warning_ledger_is_deterministic_and_not_called_a_trading_signal():
    days = calendar(62)
    prices = tuple([100.0 + 0.1*i for i in range(52)] + [65.0, 50.0, 60.0, 55.0, 53.0,
        90.0, 96.0, 92.0, 50.0, 47.0])
    policy = study("CRASH", min_confirmed_events=1)
    report = evaluate_development_events(prices, days, policy)
    assert report == evaluate_development_events(prices, days, policy)
    assert report["label_visibility"] == "OFFLINE_EX_POST"
    assert report["warnings_are_trading_orders"] is False
    assert report["track1_research_access"] is False
    assert report["no_sealed_oos_read"] is True
    assert all(w["score_available_at"] == w["issued_at_date"] for w in report["warnings"])


def test_alert_ledger_only_anchors_observed_prefix_not_future_ohlc():
    days = calendar(60)
    close = tuple([100.0] * 29 + [95.0] * 31)
    changed = close[:45] + tuple(200.0 + i for i in range(15))
    policy = study("CRASH", min_confirmed_events=1, alert_score_threshold=0.005)
    original = evaluate_development_events(close, days, policy)
    future = evaluate_development_events(changed, days, policy)
    assert original["warnings"], "fixture must have at least one warning"
    i = original["warnings"][0]["issued_at_index"]
    assert i < 45
    before = original["warnings"][0]
    after = next(w for w in future["warnings"] if w["issued_at_index"] == i)
    assert before == after
    assert before["observed_prefix_hash"] == content_hash({
        "dates": [d.isoformat() for d in days[:i+1]],
        "closes": [float(p) for p in close[:i+1]],
    })
    assert "data_content_hash" not in before
    assert original["data_content_hash"] != future["data_content_hash"]


def test_all_baselines_and_metrics_use_only_available_warning_opportunities():
    days = calendar(260)
    price = []
    level = 100.0
    for i in range(260):
        if i in (75, 135, 190, 245):
            level *= 0.72
        elif i in (76, 136, 191, 246):
            level *= 1.05
        else:
            level *= 1.0005
        price.append(level)
    result = evaluate_development_events(
        tuple(price), days, study("CRASH", min_confirmed_events=2)
    )
    assert result["status"] == "SYNTHETIC_OR_UNVERIFIED_DEVELOPMENT_ONLY"
    assert result["event_count"] >= 2
    assert result["pr_auc"] is not None
    assert result["pr_auc_benchmark_constant"] is not None
    assert 0 <= result["pr_auc"] <= 1
    assert result["always_warning"]["warning_count"] <= 2
    assert result["no_warning"]["false_warning_count"] == 0
    assert result["detector"]["warning_count"] <= 2
    assert result["economic_superiority_established"] is False


def test_online_budget_resets_only_at_calendar_year_boundary():
    days = (
        date(2022, 12, 29), date(2022, 12, 30),
        date(2023, 1, 2), date(2023, 1, 3),
    )
    assert select_budgeted_warnings(
        (1.0,) * 4, days, threshold=0.0, budget=1, cooldown=0,
    ) == (0, 2)



def test_lead_time_and_one_to_one_matching_do_not_double_count_one_crash():
    from research.indicator_engine.track2_event_detection import _warning_stats

    options = study("CRASH", min_lead_bars=1, max_lead_bars=4)
    stats = _warning_stats((4, 5), (7,), options, 250)
    assert stats["warning_count"] == 2
    assert stats["matched_event_count"] == 1
    assert stats["false_warning_count"] == 1
    assert stats["confirmed_lead_times_bars"] == (3,)
    assert stats["median_confirmed_lead_bars"] == 3
    assert stats["event_recall"] == 1
