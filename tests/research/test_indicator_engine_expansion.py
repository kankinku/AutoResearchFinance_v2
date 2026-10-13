"""Academic expansion: causal volatility measures, regime sizing, and seed upgrades."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.models import CANONICAL_FORMULAS, IndicatorCandidate
from research.indicator_engine.seed import (
    ACADEMIC_PAPERS,
    ACADEMIC_SIGNALS,
    seed_approved_references,
)
from research.indicator_engine.signals import calculate_signal, verify_signal_on_synthetic_prices


def _candidate(calculator: str, *, lookback: int = 2, **kwargs: object) -> IndicatorCandidate:
    fields = ("high", "low") if calculator == "parkinson_variance" else ("close",)
    return IndicatorCandidate.model_validate(
        {
            "signal_id": calculator,
            "paper_doi": "10.1086/296071"
            if calculator == "parkinson_variance"
            else "10.1111/jofi.12513",
            "calculator": calculator,
            "family": "volatility",
            "role": "risk",
            "required_fields": fields,
            "lookback": lookback,
            "formula": CANONICAL_FORMULAS[calculator],
            "scope": "single_asset",
            **kwargs,
        }
    )


def test_initial_sources_are_identified_and_seed_upgrade_idempotent(tmp_path: Path) -> None:
    catalog = ResearchCatalog(tmp_path / "papers.sqlite")
    seed_approved_references(catalog)
    seed_approved_references(catalog)
    assert len(ACADEMIC_PAPERS) == 6
    assert len(ACADEMIC_SIGNALS) == 7
    assert len(catalog.list_papers()) == 6
    assert len(catalog.list_indicators()) == 7
    assert catalog.get_indicator("parkinson_variance").status == "PROPOSED"
    assert catalog.get_indicator("volatility_managed_exposure").status == "PROPOSED"
    assert catalog.get_paper("10.1086/296071").published_year == 1980
    assert catalog.get_paper("10.1111/jofi.12513").published_year == 2017


def test_parkinson_estimator_manual_values_and_scale_invariance() -> None:
    sig = _candidate("parkinson_variance")
    raw = {
        "high": [110.0, 90.0, 130.0, 92.0],
        "low": [100.0, 80.0, 120.0, 82.0],
    }
    output = calculate_signal(sig, raw)
    c = 1 / (4 * math.log(2))
    assert output[0] is None
    expected0 = c * math.log(110 / 100) ** 2
    expected1 = c * math.log(90 / 80) ** 2
    assert output[1] == pytest.approx((expected0 + expected1) / 2, abs=1e-14)
    scaled = {k: [v * 3.7 for v in arr] for k, arr in raw.items()}
    assert calculate_signal(sig, scaled)[1:] == pytest.approx(output[1:], abs=1e-14)
    assert verify_signal_on_synthetic_prices(sig).passed


def test_parkinson_rejects_bad_prices_and_requires_risk_role() -> None:
    sig = _candidate("parkinson_variance")
    with pytest.raises(ValueError):
        calculate_signal(sig, {"high": [100.0, 80.0], "low": [90.0, 90.0]})
    with pytest.raises(ValueError):
        calculate_signal(sig, {"high": [100.0, float("nan")], "low": [90.0, 80.0]})
    with pytest.raises(ValidationError):
        _candidate("parkinson_variance", role="entry")


def test_volatility_managed_uses_only_past_returns_and_no_leverage() -> None:
    sig = _candidate(
        "volatility_managed_exposure",
        lookback=3,
        target_daily_variance=0.00005,
        max_exposure=0.80,
    )
    prices = {"close": [100.0, 110.0, 100.0, 110.0, 130.0, 100.0, 200.0]}
    output = calculate_signal(sig, prices)
    assert output[:3] == (None, None, None)
    rv = sum(math.log(prices["close"][j] / prices["close"][j - 1]) ** 2 for j in (1, 2, 3)) / 3
    assert output[3] == pytest.approx(min(0.80, 0.00005 / rv), abs=1e-15)
    assert 0.0 < output[3] < 0.80
    assert calculate_signal(sig, {"close": prices["close"][:4]}) == output[:4]
    assert verify_signal_on_synthetic_prices(sig).passed
    flat = calculate_signal(sig, {"close": [100.0, 100.0, 100.0, 100.0, 100.0]})
    assert flat[:3] == (None, None, None)
    assert flat[3:] == (0.80, 0.80)


def test_managed_exposure_bad_parameters_fail_closed() -> None:
    for parameters in (
        {"target_daily_variance": -0.1},
        {"target_daily_variance": 0.0},
        {"target_daily_variance": 0.1},
        {"max_exposure": 0.0},
        {"max_exposure": 1.1},
        {"max_exposure": float("nan")},
    ):
        with pytest.raises(ValidationError):
            _candidate("volatility_managed_exposure", **parameters)
    with pytest.raises(ValidationError):
        _candidate("parkinson_variance", target_daily_variance=0.0001)
    with pytest.raises(ValidationError):
        _candidate("volatility_managed_exposure", role="regime")


def test_new_signals_register_only_after_real_math_verification(tmp_path: Path) -> None:
    catalog = ResearchCatalog(tmp_path / "signals.sqlite")
    seed_approved_references(catalog)
    for name in ("parkinson_variance", "volatility_managed_exposure"):
        candidate = catalog.get_indicator(name)
        proof = verify_signal_on_synthetic_prices(candidate)
        assert proof.passed, proof.error
        registered = catalog.verify_and_register(name, proof)
        assert registered.status == "VERIFIED"
        assert catalog.get_indicator(name).status == "VERIFIED"
    assert catalog.get_indicator("cross_sectional_momentum").status == "PROPOSED"
    assert len(catalog.list_indicators(eligible_only=True)) == 2


def test_academic_seed_composes_eight_bounded_research_hypotheses(tmp_path: Path) -> None:
    from research.indicator_engine.composer import compose_hypotheses

    catalog = ResearchCatalog(tmp_path / "academic.sqlite")
    seed_approved_references(catalog)
    names = (
        "previous_range_breakout",
        "time_series_momentum",
        "sma_direction",
        "garman_klass_variance",
        "parkinson_variance",
        "volatility_managed_exposure",
    )
    for name in names:
        candidate = catalog.get_indicator(name)
        result = verify_signal_on_synthetic_prices(candidate)
        assert result.passed
        catalog.verify_and_register(name, result)
    hypotheses = compose_hypotheses(catalog, signal_ids=names, max_results=100)
    assert len(hypotheses) == 8
    assert all(not h.executable and not h.sealed_oos_approved for h in hypotheses)
    assert all(h.status == "RESEARCH_ONLY" for h in hypotheses)
    assert len({h.identity_hash for h in hypotheses}) == len(hypotheses)
