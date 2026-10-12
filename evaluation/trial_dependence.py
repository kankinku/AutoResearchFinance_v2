"""Auditable *training-window* dependence diagnostics for strategy cohorts.

Effective correlation-matrix entropy rank is a descriptive dimension, not an
effective count calibrated against extreme Sharpe statistics (DSR).  In
particular, perfectly negatively correlated tests still have effective rank
one while a two-sided maximum retains selection opportunity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import import_module
from math import isfinite
from typing import Any

from evaluation.trial_null_calibration import calibrate_cohort_gaussian_null

np: Any = import_module("numpy")

_MIN_OBSERVATIONS = 30
_MAX_CANDIDATES = 128
_MAX_OBSERVATIONS = 100_000
_METHOD = "CORRELATION_ENTROPY_EFFECTIVE_RANK"


@dataclass(frozen=True)
class CohortDependenceReport:
    status: str
    candidate_count: int
    return_observations: int
    effective_rank: float | None = None
    average_absolute_correlation: float | None = None
    observed_sharpe_dispersion: float | None = None
    method: str = _METHOD
    dsr_calibrated: bool = False
    training_cutoff_at: str | None = None
    reason: str | None = None
    null_max_sharpe_z_mean: float | None = None
    null_max_sharpe_z_ci95: tuple[float, float] | None = None
    iid_equivalent_trials_estimate: float | None = None
    iid_equivalent_trials_ci95: tuple[float, float] | None = None
    null_monte_carlo_draws: int | None = None
    null_model: str | None = None


def estimate_cohort_dependence(
    aligned_returns: Sequence[Sequence[float]],
    *,
    training_cutoff_at: str | None = None,
) -> CohortDependenceReport:
    """Estimate entropy effective rank from equally aligned training returns.

    Every tested candidate (not merely survivors) must be present; no
    pairwise missing-observation deletion, imputation, or full-period lookahead.
    Emits no raw return stream or matrix to external Evidence.
    """
    count = len(aligned_returns)
    width = len(aligned_returns[0]) if count else 0

    def denied(status: str, reason: str) -> CohortDependenceReport:
        return CohortDependenceReport(
            status,
            count,
            width,
            training_cutoff_at=training_cutoff_at,
            reason=reason,
        )

    if count < 2:
        return denied("INSUFFICIENT_CANDIDATES", "need at least two candidate return streams")
    if count > _MAX_CANDIDATES or width > _MAX_OBSERVATIONS:
        return denied("COHORT_LIMIT_EXCEEDED", "bounded diagnostic capacity exceeded")
    if any(len(row) != width for row in aligned_returns):
        return denied("MISALIGNED_RETURNS", "every return vector requires identical timestamps")
    if width < _MIN_OBSERVATIONS:
        return denied("INSUFFICIENT_TRAINING_HISTORY", "need at least 30 shared training returns")
    if any(not isfinite(value) or value < -1.0 for row in aligned_returns for value in row):
        return denied("INVALID_RETURN_OBSERVATIONS", "only finite returns >= -100% are accepted")

    # Float64 arrays are bounded above to avoid a user-controlled very-large
    # quadratic correlation matrix or hidden data filtering.
    matrix = np.asarray(aligned_returns, dtype=np.float64)
    if not np.all(np.isfinite(matrix)):
        return denied("INVALID_RETURN_OBSERVATIONS", "return conversion overflowed")
    sample_std = np.std(matrix, axis=1, ddof=1)
    if np.any(sample_std <= 1e-12) or not np.all(np.isfinite(sample_std)):
        return denied("UNMEASURABLE_CONSTANT_STRATEGY", "constant or nearly constant returns")

    correlation = np.corrcoef(matrix)
    if not np.all(np.isfinite(correlation)):
        return denied("INVALID_CORRELATION", "nonfinite empirical correlation matrix")
    eigenvalues = np.linalg.eigvalsh(correlation)
    # Numerical PSD roundoff at near-identical candidate vectors.
    if np.min(eigenvalues) < -1e-7:
        return denied("INVALID_CORRELATION", "correlation matrix is not positive semidefinite")
    weights = np.clip(eigenvalues, 0.0, None)
    total = float(np.sum(weights))
    if not isfinite(total) or total <= 0:
        return denied("INVALID_CORRELATION", "empty correlation spectrum")
    weights /= total
    positive = weights[weights > 0]
    rank = float(np.exp(-np.sum(positive * np.log(positive))))
    off_diagonal = np.abs(correlation[np.triu_indices(count, 1)])
    mean_correlation = float(np.mean(off_diagonal))

    # Cross-sectional dispersion of per-observation Sharpe estimates can help
    # future DSR calibration, but is not a validated null Sharpe variance.
    sharpe = np.mean(matrix, axis=1) / sample_std
    dispersion = float(np.std(sharpe, ddof=1))
    if not all(isfinite(item) for item in (rank, mean_correlation, dispersion)):
        return denied("INVALID_CORRELATION", "nonfinite derived diagnostics")
    try:
        null_mean, null_ci, iid_k, iid_ci = calibrate_cohort_gaussian_null(correlation)
    except ValueError:
        return denied("INVALID_NULL_REFERENCE", "cohort Gaussian null calibration failed")
    return CohortDependenceReport(
        "ESTIMATED_TRAIN_ONLY_COHORT",
        count,
        width,
        effective_rank=max(1.0, min(float(count), rank)),
        average_absolute_correlation=mean_correlation,
        observed_sharpe_dispersion=dispersion,
        training_cutoff_at=training_cutoff_at,
        reason="cohort Gaussian null proxy; not globally calibrated DSR trials",
        null_max_sharpe_z_mean=null_mean,
        null_max_sharpe_z_ci95=null_ci,
        iid_equivalent_trials_estimate=iid_k,
        iid_equivalent_trials_ci95=iid_ci,
        null_monte_carlo_draws=4096,
        null_model="GAUSSIAN_SHARPE_Z_EMPIRICAL_TRAIN_CORRELATION",
    )
