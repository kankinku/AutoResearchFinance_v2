"""Independent effective-rank anchors and fail-closed covariance diagnostics."""

from __future__ import annotations

from math import sqrt

import pytest

from evaluation.trial_dependence import estimate_cohort_dependence


def test_two_independent_orthogonal_return_streams_have_rank_two() -> None:
    first = tuple(float(v) for v in (1, -1, 1, -1) * 12)
    second = tuple(float(v) for v in (1, 1, -1, -1) * 12)
    output = estimate_cohort_dependence((first, second))
    assert output.status == "ESTIMATED_TRAIN_ONLY_COHORT"
    assert output.candidate_count == 2
    assert output.return_observations == 48
    assert output.effective_rank == pytest.approx(2.0, abs=1e-11)
    assert output.average_absolute_correlation == pytest.approx(0, abs=1e-11)
    assert output.dsr_calibrated is False
    assert output.method == "CORRELATION_ENTROPY_EFFECTIVE_RANK"


def test_identical_vectors_effective_rank_one_and_deterministic() -> None:
    values = tuple(v / 100 for v in (3, 2, 1, -1) * 12)
    output = estimate_cohort_dependence((values, values, values))
    assert output.status == "ESTIMATED_TRAIN_ONLY_COHORT"
    assert output.effective_rank == pytest.approx(1, abs=1e-11)
    assert output.average_absolute_correlation == pytest.approx(1, abs=1e-11)
    assert estimate_cohort_dependence((values, values, values)) == output


def test_partial_dependence_has_rank_strictly_between_one_and_two() -> None:
    a = tuple(float(v) for v in (1, -1, 1, -1) * 12)
    b = tuple(float(v) for v in (1, 1, -1, -1) * 12)
    mixed = tuple(0.02 * (x + y) / sqrt(2) for x, y in zip(a, b, strict=True))
    result = estimate_cohort_dependence((a, mixed))
    assert result.status == "ESTIMATED_TRAIN_ONLY_COHORT"
    assert 1 < result.effective_rank < 2
    assert result.average_absolute_correlation == pytest.approx(1 / sqrt(2))


def test_constant_and_short_windows_remain_unmeasured() -> None:
    a = (1.0,) * 48
    b = tuple(float(v) for v in (1, -1) * 24)
    result = estimate_cohort_dependence((a, b))
    assert result.status == "UNMEASURABLE_CONSTANT_STRATEGY"
    assert result.effective_rank is None
    short = estimate_cohort_dependence((b[:15], a[:15]))
    assert short.status == "INSUFFICIENT_TRAINING_HISTORY"
    assert short.effective_rank is None
    solo = estimate_cohort_dependence((b,))
    assert solo.status == "INSUFFICIENT_CANDIDATES"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_invalid_returns_are_not_silently_discarded(bad: float) -> None:
    a = (0.01,) * 47 + (bad,)
    b = tuple(0.01 if i % 2 else -0.01 for i in range(48))
    result = estimate_cohort_dependence((a, b))
    assert result.status == "INVALID_RETURN_OBSERVATIONS"
    assert result.effective_rank is None


def test_alignment_and_candidate_limits_are_explicit() -> None:
    report = estimate_cohort_dependence(((0.0,) * 48, (0.0,) * 47))
    assert report.status == "MISALIGNED_RETURNS"
    assert report.effective_rank is None
    b = tuple(float(v) for v in (1, -1) * 12)
    over = estimate_cohort_dependence((b,) * 129)
    assert over.status == "COHORT_LIMIT_EXCEEDED"
    assert over.effective_rank is None


def test_effective_rank_is_not_claimed_as_calibrated_independent_dsr_trials() -> None:
    a = tuple(float(v) for v in (1, -1) * 24)
    b = tuple(-x for x in a)
    report = estimate_cohort_dependence((a, b))
    assert report.effective_rank == pytest.approx(1.0, abs=1e-11)
    # Perfect negative dependence has rank one, but max-of-tests is not one
    # identical chance: eigenvalue entropy alone cannot calibrate DSR K.
    assert report.dsr_calibrated is False
    assert report.method != "DSR_EFFECTIVE_INDEPENDENT_TRIALS"
