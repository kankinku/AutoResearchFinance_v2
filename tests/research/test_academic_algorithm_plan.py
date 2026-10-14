"""S3 acceptance: typed regime switching and weighted indicator votes, no Python eval."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    audit_algorithm_plan,
    compile_algorithm_plan,
    compile_provider_algorithm_plan,
    evaluate_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices


def _catalog(tmp_path: Path, *, verify: bool = True):
    catalog = ResearchCatalog(tmp_path / "indicators.sqlite")
    seed_approved_references(catalog)
    if verify:
        for name in ("time_series_momentum", "previous_range_breakout",
                     "sma_direction", "parkinson_variance"):
            sig = catalog.get_indicator(name)
            if sig.status == "PROPOSED":
                catalog.verify_and_register(name, verify_signal_on_synthetic_prices(sig))
    return catalog


def _market(*, change_last: bool = False, sealed: bool = False):
    bars = []
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for i in range(650):
        price = 100.0 + i * 0.09 + (i % 22) * 0.06
        if i >= 440:
            price = 160.0 - (i - 440) * 0.13 + (i % 22) * 0.3
        if i == 649 and change_last:
            price *= 1.1
        span = 0.2 if i < 400 else 2.2
        bars.append(Bar(t0 + timedelta(days=i), "QQQ", price, price + span,
                        price - span, price, 100_000.0))
    return MarketDataSet("algo_synthetic", DataZone.SEALED_OOS if sealed
                         else DataZone.DEVELOPMENT, tuple(bars))


def _plan():
    return AlgorithmPlan.model_validate({
        "plan_id": "research_switch_01",
        "cases": [
            {"case_id": "calm", "when": {
                "indicator_id": "parkinson_variance", "op": "less_equal", "threshold": 0.0001},
             "votes": [{"indicator_id": "time_series_momentum", "weight": 0.7},
                       {"indicator_id": "previous_range_breakout", "weight": 0.3}],
             "min_score": 0.5},
            {"case_id": "volatile", "when": {
                "indicator_id": "parkinson_variance", "op": "greater_than", "threshold": 0.0001},
             "votes": [{"indicator_id": "previous_range_breakout", "weight": 0.8},
                       {"indicator_id": "time_series_momentum", "weight": 0.2}],
             "min_score": 0.5},
        ],
        "unmatched": "FLAT",
        "position_size_pct": 100,
    })


def test_weighted_conditional_algorithm_replays_with_canonical_fills(tmp_path: Path):
    catalog, market, plan = _catalog(tmp_path), _market(), _plan()
    compiled = compile_algorithm_plan(catalog, plan, market)
    assert compiled.algorithm.status == "DEVELOPMENT_ONLY"
    assert compiled.algorithm.strategy_hash == compiled.compiled.strategy_hash
    assert not compiled.compiled.broker_executable
    assert compiled.compiled.strategy.entry.conditions[0].left == "plan_entry"
    values = compiled.compiled.feature_values
    assert values["plan_branch_index"][300] == 1
    assert values["plan_branch_index"][500] == 2
    assert values["plan_vote_score"][300] == pytest.approx(0.7)
    assert values["plan_entry"][300] == 1.0
    assert values["plan_entry"][500] in (0.0, 1.0)
    audit = audit_algorithm_plan(catalog, compiled, market)
    assert audit.evaluation == evaluate_algorithm_plan(catalog, compiled, market)
    assert audit.fills
    assert len(audit.decisions) == len(market.bars)
    assert "parkinson_variance" in dict(audit.decisions[500].indicator_values)
    assert "plan_branch_index" in dict(audit.decisions[500].indicator_values)
    assert audit.llm_packet["causal_claim"] == "NOT_ESTABLISHED"
    assert audit.trace_hash == audit_algorithm_plan(catalog, compiled, market).trace_hash
    for fill in audit.fills:
        decision = next(d for d in audit.decisions if d.decision_id == fill.decision_id)
        assert decision.signal_time < fill.execution_time


def test_regime_switch_uses_gate_at_completed_close_not_future(tmp_path: Path):
    catalog, plan = _catalog(tmp_path), _plan()
    before = compile_algorithm_plan(catalog, plan, _market())
    after = compile_algorithm_plan(catalog, plan, _market(change_last=True))
    for name in before.compiled.feature_values:
        assert before.compiled.feature_values[name][:-1] == after.compiled.feature_values[name][:-1]
    assert before.compiled.replay.replay_hash != after.compiled.replay.replay_hash


def test_missing_last_case_will_remain_flat(tmp_path: Path):
    catalog, market = _catalog(tmp_path), _market()
    one = _plan().model_copy(update={"cases": _plan().cases[:1]})
    values = compile_algorithm_plan(catalog, one, market).compiled.feature_values
    assert values["plan_branch_index"][500] == 0
    assert values["plan_entry"][500] == 0
    assert values["plan_regime"][500] == 0


def test_bans_unverified_pit_and_tampering(tmp_path: Path):
    catalog, market, plan = _catalog(tmp_path, verify=False), _market(), _plan()
    with pytest.raises(ResearchCatalogError, match="VERIFIED"):
        compile_algorithm_plan(catalog, plan, market)
    catalog = _catalog(tmp_path, verify=True)
    with pytest.raises(ResearchCatalogError, match="development"):
        compile_algorithm_plan(catalog, plan, _market(sealed=True))
    compiled = compile_algorithm_plan(catalog, plan, market)
    forged = replace(compiled, compiled=replace(compiled.compiled, strategy_hash="f" * 64))
    with pytest.raises(ResearchCatalogError, match="replay|integrity|mismatch"):
        evaluate_algorithm_plan(catalog, forged, market)
    changed = dict(compiled.compiled.feature_values)
    changed["plan_entry"] = tuple(1.0 for _ in market.bars)
    tampered = replace(compiled, compiled=replace(compiled.compiled, feature_values=changed))
    with pytest.raises(ResearchCatalogError, match="replay|integrity|mismatch"):
        audit_algorithm_plan(catalog, tampered, market)
    with pytest.raises(ResearchCatalogError, match="replay|integrity|mismatch"):
        evaluate_algorithm_plan(catalog, compiled, _market(change_last=True))


@pytest.mark.parametrize("change", [
    lambda x: x.update(python_patch="print('orders')"),
    lambda x: x.update(unmatched="BUY_ALWAYS"),
    lambda x: x.update(position_size_pct=150),
    lambda x: x["cases"][0].update(min_score=1.2),
    lambda x: x["cases"][0]["when"].update(op="cross_above"),
    lambda x: x["cases"][0]["votes"][0].update(weight=-1),
    lambda x: x["cases"][0]["votes"].append(
        {"indicator_id": "time_series_momentum", "weight": 0.5}),
    lambda x: x["cases"][1].update(case_id="calm"),
    lambda x: x.update(cases=[]),
])
def test_reject_unbounded_ambiguous_or_code_like_plan(change):
    plan = _plan().model_dump(mode="json")
    change(plan)
    with pytest.raises(ValidationError):
        AlgorithmPlan.model_validate(plan)


def test_reject_unregistered_or_invalid_role(tmp_path: Path):
    catalog, market = _catalog(tmp_path), _market()
    plan = _plan().model_dump(mode="json")
    plan["cases"][0]["votes"][0]["indicator_id"] = "sma_direction"
    with pytest.raises(ResearchCatalogError, match="entry"):
        compile_algorithm_plan(catalog, AlgorithmPlan.model_validate(plan), market)
    plan = _plan().model_dump(mode="json")
    plan["cases"][0]["when"]["indicator_id"] = "previous_range_breakout"
    with pytest.raises(ResearchCatalogError, match="regime|risk"):
        compile_algorithm_plan(catalog, AlgorithmPlan.model_validate(plan), market)


def test_llm_provider_can_author_typed_plan_without_code_execution(tmp_path: Path):
    catalog, market = _catalog(tmp_path), _market()

    class FakeProvider:
        calls = 0

        def propose(self, context):
            self.calls += 1
            assert context["output_contract"] == "AlgorithmPlan"
            assert context["market"]["data_zone"] == "DEVELOPMENT"
            names = {x["indicator_id"] for x in context["verified_indicators"]}
            assert {"time_series_momentum", "previous_range_breakout",
                    "parkinson_variance"} <= names
            assert "cross_sectional_momentum" not in names
            assert context["execution_policy"] == "RESEARCH_ONLY_NEXT_OPEN"
            assert "raw_price_rows" not in context
            return _plan().model_dump(mode="json")

    provider = FakeProvider()
    compiled = compile_provider_algorithm_plan(catalog, provider, market)
    assert provider.calls == 1
    assert compiled.plan == _plan()
    assert evaluate_algorithm_plan(catalog, compiled, market).trades_count > 0


def test_provider_fail_closed_for_sealed_or_invalid_outputs(tmp_path: Path):
    catalog, market = _catalog(tmp_path), _market()

    class FakeProvider:
        calls = 0

        def propose(self, context):
            self.calls += 1
            return {**_plan().model_dump(mode="json"), "python_patch": "import os"}

    provider = FakeProvider()
    with pytest.raises(ResearchCatalogError, match="development"):
        compile_provider_algorithm_plan(catalog, provider, _market(sealed=True))
    assert provider.calls == 0
    with pytest.raises(ResearchCatalogError, match="validation"):
        compile_provider_algorithm_plan(catalog, provider, market)
    assert provider.calls == 1


def test_reject_unsafe_forged_model_copy(tmp_path: Path):
    catalog, market = _catalog(tmp_path), _market()
    plan = _plan().model_copy(update={"position_size_pct": 300})
    with pytest.raises(ResearchCatalogError, match="validation"):
        compile_algorithm_plan(catalog, plan, market)
