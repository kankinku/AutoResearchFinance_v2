"""Additive S7 quality preflight for the reviewed academic plan compiler.

Legacy research sessions remain replayable: callers must explicitly opt in to
strict rejection of proven static no-ops. This classification is based on the
canonical boolean plan compiler, not hindsight performance or an LLM opinion.
"""

from __future__ import annotations

from typing import Any

from research.indicator_engine.controlled_experiments import SUPPORTED_CONTROLLED_METRICS
from research.llm.diagnostic_research import DiagnosticResponse
from strategy_ir.schema import StrategyIR


def static_noop_hypotheses(
    parent: StrategyIR,
    diagnosis: DiagnosticResponse,
) -> tuple[str, ...]:
    """Prove one narrow redundant filter ablation without reading future bars.

    Academic Plan IR computes plan_entry=0 whenever plan_regime=0. Its outer
    plan_regime entry filter therefore cannot reject a positive plan_entry.
    This proof is only applicable to the unmodified canonical entry/exit
    structure and an otherwise unchanged one-operation filter deletion.
    """
    entry, exit_rule, filters = parent.entry, parent.exit, parent.regime_filters
    if (
        entry.logic != "AND"
        or len(entry.conditions) != 1
        or exit_rule.logic != "OR"
        or len(exit_rule.conditions) != 1
        or len(filters) != 1
    ):
        return ()
    entry_cond, exit_cond, filt = entry.conditions[0], exit_rule.conditions[0], filters[0]
    if not (
        entry_cond.enabled
        and exit_cond.enabled
        and filt.enabled
        and entry_cond.left == exit_cond.left == "plan_entry"
        and entry_cond.op == "greater_than"
        and entry_cond.value == 0.5
        and exit_cond.op == "less_equal"
        and exit_cond.value == 0.5
        and filt.left == "plan_regime"
        and filt.op == "greater_than"
        and filt.value == 0.5
    ):
        return ()
    return tuple(
        h.hypothesis_id
        for h in diagnosis.hypotheses
        if len(h.next_intent.operations) == 1
        and h.next_intent.operations[0].op == "REMOVE_REGIME_FILTER"
        and h.next_intent.operations[0].path == "regime_filters.0"
    )


def academic_diagnostic_quality_hint() -> dict[str, Any]:
    """A prompt-side hint only, excluded from the persisted context hash."""
    return {
        "schema": "academic-s7-quality-guidance-v1",
        "default_legacy_policy": "ALLOW_REPLAYABLE_NO_EFFECT",
        "strict_mcp_option": {"require_signal_change": True},
        # The typed DiagnosticResponse includes metrics not yet implemented by
        # S7; advertise the narrower runnable set BEFORE the model submits.
        "supported_controlled_metrics": sorted(SUPPORTED_CONTROLLED_METRICS),
        "known_static_noop": (
            "For the canonical AlgorithmPlan, removing its only outer "
            "regime_filters.0 (plan_regime > 0.5) never changes executions: "
            "plan_entry cannot be positive while plan_regime is nonpositive. "
            "Do not submit this as a new exploratory hypothesis."
        ),
        # This guidance is advisory only; a multi-operation mutation may still
        # be useful for engineering a compound policy. It cannot be used to
        # attribute measured performance to one changed rule.
        "causal_attribution_guidance": {
            "single_intervention": (
                "Prefer one changed semantic rule per hypothesis while diagnosing "
                "which component affects executions or metrics. Keep the same "
                "parent, market, and fee model as the unchanged control."
            ),
            "multi_intervention": (
                "Multi-operation experiments are allowed for strategy design, "
                "but their measured return or trade-count difference is JOINT, "
                "not attributable to any single operation. Test entry-only "
                "and exit-only ablations separately if both were changed."
            ),
            "ablation_design": {
                "same_parent_for_all": True,
                "separate_entry_only": True,
                "separate_exit_only": True,
                "report_each_trade_count_costs_and_return": True,
                "label": "REUSED_DEVELOPMENT_NOT_INDEPENDENT_CAUSAL_PROOF",
            },
        },
        "informative_reviewed_example": {
            "test_design": "RULE_STRUCTURE",
            "next_intent": {
                "mode": "structure",
                "operations": [
                    {
                        "op": "REPLACE_RULE",
                        "path": "entry.conditions.0",
                        "condition": {
                            "op": "greater_than",
                            "left": "plan_vote_score",
                            "value": 0.8,
                        },
                    },
                ],
            },
            "caution": (
                "Entry-only intervention example, not guaranteed improvement; "
                "if exit changes are desired, submit a separate hypothesis "
                "with the same unchanged parent. Only measured fees, trades, "
                "and signed evidence support a development comparison."
            ),
        },
    }
