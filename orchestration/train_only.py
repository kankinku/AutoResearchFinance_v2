"""Auditable train-only candidate selection for chronological development folds.

A successful report is *development evidence*, never sealed OOS promotion.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrainOnlyFold:
    fold: int
    selected_candidate_hash: str
    candidate_count: int
    train_dataset_hash: str
    train_total_return: float
    train_end_at: str
    test_start_at: str
    test_end_at: str
    test_total_return: float
    test_trade_count: int
    selection_applied: bool = True
    generation_seed: int = 0
    generated_candidate_hashes: tuple[str, ...] = ()
    candidate_generation_cutoff_at: str = ""


@dataclass(frozen=True)
class TrainOnlySelectionReport:
    status: str
    folds: tuple[TrainOnlyFold, ...] = ()
    selection_trials: int = 0
    reason: str | None = None
    sealed_oos_evaluated: bool = False
    upstream_selection_verified: bool = False
