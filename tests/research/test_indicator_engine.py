"""Fail-closed academic indicator registry, formula checks, and research-only combinations."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.models import (
    CANONICAL_FORMULAS,
    CitationSnapshot,
    IndicatorCandidate,
    Paper,
)
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import (
    calculate_signal,
    verify_signal_on_synthetic_prices,
)


def _paper() -> Paper:
    return Paper(
        doi="10.1111/j.1540-6261.1992.tb04681.x",
        title="Simple Technical Trading Rules and the Stochastic Properties of Stock Returns",
        authors=("William Brock", "Josef Lakonishok", "Blake LeBaron"),
        published_year=1992,
        source_url="https://doi.org/10.1111/j.1540-6261.1992.tb04681.x",
        venue="The Journal of Finance",
        source_scope="US equity index",
        replication_note="Signals are hypotheses, not certified alpha.",
    )


def _signal(
    signal_id: str = "moving_average_breakout",
    *,
    calculator: str = "sma_direction",
    role: str = "entry",
    fields: tuple[str, ...] = ("close",),
    lookback: int = 3,
) -> IndicatorCandidate:
    return IndicatorCandidate(
        signal_id=signal_id,
        paper_doi=_paper().doi,
        calculator=calculator,
        family="trend",
        role=role,
        required_fields=fields,
        lookback=lookback,
        formula=CANONICAL_FORMULAS[calculator],
        scope="single_asset",
        status="PROPOSED",
    )


def _prices() -> dict[str, tuple[float, ...]]:
    return {
        "open": (10.0, 11.0, 12.0, 11.0, 14.0, 13.0, 15.0, 16.0, 15.0, 17.0, 18.0, 19.0),
        "high": (11.0, 12.0, 13.0, 12.0, 15.0, 14.0, 16.0, 17.0, 16.0, 18.0, 19.0, 20.0),
        "low": (9.0, 10.0, 11.0, 10.0, 13.0, 12.0, 14.0, 15.0, 14.0, 16.0, 17.0, 18.0),
        "close": (10.0, 11.0, 12.0, 11.0, 14.0, 13.0, 15.0, 16.0, 15.0, 17.0, 18.0, 19.0),
    }


def test_paper_identity_and_citations_are_not_unverified_alpha() -> None:
    with pytest.raises(ValueError):
        _paper().model_copy(update={"doi": "https://evil.local"}).model_validate(
            {"doi": "not-doi", **_paper().model_dump(exclude={"doi"})}
        )
    with pytest.raises(ValueError):
        CitationSnapshot(count=-1, provider="Crossref", observed_on="2026-10-13")
    with pytest.raises(ValueError):
        CitationSnapshot(count=100, provider="", observed_on="2026-10-13")


def test_research_db_persists_proposals_and_blocks_unverified_combinations(
    tmp_path: Path,
) -> None:
    db = tmp_path / "indicators.sqlite"
    catalog = ResearchCatalog(db)
    catalog.add_paper(_paper())
    catalog.add_indicator(_signal())
    with pytest.raises(ResearchCatalogError):
        catalog.add_paper(_paper())
    with pytest.raises(ResearchCatalogError):
        catalog.add_indicator(_signal())
    assert catalog.list_indicators(eligible_only=True) == ()
    with pytest.raises(ResearchCatalogError):
        compose_hypotheses(catalog, signal_ids=("moving_average_breakout",))
    assert ResearchCatalog(db).get_paper(_paper().doi).title == _paper().title
    assert ResearchCatalog(db).get_indicator("moving_average_breakout").status == "PROPOSED"


def test_reference_formula_values_and_causal_prefix() -> None:
    inputs = _prices()
    ma = _signal()
    output = calculate_signal(ma, inputs)
    assert output[:2] == (None, None)
    assert output[2] == pytest.approx(1.0)
    assert output[3] == pytest.approx(0.0)
    assert verify_signal_on_synthetic_prices(ma).passed

    garman = _signal(
        "garman_klass",
        calculator="garman_klass_variance",
        role="risk",
        fields=("open", "high", "low", "close"),
        lookback=2,
    )
    actual = calculate_signal(garman, inputs)
    expected_day0 = 0.5 * math.log(11 / 9) ** 2 - (2 * math.log(2) - 1) * math.log(10 / 10) ** 2
    expected_day1 = 0.5 * math.log(12 / 10) ** 2 - (2 * math.log(2) - 1) * math.log(11 / 11) ** 2
    assert actual[0] is None
    assert actual[1] == pytest.approx((expected_day0 + expected_day1) / 2)
    assert verify_signal_on_synthetic_prices(garman).passed


def test_missing_and_invalid_ohlc_fail_closed() -> None:
    v = _signal(
        "garman_klass",
        calculator="garman_klass_variance",
        role="risk",
        fields=("open", "high", "low", "close"),
        lookback=2,
    )
    with pytest.raises(ValueError):
        calculate_signal(v, {"open": (1.0,), "high": (1.0,)})
    bad = _prices()
    bad["low"] = (12.0,) + bad["low"][1:]
    with pytest.raises(ValueError):
        calculate_signal(v, bad)


def test_registry_promotes_only_verified_math_and_quarantines_wrong_formula(
    tmp_path: Path,
) -> None:
    store = ResearchCatalog(tmp_path / "registry.sqlite")
    store.add_paper(_paper())
    store.add_indicator(_signal())
    verification = verify_signal_on_synthetic_prices(_signal())
    assert verification.passed
    store.verify_and_register("moving_average_breakout", verification)
    assert store.list_indicators(eligible_only=True)[0].status == "VERIFIED"
    with pytest.raises(ResearchCatalogError):
        store.verify_and_register("moving_average_breakout", verification)
    with pytest.raises((ValueError, KeyError)):
        store.add_indicator(_signal("unknown", calculator="not_a_calculator"))
    with pytest.raises(ResearchCatalogError):
        store.quarantine("missing", reason="bad formula")


def test_composition_only_uses_verified_diverse_roles_and_is_bounded(tmp_path: Path) -> None:
    store = ResearchCatalog(tmp_path / "composition.sqlite")
    store.add_paper(_paper())
    for sig in (
        _signal("entry", calculator="sma_direction"),
        _signal("filter", calculator="time_series_momentum", role="regime"),
        _signal(
            "risk",
            calculator="garman_klass_variance",
            role="risk",
            fields=("open", "high", "low", "close"),
        ),
    ):
        store.add_indicator(sig)
        store.verify_and_register(sig.signal_id, verify_signal_on_synthetic_prices(sig))
    first = compose_hypotheses(store, signal_ids=("entry", "filter", "risk"), max_results=6)
    second = compose_hypotheses(store, signal_ids=("risk", "filter", "entry"), max_results=6)
    assert first == second
    assert len(first) == 2
    assert all(h.status == "RESEARCH_ONLY" for h in first)
    assert all(len(set(h.roles)) == len(h.roles) for h in first)
    assert len({h.identity_hash for h in first}) == len(first)
    with pytest.raises(ValueError):
        compose_hypotheses(store, signal_ids=("entry", "filter", "risk"), max_results=0)


def test_cross_sectional_paper_requires_multi_asset_dataset(tmp_path: Path) -> None:
    catalog = ResearchCatalog(tmp_path / "multi.sqlite")
    seed_approved_references(catalog)
    cross = catalog.get_indicator("cross_sectional_momentum")
    assert cross.status == "PROPOSED"
    assert cross.scope == "cross_section"
    assert cross.paper_doi == "10.1111/j.1540-6261.1993.tb04702.x"
    assert len(catalog.list_papers()) >= 4
    assert not catalog.list_indicators(eligible_only=True)
    with pytest.raises(ResearchCatalogError):
        compose_hypotheses(catalog, signal_ids=("cross_sectional_momentum",))


def test_seed_registry_is_idempotent_and_math_only_verification_leaves_other_unverified(
    tmp_path: Path,
) -> None:
    from research.indicator_engine.seed import ACADEMIC_PAPERS, ACADEMIC_SIGNALS

    store = ResearchCatalog(tmp_path / "seed.sqlite")
    seed_approved_references(store)
    seed_approved_references(store)
    assert len(store.list_papers()) == len(ACADEMIC_PAPERS) == 4
    assert len(store.list_indicators()) == len(ACADEMIC_SIGNALS) == 5
    assert all(paper.citation_snapshot is None for paper in store.list_papers())
    selected = store.get_indicator("time_series_momentum")
    proof = verify_signal_on_synthetic_prices(selected)
    assert proof.passed
    store.verify_and_register(selected.signal_id, proof)
    seed_approved_references(store)
    assert tuple(signal.signal_id for signal in store.list_indicators(eligible_only=True)) == (
        "time_series_momentum",
    )
    assert store.get_indicator("cross_sectional_momentum").status == "PROPOSED"


def test_forged_verification_mismatched_hash_is_rejected(tmp_path: Path) -> None:
    store = ResearchCatalog(tmp_path / "bad_proof.sqlite")
    store.add_paper(_paper())
    store.add_indicator(_signal())
    valid = verify_signal_on_synthetic_prices(_signal())
    forged = valid.model_copy(update={"signal_hash": "0" * 64})
    with pytest.raises(ResearchCatalogError):
        store.verify_and_register("moving_average_breakout", forged)
    assert store.get_indicator("moving_average_breakout").status == "PROPOSED"


def test_short_lookback_candidate_on_synthetic_inputs_cannot_fake_reference_math() -> None:
    # A calculator must deliver actual non-None reference outputs.
    candidate = _signal(lookback=500)
    proof = verify_signal_on_synthetic_prices(candidate)
    assert proof.passed  # The >500-bar fixture makes a real reference evaluation possible.
    assert calculate_signal(candidate, _prices()) == tuple(None for _ in range(12))
