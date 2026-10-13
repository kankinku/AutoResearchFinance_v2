"""SQLite academic evidence catalog, independent of runtime trading/feature registry.

All writes are explicit and transactional. A citation is provenance, not
validation. Only recomputed, deterministic calculator evidence can promote
an indicator; a paper record alone never enables execution.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.integrity.hashes import content_hash
from research.indicator_engine.models import IndicatorCandidate, Paper, VerificationResult
from research.indicator_engine.signals import verify_signal_on_synthetic_prices


class ResearchCatalogError(ValueError):
    """Rejected research catalog operation; runtime registry is unchanged."""


class ResearchCatalog:
    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    doi TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS indicators (
                    signal_id TEXT PRIMARY KEY,
                    paper_doi TEXT NOT NULL REFERENCES papers(doi),
                    status TEXT NOT NULL CHECK(status IN (
                        'PROPOSED','VERIFIED','QUARANTINED')),
                    payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    verification_json TEXT,
                    quarantine_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_indicator_status ON indicators(status);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def add_paper(self, paper: Paper) -> None:
        payload = paper.model_dump(mode="json")
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO papers(doi,payload,payload_hash) VALUES(?,?,?)",
                    (paper.doi, json.dumps(payload, sort_keys=True), content_hash(payload)),
                )
        except sqlite3.IntegrityError as exc:
            raise ResearchCatalogError("paper DOI already registered") from exc

    def get_paper(self, doi: str) -> Paper:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM papers WHERE doi=?", (doi.lower(),)).fetchone()
        if row is None:
            raise ResearchCatalogError("paper not found")
        return Paper.model_validate_json(str(row["payload"]))

    def list_papers(self) -> tuple[Paper, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT payload FROM papers ORDER BY doi").fetchall()
        return tuple(Paper.model_validate_json(str(r["payload"])) for r in rows)

    def add_indicator(self, signal: IndicatorCandidate) -> None:
        if signal.status != "PROPOSED":
            raise ResearchCatalogError("new indicators must start PROPOSED")
        payload = signal.model_dump(mode="json")
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO indicators(signal_id,paper_doi,status,payload,payload_hash)"
                    " VALUES(?,?,?,?,?)",
                    (
                        signal.signal_id,
                        signal.paper_doi,
                        signal.status,
                        json.dumps(payload, sort_keys=True),
                        content_hash(payload),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ResearchCatalogError("missing paper or duplicate signal identity") from exc

    def get_indicator(self, signal_id: str) -> IndicatorCandidate:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload,payload_hash,status FROM indicators WHERE signal_id=?",
                (signal_id,),
            ).fetchone()
        if row is None:
            raise ResearchCatalogError("indicator not found")
        payload = json.loads(str(row["payload"]))
        if content_hash(payload) != row["payload_hash"] or payload.get("status") != row["status"]:
            raise ResearchCatalogError("indicator identity/status integrity failure")
        return IndicatorCandidate.model_validate(payload)

    def list_indicators(self, *, eligible_only: bool = False) -> tuple[IndicatorCandidate, ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT signal_id FROM indicators "
                + ("WHERE status='VERIFIED' " if eligible_only else "")
                + "ORDER BY signal_id"
            ).fetchall()
        return tuple(self.get_indicator(str(r["signal_id"])) for r in rows)

    def verify_and_register(
        self, signal_id: str, evidence: VerificationResult
    ) -> IndicatorCandidate:
        signal = self.get_indicator(signal_id)
        if signal.status != "PROPOSED":
            raise ResearchCatalogError("only a proposed signal can be verified")
        recomputed = verify_signal_on_synthetic_prices(signal)
        if not recomputed.passed or not evidence.passed or recomputed != evidence:
            raise ResearchCatalogError("reference, leak or identity checks failed")
        updated = signal.model_copy(update={"status": "VERIFIED"})
        payload = updated.model_dump(mode="json")
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE indicators SET status=?,payload=?,payload_hash=?,verification_json=? "
                "WHERE signal_id=? AND status='PROPOSED' AND payload_hash=?",
                (
                    "VERIFIED",
                    json.dumps(payload, sort_keys=True),
                    content_hash(payload),
                    evidence.model_dump_json(),
                    signal_id,
                    content_hash(signal.model_dump(mode="json")),
                ),
            )
        if cursor.rowcount != 1:
            raise ResearchCatalogError("concurrent update or stale indicator identity")
        return updated

    def quarantine(self, signal_id: str, *, reason: str) -> IndicatorCandidate:
        if not reason.strip():
            raise ResearchCatalogError("quarantine requires a reason")
        signal = self.get_indicator(signal_id)
        if signal.status != "PROPOSED":
            raise ResearchCatalogError("verified signals require a new version, not mutation")
        updated = signal.model_copy(update={"status": "QUARANTINED"})
        payload = updated.model_dump(mode="json")
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE indicators SET status=?,payload=?,payload_hash=?,quarantine_reason=? "
                "WHERE signal_id=? AND status='PROPOSED'",
                (
                    "QUARANTINED",
                    json.dumps(payload, sort_keys=True),
                    content_hash(payload),
                    reason,
                    signal_id,
                ),
            )
        if cursor.rowcount != 1:
            raise ResearchCatalogError("concurrent update")
        return updated
