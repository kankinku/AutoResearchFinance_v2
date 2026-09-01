from __future__ import annotations

from orchestration.generation import CANONICAL_STAGES, GenerationRunner


def test_generation_runner_records_canonical_twenty_stage_loop() -> None:
    result = GenerationRunner().run(
        generation=42,
        candidate_count=256,
        best_score=0.784,
        previous_best=0.70,
        generation_start=True,
        plateau=False,
        new_family=False,
        new_primitive=False,
    )

    assert result.generation == 42
    assert result.stages == CANONICAL_STAGES
    assert len(result.stages) == 20
    assert result.candidate_count == 256
    assert result.llm_calls == 1
    assert result.plateau is False


def test_generation_runner_calls_llm_on_plateau_but_not_ongoing_improvement() -> None:
    runner = GenerationRunner()
    plateau = runner.run(
        generation=43,
        candidate_count=12,
        best_score=0.7,
        previous_best=0.7,
        generation_start=False,
        plateau=True,
        new_family=False,
        new_primitive=False,
    )
    ongoing = runner.run(
        generation=44,
        candidate_count=12,
        best_score=0.8,
        previous_best=0.7,
        generation_start=False,
        plateau=False,
        new_family=False,
        new_primitive=False,
    )

    assert plateau.llm_calls == 1
    assert ongoing.llm_calls == 0
