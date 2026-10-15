"""D03: explicit non-executable paper-method notes and bounded formula AST drafts.

This module records human-supplied assertions. It NEVER fetches article bodies,
grants copyright permission, imports code, compiles a signal, verifies numerical
performance, or modifies the production indicator registry.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.integrity.hashes import content_hash
from research.indicator_engine.literature_discovery import LiteratureStore
from research.indicator_engine.models import DOI_PATTERN


class PaperMethodologyError(ValueError):
    """Reject mismatched/unaudited method claims or formula drafts."""


class FormulaNode(BaseModel):
    """Finite, declarative expression tree: data, not executable code."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal[
        "field",
        "constant",
        "lag",
        "rolling_mean",
        "rolling_max",
        "rolling_min",
        "add",
        "subtract",
        "multiply",
        "divide",
        "log",
    ]
    field: Literal["open", "high", "low", "close", "volume"] | None = None
    value: float | None = Field(default=None, allow_inf_nan=False)
    period: int | None = Field(default=None, ge=0, le=500)
    args: tuple[FormulaNode, ...] = ()

    @model_validator(mode="after")
    def check_arity(self) -> FormulaNode:
        arguments = len(self.args)
        required = {
            "field": 0,
            "constant": 0,
            "lag": 1,
            "rolling_mean": 1,
            "rolling_max": 1,
            "rolling_min": 1,
            "add": 2,
            "subtract": 2,
            "multiply": 2,
            "divide": 2,
            "log": 1,
        }[self.op]
        if arguments != required:
            raise ValueError("incorrect formula operator arity")
        if self.op == "field":
            if self.field is None or self.value is not None or self.period is not None:
                raise ValueError("field node requires only OHLCV field")
        elif self.op == "constant":
            if self.value is None or self.field is not None or self.period is not None:
                raise ValueError("constant node requires finite value")
        elif self.op in {"lag", "rolling_mean", "rolling_max", "rolling_min"}:
            minimum = 0 if self.op == "lag" else 2
            if (
                self.period is None
                or self.period < minimum
                or self.field is not None
                or self.value is not None
            ):
                raise ValueError("lag or rolling period is invalid")
        elif self.field is not None or self.value is not None or self.period is not None:
            raise ValueError("calculation node has extraneous parameters")
        return self


FormulaNode.model_rebuild()


class MethodReview(BaseModel):
    """User-authored observations do NOT themselves prove license or method rights."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    doi: str
    revision: int = Field(default=1, ge=1, le=50)
    source_record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    access_level: Literal["ABSTRACT_ONLY", "FULL_TEXT_REVIEWED", "UNAVAILABLE"]
    rights_status: Literal["UNKNOWN", "RESTRICTED", "OPEN_LICENSE_CLAIMED", "PERMISSION_CLAIMED"]
    evidence_location: str = Field(min_length=12, max_length=400)
    method_summary: str = Field(min_length=24, max_length=2000)
    license_reference: str = Field(min_length=15, max_length=400)
    reviewed_by: str = Field(min_length=3, max_length=80)
    status: Literal["METHODOLOGY_NOTE_ONLY"] = "METHODOLOGY_NOTE_ONLY"
    license_independently_verified: Literal[False] = False
    calculator_approved: Literal[False] = False
    broker_executable: Literal[False] = False

    @field_validator("doi")
    @classmethod
    def normalize_doi(cls, doi: str) -> str:
        value = doi.strip().lower()
        if DOI_PATTERN.fullmatch(value) is None:
            raise ValueError("invalid DOI")
        return value

    @model_validator(mode="after")
    def no_blank_notes(self) -> MethodReview:
        if not all(
            (
                self.evidence_location.strip(),
                self.method_summary.strip(),
                self.license_reference.strip(),
                self.reviewed_by.strip(),
            )
        ):
            raise ValueError("empty review evidence")
        return self


class FormulaDraft(BaseModel):
    """Versioned typed math sketch, never a live calculator or source code."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    doi: str
    formula_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    revision: int = Field(ge=1, le=100)
    method_review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    name: str = Field(min_length=4, max_length=120)
    rationale: str = Field(min_length=24, max_length=900)
    lookback: int = Field(ge=2, le=500)
    input_fields: tuple[Literal["open", "high", "low", "close", "volume"], ...] = Field(
        min_length=1, max_length=5
    )
    signal_delay_bars: Literal[1] = 1
    expression: FormulaNode
    status: Literal["PROPOSAL_ONLY_NOT_EXECUTABLE"] = "PROPOSAL_ONLY_NOT_EXECUTABLE"
    calculator_approved: Literal[False] = False
    broker_executable: Literal[False] = False
    independent_oos_approved: Literal[False] = False

    @field_validator("doi")
    @classmethod
    def normalize_doi(cls, doi: str) -> str:
        value = doi.strip().lower()
        if DOI_PATTERN.fullmatch(value) is None:
            raise ValueError("invalid DOI")
        return value

    @model_validator(mode="after")
    def check_graph(self) -> FormulaDraft:
        nodes = 0
        fields: set[str] = set()

        def visit(node: FormulaNode, depth: int) -> None:
            nonlocal nodes
            nodes += 1
            if nodes > 32 or depth > 7:
                raise ValueError("formula graph size or depth exceeds limit")
            if node.op == "field" and node.field:
                fields.add(node.field)
            if node.period is not None and node.period > self.lookback:
                raise ValueError("formula rolling/lag period exceeds declared lookback")
            for child in node.args:
                visit(child, depth + 1)

        visit(self.expression, 0)
        if not fields or fields != set(self.input_fields) or len(fields) != len(self.input_fields):
            raise ValueError("formula declared OHLCV inputs do not match expression")
        if not self.name.strip() or not self.rationale.strip():
            raise ValueError("blank formula rationale")
        return self


class PaperMethodologyStore:
    """SQLite append-only reviews and formula proposals with hash-bound provenance."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.literature = LiteratureStore(database)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS method_reviews (
                doi TEXT NOT NULL, revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
                PRIMARY KEY (doi, revision)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS formula_drafts (
                doi TEXT NOT NULL, formula_id TEXT NOT NULL, revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
                PRIMARY KEY (doi, formula_id, revision)
            )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @staticmethod
    def _decode(row: sqlite3.Row, cls: type[MethodReview] | type[FormulaDraft]) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict) or content_hash(payload) != row["payload_hash"]:
                raise PaperMethodologyError("paper methodology integrity failure")
            if payload["doi"] != row["doi"] or payload["revision"] != row["revision"]:
                raise PaperMethodologyError("paper methodology identity integrity failure")
            if "formula_id" in row.keys() and payload["formula_id"] != row["formula_id"]:
                raise PaperMethodologyError("formula identity integrity failure")
            model = cls.model_validate(payload)
            if model.calculator_approved or model.broker_executable:
                raise PaperMethodologyError("unsafe stored status integrity failure")
            return {
                **model.model_dump(mode="json"),
                **{"review_hash" if cls is MethodReview else "formula_hash": row["payload_hash"]},
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise PaperMethodologyError("paper methodology integrity failure") from exc

    def _candidate(self, doi: str) -> dict[str, Any]:
        candidates = self.literature.list_observations(doi.lower())
        if not candidates:
            raise PaperMethodologyError("DOI has not been discovered")
        return candidates[-1].record()

    def latest_review(self, doi: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM method_reviews WHERE doi=? ORDER BY revision DESC LIMIT 1",
                (doi.lower(),),
            ).fetchone()
        return self._decode(row, MethodReview) if row is not None else None

    def record_review(self, note: MethodReview) -> dict[str, Any]:
        self._candidate(note.doi)
        # Source snapshot must exist, even if later Crossref metadata changes.
        observations = self.literature.list_observations(note.doi)
        if note.source_record_hash not in {obs.source_record_hash for obs in observations}:
            raise PaperMethodologyError("review source hash does not match discovered evidence")
        payload = note.model_dump(mode="json")
        digest = content_hash(payload)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM method_reviews WHERE doi=? ORDER BY revision",
                (note.doi,),
            ).fetchall()
            for row in rows:
                self._decode(row, MethodReview)
            if any(row["revision"] == note.revision for row in rows):
                same = next(row for row in rows if row["revision"] == note.revision)
                if same["payload_hash"] != digest:
                    raise PaperMethodologyError("conflicting review revision")
                return {**payload, "review_hash": digest}
            expected = (rows[-1]["revision"] + 1) if rows else 1
            if note.revision != expected:
                raise PaperMethodologyError("review revision must advance sequentially")
            db.execute(
                "INSERT INTO method_reviews VALUES (?,?,?,?)",
                (
                    note.doi,
                    note.revision,
                    json.dumps(payload, sort_keys=True),
                    digest,
                ),
            )
        return {**payload, "review_hash": digest}

    def formulas(self, doi: str) -> tuple[dict[str, Any], ...]:
        # Also validates review content, so corrupted approval claims fail closed.
        self.latest_review(doi)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM formula_drafts WHERE doi=? ORDER BY formula_id,revision",
                (doi.lower(),),
            ).fetchall()
        return tuple(self._decode(row, FormulaDraft) for row in rows)

    def propose_formula(self, draft: FormulaDraft) -> dict[str, Any]:
        review = self.latest_review(draft.doi)
        if review is None:
            raise PaperMethodologyError("method review required before formula proposal")
        if review["access_level"] != "FULL_TEXT_REVIEWED":
            raise PaperMethodologyError("full-text method review required for formula proposal")
        if draft.method_review_hash != review["review_hash"]:
            raise PaperMethodologyError("formula review hash is stale or unrelated")
        self._candidate(draft.doi)
        payload = draft.model_dump(mode="json")
        digest = content_hash(payload)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM formula_drafts WHERE doi=? AND formula_id=? ORDER BY revision",
                (draft.doi, draft.formula_id),
            ).fetchall()
            for row in rows:
                self._decode(row, FormulaDraft)
            if any(row["revision"] == draft.revision for row in rows):
                previous = next(row for row in rows if row["revision"] == draft.revision)
                if previous["payload_hash"] != digest:
                    raise PaperMethodologyError("conflicting formula revision")
                return {**payload, "formula_hash": digest}
            expected = (rows[-1]["revision"] + 1) if rows else 1
            if draft.revision != expected:
                raise PaperMethodologyError("formula revision must advance sequentially")
            db.execute(
                "INSERT INTO formula_drafts VALUES (?,?,?,?,?)",
                (
                    draft.doi,
                    draft.formula_id,
                    draft.revision,
                    json.dumps(payload, sort_keys=True),
                    digest,
                ),
            )
        return {**payload, "formula_hash": digest}

    def review_queue(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise PaperMethodologyError("invalid review queue limit")
        output = []
        for candidate in self.literature.list_candidates(limit=limit):
            last = self.latest_review(candidate.doi)
            drafts = self.formulas(candidate.doi)
            output.append(
                {
                    "doi": candidate.doi,
                    "title": candidate.title,
                    "source_record_hash": candidate.source_record_hash,
                    "status": last["status"] if last else "METHOD_REVIEW_REQUIRED",
                    "rights_status": last["rights_status"] if last else "UNKNOWN",
                    "access_level": last["access_level"] if last else "UNAVAILABLE",
                    "review_revision": last["revision"] if last else 0,
                    "formula_count": len(drafts),
                    "license_independently_verified": False,
                    "calculator_approved": False,
                    "broker_executable": False,
                }
            )
        return tuple(output)
