"""Conservative P3 semantic preflight of an inherited StrategyIR mutation.

No execution of model-supplied code, no backtest or trading; this check uses
already verified feature signal vectors and small, provable scalar predicates.
An observed equality applies ONLY to the reused development bars. It is not
a proof of out-of-sample or of universal strategy equivalence.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, cast

from core.backtest.engine import _regime_allows, _rules_match
from core.integrity.hashes import content_hash
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy
from strategy_ir.schema import Condition, RuleSet, StrategyIR


def _implies(a: Condition, b: Condition) -> bool:
    if (
        not a.enabled
        or not b.enabled
        or a.left != b.left
        or a.right is not None
        or b.right is not None
        or type(a.value) not in (int, float)
        or type(b.value) not in (int, float)
    ):
        return False
    av, bv = cast(float, a.value), cast(float, b.value)
    if not isfinite(av) or not isfinite(bv):
        return False
    if a.op == b.op and av == bv:
        return True
    if a.op == "equal":
        x = av
        return (
            (b.op == "equal" and x == bv)
            or (b.op == "less_equal" and x <= bv)
            or (b.op == "less_than" and x < bv)
            or (b.op == "greater_equal" and x >= bv)
            or (b.op == "greater_than" and x > bv)
        )
    lower = {"greater_than", "greater_equal"}
    upper = {"less_than", "less_equal"}
    if a.op in lower and b.op in lower:
        return av > bv or (
            av == bv and (a.op == "greater_than" or b.op == "greater_equal")
        )
    if a.op in upper and b.op in upper:
        return av < bv or (
            av == bv and (a.op == "less_than" or b.op == "less_equal")
        )
    return False


def _symbolic_redundancy(before: StrategyIR, after: StrategyIR) -> str | None:
    """Prove redundancy only for one appended condition with no other changes."""
    if (
        before.features != after.features
        or before.indicators != after.indicators
        or before.regime_filters != after.regime_filters
        or before.risk != after.risk
    ):
        return None
    for name in ("entry", "exit"):
        old: RuleSet = getattr(before, name)
        new: RuleSet = getattr(after, name)
        other = "exit" if name == "entry" else "entry"
        if (
            getattr(before, other) != getattr(after, other)
            or old.logic != new.logic
            or len(new.conditions) != len(old.conditions) + 1
            or new.conditions[:-1] != old.conditions
        ):
            continue
        added = new.conditions[-1]
        if not added.enabled:
            return f"{name}:disabled_added_condition"
        if old.logic == "OR" and any(_implies(added, c) for c in old.conditions):
            return f"{name}:added_predicate_subsumed_by_existing_OR"
        if old.logic == "AND" and any(_implies(c, added) for c in old.conditions):
            return f"{name}:added_predicate_implied_by_existing_AND"
    return None


def inspect_inherited_semantics(
    parent: CompiledAcademicStrategy,
    child: CompiledAcademicStrategy,
    *,
    bars: int,
    dataset_hash: str,
) -> dict[str, Any]:
    if bars <= 0 or not dataset_hash:
        raise ValueError("semantic preflight requires verified development dataset")

    def signals(compiled: CompiledAcademicStrategy) -> dict[str, list[float | None]]:
        values = {k: list(v) for k, v in dict(compiled.replay.signals).items()}
        if (
            not values
            or set(values) != set(compiled.feature_values)
            or any(len(v) != bars for v in values.values())
        ):
            raise ValueError("semantic preflight feature replay identity mismatch")
        return values

    left = signals(parent)
    right = signals(child)

    def bits(
        strategy: StrategyIR,
        values: dict[str, list[float | None]],
    ) -> list[tuple[bool, bool, bool]]:
        for cond in (
            *strategy.entry.conditions,
            *strategy.exit.conditions,
            *strategy.regime_filters,
        ):
            if cond.left not in values or (cond.right is not None and cond.right not in values):
                raise ValueError("semantic preflight references missing replay signal")
        return [
            (
                bool(_rules_match(strategy.entry.conditions, strategy.entry.logic, values, i)),
                bool(_rules_match(strategy.exit.conditions, strategy.exit.logic, values, i)),
                bool(_regime_allows(strategy, values, i)),
            )
            for i in range(bars)
        ]

    parent_bits = bits(parent.strategy, left)
    child_bits = bits(child.strategy, right)
    mismatches = [i for i, (a, b) in enumerate(zip(parent_bits, child_bits, strict=True)) if a != b]
    symbolic = _symbolic_redundancy(parent.strategy, child.strategy)
    same_execution_policy = parent.strategy.risk == child.strategy.risk
    equivalent = not mismatches and same_execution_policy
    rejected = bool(symbolic) or equivalent
    reason = (
        "PROVABLE_CONDITION_SUBSUMPTION"
        if symbolic
        else "DEVELOPMENT_SIGNAL_EQUIVALENCE"
        if equivalent
        else "DIFFERENT_SIGNALS_OR_RISK_POLICY"
    )
    return {
        "schema": "p3-semantic-preflight-v1",
        "reject": rejected,
        "reason": reason,
        "symbolic_witness": symbolic,
        "dataset_hash": dataset_hash,
        "bars_checked": bars,
        "execution_policy_equal": same_execution_policy,
        "signal_change_bars": len(mismatches),
        "first_change_indices": mismatches[:10],
        "parent_signal_digest": content_hash(parent_bits),
        "child_signal_digest": content_hash(child_bits),
        "parent_strategy_hash": parent.strategy_hash,
        "child_strategy_hash": child.strategy_hash,
        "scope": "SCALAR_SYMBOLIC_OR_REUSED_DEVELOPMENT_ONLY_NO_OOS_CLAIM",
    }
