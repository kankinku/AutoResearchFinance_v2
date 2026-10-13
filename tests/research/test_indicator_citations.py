"""Crossref ingestion is strict, replayable, and independent of live order tools."""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import httpx
import pytest

from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.citations import (
    CitationFetchError,
    fetch_crossref,
    parse_crossref,
)
from research.indicator_engine.seed import ACADEMIC_PAPERS, seed_approved_references

PAPER = ACADEMIC_PAPERS[0]
TODAY = date(2026, 10, 13)


def response_message(count: int = 123) -> dict:
    return {
        "status": "ok",
        "message": {
            "DOI": PAPER.doi.upper(),
            "title": [PAPER.title],
            "issued": {"date-parts": [[PAPER.published_year, 6, 1]]},
            "is-referenced-by-count": count,
        },
    }


def test_typed_snapshot_persists_and_remains_isolated_from_paper_metadata(tmp_path: Path) -> None:
    db = ResearchCatalog(tmp_path / "research.sqlite")
    seed_approved_references(db)
    parsed = parse_crossref(PAPER, response_message(), observed_on=TODAY)
    assert db.capture_citation(parsed) is True
    assert db.capture_citation(parsed) is False
    snapshots = ResearchCatalog(tmp_path / "research.sqlite").list_citations(PAPER.doi)
    assert len(snapshots) == 1
    assert snapshots[0] == parsed
    assert db.get_paper(PAPER.doi).citation_snapshot is None
    assert db.list_indicators(eligible_only=True) == ()
    conflicting = parse_crossref(PAPER, response_message(124), observed_on=TODAY)
    with pytest.raises(ResearchCatalogError, match="conflicting"):
        db.capture_citation(conflicting)
    assert db.list_citations(PAPER.doi) == (parsed,)
    tomorrow = parse_crossref(PAPER, response_message(124), observed_on=date(2026, 10, 14))
    assert db.capture_citation(tomorrow)
    assert [v.count for v in db.list_citations(PAPER.doi)] == [123, 124]


@pytest.mark.parametrize(
    "bad_changes",
    [
        {"DOI": "10.3333/not-the-paper"},
        {"title": ["Entirely unrelated paper in machine learning"]},
        {"issued": {"date-parts": [[2010]]}},
        {"is-referenced-by-count": -1},
        {"is-referenced-by-count": True},
        {"is-referenced-by-count": 12.5},
        {"is-referenced-by-count": None},
        {"issued": {}},
    ],
)
def test_crossref_rejects_mismatched_or_corrupt_evidence(bad_changes: dict) -> None:
    raw = response_message()
    raw["message"].update(bad_changes)
    with pytest.raises(CitationFetchError):
        parse_crossref(PAPER, raw, observed_on=TODAY)


def test_safe_fixed_endpoint_and_replay_using_injected_http_transport() -> None:
    urls: list[str] = []

    def reply(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=response_message())

    transport = httpx.MockTransport(reply)
    with httpx.Client(transport=transport, follow_redirects=False, timeout=3) as client:
        result = fetch_crossref(PAPER, client=client, observed_on=TODAY)
        assert result.count == 123
    assert urls == ["https://api.crossref.org/works/10.1111%2Fj.1540-6261.1992.tb04681.x"]


def test_redirects_and_oversized_response_are_not_accepted() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"Location": "https://bad.example/"}),
        ),
        timeout=3,
    ) as client:
        with pytest.raises(CitationFetchError):
            fetch_crossref(PAPER, client=client)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * 262145),
        ),
        timeout=3,
    ) as client:
        with pytest.raises(CitationFetchError):
            fetch_crossref(PAPER, client=client)


def test_failed_input_never_writes_to_catalog(tmp_path: Path) -> None:
    store = ResearchCatalog(tmp_path / "clean.sqlite")
    seed_approved_references(store)
    before = store.get_paper(PAPER.doi)
    bad = response_message()
    bad["message"]["title"] = ["Malicious swapped work"]
    with pytest.raises(CitationFetchError):
        parsed = parse_crossref(PAPER, bad, observed_on=TODAY)
        store.capture_citation(parsed)
    assert store.get_paper(PAPER.doi) == before
    assert store.list_citations(PAPER.doi) == ()


def test_hash_of_metadata_changes_when_count_changes() -> None:
    a = parse_crossref(PAPER, response_message(123), observed_on=TODAY)
    b = parse_crossref(PAPER, response_message(124), observed_on=TODAY)
    assert a.source_record_hash != b.source_record_hash


def test_all_seeds_can_be_parsed_from_compatible_mock_response() -> None:
    for paper in ACADEMIC_PAPERS:
        raw = copy.deepcopy(response_message())
        raw["message"].update(
            DOI=paper.doi,
            title=[paper.title],
            issued={"date-parts": [[paper.published_year]]},
        )
        assert parse_crossref(paper, raw, observed_on=TODAY).doi == paper.doi


def test_forged_snapshot_hash_cannot_enter_registry(tmp_path: Path) -> None:
    from dataclasses import replace

    catalog = ResearchCatalog(tmp_path / "forged.sqlite")
    seed_approved_references(catalog)
    valid = parse_crossref(PAPER, response_message(), observed_on=TODAY)
    forged = replace(valid, count=500)
    with pytest.raises(ResearchCatalogError, match="invalid citation"):
        catalog.capture_citation(forged)
    assert catalog.list_citations(PAPER.doi) == ()


def test_sqlite_mutation_detected_when_reading_stored_snapshots(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "tamper.sqlite"
    catalog = ResearchCatalog(path)
    seed_approved_references(catalog)
    valid = parse_crossref(PAPER, response_message(), observed_on=TODAY)
    catalog.capture_citation(valid)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE citation_snapshots SET count=999 WHERE doi=?", (PAPER.doi,))
    with pytest.raises(ResearchCatalogError, match="integrity"):
        catalog.list_citations(PAPER.doi)
