"""D04 sandbox-only typed formula evaluation, numeric references and versioned proof ledger."""

from __future__ import annotations

from pathlib import Path

import pytest

from research.indicator_engine.formula_calculator import (
    FormulaCalculatorError,
    FormulaPreviewStore,
    evaluate_formula,
    independent_formula_reference,
)
from research.indicator_engine.paper_methodology import FormulaNode, PaperMethodologyStore
from tests.research.test_paper_methodology_d03 import DOI, _db, _draft, _review


def _saved(tmp_path: Path) -> tuple[PaperMethodologyStore, dict]:
    store = _db(tmp_path)
    source = store.review_queue()[0]["source_record_hash"]
    recorded = store.record_review(_review().model_copy(update={"source_record_hash": source}))
    draft = store.propose_formula(_draft(recorded["review_hash"]))
    return store, draft


def _bars(length: int = 93) -> dict[str, tuple[float, ...]]:
    close = tuple(101.0 + k * 0.13 + (k % 9) * 0.17 for k in range(length))
    return {
        "close": close,
        "open": tuple(c - 0.15 for c in close),
        "high": tuple(c + 0.7 for c in close),
        "low": tuple(c - 0.9 for c in close),
        "volume": tuple(1000.0 + 3.0 * k for k in range(length)),
    }


def test_sandbox_formula_computes_lagged_return_and_reference(tmp_path: Path) -> None:
    _, item = _saved(tmp_path)
    bars = {"close": _bars()["close"]}
    result = evaluate_formula(item, bars)
    truth = independent_formula_reference(item, bars)
    assert len(result) == len(bars["close"])
    assert result == pytest.approx(truth, nan_ok=True)
    assert all(result[i] is None for i in range(21))
    assert result[21] == pytest.approx(bars["close"][21] / bars["close"][0] - 1)
    assert result[22] == pytest.approx(bars["close"][22] / bars["close"][1] - 1)


def test_repeatable_reference_proof_and_versioned_ledger(tmp_path: Path) -> None:
    store, item = _saved(tmp_path)
    preview = FormulaPreviewStore(store)
    bars = {"close": _bars()["close"]}
    report = preview.evaluate(DOI, "lagged_momentum", 1, bars)
    assert report["status"] == "RESEARCH_NUMERIC_CROSSCHECK_ONLY"
    assert report["calculator_approved"] is False
    assert report["broker_executable"] is False
    assert report["independent_oos_approved"] is False
    assert report["math_reference_match"] is True
    assert report["prefix_causal_check"] is True
    assert report["finite_outputs"] > 0
    assert preview.evaluate(DOI, "lagged_momentum", 1, bars) == report
    assert preview.list_reports(DOI) == (report,)
    assert len(store.formulas(DOI)) == 1
    new_version = _draft(item["method_review_hash"]).model_copy(update={"revision": 2})
    store.propose_formula(new_version)
    newer = preview.evaluate(DOI, "lagged_momentum", 2, bars)
    assert newer["formula_revision"] == 2
    assert len(preview.list_reports(DOI)) == 2
    assert report["formula_hash"] != newer["formula_hash"]


def test_all_operators_against_independent_scalar(tmp_path: Path) -> None:
    _, original = _saved(tmp_path)
    base = _draft(original["method_review_hash"])
    fields = (
        FormulaNode(op="field", field="close"),
        FormulaNode(op="field", field="high"),
        FormulaNode(op="field", field="low"),
    )
    expressions = [
        FormulaNode(op="rolling_mean", period=7, args=(fields[0],)),
        FormulaNode(op="rolling_max", period=5, args=(fields[1],)),
        FormulaNode(op="rolling_min", period=5, args=(fields[2],)),
        FormulaNode(op="log", args=(fields[0],)),
        FormulaNode(op="add", args=(fields[0], FormulaNode(op="constant", value=4.0))),
        FormulaNode(op="multiply", args=(fields[0], FormulaNode(op="constant", value=0.2))),
        FormulaNode(op="subtract", args=(fields[1], fields[2])),
        FormulaNode(op="divide", args=(fields[0], fields[1])),
        FormulaNode(op="lag", period=0, args=(fields[0],)),
        FormulaNode(
            op="lag", period=4, args=(FormulaNode(op="rolling_mean", period=6, args=(fields[0],)),)
        ),
    ]
    for node in expressions:
        uses = tuple(
            sorted({n.field for n in _walk(node) if n.op == "field" and n.field is not None})
        )
        draft = base.model_copy(update={"expression": node, "input_fields": uses})
        raw = draft.model_dump(mode="json")
        bars = {k: v for k, v in _bars().items() if k in uses}
        actual = evaluate_formula(raw, bars)
        expected = independent_formula_reference(raw, bars)
        for a, b in zip(actual, expected, strict=True):
            if b is None:
                assert a is None
            else:
                assert a == pytest.approx(b, rel=1e-12, abs=1e-10)


def _walk(node: FormulaNode) -> tuple[FormulaNode, ...]:
    return (node, *tuple(child for part in node.args for child in _walk(part)))


def test_zero_division_and_invalid_log_produce_missing_not_inf(tmp_path: Path) -> None:
    _, item = _saved(tmp_path)
    base = _draft(item["method_review_hash"])
    close = FormulaNode(op="field", field="close")
    zero = FormulaNode(op="subtract", args=(close, close))
    for expression in (
        FormulaNode(op="divide", args=(close, zero)),
        FormulaNode(op="log", args=(zero,)),
    ):
        draft = base.model_copy(update={"expression": expression})
        output = evaluate_formula(draft.model_dump(mode="json"), {"close": _bars()["close"]})
        assert all(x is None for x in output)


def test_prefix_is_causal_and_requires_next_bar_for_execution(tmp_path: Path) -> None:
    _, item = _saved(tmp_path)
    original = {"close": _bars()["close"]}
    observed = evaluate_formula(item, original)
    edited = {
        "close": (*original["close"][:67], *tuple(value * 3 for value in original["close"][67:]))
    }
    after = evaluate_formula(item, edited)
    assert observed[:67] == after[:67]
    assert observed[68] != after[68]


@pytest.mark.parametrize(
    "bad",
    [
        {"close": (100.0, float("nan"), 102.0)},
        {"close": (100.0, 0.0, 102.0)},
        {"close": (100.0, float("inf"), 102.0)},
        {"close": (100.0,) * 2050},
        {"close": "user-supplied executable text"},
        {"close": []},
    ],
)
def test_missing_nonfinite_and_unbounded_bars_fail_closed(tmp_path: Path, bad) -> None:
    _, item = _saved(tmp_path)
    with pytest.raises(FormulaCalculatorError):
        evaluate_formula(item, bad)


def test_stale_review_tampering_and_unseen_formula_blocked(tmp_path: Path) -> None:
    store, item = _saved(tmp_path)
    preview = FormulaPreviewStore(store)
    bars = {"close": _bars()["close"]}
    with pytest.raises(FormulaCalculatorError, match="not found"):
        preview.evaluate(DOI, "missing", 1, bars)
    review = store.latest_review(DOI)
    assert review is not None
    newer_review = _review().model_copy(
        update={
            "source_record_hash": review["source_record_hash"],
            "revision": 2,
            "method_summary": (
                "A different methods review record supersedes the earlier interpretation."
            ),
        }
    )
    store.record_review(newer_review)
    with pytest.raises(FormulaCalculatorError, match="stale"):
        preview.evaluate(DOI, "lagged_momentum", 1, bars)


def test_preview_ledger_corruption_fails_closed(tmp_path: Path) -> None:
    store, _ = _saved(tmp_path)
    preview = FormulaPreviewStore(store)
    bars = {"close": _bars()["close"]}
    preview.evaluate(DOI, "lagged_momentum", 1, bars)
    with preview._connect() as db:
        db.execute("UPDATE formula_numeric_proofs SET payload_hash=?", ("0" * 64,))
    with pytest.raises(FormulaCalculatorError, match="integrity"):
        preview.list_reports(DOI)
    with pytest.raises(FormulaCalculatorError, match="integrity"):
        preview.evaluate(DOI, "lagged_momentum", 1, bars)


def test_mismatched_fields_and_structure_rejected(tmp_path: Path) -> None:
    _, item = _saved(tmp_path)
    with pytest.raises(FormulaCalculatorError, match="fields"):
        evaluate_formula(item, _bars())  # extraneous OHLC fields disallowed
    with pytest.raises(FormulaCalculatorError):
        evaluate_formula(item, {"close": [100.0, 101.0], "high": [101.0]})


def test_offline_preview_cli_preserves_unapproved_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json
    import sys

    from research.indicator_engine.cli import main

    store, _ = _saved(tmp_path)
    src = tmp_path / "market-bars.json"
    src.write_text(json.dumps({"close": _bars()["close"]}), encoding="utf-8")
    database = tmp_path / "research.sqlite"

    def cli(*args: str) -> tuple[int, dict]:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "indicator-research",
                "--database",
                str(database),
                *args,
            ],
        )
        code = main()
        return code, json.loads(capsys.readouterr().out)

    code, output = cli(
        "preview-paper-calculation",
        "--doi",
        DOI,
        "--formula-id",
        "lagged_momentum",
        "--revision",
        "1",
        "--input-json-file",
        str(src),
    )
    assert code == 0
    assert output["status"] == "RESEARCH_NUMERIC_CROSSCHECK_ONLY"
    assert output["calculator_approved"] is False
    assert output["orders_enabled"] is False
    assert output["result"]["formula_revision"] == 1

    code, evidence = cli("list-paper-calculation-proofs", "--doi", DOI)
    assert code == 0
    assert len(evidence["result"]) == 1
    assert evidence["result"][0]["output_hash"] == output["result"]["output_hash"]

    denied = tmp_path / "wrong-data.json"
    denied.write_text(json.dumps({"close": [0, 1, 2]}), encoding="utf-8")
    code, bad = cli(
        "preview-paper-calculation",
        "--doi",
        DOI,
        "--formula-id",
        "lagged_momentum",
        "--revision",
        "1",
        "--input-json-file",
        str(denied),
    )
    assert code == 2
    assert bad["status"] == "FORMULA_PREVIEW_REJECTED"
    assert bad["orders_enabled"] is False
