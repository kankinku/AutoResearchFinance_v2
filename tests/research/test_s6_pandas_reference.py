"""S6 optional-to-research pandas verification backend, fail-closed and immutable."""

from pathlib import Path

import pytest

from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.external_reference import (
    ReferenceBackendError,
    audit_s6_external_reference,
    capture_s6_external_reference,
    get_s6_external_reference,
)
from research.indicator_engine.s6_seed import S6_SIGNALS
from research.indicator_engine.signals import _synthetic_prices


def test_s6_independent_pandas_reference_matches_all_four_sources():
    for candidate in S6_SIGNALS:
        report = audit_s6_external_reference(candidate)
        assert report.passed
        assert report.backend == 'pandas'
        assert report.license == 'BSD-3-Clause'
        assert report.version
        assert report.signal_id == candidate.signal_id
        assert report.fixtures_verified == ('synthetic_trend', 'flat', 'choppy')
        assert len(report.result_hash) == 64
        assert report.borderline_binary_count >= 0
        assert report == audit_s6_external_reference(candidate)


def test_s6_rejects_wrong_calculator_or_bad_pandas_reference(monkeypatch):
    from research.indicator_engine import external_reference as module

    with pytest.raises(ReferenceBackendError, match='not approved'):
        forged = S6_SIGNALS[0].model_copy(update={'calculator': 'not_whitelisted'})
        audit_s6_external_reference(forged)
    def forged(*args: object, **kwargs: object) -> tuple[float, ...]:
        return (1.0,) * 530
    monkeypatch.setattr(module, '_pandas_reference', forged)
    with pytest.raises(ReferenceBackendError, match='mismatch'):
        audit_s6_external_reference(S6_SIGNALS[0])


def test_s6_fail_closed_on_backend_major_incompatibility(monkeypatch):
    from research.indicator_engine import external_reference as module

    monkeypatch.setattr(module, '_backend_version', lambda: '4.0.0')
    with pytest.raises(ReferenceBackendError, match='version'):
        audit_s6_external_reference(S6_SIGNALS[0])


def test_s6_pandas_provenance_store_is_immutable_and_detects_tampering(tmp_path: Path):
    catalog = ResearchCatalog(tmp_path / 'v2.sqlite')
    from research.indicator_engine.s6_seed import seed_s6_references
    from research.indicator_engine.seed import seed_approved_references
    seed_approved_references(catalog)
    seed_s6_references(catalog)
    report = audit_s6_external_reference(S6_SIGNALS[0])
    capture_s6_external_reference(catalog, report)
    assert capture_s6_external_reference(catalog, report) is False
    assert get_s6_external_reference(catalog, report.signal_id) == report
    with catalog._connect() as db:
        db.execute('UPDATE s6_external_provenance SET report_hash=? WHERE signal_id=?',
                   ('f' * 64, report.signal_id))
    with pytest.raises(ResearchCatalogError, match='integrity'):
        get_s6_external_reference(catalog, report.signal_id)
    with pytest.raises(ResearchCatalogError, match='integrity'):
        capture_s6_external_reference(catalog, report)


def test_s6_pandas_reference_fixture_is_finite_and_not_future_based():
    report = audit_s6_external_reference(S6_SIGNALS[2])
    assert report.passed
    prices = _synthetic_prices()
    assert len(prices['close']) == 530
    assert report.prefix_consistency
