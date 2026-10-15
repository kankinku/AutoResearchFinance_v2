"""D03 review queue: human-supplied rights/method notes are not source verification."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from research.indicator_engine.literature_discovery import (
    LiteratureStore,
    discover_crossref_literature,
)
from research.indicator_engine.paper_methodology import (
    FormulaDraft,
    FormulaNode,
    MethodReview,
    PaperMethodologyError,
    PaperMethodologyStore,
)
from tests.research.test_literature_discovery import OBS, _client, _record, _reply

DOI = "10.1234/example.2012"


def _db(tmp_path: Path) -> PaperMethodologyStore:
    archive = LiteratureStore(tmp_path / "research.sqlite")
    with _client(_reply(_record(DOI))) as client:
        batch = discover_crossref_literature(
            "time series momentum", client=client, limit=10, observed_at=OBS
        )
    archive.capture_batch(batch)
    return PaperMethodologyStore(tmp_path / "research.sqlite")


def _review(*, access: str = "FULL_TEXT_REVIEWED", rights: str = "UNKNOWN") -> MethodReview:
    return MethodReview(
        doi=DOI,
        source_record_hash="1" * 64,
        access_level=access,
        rights_status=rights,
        evidence_location="Publisher section 3.2, equation 4",
        method_summary=(
            "Rolling momentum uses lagged daily close returns and a fixed lookback window."
        ),
        license_reference="No checked reuse license; methodology only.",
        reviewed_by="method_reviewer",
    )


def _draft(review_hash: str) -> FormulaDraft:
    return FormulaDraft(
        doi=DOI,
        formula_id="lagged_momentum",
        revision=1,
        method_review_hash=review_hash,
        name="Lagged close momentum",
        rationale="Compare current close with a sufficiently lagged close, and evaluate next bar.",
        lookback=21,
        input_fields=("close",),
        signal_delay_bars=1,
        expression=FormulaNode(
            op="subtract",
            args=(
                FormulaNode(
                    op="divide",
                    args=(
                        FormulaNode(op="field", field="close"),
                        FormulaNode(
                            op="lag", period=21, args=(FormulaNode(op="field", field="close"),)
                        ),
                    ),
                ),
                FormulaNode(op="constant", value=1.0),
            ),
        ),
    )


def test_new_candidate_starts_unreviewed_and_cannot_stage_formula(tmp_path: Path) -> None:
    store = _db(tmp_path)
    queue = store.review_queue()
    assert len(queue) == 1
    assert queue[0]["doi"] == DOI
    assert queue[0]["status"] == "METHOD_REVIEW_REQUIRED"
    assert queue[0]["calculator_approved"] is False
    with pytest.raises(PaperMethodologyError, match="review"):
        store.propose_formula(_draft("0" * 64))


def test_methods_from_abstract_do_not_unlock_spec(tmp_path: Path) -> None:
    store = _db(tmp_path)
    entry = store.review_queue()[0]
    review = _review(access="ABSTRACT_ONLY").model_copy(
        update={"source_record_hash": entry["source_record_hash"]}
    )
    saved = store.record_review(review)
    assert saved == store.record_review(review)
    assert saved["status"] == "METHODOLOGY_NOTE_ONLY"
    with pytest.raises(PaperMethodologyError, match="full.text"):
        store.propose_formula(_draft(saved["review_hash"]))
    assert store.formulas(DOI) == ()


def test_fulltext_method_draft_is_versioned_but_never_executable(tmp_path: Path) -> None:
    store = _db(tmp_path)
    fingerprint = store.review_queue()[0]["source_record_hash"]
    review = _review().model_copy(update={"source_record_hash": fingerprint})
    first = store.record_review(review)
    saved = store.propose_formula(_draft(first["review_hash"]))
    assert saved["status"] == "PROPOSAL_ONLY_NOT_EXECUTABLE"
    assert saved["broker_executable"] is False
    assert saved["calculator_approved"] is False
    assert saved["independent_oos_approved"] is False
    assert store.propose_formula(_draft(first["review_hash"])) == saved
    assert len(store.formulas(DOI)) == 1
    assert len(store.review_queue()) == 1
    assert store.review_queue()[0]["formula_count"] == 1
    assert store.formulas(DOI)[0]["formula_hash"] == saved["formula_hash"]
    with pytest.raises(PaperMethodologyError, match="conflicting"):
        store.propose_formula(_draft(first["review_hash"]).model_copy(update={"lookback": 22}))
    next_version = _draft(first["review_hash"]).model_copy(update={"revision": 2, "lookback": 22})
    assert store.propose_formula(next_version)["revision"] == 2
    with pytest.raises(PaperMethodologyError, match="revision"):
        store.propose_formula(next_version.model_copy(update={"revision": 4}))


def test_unknown_rights_are_not_claimed_verified(tmp_path: Path) -> None:
    store = _db(tmp_path)
    source = store.review_queue()[0]["source_record_hash"]
    note = _review().model_copy(update={"source_record_hash": source})
    assert store.record_review(note)["rights_status"] == "UNKNOWN"
    status = store.review_queue()[0]
    assert status["license_independently_verified"] is False
    assert status["status"] == "METHODOLOGY_NOTE_ONLY"
    assert store.latest_review(DOI)["access_level"] == "FULL_TEXT_REVIEWED"
    with pytest.raises(PaperMethodologyError, match="source"):
        store.record_review(note.model_copy(update={"source_record_hash": "0" * 64}))


def test_invalid_expression_rejects_lookahead_and_unsafe_ops() -> None:
    with pytest.raises(ValidationError):
        FormulaNode(op="lag", period=-1, args=(FormulaNode(op="field", field="close"),))
    with pytest.raises(ValidationError):
        FormulaNode.model_validate({"op": "__import__", "args": []})
    with pytest.raises(ValidationError):
        FormulaNode.model_validate({"op": "field", "field": "future_close"})
    with pytest.raises(ValidationError):
        FormulaNode(op="constant", value=float("inf"))
    too_deep = {"op": "field", "field": "close"}
    for _ in range(9):
        too_deep = {"op": "lag", "period": 1, "args": [too_deep]}
    with pytest.raises(ValidationError, match="depth|size"):
        FormulaDraft.model_validate(
            {
                **_draft("a" * 64).model_dump(mode="json"),
                "expression": too_deep,
            }
        )


def test_tamper_and_unseen_doi_fail_closed(tmp_path: Path) -> None:
    store = _db(tmp_path)
    source = store.review_queue()[0]["source_record_hash"]
    review = store.record_review(_review().model_copy(update={"source_record_hash": source}))
    store.propose_formula(_draft(review["review_hash"]))
    with store._connect() as db:
        db.execute("UPDATE method_reviews SET payload_hash=? WHERE doi=?", ("0" * 64, DOI))
    with pytest.raises(PaperMethodologyError, match="integrity"):
        store.formulas(DOI)
    with pytest.raises(PaperMethodologyError, match="discovered"):
        store.record_review(_review().model_copy(update={"doi": "10.1234/missing"}))


def test_refuses_unsupported_claims_and_code_in_formula(tmp_path: Path) -> None:
    store = _db(tmp_path)
    source = store.review_queue()[0]["source_record_hash"]
    saved = store.record_review(_review().model_copy(update={"source_record_hash": source}))
    raw = _draft(saved["review_hash"]).model_dump(mode="json")
    raw["expression"] = "__import__('os').system('echo exploit')"
    with pytest.raises(ValidationError):
        FormulaDraft.model_validate(raw)
    with pytest.raises(ValidationError):
        MethodReview.model_validate({**_review().model_dump(), "rights_status": "APPROVED"})
    assert store.formulas(DOI) == ()


def test_cli_review_queue_and_non_executable_formula(tmp_path: Path, monkeypatch, capsys) -> None:
    import json
    import sys

    from research.indicator_engine.cli import main

    store = _db(tmp_path)
    path = tmp_path / "research.sqlite"

    def call(*extra: str) -> dict:
        monkeypatch.setattr(sys, "argv", ["research-cli", "--database", str(path), *extra])
        assert main() == 0
        return json.loads(capsys.readouterr().out)

    queued = call("list-paper-review-queue", "--limit", "2")
    assert queued["result"][0]["status"] == "METHOD_REVIEW_REQUIRED"
    record = _review().model_copy(
        update={
            "source_record_hash": store.review_queue()[0]["source_record_hash"],
        }
    )
    review_json = tmp_path / "review.json"
    review_json.write_text(record.model_dump_json(), encoding="utf-8")
    stored_review = call("record-paper-method-review", "--json-file", str(review_json))
    assert stored_review["result"]["calculator_approved"] is False

    formula_json = tmp_path / "formula.json"
    formula_json.write_text(
        _draft(stored_review["result"]["review_hash"]).model_dump_json(), encoding="utf-8"
    )
    drafted = call("propose-paper-formula", "--json-file", str(formula_json))
    assert drafted["result"]["status"] == "PROPOSAL_ONLY_NOT_EXECUTABLE"
    saved = call("list-paper-formulas", "--doi", DOI)
    assert saved["result"][0]["formula_hash"] == drafted["result"]["formula_hash"]
    assert saved["orders_enabled"] is False
