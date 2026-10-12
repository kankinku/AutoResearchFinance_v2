"""Bounded deterministic hypotheses derived from verified failed development attempts.

Research proposals are not causal diagnoses. Never relax evaluation gates, read
sealed OOS, promote candidates, or call an LLM from a local batch worker.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

from experiments.candidate_generator import generate_candidates
from experiments.identity import semantic_strategy_hash
from memory.rescue_pool import VerifiedRescue
from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain
from strategy_ir.schema import StrategyIR

_SUPPORTED_GATES = frozenset(
    {
        "robustness",
        "validation",
        "fast",
        "full",
        "annual_trade_count",
        "risk",
        "qqq_cagr_delta",
    }
)


def verified_failed_gates(
    events: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    attempt_id: str,
) -> tuple[str, ...] | None:
    """Return only verified all-REJECT candidate gates from immutable Evidence."""
    matching = [
        event.get("payload")
        for event in events
        if event.get("kind") == "attempt" and event.get("id") == f"attempt:{attempt_id}"
    ]
    if len(matching) != 1 or not isinstance(matching[0], dict):
        return None
    attempt = matching[0]
    if (
        attempt.get("research_run_id") != run_id
        or attempt.get("attempt_id") != attempt_id
        or attempt.get("status") != "COMPLETED"
        or attempt.get("verification") is not None
        or not isinstance(attempt.get("execution"), dict)
    ):
        return None
    candidates = attempt.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    if any(
        not isinstance(c, dict)
        or c.get("status") != "REJECT"
        or not isinstance(c.get("candidate_hash"), str)
        or not isinstance(c.get("semantic_strategy_hash"), str)
        for c in candidates
    ):
        return None
    counter: Counter[str] = Counter()
    for candidate in candidates:
        gates = candidate.get("failed_gates")
        if not isinstance(gates, list) or not all(isinstance(g, str) for g in gates):
            return None
        counter.update(set(gates) & _SUPPORTED_GATES)
    return tuple(g for g, _ in sorted(counter.items(), key=lambda item: (-item[1], item[0])))


@dataclass(frozen=True)
class LocalHypothesis:
    reason_code: str
    trigger_gate: str
    applied_after_attempt_id: str
    operations: tuple[MutationOperation, ...]
    domains: tuple[ParameterDomain, ...]
    preview_new_candidates: int
    rescue_candidate_hash: str | None = None

    def summary(self) -> dict[str, object]:
        return {
            "reason_code": self.reason_code,
            "trigger_gate": self.trigger_gate,
            "based_on_attempt_id": self.applied_after_attempt_id,
            "preview_new_candidates": self.preview_new_candidates,
            "experiment_paths": [
                *(op.path for op in self.operations if op.path),
                *(d.name for d in self.domains),
            ],
            "causal_status": "HYPOTHESIS_NOT_VERIFIED_CAUSE",
            "validation_scope": "REUSED_DEVELOPMENT_DATA_NOT_INDEPENDENT_OOS",
            "controller": "BOUNDED_LOCAL_REPLANNING_NO_LLM_CALL",
            "crossover_parent_ids": [
                op.other.strategy_id for op in self.operations if op.other is not None
            ],
            "rescue_source_candidate_hash": self.rescue_candidate_hash,
        }


def propose_next_hypothesis(
    *,
    parent: StrategyIR,
    initial_operations: tuple[MutationOperation, ...],
    initial_domains: tuple[ParameterDomain, ...],
    gate_names: tuple[str, ...],
    prior_attempt_id: str,
    used_hypotheses: frozenset[str],
    already_evaluated: frozenset[str],
    method: str,
    count: int,
    next_seed: int,
    partner: StrategyIR | None = None,
    rescue: VerifiedRescue | None = None,
) -> LocalHypothesis | None:
    """Explore a tiny approved IR mutation menu; accept only unseen semantics."""
    if not gate_names:
        return None

    variants: list[tuple[str, str, tuple[MutationOperation, ...], tuple[ParameterDomain, ...]]] = []
    preferred = next((gate for gate in gate_names if gate in _SUPPORTED_GATES), None)
    if preferred is None:
        return None

    def risk_domain(name: str, values: tuple[float, float], label: str) -> None:
        # At most four total parameter axes. Do not silently extend user budget.
        if len(initial_domains) >= 4 or any(d.name == name for d in initial_domains):
            return
        variants.append(
            (
                label,
                preferred,
                initial_operations,
                (*initial_domains, ParameterDomain(name, values)),
            )
        )

    def entry_variants() -> None:
        for index, condition in enumerate(parent.entry.conditions):
            value = condition.value
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(value)
                or condition.op
                not in {
                    "less_than",
                    "less_equal",
                    "greater_than",
                    "greater_equal",
                }
            ):
                continue
            for modifier, suffix in ((-1.0, "TIGHTER"), (1.0, "LOOSER")):
                payload = condition.model_dump(mode="python")
                payload["value"] = round(float(value) + modifier, 6)
                variants.append(
                    (
                        f"ENTRY_THRESHOLD_EXPERIMENT_{suffix}",
                        preferred,
                        (
                            *initial_operations,
                            MutationOperation("REPLACE_RULE", f"entry.conditions.{index}", payload),
                        ),
                        initial_domains,
                    )
                )
            break

    position = parent.risk.position_size_pct
    sizing = tuple(v for v in (75.0, 50.0, 25.0, 100.0) if v != position)[:2]
    stop = parent.risk.stop_loss_pct
    stop_values = tuple(
        v for v in (round(max(0.2, stop * 0.65), 3), round(max(0.5, stop * 1.35), 3)) if v != stop
    )
    profit = parent.risk.take_profit_pct
    profit_values = (round(profit + 1.0, 3), round(profit + 2.0, 3))

    if preferred in {"validation", "fast", "full", "annual_trade_count"}:
        entry_variants()
    if preferred in {"robustness", "risk", "validation", "fast", "full", "annual_trade_count"}:
        if len(sizing) == 2:
            risk_domain(
                "risk.position_size_pct", (sizing[0], sizing[1]), "RISK_POSITION_SIZING_EXPERIMENT"
            )
        if len(stop_values) == 2:
            risk_domain(
                "risk.stop_loss_pct", (stop_values[0], stop_values[1]), "RISK_STOP_LOSS_EXPERIMENT"
            )
    if preferred in {"robustness", "risk"}:
        entry_variants()
    risk_domain("risk.take_profit_pct", profit_values, "RISK_TAKE_PROFIT_EXPERIMENT")

    # Structural fallbacks are attempted only after the bounded entry/risk menu.
    # The mutation engine and strategy validator, not this planner, determine
    # whether a proposed Strategy IR is executable and semantically novel.
    for index, condition in enumerate(parent.exit.conditions):
        value = condition.value
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
            and condition.op in {"less_than", "less_equal", "greater_than", "greater_equal"}
        ):
            for delta, label in (
                (-1.0, "EXIT_THRESHOLD_EXPERIMENT_TIGHTER"),
                (1.0, "EXIT_THRESHOLD_EXPERIMENT_LOOSER"),
            ):
                payload = condition.model_dump(mode="python")
                payload["value"] = round(float(value) + delta, 6)
                variants.append(
                    (
                        label,
                        preferred,
                        (
                            *initial_operations,
                            MutationOperation("REPLACE_RULE", f"exit.conditions.{index}", payload),
                        ),
                        initial_domains,
                    )
                )
            break

    # A registered RSI confirmation alongside the existing entry signal is
    # an actual indicator/rule composition, rather than a parameter-only edit.
    # Avoid shadowing an existing RSI signal or an existing generated alias.
    alias = "adaptive_rsi_14"
    if alias not in parent.indicators and not any(
        item.type == "RSI" for item in parent.indicators.values()
    ):
        variants.append(
            (
                "INDICATOR_RSI_ENTRY_CONFIRMATION",
                preferred,
                (
                    *initial_operations,
                    MutationOperation(
                        "ADD_INDICATOR",
                        f"indicators.{alias}",
                        {"type": "RSI", "period": 14, "parameters": {}},
                    ),
                    MutationOperation(
                        "ADD_RULE",
                        "entry.conditions",
                        {"left": alias, "op": "less_equal", "value": 35, "enabled": True},
                    ),
                    MutationOperation("CHANGE_AND_OR", "entry.logic", "AND"),
                ),
                initial_domains,
            )
        )

    # Crossover is only available with an explicitly registered second parent.
    # Never infer eligible partners from unverified/rejected candidate hashes.
    if (
        partner is not None
        and partner.strategy_id != parent.strategy_id
        and partner.exit != parent.exit
    ):
        variants.append(
            (
                "CROSSOVER_REGISTERED_PARENT_EXIT",
                preferred,
                (*initial_operations, MutationOperation("CROSSOVER", other=partner)),
                initial_domains,
            )
        )

    # Rescue is a structural experiment with an independently verified IR.
    if rescue is not None and rescue.strategy.exit != parent.exit:
        variants.append(
            (
                "RESCUE_VERIFIED_NEAR_MISS_EXIT",
                preferred,
                (*initial_operations, MutationOperation("CROSSOVER", other=rescue.strategy)),
                initial_domains,
            )
        )

    for label, trigger, operations, domains in variants:
        if label in used_hypotheses:
            continue
        try:
            candidates = generate_candidates(
                parent,
                operations,
                domains,
                method=method,
                count=count,
                seed=next_seed,
            )
        except (TypeError, ValueError):
            continue
        novel = {
            semantic_strategy_hash(candidate.strategy) for candidate in candidates
        } - already_evaluated
        if novel:
            return LocalHypothesis(
                label,
                trigger,
                prior_attempt_id,
                operations,
                domains,
                len(novel),
                rescue.candidate_hash
                if rescue is not None and label.startswith("RESCUE_")
                else None,
            )
    return None
