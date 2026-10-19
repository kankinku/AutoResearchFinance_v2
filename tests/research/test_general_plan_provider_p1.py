"""P1-3: opt-in typed LLM plan -> causally validated costed research replay."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.general_plan import (
    GeneralResearchPlan,
    GeneralResearchPlanError,
    build_general_plan_context,
    compile_general_research_plan,
    compile_provider_general_plan,
    evaluate_general_research_plan,
)


def _price_market(*, change_last=False, zone=DataZone.DEVELOPMENT):
    bars = []
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    pattern = [90.0, 92.0, 97.0, 102.0, 107.0, 113.0, 116.0, 112.0, 104.0, 96.0, 89.0, 86.0]
    for i in range(96):
        price = pattern[i % len(pattern)]
        if i == 95 and change_last:
            price = 160.0
        bars.append(
            Bar(t0 + timedelta(days=i), "QQQ", price, price + 2.0, price - 2.0, price, 100_000.0)
        )
    return MarketDataSet("p1-3-synthetic", zone, tuple(bars))


def _src(name="close"):
    return {"op": "source", "name": name}


def _const(value):
    return {"op": "const", "value": float(value)}


def _op(operator, *args, **other):
    return {"op": operator, "args": list(args), **other}


def _expression_plan():
    return {
        "plan_id": "new_arithmetic_plan",
        "entry": {
            "kind": "expression",
            "expression": _op(
                "and",
                _op("cross_above", _src(), _const(100)),
                _op("gt", _src(), _op("rolling_mean", _src(), window=3)),
            ),
        },
        "exit": {
            "kind": "expression",
            "expression": _op("lt", _src(), _const(96)),
        },
        "position_size_pct": 100,
    }


def _machine_plan():
    return {
        "machine_id": "swing_wait_machine",
        "states": [
            {"name": "idle"},
            {"name": "armed", "timeout_bars": 4, "timeout_to": "idle"},
            {"name": "triggered"},
        ],
        "initial_state": "idle",
        "transitions": [
            {
                "transition_id": "arm",
                "from_state": "idle",
                "to_state": "armed",
                "when": _op("gt", _src(), _const(100)),
            },
            {
                "transition_id": "fire",
                "from_state": "armed",
                "to_state": "triggered",
                "when": _op("gt", _src(), _const(110)),
            },
            {
                "transition_id": "reset",
                "from_state": "triggered",
                "to_state": "idle",
                "when": _op("lt", _src(), _const(95)),
            },
        ],
        "signal_on_states": ["triggered"],
    }


def _state_plan():
    return {
        "plan_id": "custom_state_sequence",
        "entry": {"kind": "state_machine", "state_machine": _machine_plan()},
        "exit": {"kind": "expression", "expression": _op("lt", _src(), _const(95))},
        "position_size_pct": 100,
    }


def test_external_provider_authors_arbitrary_nested_math_and_replays_canonically():
    market = _price_market()

    class Provider:
        seen = None

        def propose(self, context):
            self.seen = context
            assert context["output_contract"] == "GeneralResearchPlan"
            assert context["market"]["data_zone"] == "DEVELOPMENT"
            assert context["available_sources"] == ("open", "high", "low", "close", "volume")
            assert "raw_market_rows" not in context
            assert "sealed_oos" not in context
            return _expression_plan()

    provider = Provider()
    compiled = compile_provider_general_plan(provider, market)
    result = evaluate_general_research_plan(compiled, market)
    assert provider.seen is not None
    assert compiled.compiled.strategy.entry.conditions[0].left == "plan_entry"
    assert compiled.compiled.strategy.exit.conditions[0].left == "plan_exit"
    assert compiled.status == "NON_PIT_DEVELOPMENT_ONLY"
    assert not compiled.broker_executable
    assert not result.broker_executable and not result.candidate_promotable
    assert result.status == "NON_PIT_DEVELOPMENT_RESULT"
    assert result.trades_count >= 2
    assert result.total_paid_costs > 0
    assert result == evaluate_general_research_plan(compiled, market)


def test_provider_can_generate_state_machine_and_expression_exit():
    market = _price_market()
    compiled = compile_provider_general_plan(
        type("FixtureProvider", (), {"propose": lambda self, context: _state_plan()})(),
        market,
    )
    signals = compiled.compiled.feature_values
    assert signals["plan_entry"][5] == 1.0
    assert signals["plan_exit"][10] == 1.0
    assert compiled.entry_trace_hash is not None
    assert compiled.exit_trace_hash is None
    result = evaluate_general_research_plan(compiled, market)
    assert result.trades_count > 1


def test_provider_contract_is_generic_and_does_not_privilege_pine_examples():
    market = _price_market()
    info = build_general_plan_context(market)
    assert info["execution_policy"] == "RESEARCH_ONLY_NEXT_OPEN"
    assert info["position_sizing"] == "FIXED_100_PCT_CASH_ONLY"
    assert "source_code" not in info
    assert "preferred_strategies" not in info
    assert "Pine" not in repr(info)
    assert "machine_id" in repr(info["general_plan_schema"])
    assert "output_contract" in info


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(python_code="import os"),
        lambda p: p.update(position_size_pct=150),
        lambda p: p.update(entry={"kind": "expression", "expression": _src("future_close")}),
        lambda p: p.update(entry={"kind": "expression", "expression": _const(10)}),
        lambda p: p.update(
            entry={"kind": "expression", "expression": _op("gt", _src("vix"), _const(20))}
        ),
        lambda p: p.update(
            entry={
                "kind": "state_machine",
                "state_machine": _machine_plan(),
                "expression": _const(10),
            }
        ),
        lambda p: p.update(exit={"kind": "expression", "state_machine": _machine_plan()}),
        lambda p: p.update(
            exit={"kind": "state_machine", "state_machine": {"code": "strategy.entry(1)"}}
        ),
        lambda p: p.update(
            exit={
                "kind": "expression",
                "expression": {"op": "const", "value": True, "secret": True},
            }
        ),
    ],
)
def test_provider_rejects_unsafe_or_unavailable_plan(change):
    invalid = _expression_plan()
    change(invalid)
    with pytest.raises((ValidationError, GeneralResearchPlanError)):
        compile_general_research_plan(invalid, _price_market())


def test_non_dev_wrong_market_and_tampering_fail_closed():
    market = _price_market()
    with pytest.raises(GeneralResearchPlanError, match="DEVELOPMENT|development"):
        compile_general_research_plan(_expression_plan(), _price_market(zone=DataZone.SEALED_OOS))
    compiled = compile_general_research_plan(_state_plan(), market)
    with pytest.raises(GeneralResearchPlanError, match="data|mismatch|integrity"):
        evaluate_general_research_plan(compiled, _price_market(change_last=True))
    with pytest.raises(GeneralResearchPlanError, match="integrity|mismatch"):
        evaluate_general_research_plan(replace(compiled, plan_hash="f" * 64), market)
    changed = dict(compiled.compiled.feature_values)
    changed["plan_entry"] = tuple(1.0 for _ in market.bars)
    with pytest.raises(GeneralResearchPlanError, match="integrity|mismatch"):
        evaluate_general_research_plan(
            replace(compiled, compiled=replace(compiled.compiled, feature_values=changed)),
            market,
        )


def test_later_bar_changes_never_repaint_prior_state_decisions():
    before = compile_general_research_plan(_state_plan(), _price_market())
    after = compile_general_research_plan(_state_plan(), _price_market(change_last=True))
    for key, original in before.compiled.feature_values.items():
        assert original[:-1] == after.compiled.feature_values[key][:-1]
    assert before.compiled.replay.replay_hash != after.compiled.replay.replay_hash


def test_rejection_of_forged_pydantic_model_copy_and_numeric_bad_input():
    typed = GeneralResearchPlan.model_validate(_expression_plan())
    copied = typed.model_copy(update={"position_size_pct": 400})
    with pytest.raises(GeneralResearchPlanError):
        compile_general_research_plan(copied, _price_market())
    src = _expression_plan()
    src["entry"]["expression"]["args"][0]["args"][1] = {"op": "const", "value": float("nan")}
    with pytest.raises((ValidationError, GeneralResearchPlanError)):
        compile_general_research_plan(src, _price_market())


def test_prior_algorithm_plan_and_strategy_ir_remain_unchanged(tmp_path):
    from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
    from research.indicator_engine.catalog import ResearchCatalog
    from research.indicator_engine.seed import seed_approved_references
    from research.indicator_engine.signals import verify_signal_on_synthetic_prices

    catalog = ResearchCatalog(tmp_path / "baseline.sqlite")
    seed_approved_references(catalog)
    for name in ("sma_direction", "time_series_momentum"):
        item = catalog.get_indicator(name)
        catalog.verify_and_register(name, verify_signal_on_synthetic_prices(item))
    legacy = AlgorithmPlan.model_validate(
        {
            "plan_id": "legacy_plan",
            "cases": [
                {
                    "case_id": "uptrend",
                    "when": {
                        "indicator_id": "sma_direction",
                        "op": "greater_than",
                        "threshold": 0.5,
                    },
                    "votes": [{"indicator_id": "time_series_momentum", "weight": 1}],
                    "min_score": 0.5,
                }
            ],
            "unmatched": "FLAT",
            "position_size_pct": 100,
        }
    )
    original = compile_algorithm_plan(catalog, legacy, _price_market())
    assert compile_algorithm_plan(catalog, legacy, _price_market()) == original


def test_canonical_next_open_fills_from_prior_completed_expression_signal():
    compiled = compile_general_research_plan(_expression_plan(), _price_market())
    result = evaluate_general_research_plan(compiled, _price_market())
    market = _price_market()
    sources = compiled.compiled.feature_values
    assert result.trades
    for fill in result.trades:
        t = next(i for i, b in enumerate(market.bars) if b.timestamp.isoformat() == fill.timestamp)
        assert t > 0
        assert sources["plan_entry" if fill.side == "buy" else "plan_exit"][t - 1] == 1.0
        assert fill.price == market.bars[t].open


def test_validation_declines_unsupported_market_shape_and_unbounded_input():
    original = _price_market()
    restricted = MarketDataSet(
        "p1-3-synthetic", DataZone.DEVELOPMENT, original.bars, timeframe="15m"
    )
    with pytest.raises(GeneralResearchPlanError, match="1d"):
        build_general_plan_context(restricted)
    multi = MarketDataSet(
        "p1-3-multi",
        DataZone.DEVELOPMENT,
        (*original.bars, Bar(original.bars[0].timestamp, "SPY", 100, 101, 99, 100, 1000)),
    )
    with pytest.raises(GeneralResearchPlanError, match="single-asset"):
        compile_general_research_plan(_expression_plan(), multi)


def test_provider_rejects_extra_unsafe_keys_instead_of_silent_stripping():
    market = _price_market()

    class Provider:
        def propose(self, context):
            return {**_expression_plan(), "execution_mode": "REAL_BROKER"}

    with pytest.raises(GeneralResearchPlanError, match="provider output validation"):
        compile_provider_general_plan(Provider(), market)


def test_provider_never_mutates_input_context_or_exposes_prices():
    market = _price_market()

    class Provider:
        def propose(self, context):
            context["available_sources"] = []
            context["execution_policy"] = "BROKER_TRADES"
            return _expression_plan()

    original = build_general_plan_context(market)
    compile_provider_general_plan(Provider(), market)
    assert build_general_plan_context(market) == original


def test_both_entry_and_exit_can_be_independent_stateful_algorithms():
    candidate = _state_plan()
    candidate["exit"] = {
        "kind": "state_machine",
        "state_machine": {
            "machine_id": "reversion_exit",
            "states": [{"name": "watch"}, {"name": "ready"}],
            "initial_state": "watch",
            "transitions": [
                {
                    "transition_id": "exit_trigger",
                    "from_state": "watch",
                    "to_state": "ready",
                    "when": _op("lt", _src(), _const(95)),
                },
                {
                    "transition_id": "rearm",
                    "from_state": "ready",
                    "to_state": "watch",
                    "when": _op("gt", _src(), _const(105)),
                },
            ],
            "signal_on_states": ["ready"],
        },
    }
    market = _price_market()
    compiled = compile_general_research_plan(candidate, market)
    assert compiled.entry_trace_hash is not None
    assert compiled.exit_trace_hash is not None
    assert compiled.compiled.feature_values["plan_entry"][5] == 1.0
    assert compiled.compiled.feature_values["plan_exit"][10] == 1.0
    assert evaluate_general_research_plan(compiled, market).trades_count >= 2
