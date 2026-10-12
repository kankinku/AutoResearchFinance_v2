"""Local Gaussian-null maximum Sharpe-Z calibration; not global DSR approval."""
from __future__ import annotations

from importlib import import_module
from math import isfinite
from statistics import NormalDist
from typing import Any

np: Any = import_module("numpy")
_MC_DRAWS = 4096
_MC_SEED = 20261012


def iid_gaussian_max_expectation(k: float) -> float:
    """Numerically integrate the expected maximum of K iid standard normals.

    Extends integer K continuously for descriptive IID-equivalent comparison.
    """
    if not isfinite(k) or k < 1:
        raise ValueError("IID reference requires finite K >= 1")
    if k == 1:
        return 0.0
    step = 0.02
    cdf = NormalDist().cdf
    total = 0.0
    for index in range(501):
        t = step * index
        probability = cdf(t)
        integrand = 1.0 - probability**k - (1.0 - probability)**k
        total += (0.5 if index in (0, 500) else 1.0) * integrand
    return total * step


def iid_equivalent_k(maximum_z: float) -> float:
    if not isfinite(maximum_z):
        raise ValueError("max Sharpe-Z estimate must be finite")
    if maximum_z <= 0:
        return 1.0
    low, high = 1.0, 2.0
    while iid_gaussian_max_expectation(high) < maximum_z and high < 16384:
        high *= 2.0
    if iid_gaussian_max_expectation(high) < maximum_z:
        raise ValueError("Gaussian null maximum outside bounded IID reference")
    for _ in range(35):
        mid = (low + high) / 2
        if iid_gaussian_max_expectation(mid) < maximum_z:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def calibrate_cohort_gaussian_null(
    correlation: Any,
) -> tuple[float, tuple[float, float], float, tuple[float, float]]:
    """Use 4096 seeded correlated Gaussian Sharpe-Z null draws.

    This is an asymptotic Gaussian score approximation, not studentized
    per-trial market Sharpe nulls. Confidence bounds describe Monte Carlo
    variability conditional on the estimated empirical correlation matrix.
    """
    eigenvalues, eigenvectors = np.linalg.eigh(correlation)
    if np.min(eigenvalues) < -1e-7:
        raise ValueError("empirical correlation is not positive semidefinite")
    loading = eigenvectors * np.sqrt(np.clip(eigenvalues, 0.0, None))
    rng = np.random.default_rng(_MC_SEED)
    maxima = np.max(
        rng.standard_normal((_MC_DRAWS, correlation.shape[0])) @ loading.T,
        axis=1,
    )
    mean = float(np.mean(maxima))
    se = float(np.std(maxima, ddof=1) / np.sqrt(_MC_DRAWS))
    if not isfinite(mean) or not isfinite(se):
        raise ValueError("Gaussian null produced nonfinite statistics")
    interval = (mean - 1.96 * se, mean + 1.96 * se)
    return (
        mean,
        interval,
        iid_equivalent_k(mean),
        (iid_equivalent_k(interval[0]), iid_equivalent_k(interval[1])),
    )
