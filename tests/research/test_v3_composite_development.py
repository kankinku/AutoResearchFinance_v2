"""C composite descendants: real canonical S2, P2 and S7 controlled replay."""

from dataclasses import replace

import pytest

from core.backtest.p2_policy import ChildRiskBudget
from core.integrity.hashes import content_hash
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.llm.composite_crossover_v3 import VerifiedDonor, compose
from research.llm.composite_validation_v3 import CompositeValidationError, validate_composite
from research.llm.diagnostic_research import build_diagnostic_context
from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture


def _inputs():
    baseline, market = _warmup_fixture()
    donors = {}
    compiled = {}
    for i, pct in ((11, 100.0), (12, 100.0), (13, 40.0)):
        risk = baseline.strategy.risk.model_copy(update={"position_size_pct": pct})
        ir = baseline.strategy.model_copy(update={
            "strategy_id": f"verified-{i}", "generation": i, "risk": risk,
        })
        digest = content_hash(ir.model_dump(mode="json", by_alias=True))
        donors[i] = VerifiedDonor(i, f"{i:064x}", f"{i+1:064x}", ir, digest, True)
        compiled[digest] = replace(baseline, strategy=ir, strategy_hash=digest)
    candidate = compose(entry=donors[11], exit=donors[12], risk=donors[13])
    return candidate, compiled, market


def _diagnosis(compiled, market):
    audited = audit_inherited_decisions(compiled, market)
    ctx = build_diagnostic_context(audited, compiled.strategy)
    sample = ctx["observations"]["execution_samples"][0]
    return {
        "context_hash": ctx["context_hash"],
        "audit_hash": ctx["audit_hash"],
        "strategy_hash": ctx["strategy_hash"],
        "dataset_hash": ctx["dataset_hash"],
        "summary": "Compare changed exit to observed canonical development fill timing.",
        "hypotheses": [{
            "hypothesis_id": "crossover_exit_control_01",
            "observed_ids": [sample["trade_id"], sample["decision_id"]],
            "mechanism": "Earlier close on a weakened signal may reduce observed losses.",
            "alternative": "Exit may reduce capture of subsequent recovery.",
            "expected_metric": "total_return",
            "predicted_direction": "DECREASE",
            "test_design": "RULE_STRUCTURE",
            "control": "PARENT_UNCHANGED",
            "next_intent": {
                "mode": "structure",
                "parent_ids": [compiled.strategy.strategy_id],
                "operations": [{
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": {
                        "op": "less_equal", "left": "slow", "value": -1.0,
                    },
                }],
                "rationale": "Controlled exit rule mutation on the composed genome.",
            },
        }],
    }


def test_real_three_donor_s2_risk_and_s7_paired_comparison():
    candidate, donors, market = _inputs()
    base = donors[candidate.source_hashes[0]]
    child = replace(
        base, strategy=candidate.strategy,
        strategy_hash=content_hash(candidate.strategy.model_dump(mode="json", by_alias=True)),
    )
    # P2 pass with explicit development-only tiny-fixture budget.
    budget = ChildRiskBudget(max_child_mdd_pct=100, max_mdd_increase_pp=100,
                             min_closed_trades=1)
    result = validate_composite(
        candidate, donors, market, budget=budget, diagnosis=_diagnosis(child, market),
    )
    assert result.p2_review["eligible"] is True
    assert result.audit.evaluation.trades_count >= 2
    assert result.audit.llm_packet["audit_hash"] == result.audit.trace_hash
    assert result.s7 is not None and len(result.s7.experiments) == 1
    assert result.s7.audit_hash == result.audit.trace_hash
    assert result.s7.experiments[0].child_strategy_hash != child.strategy_hash
    assert result.s7.experiments[0].parent_fill_count == result.audit.evaluation.trades_count
    assert result.dev_only and not result.independent_oos


def test_fail_closed_on_parent_forgery_and_risk_gate():
    candidate, donors, market = _inputs()
    original = donors[candidate.source_hashes[0]]
    tampered = dict(donors)
    tampered[original.strategy_hash] = replace(original, strategy_hash="0"*64)
    with pytest.raises(CompositeValidationError, match="donor"):
        validate_composite(candidate, tampered, market,
                           budget=ChildRiskBudget(max_child_mdd_pct=100,
                                                  max_mdd_increase_pp=100,
                                                  min_closed_trades=1))
    with pytest.raises(CompositeValidationError, match="risk"):
        validate_composite(candidate, donors, market,
                           budget=ChildRiskBudget(max_child_mdd_pct=100,
                                                  max_mdd_increase_pp=100,
                                                  min_closed_trades=2))


def test_donor_component_spoofing_rejected_even_with_matching_lineage_hash():
    candidate, sources, market = _inputs()
    swapped = candidate.strategy.model_copy(update={
        "entry": candidate.strategy.entry.model_copy(update={
            "logic": "AND" if candidate.strategy.entry.logic == "OR" else "OR",
        }),
    })
    with pytest.raises(CompositeValidationError, match="component"):
        validate_composite(
            replace(candidate, strategy=swapped),
            sources,
            market,
            budget=ChildRiskBudget(max_child_mdd_pct=100,
                                   max_mdd_increase_pp=100, min_closed_trades=1),
        )


def test_composite_risk_donor_fixed_fraction_affects_development_fill():
    candidate, sources, market = _inputs()
    checked = validate_composite(
        candidate, sources, market,
        budget=ChildRiskBudget(max_child_mdd_pct=100,
                               max_mdd_increase_pp=100, min_closed_trades=1),
    )
    assert checked.audit.fills[0].trade.notional < 10_000
    assert checked.audit.fills[0].trade.cost > 0


def test_distinct_donor_replays_are_union_compiled_not_forced_equal():
    from research.indicator_engine.bridge import ResearchSignalReplay

    base, market = _warmup_fixture()
    sources = {}
    donors = []
    for gen, suffix, pct in ((101, "_a", 100), (102, "_b", 100), (103, "_c", 40)):
        features = {k + suffix: value for k, value in base.strategy.features.items()}
        entry = base.strategy.entry.model_copy(update={
            "conditions": [part.model_copy(update={"left": part.left + suffix})
                           for part in base.strategy.entry.conditions],
        })
        exit_rule = base.strategy.exit.model_copy(update={
            "conditions": [part.model_copy(update={"left": part.left + suffix})
                           for part in base.strategy.exit.conditions],
        })
        ir = base.strategy.model_copy(update={
            "strategy_id": f"separate-{gen}",
            "generation": gen,
            "entry": entry,
            "exit": exit_rule,
            "features": features,
            "risk": base.strategy.risk.model_copy(
                update={"position_size_pct": pct},
            ),
        })
        dataset_hash = market.dataset_hash
        h = content_hash({"donor":gen,"data":dataset_hash})
        signals = tuple((alias + suffix, seq) for alias, seq in base.replay.signals)
        next_bar = base.replay.execution_not_before
        timestamps = base.replay.timestamps
        replay_hash = content_hash({
            "hypothesis": h,
            "dataset": dataset_hash,
            "signals": signals,
            "decision_timestamps": [t.isoformat() for t in timestamps],
            "earliest_next_bar": [t.isoformat() if t else None for t in next_bar],
            "research_only": True,
        })
        replay = ResearchSignalReplay(
            hypothesis_hash=h, data_hash=dataset_hash, signals=signals,
            timestamps=timestamps, execution_not_before=next_bar,
            entry_regime_observations=0, replay_hash=replay_hash,
        )
        digest = content_hash(ir.model_dump(mode="json", by_alias=True))
        parent = replace(base, hypothesis_hash=h, replay=replay,
                         strategy=ir, strategy_hash=digest,
                         feature_values=dict(signals))
        donors.append(VerifiedDonor(gen, f"{gen:064x}",
                                    f"{gen+1:064x}", ir, digest, True))
        sources[digest] = parent
    candidate = compose(entry=donors[0], exit=donors[1], risk=donors[2])
    assert len(candidate.strategy.features) == 6
    result = validate_composite(
        candidate, sources, market,
        budget=ChildRiskBudget(max_child_mdd_pct=100,
                               max_mdd_increase_pp=100,
                               min_closed_trades=1),
    )
    assert result.audit.evaluation.trades_count > 0
    assert len(result.audit.decisions[0].indicator_values) == 6
    assert result.s7 is None
