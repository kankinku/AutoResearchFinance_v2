"""V3 typed genetic composition regression tests."""
from dataclasses import replace

import pytest

from core.integrity.hashes import content_hash
from research.llm.composite_crossover_v3 import CrossoverRejected, VerifiedDonor, compose
from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture


def donor(n, risk_pct=100):
    base, _ = _warmup_fixture()
    changed = base.strategy.model_copy(update={
        "strategy_id": f"parent-{n}",
        "generation": n,
        "risk": base.strategy.risk.model_copy(update={"position_size_pct": risk_pct}),
    })
    return VerifiedDonor(
        generation=n,
        evidence_hash=f"{n:064x}",
        report_hash=f"{n+1:064x}",
        strategy=changed,
        strategy_hash=content_hash(changed.model_dump(mode="json", by_alias=True)),
        replay_verified=True,
    )


def test_entry_exit_risk_three_parents_and_origin_hash():
    a, b, c = donor(4), donor(8), donor(12, 50)
    result = compose(entry=a, exit=b, risk=c)
    assert result.strategy.parents == ["parent-4", "parent-8", "parent-12"]
    assert result.strategy.entry == a.strategy.entry
    assert result.strategy.exit == b.strategy.exit
    assert result.strategy.risk == c.strategy.risk
    assert result.strategy.generation == 13
    assert result.genome_hash
    assert result.source_hashes == (a.strategy_hash, b.strategy_hash, c.strategy_hash)


def test_composition_rejects_unverified_and_alias_conflicts():
    a, b, c = donor(4), donor(8), donor(12)
    with pytest.raises(CrossoverRejected, match="replay"):
        compose(entry=replace(a, replay_verified=False), exit=b, risk=c)
    with pytest.raises(CrossoverRejected, match="hash"):
        compose(entry=replace(a, strategy_hash="0" * 64), exit=b, risk=c)
    with pytest.raises(CrossoverRejected, match="distinct"):
        compose(entry=a, exit=a, risk=a)
    changed = b.strategy.model_copy(update={
        "indicators": {**b.strategy.indicators,
                       "_unused_sma": b.strategy.indicators["_unused_sma"].model_copy(
                           update={"period": 99}
                       )}
    })
    with pytest.raises(CrossoverRejected, match="conflicting indicator"):
        compose(entry=a, exit=replace(
            b, strategy=changed,
            strategy_hash=content_hash(changed.model_dump(mode="json", by_alias=True))), risk=c)


def test_composed_strategy_has_real_costed_fill_and_sizing_effects():
    from research.indicator_engine.strategy_adapter import evaluate_compiled_development

    initial, dataset = _warmup_fixture()
    a, b, c = donor(4), donor(8), donor(12, 50)
    new_exit = b.strategy.model_copy(update={
        "exit": b.strategy.exit.model_copy(update={
            "conditions": [b.strategy.exit.conditions[0].model_copy(update={
                "op": "greater_than", "value": 0.5,
            })],
        }),
    })
    b = replace(b, strategy=new_exit, strategy_hash=content_hash(
        new_exit.model_dump(mode="json", by_alias=True),
    ))
    candidate = compose(entry=a, exit=b, risk=c)
    changed = replace(
        initial,
        strategy=candidate.strategy,
        strategy_hash=content_hash(candidate.strategy.model_dump(mode="json", by_alias=True)),
    )
    original = evaluate_compiled_development(initial, dataset)
    result = evaluate_compiled_development(changed, dataset)
    assert [x.side for x in result.trades] == ["buy", "sell"]
    assert result.trades[0].notional < original.trades[0].notional
    assert result.trades[1].timestamp != original.trades[1].timestamp
    assert result.final_equity != original.final_equity


def test_composite_supports_typed_indicator_and_logic_mutations():
    from research.llm.composite_crossover_v3 import mutate_composite
    from research.llm.director import ResearchIntent

    candidate = compose(entry=donor(4), exit=donor(8), risk=donor(12))
    intent = ResearchIntent.model_validate({
        "mode": "structure",
        "parent_ids": [candidate.strategy.strategy_id],
        "operations": [
            {"op": "CHANGE_AND_OR", "path": "entry.logic", "logic": "AND"},
        ],
        "rationale": "A controlled post-crossover selectivity change on the registered signals.",
    })
    mutated = mutate_composite(candidate, intent)
    assert mutated.strategy.entry.logic == "AND"
    assert mutated.strategy.generation == candidate.strategy.generation + 1
    assert mutated.genome_hash != candidate.genome_hash
    assert candidate.strategy.strategy_id in mutated.strategy.parents
    assert mutated.strategy.provenance.source_hash == mutated.genome_hash
    assert mutated.source_hashes == candidate.source_hashes


def test_distinct_legacy_sources_with_shared_strategy_id_do_not_collapse():
    # Historical counted variants can share the base StrategyIR id/generation
    # even though their source generation and actual strategy hashes differ.
    d1, d2, d3 = donor(10, 100), donor(20, 60), donor(30, 30)
    same_base_id = "legacy-plan-base"
    vals = []
    for source in (d1, d2, d3):
        strategy = source.strategy.model_copy(update={
            "strategy_id": same_base_id,
            "generation": 4,
        })
        vals.append(replace(
            source, strategy=strategy,
            strategy_hash=content_hash(strategy.model_dump(mode="json", by_alias=True)),
        ))
    result = compose(entry=vals[0], exit=vals[1], risk=vals[2])
    assert len(result.strategy.parents) == 3
    assert len(set(result.strategy.parents)) == 3
    assert all("@G" in value for value in result.strategy.parents)
    assert [p["source_generation"] for p in result.provenance["lineage"]] == [
        10, 20, 30,
    ]
