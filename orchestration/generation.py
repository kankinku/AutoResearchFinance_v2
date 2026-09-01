from __future__ import annotations

from dataclasses import dataclass

from research.llm.context_builder import should_call_llm

CANONICAL_STAGES = (
    "load_champion_frontier",
    "load_knowledge",
    "llm_research_direction",
    "local_experiment_planning",
    "candidate_generation",
    "cache_check",
    "strategy_mutation",
    "strategy_validation",
    "parallel_fast_backtest",
    "hard_gate",
    "parallel_full_backtest",
    "robustness_validation",
    "local_statistical_analysis",
    "robust_score",
    "state_update",
    "experiment_db_save",
    "knowledge_extraction",
    "llm_context_compression",
    "plateau_detection",
    "next_generation",
)


@dataclass(frozen=True)
class GenerationResult:
    generation: int
    stages: tuple[str, ...]
    candidate_count: int
    best_score: float
    llm_calls: int
    plateau: bool


class GenerationRunner:
    def run(
        self,
        *,
        generation: int,
        candidate_count: int,
        best_score: float,
        previous_best: float,
        generation_start: bool,
        plateau: bool,
        new_family: bool,
        new_primitive: bool,
    ) -> GenerationResult:
        if generation < 0 or candidate_count < 0:
            raise ValueError("generation and candidate count cannot be negative")
        llm_calls = int(
            should_call_llm(
                generation_start=generation_start,
                plateau=plateau,
                new_family=new_family,
                new_primitive=new_primitive,
            )
        )
        if best_score < previous_best and not plateau:
            raise ValueError("best score cannot regress without plateau classification")
        return GenerationResult(
            generation,
            CANONICAL_STAGES,
            candidate_count,
            best_score,
            llm_calls,
            plateau,
        )
