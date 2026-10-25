"""T4-P5: prevent wrong feature units and opt-in non-trading plans before staging."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from research.llm.t4_feature_units import (
    FeatureUnitMismatch,
    verified_feature_unit_guidance,
    verify_feature_condition_ranges,
)
from strategy_ir.schema import Condition, FeatureRef
from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture


def _stc_strategy(*, section: str, cutoff: float, op: str = "greater_than"):
    parent, _ = _warmup_fixture()
    strategy = parent.strategy.model_copy(deep=True)
    strategy.features["stc_cycle"] = FeatureRef(
        feature_id="schaff_trend_cycle",
        timeframe="1d",
        lookback=14,
        inputs=("close",),
    )
    condition = Condition(op=op, left="stc_cycle", value=cutoff)
    if section == "entry":
        strategy.entry.conditions.append(condition)
    elif section == "exit":
        strategy.exit.conditions.append(condition)
    else:
        strategy.regime_filters.append(condition)
    return strategy


@pytest.mark.parametrize(
    ("section", "cutoff", "op"),
    [
        ("entry", 50.0, "greater_than"),
        ("exit", 25.0, "less_equal"),
        ("regime", -2.0, "greater_than"),
    ],
)
def test_canonical_normalized_stc_thresholds_outside_unit_range_rejected(
    section: str,
    cutoff: float,
    op: str,
):
    with pytest.raises(FeatureUnitMismatch, match="FEATURE_THRESHOLD_OUTSIDE_DOMAIN"):
        verify_feature_condition_ranges(
            _stc_strategy(section=section, cutoff=cutoff, op=op),
        )


@pytest.mark.parametrize("threshold", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_correct_unit_stc_thresholds_remain_executable(threshold: float):
    verify_feature_condition_ranges(_stc_strategy(section="entry", cutoff=threshold))


def test_unknown_feature_unit_not_invented():
    details = verified_feature_unit_guidance()
    assert details["registered_feature_units"]["schaff_trend_cycle"]["value_range"] == [0.0, 1.0]
    assert (
        details["registered_feature_units"]["schaff_trend_cycle"]["scale"] == "normalized_fraction"
    )
    assert details["unlisted_feature_policy"] == "UNKNOWN_DO_NOT_ASSUME"
    assert "normalized_atr_percent" not in details["registered_feature_units"]


def test_unrelated_indicator_rules_left_unchanged():
    from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture

    parent, _ = _warmup_fixture()
    verify_feature_condition_ranges(parent.strategy)


def test_p5_existing_session_model_context_includes_unit_advice_without_mutation():
    root = Path("/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021")
    state_dir = Path("/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024")
    if not (state_dir / "p5_session_id.txt").exists():
        pytest.skip("isolated P5 state not mounted")
    svc = AcademicMCPCheckpointService(
        project_root=root,
        state_dir=state_dir,
        parent_portfolio_v2=True,
        generalization_parent_v1=True,
        p4_quality_gate_v1=True,
        p4_s7_quality_v1=True,
    )
    sid = (state_dir / "p5_session_id.txt").read_text().strip()
    before = svc.get({"session_id": sid})
    assert before["completed_generations"] >= 27
    note = before["model_context"]["feature_unit_guidance"]
    assert note["registered_feature_units"]["schaff_trend_cycle"]["value_range"] == [0.0, 1.0]
    after = svc.get({"session_id": sid})
    assert before["history"] == after["history"]
    assert before["checkpoint_token"] == after["checkpoint_token"]


def test_registered_stc_calculator_emits_normalized_percentile_not_0_to_100():
    from math import cos

    from core.features.calculators import calculate_feature
    from core.features.registry import research_feature_specs

    spec = next(x for x in research_feature_specs() if x.name == "schaff_trend_cycle")
    close = tuple(120.0 + 0.015 * i + 3.0 * cos(i / 7.0) for i in range(240))
    observed = [v for v in calculate_feature(spec, {"close": close}) if v is not None]
    assert len(observed) > 20
    assert all(0.0 <= v <= 1.0 for v in observed)
    assert min(observed) < 0.25 and max(observed) > 0.75


def test_opt_in_no_trades_gate_uses_actual_fills_not_model_scores():
    from types import SimpleNamespace

    from research.llm.t4_feature_units import require_nonempty_executions

    with pytest.raises(ValueError, match="NO_EXECUTED_TRADES_PRECOMMIT"):
        require_nonempty_executions(SimpleNamespace(fills=(), round_trips=()))
    with pytest.raises(ValueError, match="NO_EXECUTED_TRADES_PRECOMMIT"):
        require_nonempty_executions(SimpleNamespace(fills=("buy",), round_trips=()))
    require_nonempty_executions(SimpleNamespace(fills=("buy", "sell"), round_trips=("trade-1",)))


def test_legacy_no_trade_policy_remains_opt_in_and_historical_evidence_unchanged():
    from types import SimpleNamespace

    from research.llm.t4_feature_units import require_nonempty_executions

    require_nonempty_executions(SimpleNamespace(fills=(), round_trips=()), required=False)


def test_real_checkpoint_zero_activity_opt_in_rejection_does_not_consume_plan_token(tmp_path):
    from tests.integrations.test_quant_p4_s7_precommit import _svc
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    svc = _svc(tmp_path)
    started = svc.start({"data_path": "data/study.parquet", "generations": 1})
    plan = ScriptedResearcher().propose(started["model_context"])
    # Both branches request impossible negative Parkinson variance, and
    # FLAT unmatched branch: executable StrategyIR, zero actual closed fills.
    for branch in plan["cases"]:
        branch["when"]["op"] = "less_equal"
        branch["when"]["threshold"] = -1.0
    args = {
        "session_id": started["session_id"],
        "checkpoint_token": started["checkpoint_token"],
        "plan": plan,
        "require_trade_activity": True,
    }
    with pytest.raises(ValueError, match="NO_EXECUTED_TRADES_PRECOMMIT"):
        svc.submit_plan(args)
    after = svc.get({"session_id": started["session_id"]})
    assert after["completed_generations"] == 0
    assert after["checkpoint_phase"] == "AWAITING_PLAN"
    assert after["checkpoint_token"] == started["checkpoint_token"]
    assert after["history"] == started["history"]
    assert not after["orders_enabled"] and not after["independent_oos_approved"]

    # Same token remains usable: no silent policy downgrade or time-travel.
    valid_plan = ScriptedResearcher().propose(after["model_context"])
    staged = svc.submit_plan({**args, "plan": valid_plan})
    assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    assert staged["completed_generations"] == 0
    assert staged["model_context"]["observations"]["closed_trades"] > 0


def test_require_trade_activity_must_be_exact_boolean(tmp_path):
    from tests.integrations.test_quant_p4_s7_precommit import _svc
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    svc = _svc(tmp_path)
    state = svc.start({"data_path": "data/study.parquet", "generations": 1})
    args = {
        "session_id": state["session_id"],
        "checkpoint_token": state["checkpoint_token"],
        "plan": ScriptedResearcher().propose(state["model_context"]),
        "require_trade_activity": "true",
    }
    with pytest.raises(ValueError, match="require_trade_activity must be a boolean"):
        svc.submit_plan(args)
