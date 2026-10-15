"""Bounded Crossref metadata scouting and immutable REVIEW_REQUIRED literature queue.

Discoveries never install, execute or promote indicator code. A reviewed DOI
may be staged as a bibliographic Paper; signals still require separately
approved calculator definitions, mathematical reference and causal gates.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx

from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.citations import CitationFetchError, _published_year
from research.indicator_engine.models import DOI_PATTERN, Paper

_API = "https://api.crossref.org/works"
_MAX_BYTES = 512_000
_MAX_ITEMS = 20
_ALLOWED_TYPES = {"journal-article", "proceedings-article", "posted-content"}
_STOP_WORDS = {"a", "the", "and", "of", "for", "on", "in", "an", "to", "with", "from"}


class LiteratureDiscoveryError(ValueError):
    """Untrusted metadata, an invalid catalog state, or a declined intake."""


class LiteratureRateLimited(LiteratureDiscoveryError):
    """The provider requested fewer requests; do not auto-retry."""


@dataclass(frozen=True)
class LiteratureCandidate:
    doi: str
    title: str
    authors: tuple[str, ...]
    published_year: int
    venue: str
    work_type: str
    citations: int
    observed_at: str
    source_url: str
    source_record_hash: str
    status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"
    license_review_required: Literal[True] = True
    calculator_approved: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LiteratureBatch:
    query: str
    observed_at: str
    response_sha256: str
    candidates: tuple[LiteratureCandidate, ...]
    provider: Literal["Crossref"] = "Crossref"
    status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "query": self.query,
            "observed_at": self.observed_at,
            "response_sha256": self.response_sha256,
            "provider": self.provider,
            "status": self.status,
            "broker_executable": False,
            "candidate_count": len(self.candidates),
            "candidates": [item.record() for item in self.candidates],
        }


def _tokens(value: str) -> set[str]:
    return {part for part in re.findall(r"[a-z0-9]+", value.casefold()) if part not in _STOP_WORDS}


def _parse_candidate(message: object, query: str, observed_at: str) -> LiteratureCandidate | None:
    if not isinstance(message, dict):
        return None
    doi = message.get("DOI")
    title = message.get("title")
    kind = message.get("type")
    count = message.get("is-referenced-by-count")
    authors = message.get("author")
    venue = message.get("container-title")
    if (
        not isinstance(doi, str)
        or DOI_PATTERN.fullmatch(doi.strip().lower()) is None
        or not isinstance(title, list)
        or not title
        or not isinstance(title[0], str)
        or not title[0].strip()
        or kind not in _ALLOWED_TYPES
        or type(count) is not int
        or count < 0
        or not isinstance(authors, list)
        or not authors
        or not isinstance(venue, list)
        or not venue
        or not isinstance(venue[0], str)
        or not venue[0].strip()
    ):
        return None
    cleaned_title = re.sub(r"\s+", " ", title[0]).strip()[:350]
    terms = _tokens(query)
    if not terms or len(_tokens(cleaned_title) & terms) < math.ceil(len(terms) * 0.5):
        return None
    names: list[str] = []
    for entry in authors[:32]:
        if not isinstance(entry, dict):
            return None
        name = (
            str(entry.get("given", "")).strip() + " " + str(entry.get("family", "")).strip()
        ).strip()
        if not name or name in {"None", "null"}:
            return None
        names.append(re.sub(r"\s+", " ", name)[:120])
    if not names:
        return None
    try:
        published_year = _published_year(message)
    except CitationFetchError:
        return None
    identity = {
        "doi": doi.strip().lower(),
        "title": cleaned_title,
        "authors": names,
        "year": published_year,
        "venue": venue[0].strip()[:200],
        "work_type": kind,
        "citations": count,
    }
    return LiteratureCandidate(
        doi=identity["doi"],
        title=identity["title"],
        authors=tuple(names),
        published_year=published_year,
        venue=identity["venue"],
        work_type=kind,
        citations=count,
        observed_at=observed_at,
        source_url=f"https://doi.org/{identity['doi']}",
        source_record_hash=content_hash(identity),
    )


def discover_crossref_literature(
    query: str,
    *,
    client: httpx.Client,
    limit: int = 10,
    observed_at: datetime | None = None,
) -> LiteratureBatch:
    """One bounded API request; metadata-only, no PDF or user-controlled URLs."""
    if (
        not isinstance(query, str)
        or not 5 <= len(query.strip()) <= 160
        or any(ord(c) < 32 or ord(c) == 127 for c in query)
    ):
        raise LiteratureDiscoveryError("query must be a bounded printable research phrase")
    if type(limit) is not int or not 1 <= limit <= _MAX_ITEMS:
        raise LiteratureDiscoveryError("limit must be 1..20")
    if client.follow_redirects:
        raise LiteratureDiscoveryError("redirect-following client prohibited")
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise LiteratureDiscoveryError("observed timestamp requires UTC offset")
    stamp = observed.astimezone(timezone.utc).isoformat()
    cleaned_query = query.strip()
    try:
        response = client.get(
            _API,
            params={
                "query.title": cleaned_query,
                "rows": limit,
                "select": (
                    "DOI,title,issued,published,published-print,published-online,"
                    "author,container-title,is-referenced-by-count,type"
                ),
            },
            headers={"Accept": "application/json"},
        )
        if response.status_code == 429:
            raise LiteratureRateLimited("Crossref HTTP 429; retry later")
        if response.status_code != 200 or response.url.host != "api.crossref.org":
            raise LiteratureDiscoveryError("Crossref response status/source invalid")
        if len(response.content) > _MAX_BYTES:
            raise LiteratureDiscoveryError("Crossref response exceeds bounded size")
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, LiteratureDiscoveryError):
            raise
        raise LiteratureDiscoveryError("Crossref metadata request failed") from exc
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise LiteratureDiscoveryError("Crossref metadata status invalid")
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("items"), list):
        raise LiteratureDiscoveryError("Crossref result list missing")
    raw_items = message["items"]
    if len(raw_items) > limit:
        raise LiteratureDiscoveryError("Crossref returned over limit")
    seen: set[str] = set()
    candidates: list[LiteratureCandidate] = []
    for item in raw_items:
        entry = _parse_candidate(item, cleaned_query, stamp)
        if entry is not None and entry.doi not in seen:
            candidates.append(entry)
            seen.add(entry.doi)
    candidates.sort(key=lambda item: (-item.citations, item.doi))
    return LiteratureBatch(
        query=cleaned_query,
        observed_at=stamp,
        response_sha256=hashlib.sha256(response.content).hexdigest(),
        candidates=tuple(candidates),
    )


class LiteratureStore:
    """Append-only bibliographic observations in the research SQLite database."""

    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS literature_observations (
                doi TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                candidate_json TEXT NOT NULL,
                candidate_hash TEXT NOT NULL,
                response_sha256 TEXT NOT NULL,
                PRIMARY KEY (doi, observed_at)
            )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @staticmethod
    def _decode(row: sqlite3.Row) -> LiteratureCandidate:
        try:
            data = json.loads(row["candidate_json"])
            if (
                content_hash(data) != row["candidate_hash"]
                or data.get("doi") != row["doi"]
                or data.get("observed_at") != row["observed_at"]
            ):
                raise LiteratureDiscoveryError("literature observation integrity failure")
            data["authors"] = tuple(data["authors"])
            entry = LiteratureCandidate(**data)
            if (
                entry.status != "REVIEW_REQUIRED"
                or entry.calculator_approved
                or entry.broker_executable
                or not entry.license_review_required
            ):
                raise LiteratureDiscoveryError("literature status integrity failure")
            return entry
        except (KeyError, ValueError, TypeError) as exc:
            raise LiteratureDiscoveryError("literature observation integrity failure") from exc

    def capture_batch(self, batch: LiteratureBatch) -> int:
        inserted = 0
        with self._connect() as db:
            for candidate in batch.candidates:
                payload = candidate.record()
                if (
                    candidate.observed_at != batch.observed_at
                    or candidate.broker_executable
                    or candidate.calculator_approved
                    or candidate.status != "REVIEW_REQUIRED"
                ):
                    raise LiteratureDiscoveryError("untrusted literature batch")
                row = db.execute(
                    "SELECT * FROM literature_observations WHERE doi=? AND observed_at=?",
                    (candidate.doi, candidate.observed_at),
                ).fetchone()
                if row is not None:
                    self._decode(row)
                    if (
                        row["candidate_hash"] != content_hash(payload)
                        or row["response_sha256"] != batch.response_sha256
                    ):
                        raise LiteratureDiscoveryError("conflicting literature observation")
                    continue
                db.execute(
                    "INSERT INTO literature_observations VALUES(?,?,?,?,?)",
                    (
                        candidate.doi,
                        candidate.observed_at,
                        json.dumps(payload, sort_keys=True),
                        content_hash(payload),
                        batch.response_sha256,
                    ),
                )
                inserted += 1
        return inserted

    def list_candidates(self, *, limit: int = 100) -> tuple[LiteratureCandidate, ...]:
        if not 1 <= limit <= 100:
            raise LiteratureDiscoveryError("invalid literature listing limit")
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM literature_observations ORDER BY observed_at DESC, doi"
            ).fetchall()
        seen: set[str] = set()
        results = []
        for row in rows:
            entry = self._decode(row)
            if entry.doi not in seen:
                results.append(entry)
                seen.add(entry.doi)
        return tuple(sorted(results, key=lambda x: (-x.citations, x.doi))[:limit])

    def list_observations(self, doi: str) -> tuple[LiteratureCandidate, ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM literature_observations WHERE doi=? ORDER BY observed_at",
                (doi.lower(),),
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def stage_paper(
        self,
        doi: str,
        *,
        catalog: ResearchCatalog,
        source_scope: str,
        replication_note: str,
    ) -> Paper:
        """Explicit bibliographic intake, not a feature or numerical endorsement."""
        if not source_scope.strip() or not replication_note.strip():
            raise LiteratureDiscoveryError("explicit source scope and replication note required")
        items = self.list_observations(doi)
        if not items:
            raise LiteratureDiscoveryError("DOI not found in discovery queue")
        latest = items[-1]
        if latest.work_type not in {"journal-article", "proceedings-article"}:
            raise LiteratureDiscoveryError("preprints require manual independent review")
        paper = Paper(
            doi=latest.doi,
            title=latest.title,
            authors=latest.authors,
            published_year=latest.published_year,
            source_url=latest.source_url,
            venue=latest.venue,
            source_scope=source_scope,
            replication_note=replication_note,
        )
        try:
            catalog.add_paper(paper)
        except ResearchCatalogError as exc:
            raise LiteratureDiscoveryError("paper DOI already staged") from exc
        return paper


DEFAULT_LITERATURE_TOPICS = (
    "time series momentum",
    "volatility managed portfolios",
    "range based volatility estimator",
    "cross sectional stock momentum",
    "market regime detection",
)


def sweep_crossref_literature(
    store: LiteratureStore,
    *,
    client: httpx.Client,
    topics: tuple[str, ...] = DEFAULT_LITERATURE_TOPICS,
    limit_per_topic: int = 8,
) -> dict[str, object]:
    """Run a small curated topic sweep; store each DOI only once per sweep.

    The source hash for every candidate still corresponds to its own Crossref
    response. No discovered candidate is an approved mathematical indicator.
    """
    if not 1 <= len(topics) <= 8 or len(set(topics)) != len(topics):
        raise LiteratureDiscoveryError("sweep requires 1..8 distinct topics")
    if not 1 <= limit_per_topic <= _MAX_ITEMS:
        raise LiteratureDiscoveryError("invalid sweep limit")
    selected: set[str] = set()
    saved = 0
    succeeded = 0
    pending: list[str] = []
    status = "SWEEP_COMPLETE"
    for i, topic in enumerate(topics):
        try:
            batch = discover_crossref_literature(
                topic, client=client, limit=limit_per_topic,
            )
        except LiteratureRateLimited:
            status = "PARTIAL_RATE_LIMITED"
            pending = list(topics[i:])
            break
        except LiteratureDiscoveryError:
            status = "PARTIAL_FAILED"
            pending = list(topics[i:])
            break
        new_candidates = tuple(c for c in batch.candidates if c.doi not in selected)
        selected.update(c.doi for c in new_candidates)
        staged = LiteratureBatch(
            query=batch.query, observed_at=batch.observed_at,
            response_sha256=batch.response_sha256, candidates=new_candidates,
        )
        saved += store.capture_batch(staged)
        succeeded += 1
    return {
        "status": status,
        "topics_queried": succeeded,
        "pending_topics": pending,
        "unique_candidates": len(selected),
        "new_observations": saved,
        "calculator_approved": False,
        "orders_enabled": False,
        "queries": list(topics[:succeeded]),
    }
