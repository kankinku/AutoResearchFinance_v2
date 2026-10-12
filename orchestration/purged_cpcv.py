"""Retrospective purged CPCV for a frozen cohort of native-indicator strategies.

A fold refits parameter *selection* on training data, not an ML estimator.
CSCV-style fold research is nonchronological and is never sealed OOS proof.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from math import comb, isfinite, log1p

from core.data.contracts import DataZone, MarketDataSet
from core.validation.cpcv import cpcv_splits
from experiments.candidate_generator import Candidate
from memory.evidence_store import digest

Evaluator = Callable[[Candidate, MarketDataSet, datetime | None], float]


@dataclass(frozen=True)
class TestBlock:
    group: int
    split: int
    candidate_hash: str
    start_at: str
    end_at: str
    total_return: float


@dataclass(frozen=True)
class CPCVFold:
    split: int
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    selected_hash: str
    training_score: float
    test_blocks: tuple[TestBlock, ...]


@dataclass(frozen=True)
class CPCVPath:
    index: int
    total_return: float
    blocks: tuple[TestBlock, ...]


@dataclass(frozen=True)
class PurgedCPCVReport:
    status: str
    folds: tuple[CPCVFold, ...] = ()
    paths: tuple[CPCVPath, ...] = ()
    reason: str | None = None
    methodology: str = "RETROSPECTIVE_PURGED_FOLD_SELECTION"
    chronological_train_only: bool = False
    sealed_oos_evaluated: bool = False
    dataset_hash: str | None = None
    label_end_indices_hash: str | None = None
    embargo_bars: int = 0


def _subset(data: MarketDataSet, dates: Sequence[datetime]) -> MarketDataSet:
    selected = set(dates)
    return MarketDataSet(
        data.version,
        data.zone,
        tuple(bar for bar in data.bars if bar.timestamp in selected),
        data.timeframe,
        data.calendar,
        data.provenance,
    )


def _runs(indices: Sequence[int]) -> tuple[tuple[int, ...], ...]:
    runs: list[list[int]] = []
    for index in indices:
        if not runs or index != runs[-1][-1] + 1:
            runs.append([index])
        else:
            runs[-1].append(index)
    return tuple(tuple(run) for run in runs)


def assign_paths(
    groups: int, heldout: int, heldout_sets: Sequence[tuple[int, ...]]
) -> tuple[dict[int, int], ...]:
    """Color a bipartite incidence graph with maximum degree phi colors.

    Exact coverage: each group occurs once in each of phi paths, and a split
    contributes no more than one block per path. Alternating-path recoloring
    prevents greedy matching from exhausting useful incidences too early.
    """
    if groups < 2 or not 0 < heldout < groups:
        raise ValueError("invalid CPCV reconstruction configuration")
    expected = tuple(combinations(range(groups), heldout))
    if tuple(heldout_sets) != expected:
        raise ValueError("CPCV test group combinations are incomplete or unordered")
    phi = comb(groups - 1, heldout - 1)
    edge_colors: dict[tuple[int, int], int] = {}

    def free_colors(node: int, *, is_group: bool) -> set[int]:
        occupied = {
            color
            for (group, split), color in edge_colors.items()
            if (group if is_group else split) == node
        }
        return set(range(phi)) - occupied

    for split, heldout_groups in enumerate(heldout_sets):
        for group in heldout_groups:
            left_available = free_colors(group, is_group=True)
            right_available = free_colors(split, is_group=False)
            common = left_available & right_available
            if common:
                edge_colors[(group, split)] = min(common)
                continue
            alpha, beta = min(left_available), min(right_available)
            # Starting at a left node missing alpha, follow beta/alpha
            # alternating edges. The right node is missing beta, so it
            # cannot be on this path. Swapping frees beta at both endpoints.
            node = group
            left = True
            desired = beta
            alternating: list[tuple[int, int]] = []
            while True:
                matches = [
                    edge
                    for edge, color in edge_colors.items()
                    if color == desired and (edge[0] if left else edge[1]) == node
                ]
                if not matches:
                    break
                if len(matches) != 1:
                    raise ValueError("CPCV matching has repeated incident colors")
                edge = matches[0]
                alternating.append(edge)
                node = edge[1] if left else edge[0]
                left = not left
                desired = alpha if desired == beta else beta
            for edge in alternating:
                edge_colors[edge] = alpha if edge_colors[edge] == beta else beta
            if beta not in free_colors(group, is_group=True) or beta not in free_colors(
                split, is_group=False
            ):
                raise ValueError("CPCV alternating recoloring failed")
            edge_colors[(group, split)] = beta
    paths: list[dict[int, int]] = []
    for color in range(phi):
        mapping = {group: split for (group, split), c in edge_colors.items() if c == color}
        if len(mapping) != groups or len(set(mapping.values())) != groups:
            raise ValueError("CPCV path misses groups or repeats test splits")
        paths.append(mapping)
    if len(edge_colors) != len(heldout_sets) * heldout:
        raise ValueError("CPCV test incidence lost")
    return tuple(paths)


def run_purged_cpcv(
    *,
    dataset: MarketDataSet,
    candidates: tuple[Candidate, ...],
    evaluate: Evaluator,
    label_end_indices: tuple[int, ...],
    embargo_bars: int,
    groups: int = 4,
    test_groups: int = 2,
) -> PurgedCPCVReport:
    """Choose per-fold candidates on purged train only and test each block.

    Native-indicator candidates only. Candidate generation/hypotheses must have
    been predeclared; test data can veto but cannot influence within-fold fit.
    Held-out groups are evaluated with only *past* indicator warmup and reset
    equity. CPCV training on later data is explicitly retrospective.
    """
    if DataZone(dataset.zone) is not DataZone.DEVELOPMENT:
        raise PermissionError("CPCV runs on development-only data")
    if not candidates:
        return PurgedCPCVReport("INSUFFICIENT_CANDIDATES")
    if any(candidate.strategy.features for candidate in candidates):
        return PurgedCPCVReport(
            "UNSUPPORTED_UNVERIFIED_FEATURES",
            reason="external feature release timing is not verified",
        )
    if groups < 2 or not 0 < test_groups < groups or comb(groups, test_groups) > 28:
        raise ValueError("invalid or unbounded CPCV group configuration")
    times = tuple(sorted({bar.timestamp for bar in dataset.bars}))
    if len(label_end_indices) != len(times):
        raise ValueError("CPCV requires explicit label end per unique timestamp")
    if len(times) < groups * 3:
        return PurgedCPCVReport("INSUFFICIENT_HISTORY")
    splits = cpcv_splits(
        tuple(range(len(times))),
        groups=groups,
        test_groups=test_groups,
        label_end_indices=label_end_indices,
        embargo_bars=embargo_bars,
    )
    quotient, remainder = divmod(len(times), groups)
    partitions: list[tuple[int, ...]] = []
    offset = 0
    for group in range(groups):
        width = quotient + (group < remainder)
        partitions.append(tuple(range(offset, offset + width)))
        offset += width
    test_sets = tuple(combinations(range(groups), test_groups))
    folds: list[CPCVFold] = []
    for fold_id, (train_indices, test_indices) in enumerate(splits):
        if not any(len(run) >= 2 for run in _runs(train_indices)):
            return PurgedCPCVReport(
                "INSUFFICIENT_TRAIN_AFTER_PURGE",
                reason=f"split {fold_id}: no training labels left",
            )
        scored: list[tuple[float, str, Candidate]] = []
        for candidate in candidates:
            score = 0.0
            # Train segments must NOT be joined across purged/test gaps.
            for run in _runs(train_indices):
                if len(run) < 2:
                    continue
                subdata = _subset(dataset, tuple(times[idx] for idx in run))
                ret = evaluate(candidate, subdata, None)
                if not isfinite(ret) or ret <= -1.0:
                    raise ValueError("invalid CPCV training segment return")
                score += log1p(ret)
            scored.append((-score, candidate.candidate_hash, candidate))
        negative_score, _, selected = min(scored, key=lambda item: (item[0], item[1]))
        blocks: list[TestBlock] = []
        for group in test_sets[fold_id]:
            positions = partitions[group]
            first, last = positions[0], positions[-1]
            # Only indicator prices available THROUGH the group end; no
            # warmup orders. Later prices are never passed to the evaluator.
            prefix = _subset(dataset, times[: last + 1])
            ret = evaluate(selected, prefix, times[first])
            if not isfinite(ret) or ret < -1.0:
                raise ValueError("invalid CPCV held-out return")
            blocks.append(
                TestBlock(
                    group,
                    fold_id,
                    selected.candidate_hash,
                    times[first].isoformat(),
                    times[last].isoformat(),
                    ret,
                )
            )
        folds.append(
            CPCVFold(
                fold_id,
                train_indices,
                test_indices,
                selected.candidate_hash,
                -negative_score,
                tuple(blocks),
            )
        )
    blocks_by_key = {
        (block.split, block.group): block for fold in folds for block in fold.test_blocks
    }
    assignments = assign_paths(groups, test_groups, test_sets)
    paths: list[CPCVPath] = []
    for path_id, mapping in enumerate(assignments):
        path_blocks = tuple(blocks_by_key[(mapping[group], group)] for group in range(groups))
        capital = 1.0
        for block in path_blocks:
            capital *= 1.0 + block.total_return
        paths.append(CPCVPath(path_id, capital - 1.0, path_blocks))
    if len(blocks_by_key) != len(paths) * groups:
        raise ValueError("CPCV path coverage mismatch")
    return PurgedCPCVReport(
        "EVALUATED_RETROSPECTIVE",
        tuple(folds),
        tuple(paths),
        dataset_hash=dataset.dataset_hash,
        label_end_indices_hash=digest(label_end_indices),
        embargo_bars=embargo_bars,
    )
