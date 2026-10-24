"""P3 generalization parent ranking: deterministic ex-post research, never OOS."""
from dataclasses import asdict, replace

import pytest

from core.integrity.hashes import content_hash
from research.indicator_engine.historical_robustness import HistoricalPeriod
from research.indicator_engine.inherited_historical_robustness import InheritedRobustnessReport
from research.llm.generalization_parent_v1 import (
    GeneralizationParentError,
    select_generalization_parent,
)


def example(generation, return_full, drawdown_full, returns, drawdowns):
    key = f"{generation:064x}"
    evidence = f"{generation + 100:064x}"
    audit = f"{generation + 200:064x}"
    benchmark = (-.33, .50, .20)
    periods = tuple(HistoricalPeriod(
        year=year,
        period_first=f"{year}-01-03T00:00:00+00:00",
        period_last=f"{year}-12-30T00:00:00+00:00",
        year_end_coverage="YEAR_END_OBSERVED",
        trading_bars=250, initial_cash=10000, first_holdout_equity=10000,
        final_equity=10000*(1+returns[i]), total_return=returns[i],
        cagr=returns[i], max_drawdown=drawdowns[i], sharpe=None,
        completed_trades=6, fill_count=12, paid_costs=50,
        first_fill=f"{year}-01-04T00:00:00+00:00",
        market_qqq_costed_return=benchmark[i],
        excess_costed_return=returns[i]-benchmark[i],
        evaluation_hash=f"{generation*100+i:064x}",
        benchmark_hash=f"{i+150:064x}"
    ) for i,year in enumerate((2022, 2023, 2024)))
    report_body = {
        "schema":"audited-inherited-ir-historical-v1",
        "full_audit_hash":audit, "source_evidence_hash":evidence,
        "source_data_hash":"e"*64, "years":[p.year for p in periods],
        "periods":[asdict(p) for p in periods], "cutoff":"2025-12-31",
        "oos_approved":False,
    }
    report=InheritedRobustnessReport(
        strategy_hash=key, source_evidence_hash=evidence,
        full_audit_hash=audit, development_hash="e"*64,
        cutoff_date="2025-12-31",periods=periods,
        report_hash=content_hash(report_body),
    )
    candidate={
        "source_generation":generation, "source_kind":"COUNTED_GENERATION",
        "source_evidence_hash":evidence, "audit_hash":audit,
        "effective_signal_hash":f"signal-{generation}",
        "successor_strategy_hash":key, "replay_verified":True,
        "independent_oos_approved":False, "broker_executable":False,
        "parent_quality":{"total_return":return_full,
                          "max_drawdown":drawdown_full,
                          "closed_trades":40,"market_exposure":.6},
    }
    return candidate, report


def fixtures():
    return [
        example(1,1.7,.34,(-.45,.72,.35),(.30,.28,.20)),
        example(2,1.0,.14,(-.10,.43,.19),(.07,.07,.08)),
        example(3,1.4,.20,(-.19,.54,.25),(.11,.12,.13)),
    ]


def select(items, generation=100):
    return select_generalization_parent(
        [c for c,_ in items], {r.strategy_hash:r for _,r in items},
        next_generation=generation
    )


def test_real_objectives_keep_distinct_growth_defense_and_consistency():
    items=fixtures()
    result=select(items)
    assert result.lane_names == ("GROWTH","DOWNSIDE","CONSISTENCY")
    assert result.lane_generations == (1,2,3)
    assert result.chosen_generation == 1
    assert tuple(select(items,g).chosen_generation for g in (100,101,102)) == (1,2,3)
    assert result == select(list(reversed(items)))
    assert result.candidate_reviews[0].worst_year_excess_vs_qqq == pytest.approx(-.12)
    assert result.candidate_reviews[1].total_annual_completed_trades == 18
    assert not result.independent_oos_approved
    assert not result.broker_executable and not result.candidate_promotable


def test_evidence_tampering_fails_closed():
    original,report=fixtures()[0]
    for field,value in (
        ("replay_verified",False),
        ("source_kind","COUNTED_S7_CHILD"),
        ("broker_executable",True),
        ("independent_oos_approved",True),
        ("audit_hash","f"*64),
        ("source_evidence_hash","f"*64),
        ("successor_strategy_hash","f"*64),
    ):
        candidate={**original, field:value}
        with pytest.raises(GeneralizationParentError):
            select([(candidate,report)])
    with pytest.raises(GeneralizationParentError):
        select([(original,replace(report,report_hash="f"*64))])
    with pytest.raises(GeneralizationParentError):
        select([(original,replace(report,periods=(
            replace(report.periods[0],total_return=.99),*report.periods[1:]
        )))])
    with pytest.raises(GeneralizationParentError):
        select([(original,replace(report,independent_oos_approved=True))])


def test_comparability_sample_and_duplicates():
    items=fixtures()
    first,second=items[0],items[1]
    with pytest.raises(GeneralizationParentError):
        select([first,(second[0],replace(second[1],development_hash="f"*64))])
    copy_candidate={**second[0],"effective_signal_hash":first[0]["effective_signal_hash"]}
    with pytest.raises(GeneralizationParentError):
        select([first,(copy_candidate,second[1])])
    with pytest.raises(GeneralizationParentError):
        select([])
    with pytest.raises(GeneralizationParentError):
        select(items,generation=1)
    with pytest.raises(GeneralizationParentError):
        select([(first[0],replace(first[1],periods=first[1].periods[:2]))])



def test_fallback_diversity_is_never_mislabeled_as_best_consistency():
    # An extra parent is nondominated thanks to its all-period drawdown,
    # but it is NOT the most consistent on worst-year QQQ excess.
    items = [
        example(64,1.8853,.2413,(-.16,.45,.22),(.20,.20,.20)),
        example(61,1.503,.2197,(-.18,.42,.18),(.15,.17,.15)),
        example(45,1.387,.2095,(-.21,.43,.15),(.18,.18,.18)),
    ]
    answer=select(items,generation=69)
    assert answer.lane_generations == (64,61,45)
    assert answer.lane_names == ("GROWTH","DOWNSIDE","PARETO_DIVERSITY")
    assert answer.chosen_generation == 45


def test_verified_s7_child_competes_and_tamper_blocks():
    counted, old = fixtures()[0]
    child, report = example(9, 1.85, .20, (-.12, .56, .25), (.12, .15, .13))
    lineage = {
        "schema": "counted-s7-child-origin-v1",
        "source_generation": child["source_generation"],
        "source_evidence_hash": child["source_evidence_hash"],
        "source_report_hash": "a" * 64,
        "hypothesis_id": "signed_child_study",
        "child_strategy_hash": child["successor_strategy_hash"],
    }
    child = {
        **child, "source_kind": "COUNTED_S7_CHILD",
        "source_report_hash": lineage["source_report_hash"],
        "hypothesis_id": lineage["hypothesis_id"],
        "lineage_report_hash": content_hash(lineage),
    }
    choice = select([(counted, old), (child, report)])
    assert any(x.source_kind == "COUNTED_S7_CHILD" for x in choice.candidate_reviews)
    assert any(x.lineage_report_hash == child["lineage_report_hash"]
               for x in choice.candidate_reviews)
    broken = {**child, "hypothesis_id": "unverified_study"}
    with pytest.raises(GeneralizationParentError, match="S7 lineage"):
        select([(broken, report)])
    broken = {**child, "source_report_hash": "b" * 64}
    with pytest.raises(GeneralizationParentError, match="S7 lineage"):
        select([(broken, report)])
    broken = {**child, "lineage_report_hash": "b" * 64}
    with pytest.raises(GeneralizationParentError, match="S7 lineage"):
        select([(broken, report)])
    assert choice.independent_oos_approved is False
