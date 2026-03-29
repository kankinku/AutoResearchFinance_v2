from __future__ import annotations

from pathlib import Path

import pytest


MUTABLE_TARGET_PATH = "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"


def make_genome(**overrides: object) -> dict[str, object]:
    genome: dict[str, object] = {
        "kind": "strategy_genome_v1",
        "target_path": MUTABLE_TARGET_PATH,
        "hypothesis": "Prefer a structured EMA crossover candidate.",
        "change_summary": "Compile an EMA crossover genome into the mutable strategy file.",
        "expected_effects": ["Preserve a simple crossover baseline."],
        "family_id": "replace_indicator",
        "rationale": "Keep the strategy audit-friendly while moving to a structured artifact.",
        "regime_policy": "preserve_current_regime_model",
        "indicator_specs": [
            {
                "id": "fast_ema",
                "indicator": "ema",
                "input": "close",
                "params": {"window": 20},
            },
            {
                "id": "slow_ema",
                "indicator": "ema",
                "input": "close",
                "params": {"window": 50},
            },
        ],
        "entry_clauses": [
            {
                "left": "fast_ema",
                "operator": "cross_over",
                "right": "slow_ema",
            }
        ],
        "exit_clauses": [
            {
                "left": "fast_ema",
                "operator": "cross_under",
                "right": "slow_ema",
            }
        ],
        "risk_clauses": [],
        "params": {
            "fast_window": 20,
            "slow_window": 50,
        },
    }
    genome.update(overrides)
    return genome


def test_genome_compiler_is_deterministic() -> None:
    from finance_autoresearch.strategy_dsl.compiler import compile_strategy_genome

    first = compile_strategy_genome(make_genome())
    second = compile_strategy_genome(make_genome())

    assert first.target_path == MUTABLE_TARGET_PATH
    assert second.target_path == MUTABLE_TARGET_PATH
    assert first.full_file_contents == second.full_file_contents
    assert first.compile_status == "compiled"
    assert second.compile_status == "compiled"


def test_genome_compiler_enforces_complexity_budget() -> None:
    from finance_autoresearch.strategy_dsl.compiler import compile_strategy_genome

    with pytest.raises(ValueError, match="indicator"):
        compile_strategy_genome(
            make_genome(
                indicator_specs=[
                    {"id": "a", "indicator": "ema", "input": "close", "params": {"window": 5}},
                    {"id": "b", "indicator": "ema", "input": "close", "params": {"window": 10}},
                    {"id": "c", "indicator": "ema", "input": "close", "params": {"window": 20}},
                    {"id": "d", "indicator": "ema", "input": "close", "params": {"window": 50}},
                    {"id": "e", "indicator": "ema", "input": "close", "params": {"window": 100}},
                ]
            )
        )


def test_genome_compiler_rejects_unknown_indicator_name() -> None:
    from finance_autoresearch.strategy_dsl.compiler import compile_strategy_genome

    with pytest.raises(ValueError, match="unknown indicator name"):
        compile_strategy_genome(
            make_genome(
                indicator_specs=[
                    {
                        "id": "fast_signal",
                        "indicator": "does_not_exist",
                        "input": "close",
                        "params": {"window": 20},
                    }
                ]
            )
        )


def test_genome_compiler_rejects_unknown_clause_reference() -> None:
    from finance_autoresearch.strategy_dsl.compiler import compile_strategy_genome

    with pytest.raises(ValueError, match="unknown clause reference"):
        compile_strategy_genome(
            make_genome(
                entry_clauses=[
                    {
                        "left": "missing_ref",
                        "operator": "greater_than",
                        "value": 0.0,
                    }
                ]
            )
        )


def test_genome_compiler_rejects_true_regime_split_policy() -> None:
    from finance_autoresearch.strategy_dsl.compiler import compile_strategy_genome

    with pytest.raises(ValueError, match="raw strategy path"):
        compile_strategy_genome(make_genome(regime_policy="consider_split_bull_bear"))


def test_genome_compiler_emits_truthful_metadata() -> None:
    from finance_autoresearch.strategy_dsl.compiler import compile_strategy_genome

    result = compile_strategy_genome(make_genome())
    payload = result.to_payload()

    assert payload["direction_mode"] == "mirrored_long_short"
    assert payload["supports_true_regime_split"] is False
    assert payload["validated_indicator_ids"] == ["fast_ema", "slow_ema"]
    assert payload["validated_clause_refs"] == ["fast_ema", "slow_ema"]


def test_apply_mutation_artifact_compiles_genome_into_mutable_target(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_mutation_artifact

    result = apply_mutation_artifact(make_genome(), repository_root=tmp_path)
    target_path = tmp_path / MUTABLE_TARGET_PATH

    assert result.artifact_kind == "strategy_genome_v1"
    assert result.written_path == target_path
    assert target_path.exists()
    assert result.compile_result is not None
    assert result.compile_result["direction_mode"] == "mirrored_long_short"
    assert result.compile_result["validated_indicator_ids"] == ["fast_ema", "slow_ema"]
    assert "def build_strategy(context: StrategyContext) -> StrategyDefinition:" in target_path.read_text(
        encoding="utf-8"
    )


def test_apply_mutation_artifact_rejects_non_mutable_target_for_genome(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_mutation_artifact

    with pytest.raises(ValueError, match="target_path"):
        apply_mutation_artifact(
            make_genome(target_path="src/finance_autoresearch/strategy/base_contract.py"),
            repository_root=tmp_path,
        )
