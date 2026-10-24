"""The fixed-plan historical diagnostic must never claim unseen-data validation."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.historical_robustness import evaluate_historical_robustness
from tests.research.test_academic_algorithm_plan import _catalog, _plan


def _prices(*, perturb_final: bool = False) -> MarketDataSet:
    first = datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(1050):
        dt = first + timedelta(days=i)
        p = 125.0 + i * 0.075 + (i % 31) * 0.12
        if i > 720:
            p -= (i - 720) * 0.095
        if perturb_final and dt.year == 2022:
            p += (dt.timetuple().tm_yday / 366.0) * 35.0
        bars.append(Bar(dt, "QQQ", p, p + 0.7, p - 0.7, p, 10000.0))
    return MarketDataSet("historical-period-test", DataZone.DEVELOPMENT, tuple(bars))


def test_replay_is_ex_post_and_uses_frozen_plan(tmp_path: Path) -> None:
    cat, market, plan = _catalog(tmp_path), _prices(), _plan()
    report = evaluate_historical_robustness(
        cat, plan, market, years=(2021, 2022),
        last_development_date=date(2022, 12, 31),
    )
    assert report.status == "EX_POST_DEVELOPMENT_ROBUSTNESS_ONLY"
    assert not report.independent_oos_approved
    assert not report.broker_executable
    assert not report.candidate_promotable
    assert report.selection_scope == "PLAN_FROZEN_EX_POST_NOT_WALKFORWARD_SELECTION"
    assert tuple(x.year for x in report.periods) == (2021, 2022)
    assert report.plan_hash
    assert report.report_hash
    for x in report.periods:
        assert x.period_first.startswith(str(x.year))
        assert x.initial_cash == 10000
        assert x.first_holdout_equity == 10000
        assert x.completed_trades <= x.fill_count
        assert x.first_fill is None or x.first_fill > x.period_first
        assert x.market_qqq_costed_return > -1
        assert x.excess_costed_return == pytest.approx(
            x.total_return - x.market_qqq_costed_return
        )
        assert x.evaluation_hash
    assert report == evaluate_historical_robustness(
        cat, plan, market, years=(2021, 2022),
        last_development_date=date(2022, 12, 31),
    )


def test_future_period_change_cannot_change_prior_period_result(tmp_path: Path) -> None:
    cat, plan = _catalog(tmp_path), _plan()
    before = evaluate_historical_robustness(
        cat, plan, _prices(), years=(2021, 2022),
        last_development_date=date(2022, 12, 31),
    )
    after = evaluate_historical_robustness(
        cat, plan, _prices(perturb_final=True), years=(2021, 2022),
        last_development_date=date(2022, 12, 31),
    )
    assert before.periods[0] == after.periods[0]
    assert before.periods[1].evaluation_hash != after.periods[1].evaluation_hash
    assert before.report_hash != after.report_hash


def test_rejects_future_data_even_when_not_in_selected_years(tmp_path: Path) -> None:
    cat, plan, market = _catalog(tmp_path), _plan(), _prices()
    with pytest.raises(ResearchCatalogError, match="cutoff"):
        evaluate_historical_robustness(
            cat, plan, market, years=(2021,),
            last_development_date=date(2021, 12, 31),
        )


@pytest.mark.parametrize("years", [
    (2022, 2021), (2021, 2021), (2020,), (2021, 2025), (), (2026,),
])
def test_fail_closed_for_invalid_years_or_warmup(tmp_path: Path, years) -> None:
    cat, market, plan = _catalog(tmp_path), _prices(), _plan()
    with pytest.raises(ResearchCatalogError):
        evaluate_historical_robustness(
            cat, plan, market, years=years,
            last_development_date=date(2022, 12, 31),
        )


def test_refuses_sealed_data_and_non_qqq(tmp_path: Path) -> None:
    cat, plan, market = _catalog(tmp_path), _plan(), _prices()
    for invalid in (
        replace(market, zone=DataZone.SEALED_OOS),
        replace(market, zone=DataZone.VALIDATION),
        replace(market, bars=tuple(replace(b, symbol="SPY") for b in market.bars)),
    ):
        with pytest.raises(ResearchCatalogError, match="development|QQQ"):
            evaluate_historical_robustness(
                cat, plan, invalid, years=(2021, 2022),
                last_development_date=date(2022, 12, 31),
            )


def test_missing_year_rejected_not_marked_zero_return(tmp_path: Path) -> None:
    cat, market, plan = _catalog(tmp_path), _prices(), _plan()
    with pytest.raises(ResearchCatalogError, match="missing|insufficient"):
        evaluate_historical_robustness(
            cat, plan, market, years=(2023,),
            last_development_date=date(2023, 12, 31),
        )
