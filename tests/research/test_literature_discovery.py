"""S9 literature scouting: metadata stays unapproved until explicit review."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.literature_discovery import (
    LiteratureDiscoveryError,
    LiteratureStore,
    discover_crossref_literature,
)

OBS = datetime(2026, 10, 15, 14, 20, tzinfo=timezone.utc)


def _record(doi: str, *, cites: int = 112, title: str = "Time Series Momentum") -> dict:
    return {
        "DOI": doi,
        "title": [title],
        "issued": {"date-parts": [[2012, 8]]},
        "author": [{"given": "Jane", "family": "Doe"}],
        "container-title": ["Financial Research Review"],
        "type": "journal-article",
        "is-referenced-by-count": cites,
    }


def _reply(*records: dict) -> bytes:
    return json.dumps({"status": "ok", "message": {"items": list(records)}}).encode()


def _client(raw: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.crossref.org"
        assert request.url.path == "/works"
        assert request.url.params["rows"] == "10"
        return httpx.Response(200, content=raw, headers={"Content-Type": "application/json"})

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_discovery_collects_doi_metadata_and_filters_unusable_items():
    raw = _reply(
        _record("10.1234/example.2012", cites=114),
        _record("10.1234/example.2012", cites=114),
        _record("not_a_doi"),
        _record("10.1234/another", title="Off Topic Title"),
    )
    with _client(raw) as client:
        batch = discover_crossref_literature(
            "time series momentum", client=client, limit=10, observed_at=OBS
        )
    assert batch.provider == "Crossref"
    assert batch.response_sha256
    assert len(batch.candidates) == 1
    match = batch.candidates[0]
    assert match.doi == "10.1234/example.2012"
    assert match.authors == ("Jane Doe",)
    assert match.citations == 114
    assert match.status == "REVIEW_REQUIRED"
    assert match.license_review_required
    assert not match.calculator_approved
    assert not match.broker_executable


def test_append_only_observations_and_reviewed_catalog_stage(tmp_path: Path):
    store = LiteratureStore(tmp_path / "local-only.sqlite")
    with _client(_reply(_record("10.1234/example.2012"))) as client:
        first = discover_crossref_literature(
            "time series momentum", client=client, limit=10, observed_at=OBS
        )
    assert store.capture_batch(first) == 1
    assert store.capture_batch(first) == 0
    assert store.list_candidates()[0].doi == first.candidates[0].doi
    assert store.list_observations("10.1234/example.2012") == (first.candidates[0],)
    with _client(_reply(_record("10.1234/example.2012", cites=120))) as client:
        later = discover_crossref_literature(
            "time series momentum", client=client, limit=10, observed_at=OBS + timedelta(days=1)
        )
    assert store.capture_batch(later) == 1
    assert len(store.list_observations("10.1234/example.2012")) == 2
    db = ResearchCatalog(tmp_path / "local-only.sqlite")
    paper = store.stage_paper(
        "10.1234/example.2012",
        catalog=db,
        source_scope="global developed-market futures",
        replication_note="Metadata-only; full-text rights, math and reproducibility pending.",
    )
    assert db.get_paper(paper.doi) == paper
    assert db.list_indicators() == ()
    with pytest.raises(LiteratureDiscoveryError, match="already"):
        store.stage_paper(
            paper.doi, catalog=db, source_scope="global futures", replication_note="Review pending"
        )


def test_malformed_response_or_network_redirect_is_refused():
    with _client(_reply(_record("10.1234/a"))) as client:
        with pytest.raises(LiteratureDiscoveryError, match="query"):
            discover_crossref_literature("x", client=client, limit=10)
        with pytest.raises(LiteratureDiscoveryError, match="limit"):
            discover_crossref_literature("time series momentum", client=client, limit=99)
    with _client(b'{"status":"failed","message":{}}') as client:
        with pytest.raises(LiteratureDiscoveryError):
            discover_crossref_literature("time series momentum", client=client, limit=10)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"Location": "https://other.site/"})
        ),
        follow_redirects=False,
    ) as client:
        with pytest.raises(LiteratureDiscoveryError):
            discover_crossref_literature("time series momentum", client=client, limit=10)


def test_tampered_db_blocks_staging(tmp_path: Path):
    store = LiteratureStore(tmp_path / "lit.sqlite")
    with _client(_reply(_record("10.1234/example.2012"))) as client:
        batch = discover_crossref_literature(
            "time series momentum", client=client, limit=10, observed_at=OBS
        )
    store.capture_batch(batch)
    with store._connect() as conn:
        conn.execute("UPDATE literature_observations SET candidate_json=?", ("{}",))
    with pytest.raises(LiteratureDiscoveryError, match="integrity"):
        store.list_candidates()


def test_review_queue_listing_is_deduplicated_across_batch_topics(tmp_path: Path):
    from research.indicator_engine.literature_discovery import sweep_crossref_literature

    store = LiteratureStore(tmp_path / "queue.sqlite")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params["query.title"])
        return httpx.Response(200, content=_reply(_record("10.1234/finance.2012")))

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        summary = sweep_crossref_literature(
            store,
            client=client,
            topics=("time series momentum", "volatility managed"),
            limit_per_topic=2,
        )
    assert summary["topics_queried"] == 2
    assert summary["new_observations"] == 1
    assert summary["unique_candidates"] == 1
    assert len(requests) == 2
    assert len(store.list_candidates()) == 1
    assert summary["calculator_approved"] is False


def test_sweep_retains_success_before_crossref_rate_limit(tmp_path: Path):
    from research.indicator_engine.literature_discovery import sweep_crossref_literature

    store = LiteratureStore(tmp_path / "queue.sqlite")
    calls = []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params["query.title"])
        if len(calls) == 1:
            return httpx.Response(200, content=_reply(_record("10.1234/example.2012")))
        return httpx.Response(429, content=b"")

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        summary = sweep_crossref_literature(
            store, client=client,
            topics=("time series momentum", "volatility managed", "market regime analysis"),
            limit_per_topic=2,
        )
    assert summary["status"] == "PARTIAL_RATE_LIMITED"
    assert summary["topics_queried"] == 1
    assert summary["pending_topics"] == ["volatility managed", "market regime analysis"]
    assert summary["new_observations"] == 1
    assert len(store.list_candidates()) == 1
    assert len(calls) == 2  # respect rate limit, no third request
