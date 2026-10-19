from datetime import datetime

import pytest

from core.features.pine_liquidity_levels import completed_period_levels


def test_previous_day_not_same_day_and_completed_week():
    bars = [
        (datetime(2026, 10, 16, 9), 110, 90),
        (datetime(2026, 10, 16, 10), 120, 95),
        (datetime(2026, 10, 19, 9), 125, 100),
        (datetime(2026, 10, 19, 10), 130, 110),
        (datetime(2026, 10, 20, 9), 140, 115),
    ]
    levels = completed_period_levels(bars)
    assert levels[0].previous_day_high is None
    assert levels[1].previous_day_high is None
    assert levels[2].previous_day_high == 120
    assert levels[2].previous_day_low == 90
    assert levels[2].previous_day_eq == 105
    assert levels[2].previous_week_high == 120
    assert levels[2].previous_week_low == 90
    assert levels[3].previous_day_high == 120
    assert levels[4].previous_day_high == 130
    assert levels[4].previous_week_high == 120


def test_reject_nonchronological_and_bad_high_low():
    with pytest.raises(ValueError):
        completed_period_levels(
            [
                (datetime(2026, 10, 20), 10, 1),
                (datetime(2026, 10, 19), 12, 2),
            ]
        )
    with pytest.raises(ValueError):
        completed_period_levels([(datetime(2026, 10, 20), 1, 2)])
