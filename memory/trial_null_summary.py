"""Validate and project untrusted, immutable cohort null-calibration metadata."""
from __future__ import annotations

from math import isfinite
from typing import Any

from memory.evidence_store import EvidenceIntegrityError


def null_calibration_projection(source: dict[str, Any]) -> dict[str, object] | None:
    """Never fabricate a legacy Gaussian calibration or global DSR trial count."""
    fields = (
        "null_max_sharpe_z_mean",
        "null_max_sharpe_z_ci95",
        "iid_equivalent_trials_estimate",
        "iid_equivalent_trials_ci95",
        "null_monte_carlo_draws",
        "null_model",
    )
    if all(source.get(key) is None for key in fields):
        return None
    if any(source.get(key) is None for key in fields):
        raise EvidenceIntegrityError("incomplete cohort null calibration")

    def number(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise EvidenceIntegrityError("invalid cohort null calibration number")
        n = float(value)
        if not isfinite(n):
            raise EvidenceIntegrityError("nonfinite cohort null calibration number")
        return n

    def interval(value: object) -> tuple[float, float]:
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise EvidenceIntegrityError("invalid cohort null calibration interval")
        low, high = number(value[0]), number(value[1])
        if low > high:
            raise EvidenceIntegrityError("reversed cohort null calibration interval")
        return low, high

    null_mean = number(source["null_max_sharpe_z_mean"])
    null_ci = interval(source["null_max_sharpe_z_ci95"])
    k = number(source["iid_equivalent_trials_estimate"])
    k_ci = interval(source["iid_equivalent_trials_ci95"])
    if (
        source["null_model"] != "GAUSSIAN_SHARPE_Z_EMPIRICAL_TRAIN_CORRELATION"
        or type(source["null_monte_carlo_draws"]) is not int
        or source["null_monte_carlo_draws"] != 4096
        or source.get("dsr_calibrated") is not False
        or not null_ci[0] <= null_mean <= null_ci[1]
        or not k_ci[0] <= k <= k_ci[1]
        or k_ci[0] < 1
    ):
        raise EvidenceIntegrityError("invalid cohort null calibration provenance")
    return {
        "null_max_sharpe_z_mean": null_mean,
        "null_max_sharpe_z_ci95": list(null_ci),
        "iid_equivalent_trials_estimate": k,
        "iid_equivalent_trials_ci95": list(k_ci),
        "null_monte_carlo_draws": 4096,
        "null_model": source["null_model"],
        "global_dsr_approved": False,
    }
