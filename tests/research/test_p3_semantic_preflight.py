"""P3 semantic guard: provable scalar subset and sampled execution-gate identity."""

from __future__ import annotations

from copy import deepcopy

import pytest

from research.llm.p3_semantic_preflight import _implies, _symbolic_redundancy
from strategy_ir.schema import Condition, StrategyIR


def c(op: str, value: float, *, left: str = "vote") -> Condition:
    return Condition(op=op, left=left, value=value)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (c("less_equal", 0.25), c("less_equal", 0.5), True),
        (c("less_than", 0.5), c("less_equal", 0.5), True),
        (c("less_equal", 0.5), c("less_than", 0.5), False),
        (c("greater_than", 0.75), c("greater_equal", 0.75), True),
        (c("greater_equal", 0.75), c("greater_than", 0.75), False),
        (c("equal", 0.5), c("less_equal", 0.5), True),
        (c("equal", 0.5), c("greater_than", 0.5), False),
        (c("less_equal", 0.5), c("less_equal", 0.25), False),
        (c("less_equal", 0.25), c("less_equal", 0.5, left="different"), False),
    ],
)
def test_implies_boundaries(a, b, expected):
    assert _implies(a, b) is expected


def sample_strategy():
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "strategy_id": "base",
            "family": "test",
            "generation": 1,
            "indicators": {"ema": {"type": "EMA", "period": 20}},
            "features": {"vote": {"feature_id": "simple"}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "vote", "value": 0.5}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "less_equal", "left": "vote", "value": 0.5}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0, "position_size_pct": 100},
        }
    )


def test_provable_or_condition_subsumption():
    parent = sample_strategy()
    newer = deepcopy(parent)
    newer.exit.conditions.append(c("less_equal", 0.25))
    assert _symbolic_redundancy(parent, newer) == ("exit:added_predicate_subsumed_by_existing_OR")
    newer.exit.conditions[-1] = c("less_equal", 0.75)
    assert _symbolic_redundancy(parent, newer) is None


def test_provable_and_condition_subsumption():
    parent = sample_strategy()
    parent.entry.conditions = [c("greater_than", 0.75)]
    newer = deepcopy(parent)
    newer.entry.conditions.append(c("greater_than", 0.5))
    assert _symbolic_redundancy(parent, newer) == ("entry:added_predicate_implied_by_existing_AND")


def test_policy_or_other_exit_change_does_not_claim_universal_equivalence():
    parent = sample_strategy()
    newer = deepcopy(parent)
    newer.exit.conditions.append(c("less_equal", 0.25))
    newer.risk.position_size_pct = 50
    assert _symbolic_redundancy(parent, newer) is None
    newer.risk.position_size_pct = 100
    newer.entry.conditions.append(c("greater_than", 0.75))
    assert _symbolic_redundancy(parent, newer) is None


def make_compiled_for_signals(strategy, vote, *, key="vote"):
    from types import SimpleNamespace

    return SimpleNamespace(
        strategy=strategy,
        strategy_hash="mock-" + key + str(len(vote)),
        replay=SimpleNamespace(signals=((key, tuple(vote)),)),
        feature_values={key: tuple(vote)},
    )


def test_observed_same_binary_signal_but_not_universal_equivalence():
    from research.llm.p3_semantic_preflight import inspect_inherited_semantics

    parent = sample_strategy()
    child = deepcopy(parent)
    child.exit.conditions.append(c("less_equal", 0.75))
    old = make_compiled_for_signals(parent, [0.0, 1.0, 1.0, 0.0])
    new = make_compiled_for_signals(child, [0.0, 1.0, 1.0, 0.0])
    report = inspect_inherited_semantics(old, new, bars=4, dataset_hash="verified-dev")
    assert report["reject"] is True
    assert report["reason"] == "DEVELOPMENT_SIGNAL_EQUIVALENCE"
    assert report["symbolic_witness"] is None
    assert report["signal_change_bars"] == 0
    assert report["scope"].endswith("NO_OOS_CLAIM")


def test_observed_signal_difference_is_not_rejected():
    from research.llm.p3_semantic_preflight import inspect_inherited_semantics

    parent = sample_strategy()
    child = deepcopy(parent)
    child.exit.conditions.append(c("less_equal", 0.75))
    old = make_compiled_for_signals(parent, [0.0, 0.6, 1.0, 0.0])
    new = make_compiled_for_signals(child, [0.0, 0.6, 1.0, 0.0])
    report = inspect_inherited_semantics(old, new, bars=4, dataset_hash="verified-dev")
    assert report["reject"] is False
    assert report["signal_change_bars"] == 1
    assert report["first_change_indices"] == [1]


def test_same_signals_but_new_risk_policy_is_not_falsely_rejected():
    from research.llm.p3_semantic_preflight import inspect_inherited_semantics

    parent = sample_strategy()
    child = deepcopy(parent)
    child.risk.position_size_pct = 50
    old = make_compiled_for_signals(parent, [0.0, 1.0, 1.0, 0.0])
    new = make_compiled_for_signals(child, [0.0, 1.0, 1.0, 0.0])
    report = inspect_inherited_semantics(old, new, bars=4, dataset_hash="verified-dev")
    assert report["reject"] is False
    assert report["execution_policy_equal"] is False
