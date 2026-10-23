"""Development-only V3 parent audit sidecar, not official GPT checkpoint."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash


class SidecarIntegrityError(ValueError):
    pass


class SidecarInputError(ValueError):
    pass


@dataclass(frozen=True)
class SidecarRecord:
    sequence: int
    proposal_id: str
    decision: str
    previous_parent_hash: str
    selected_parent_hash: str
    event_hash: str
    is_counted_gpt_generation: bool = False


_HASH_CHARS = frozenset("0123456789abcdef")
_KEYS = frozenset(
    {
        "proposal_id",
        "economic_fingerprint",
        "strategy_hash",
        "audit_hash",
        "dataset_hash",
        "source_ledger_head",
        "donor_generations",
        "donor_component_hashes",
        "source_evidence_hashes",
        "source_s7_report_hashes",
        "entry_generation",
        "exit_generation",
        "risk_generation",
        "return",
        "mdd",
        "closed_trades",
        "risk_eligible",
        "economic_duplicate_of",
        "s7_status",
        "s7_evidence_hash",
        "measured_costs",
        "validation_origin",
        "model_origin",
        "broker_executable",
        "oos_approved",
    }
)
_S7 = frozenset(
    {
        "NOT_RUN",
        "NO_OBSERVED_EFFECT",
        "DIRECTION_MATCHED",
        "DIRECTION_MISMATCHED",
        "RETURN_WORSE",
        "DIRECTION_UNMEASURABLE",
    }
)


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HASH_CHARS


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def adjudicate_candidate(
    candidate: dict[str, Any],
    prior_fingerprints: frozenset[str] = frozenset(),
) -> str:
    if candidate.get("s7_status") not in _S7:
        raise SidecarInputError("unsupported S7 status")
    if candidate["economic_duplicate_of"]:
        return "REJECT_ECONOMIC_DUPLICATE"
    if candidate["economic_fingerprint"] in prior_fingerprints:
        return "REJECT_PRIOR_CANDIDATE_DUPLICATE"
    if not candidate["risk_eligible"]:
        return "REJECT_RISK"
    if candidate["s7_status"] == "NOT_RUN":
        return "REJECT_MISSING_S7"
    if candidate["s7_status"] != "DIRECTION_MATCHED":
        return "REJECT_S7_UNFAVORABLE_OR_NO_EFFECT"
    return "SELECT_RESEARCH_PARENT_CANDIDATE"


def _valid_receipt(value: dict[str, Any], cohort: dict[str, Any]) -> None:
    if set(value) != _KEYS:
        raise SidecarInputError("unexpected receipt fields")
    if any(
        not _sha(value[key])
        for key in (
            "proposal_id",
            "economic_fingerprint",
            "strategy_hash",
            "audit_hash",
            "dataset_hash",
            "source_ledger_head",
        )
    ):
        raise SidecarInputError("invalid receipt hashes")
    if value["dataset_hash"] != cohort["dataset_hash"] or (
        value["source_ledger_head"] != cohort["source_ledger_head"]
    ):
        raise SidecarInputError("wrong pinned source")
    generations = value["donor_generations"]
    if (
        not isinstance(generations, list)
        or len(generations) != len(cohort["source_generations"])
        or set(generations) != set(cohort["source_generations"])
        or any(type(x) is not int for x in generations)
    ):
        raise SidecarInputError("donor generations differ")
    for key in ("donor_component_hashes", "source_evidence_hashes", "source_s7_report_hashes"):
        listed = value[key]
        if (
            not isinstance(listed, list)
            or len(listed) != len(generations)
            or not all(_sha(x) for x in listed)
        ):
            raise SidecarInputError("donor source hashes differ")

    roles = [value[k] for k in ("entry_generation", "exit_generation", "risk_generation")]
    if any(type(x) is not int or x not in generations for x in roles) or len(set(roles)) != 3:
        raise SidecarInputError("donor roles invalid")
    if (
        type(value["risk_eligible"]) is not bool
        or not isinstance(value["economic_duplicate_of"], list)
        or any(type(g) is not int or g not in generations for g in value["economic_duplicate_of"])
    ):
        raise SidecarInputError("risk/duplicate flag invalid")
    from math import isfinite

    for name in ("return", "mdd", "measured_costs"):
        if type(value[name]) not in (int, float) or not isfinite(value[name]):
            raise SidecarInputError("invalid measured metrics")
    if not 0 <= value["mdd"] <= 1 or value["measured_costs"] < 0:
        raise SidecarInputError("invalid development risk metrics")
    if type(value["closed_trades"]) is not int or value["closed_trades"] < 0:
        raise SidecarInputError("invalid closed trade count")
    if value["s7_status"] not in _S7:
        raise SidecarInputError("unsupported S7 status")
    if value["s7_status"] == "NOT_RUN":
        if value["s7_evidence_hash"] is not None:
            raise SidecarInputError("unmeasured S7 cannot have proof")
    elif not _sha(value["s7_evidence_hash"]):
        raise SidecarInputError("missing S7 proof")
    if (
        value["validation_origin"] != "COSTED_S2_DEVELOPMENT_REPLAY"
        or value["model_origin"] != "SCRIPTED_NOT_GPT"
        or value["broker_executable"] is not False
        or value["oos_approved"] is not False
    ):
        raise SidecarInputError("unsupported origin or permission")


class ResearchParentSidecar:
    """Locally chained, atomic, research-only selection events."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise SidecarInputError("sidecar symlink unsupported")
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cohorts (
                    cohort_id TEXT PRIMARY KEY,
                    manifest_json TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidate_events (
                    cohort_id TEXT NOT NULL REFERENCES cohorts(cohort_id),
                    sequence INTEGER NOT NULL,
                    proposal_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    previous_hash TEXT,
                    event_hash TEXT NOT NULL,
                    PRIMARY KEY(cohort_id, sequence),
                    UNIQUE(cohort_id, proposal_id)
                );
            """)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=20000")
            yield db
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _manifest(self, db: sqlite3.Connection, cohort_id: str) -> dict[str, Any]:
        row = db.execute(
            "SELECT manifest_json, manifest_hash FROM cohorts WHERE cohort_id=?", (cohort_id,)
        ).fetchone()
        if row is None:
            raise SidecarIntegrityError("unknown sidecar cohort pin")
        try:
            manifest = json.loads(row["manifest_json"])
        except (ValueError, TypeError) as exc:
            raise SidecarIntegrityError("invalid cohort pin") from exc
        if (
            not isinstance(manifest, dict)
            or content_hash(manifest) != row["manifest_hash"]
            or manifest.get("cohort_id") != cohort_id
            or manifest.get("research_only") is not True
        ):
            raise SidecarIntegrityError("invalid cohort pin")
        return manifest

    def pin_cohort(
        self,
        *,
        cohort_id: str,
        source_ledger_head: str,
        dataset_hash: str,
        initial_parent_hash: str,
        source_generations: tuple[int, ...],
    ) -> str:
        if (
            not cohort_id
            or len(cohort_id) > 120
            or any(not _sha(h) for h in (source_ledger_head, dataset_hash, initial_parent_hash))
            or len(source_generations) < 2
            or len(set(source_generations)) != len(source_generations)
            or any(type(g) is not int or g < 1 for g in source_generations)
        ):
            raise SidecarInputError("invalid source pin")
        manifest = {
            "schema": "v3-development-parent-sidecar-v1",
            "cohort_id": cohort_id,
            "source_ledger_head": source_ledger_head,
            "dataset_hash": dataset_hash,
            "initial_parent_hash": initial_parent_hash,
            "source_generations": list(source_generations),
            "research_only": True,
        }
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT 1 FROM cohorts WHERE cohort_id=?", (cohort_id,)
            ).fetchone()
            if existing:
                if self._manifest(db, cohort_id) != manifest:
                    raise SidecarIntegrityError("conflicting cohort pin")
            else:
                db.execute(
                    "INSERT INTO cohorts VALUES (?,?,?)",
                    (cohort_id, _json(manifest), content_hash(manifest)),
                )
            db.commit()
        return cohort_id

    def _audit(self, db: sqlite3.Connection, cohort_id: str) -> dict[str, Any]:
        manifest = self._manifest(db, cohort_id)
        previous_hash: str | None = None
        current_parent = manifest["initial_parent_hash"]
        seen: set[str] = set()
        seen_fingerprints: set[str] = set()
        rows = db.execute(
            "SELECT * FROM candidate_events WHERE cohort_id=? ORDER BY sequence",
            (cohort_id,),
        ).fetchall()
        for sequence, row in enumerate(rows, start=1):
            try:
                event = json.loads(row["event_json"])
                trial = event["trial"]
                _valid_receipt(trial, manifest)
                decision = adjudicate_candidate(trial, frozenset(seen_fingerprints))
            except (KeyError, ValueError, TypeError) as exc:
                raise SidecarIntegrityError("candidate event chain invalid") from exc
            selected = (
                trial["strategy_hash"]
                if decision == "SELECT_RESEARCH_PARENT_CANDIDATE"
                else current_parent
            )
            if (
                row["sequence"] != sequence
                or row["previous_hash"] != previous_hash
                or row["proposal_id"] != trial["proposal_id"]
                or trial["proposal_id"] in seen
                or event.get("sequence") != sequence
                or event.get("cohort_id") != cohort_id
                or event.get("previous_hash") != previous_hash
                or event.get("input_hash") != content_hash(trial)
                or event.get("previous_parent_hash") != current_parent
                or event.get("decision") != decision
                or event.get("selected_parent_hash") != selected
                or event.get("is_counted_gpt_generation") is not False
                or row["event_hash"] != content_hash(event)
            ):
                raise SidecarIntegrityError("candidate event chain mismatch")
            seen.add(trial["proposal_id"])
            seen_fingerprints.add(trial["economic_fingerprint"])
            previous_hash = row["event_hash"]
            current_parent = selected
        return {
            "cohort_id": cohort_id,
            "attempt_count": len(rows),
            "selected_parent_hash": current_parent,
            "last_event_hash": previous_hash,
        }

    def audit(self, cohort_id: str) -> dict[str, Any]:
        with self._db() as db:
            return self._audit(db, cohort_id)

    def record_candidate(self, cohort_id: str, trial: dict[str, Any]) -> SidecarRecord:
        """Transactional one-shot candidate event, including rejected attempts.

        Repeating exactly the same proposal is a read-only replay; changing the
        source/performance under a previously used proposal ID is prohibited.
        """
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            status = self._audit(db, cohort_id)
            manifest = self._manifest(db, cohort_id)
            _valid_receipt(trial, manifest)
            prior = db.execute(
                "SELECT event_json, event_hash FROM candidate_events "
                "WHERE cohort_id=? AND proposal_id=?",
                (cohort_id, trial["proposal_id"]),
            ).fetchone()
            if prior is not None:
                previous = json.loads(prior["event_json"])
                if previous["input_hash"] != content_hash(trial):
                    raise SidecarIntegrityError("conflicting replay of proposal ID")
                return SidecarRecord(
                    sequence=previous["sequence"],
                    proposal_id=trial["proposal_id"],
                    decision=previous["decision"],
                    previous_parent_hash=previous["previous_parent_hash"],
                    selected_parent_hash=previous["selected_parent_hash"],
                    event_hash=prior["event_hash"],
                )
            receipts = db.execute(
                "SELECT event_json FROM candidate_events WHERE cohort_id=?", (cohort_id,)
            ).fetchall()
            prior_economics = frozenset(
                json.loads(x["event_json"])["trial"]["economic_fingerprint"] for x in receipts
            )
            decision = adjudicate_candidate(trial, prior_economics)
            parent = status["selected_parent_hash"]
            selected = (
                trial["strategy_hash"] if decision == "SELECT_RESEARCH_PARENT_CANDIDATE" else parent
            )
            sequence = status["attempt_count"] + 1
            event = {
                "schema": "v3-research-candidate-event-v1",
                "sequence": sequence,
                "cohort_id": cohort_id,
                "trial": trial,
                "input_hash": content_hash(trial),
                "previous_hash": status["last_event_hash"],
                "previous_parent_hash": parent,
                "decision": decision,
                "selected_parent_hash": selected,
                "is_counted_gpt_generation": False,
            }
            digest = content_hash(event)
            db.execute(
                "INSERT INTO candidate_events VALUES(?,?,?,?,?,?)",
                (
                    cohort_id,
                    sequence,
                    trial["proposal_id"],
                    _json(event),
                    status["last_event_hash"],
                    digest,
                ),
            )
            db.commit()
            return SidecarRecord(
                sequence,
                trial["proposal_id"],
                decision,
                parent,
                selected,
                digest,
            )
