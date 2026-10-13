"""Constrained Crossref DOI citation snapshots; never equate popularity with alpha.

Only GET https://api.crossref.org/works/{curated DOI}, no redirects or
user-selected URLs, no bulk PDF fetch, no executable fetched metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from core.integrity.hashes import content_hash
from research.indicator_engine.models import Paper

_MAX_RESPONSE_BYTES = 262_144
_API_ROOT = "https://api.crossref.org/works/"
_YEAR_TOLERANCE = 1


class CitationFetchError(ValueError):
    """Missing, incompatible or untrusted DOI metadata; no catalog write."""


@dataclass(frozen=True)
class CitationEvidence:
    doi: str
    count: int
    provider: str
    observed_on: date
    source_record_hash: str
    canonical_title: str
    publication_year: int


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _published_year(message: dict[str, Any]) -> int:
    # Crossref can register online year before print year. Prefer
    # publication-year or issued, then publication alternatives.
    for key in ("issued", "published", "published-print", "published-online"):
        payload = message.get(key)
        if not isinstance(payload, dict):
            continue
        parts = payload.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list):
            year = parts[0][0] if parts[0] else None
            if type(year) is int and 1900 <= year <= 2100:
                return year
    raise CitationFetchError("Crossref publication year is unavailable")


def parse_crossref(paper: Paper, payload: object, *, observed_on: date) -> CitationEvidence:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise CitationFetchError("Crossref response status is invalid")
    message = payload.get("message")
    if not isinstance(message, dict):
        raise CitationFetchError("Crossref work record is missing")
    doi = message.get("DOI")
    if not isinstance(doi, str) or doi.strip().lower() != paper.doi:
        raise CitationFetchError("Crossref DOI does not match approved academic record")
    titles = message.get("title")
    if not isinstance(titles, list) or not titles or not isinstance(titles[0], str):
        raise CitationFetchError("Crossref record title is missing")
    title = titles[0]
    words = _tokens(paper.title)
    returned_words = _tokens(title)
    overlap = len(words & returned_words) / max(1, len(words))
    if overlap < 0.75:
        raise CitationFetchError("Crossref title disagrees with approved academic record")
    year = _published_year(message)
    if abs(year - paper.published_year) > _YEAR_TOLERANCE:
        raise CitationFetchError("Crossref publication year disagrees with approved record")
    count = message.get("is-referenced-by-count")
    if type(count) is not int or count < 0:
        raise CitationFetchError("Crossref citation count is missing/invalid")
    # This is an evidence hash, not a claim that Crossref counts are complete.
    # Hash the fields actually verified; avoid republishing arbitrary abstracts.
    verified = {
        "doi": paper.doi,
        "title": title,
        "published_year": year,
        "count": count,
        "provider": "Crossref",
    }
    return CitationEvidence(
        doi=paper.doi,
        count=count,
        provider="Crossref",
        observed_on=observed_on,
        source_record_hash=content_hash(verified),
        canonical_title=title,
        publication_year=year,
    )


def fetch_crossref(
    paper: Paper,
    *,
    client: httpx.Client,
    observed_on: date | None = None,
) -> CitationEvidence:
    """Fetch one reviewed DOI with client-level timeout and transport injection."""
    if client.follow_redirects:
        raise CitationFetchError("Crossref client must not follow redirects")
    when = observed_on or datetime.now(timezone.utc).date()
    url = _API_ROOT + quote(paper.doi, safe="")
    try:
        response = client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise CitationFetchError("Crossref response exceeds safe size")
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, CitationFetchError):
            raise
        raise CitationFetchError("Crossref request or JSON validation failed") from exc
    return parse_crossref(paper, payload, observed_on=when)


def validate_citation_evidence(paper: Paper, evidence: CitationEvidence) -> None:
    """Detect mutated local snapshots; hash is integrity, not provider attestation."""
    if evidence.doi != paper.doi or evidence.provider != "Crossref":
        raise CitationFetchError("citation DOI/provider mismatch")
    if type(evidence.count) is not int or evidence.count < 0:
        raise CitationFetchError("citation count is invalid")
    if abs(evidence.publication_year - paper.published_year) > _YEAR_TOLERANCE:
        raise CitationFetchError("citation publication year mismatch")
    title_overlap = len(_tokens(paper.title) & _tokens(evidence.canonical_title))
    if title_overlap / max(1, len(_tokens(paper.title))) < 0.75:
        raise CitationFetchError("citation title mismatch")
    check = content_hash(
        {
            "doi": evidence.doi,
            "title": evidence.canonical_title,
            "published_year": evidence.publication_year,
            "count": evidence.count,
            "provider": evidence.provider,
        }
    )
    if evidence.source_record_hash != check:
        raise CitationFetchError("citation evidence integrity failure")
