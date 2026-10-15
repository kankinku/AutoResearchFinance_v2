"""D04: sandbox-only typed OHLCV formula evaluation and independent numeric checks.

Strictly research-only: no arbitrary Python compilation, broker instructions, live
indicator registration, sealed OOS input, or license/alpha approval.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from core.integrity.hashes import content_hash
from research.indicator_engine.paper_methodology import (
    FormulaDraft,
    FormulaNode,
    PaperMethodologyError,
    PaperMethodologyStore,
)

MAX_ROWS = 2048
MAX_MAGNITUDE = 1e12
CALCULATOR_VERSION = "safe_formula_ast_v1"


class FormulaCalculatorError(ValueError):
    """Unsafe input, stale formula revision, or numeric reference disagreement."""


def _finite(value: float) -> float | None:
    if not math.isfinite(value) or abs(value) > MAX_MAGNITUDE:
        return None
    return value


def _input(draft: FormulaDraft, raw: Mapping[str, Sequence[float]]) -> dict[str, tuple[float, ...]]:
    expected = set(draft.input_fields)
    if set(raw) != expected:
        raise FormulaCalculatorError("input fields must exactly match draft")
    if not expected:
        raise FormulaCalculatorError("empty formula input fields")
    result: dict[str, tuple[float, ...]] = {}
    count: int | None = None
    for field in draft.input_fields:
        series = raw[field]
        if isinstance(series, (str, bytes)) or not isinstance(series, Sequence):
            raise FormulaCalculatorError("OHLCV values must be finite numeric sequences")
        if count is None:
            count = len(series)
            if not 1 <= count <= MAX_ROWS:
                raise FormulaCalculatorError("unbounded or empty market series")
        if len(series) != count:
            raise FormulaCalculatorError("unequal OHLCV series length")
        values: list[float] = []
        for x in series:
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise FormulaCalculatorError("non-numeric market observation")
            n = float(x)
            if not math.isfinite(n) or abs(n) > MAX_MAGNITUDE:
                raise FormulaCalculatorError("nonfinite or unbounded observation")
            if (field == "volume" and n < 0) or (field != "volume" and n <= 0):
                raise FormulaCalculatorError("invalid nonpositive OHLCV observation")
            values.append(n)
        result[field] = tuple(values)
    # Enforce structural candle rules only when both fields were supplied.
    if "high" in result and "low" in result:
        if any(high < low for high, low in zip(result["high"], result["low"], strict=True)):
            raise FormulaCalculatorError("inconsistent high/low observations")
    for p in ("open", "close"):
        if "high" in result and p in result:
            if any(h < v for h, v in zip(result["high"], result[p], strict=True)):
                raise FormulaCalculatorError("high is lower than open/close")
        if "low" in result and p in result:
            if any(low > value for low, value in zip(result["low"], result[p], strict=True)):
                raise FormulaCalculatorError("low is higher than open/close")
    return result


def _operation(op: str, nums: tuple[float, ...]) -> float | None:
    try:
        if op == "add":
            computed = nums[0] + nums[1]
        elif op == "subtract":
            computed = nums[0] - nums[1]
        elif op == "multiply":
            computed = nums[0] * nums[1]
        elif op == "divide":
            if nums[1] == 0:
                return None
            computed = nums[0] / nums[1]
        elif op == "log":
            if nums[0] <= 0:
                return None
            computed = math.log(nums[0])
        else:
            raise FormulaCalculatorError("unsupported formula arithmetic operation")
    except (OverflowError, ZeroDivisionError, ValueError):
        return None
    return _finite(computed)


def _vector(
    node: FormulaNode,
    data: dict[str, tuple[float, ...]],
    cache: dict[int, tuple[float | None, ...]],
) -> tuple[float | None, ...]:
    ident = id(node)
    if ident in cache:
        return cache[ident]
    n = len(next(iter(data.values())))
    output: tuple[float | None, ...]
    if node.op == "field":
        assert node.field is not None
        output = data[node.field]
    elif node.op == "constant":
        assert node.value is not None
        output = (node.value,) * n
    else:
        args = tuple(_vector(part, data, cache) for part in node.args)
        if node.op == "lag":
            assert node.period is not None
            p = node.period
            output = (None,) * min(p, n) + (args[0][: n - p] if p < n else ())
        elif node.op in {"rolling_mean", "rolling_max", "rolling_min"}:
            assert node.period is not None
            p = node.period
            values: list[float | None] = []
            for t in range(n):
                if t + 1 < p:
                    values.append(None)
                    continue
                window = args[0][t - p + 1 : t + 1]
                if any(item is None for item in window):
                    values.append(None)
                    continue
                complete = tuple(float(item) for item in window if item is not None)
                if node.op == "rolling_mean":
                    values.append(_finite(math.fsum(complete) / p))
                elif node.op == "rolling_max":
                    values.append(max(complete))
                else:
                    values.append(min(complete))
            output = tuple(values)
        else:
            result: list[float | None] = []
            for t in range(n):
                at = tuple(item[t] for item in args)
                if any(v is None for v in at):
                    result.append(None)
                else:
                    complete = tuple(float(v) for v in at if v is not None)
                    result.append(_operation(node.op, complete))
            output = tuple(result)
    cache[ident] = output
    return output


def _parse_draft(proposal: FormulaDraft | dict[str, Any]) -> FormulaDraft:
    if isinstance(proposal, FormulaDraft):
        return proposal
    if "formula_hash" in proposal:
        payload = {k: v for k, v in proposal.items() if k != "formula_hash"}
        if content_hash(payload) != proposal["formula_hash"]:
            raise FormulaCalculatorError("stored formula identity integrity failure")
        return FormulaDraft.model_validate(payload)
    return FormulaDraft.model_validate(proposal)


def evaluate_formula(
    proposal: FormulaDraft | dict[str, Any],
    inputs: Mapping[str, Sequence[float]],
) -> tuple[float | None, ...]:
    """Evaluate a bounded AST on completed research bars; never create trades."""
    draft = _parse_draft(proposal)
    prices = _input(draft, inputs)
    return _vector(draft.expression, prices, {})


def _scalar(
    node: FormulaNode,
    t: int,
    data: dict[str, tuple[float, ...]],
) -> float | None:
    """Independent direct per-bar implementation; no vector cache or future indices."""
    if node.op == "field":
        assert node.field is not None
        return data[node.field][t]
    if node.op == "constant":
        assert node.value is not None
        return node.value
    if node.op == "lag":
        assert node.period is not None
        if t < node.period:
            return None
        return _scalar(node.args[0], t - node.period, data)
    if node.op in ("rolling_mean", "rolling_max", "rolling_min"):
        assert node.period is not None
        if t < node.period - 1:
            return None
        observed = [_scalar(node.args[0], k, data) for k in range(t - node.period + 1, t + 1)]
        if any(v is None for v in observed):
            return None
        clean = [float(v) for v in observed if v is not None]
        if node.op == "rolling_mean":
            return _finite(sum(clean) / len(clean))
        if node.op == "rolling_max":
            return max(clean)
        return min(clean)
    a = tuple(_scalar(child, t, data) for child in node.args)
    if any(v is None for v in a):
        return None
    return _operation(node.op, tuple(float(v) for v in a if v is not None))


def independent_formula_reference(
    proposal: FormulaDraft | dict[str, Any],
    inputs: Mapping[str, Sequence[float]],
) -> tuple[float | None, ...]:
    draft = _parse_draft(proposal)
    values = _input(draft, inputs)
    n = len(next(iter(values.values())))
    return tuple(_scalar(draft.expression, t, values) for t in range(n))


def _same(
    left: tuple[float | None, ...],
    right: tuple[float | None, ...],
) -> bool:
    if len(left) != len(right):
        return False
    return all(
        (a is None and b is None)
        or (
            a is not None
            and b is not None
            and math.isclose(
                a,
                b,
                rel_tol=1e-10,
                abs_tol=1e-9,
            )
        )
        for a, b in zip(left, right, strict=True)
    )


class FormulaPreviewStore:
    """Research numerical proof ledger, deliberately NOT a verified signal registry."""

    def __init__(self, methods: PaperMethodologyStore) -> None:
        self.methods = methods
        self.database = methods.database
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS formula_numeric_proofs (
                doi TEXT NOT NULL, formula_id TEXT NOT NULL,
                revision INTEGER NOT NULL, input_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
                PRIMARY KEY(doi, formula_id, revision, input_hash)
            )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload_json"])
            if (
                not isinstance(payload, dict)
                or content_hash(payload) != row["payload_hash"]
                or payload["doi"] != row["doi"]
                or payload["formula_id"] != row["formula_id"]
                or payload["formula_revision"] != row["revision"]
                or payload["input_hash"] != row["input_hash"]
                or payload["status"] != "RESEARCH_NUMERIC_CROSSCHECK_ONLY"
                or payload["calculator_approved"] is not False
                or payload["broker_executable"] is not False
                or payload["independent_oos_approved"] is not False
            ):
                raise FormulaCalculatorError("formula numeric ledger integrity failure")
            return payload
        except (ValueError, KeyError, TypeError) as exc:
            raise FormulaCalculatorError("formula numeric ledger integrity failure") from exc

    def list_reports(self, doi: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM formula_numeric_proofs WHERE doi=? "
                "ORDER BY formula_id, revision, input_hash",
                (doi.lower(),),
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def evaluate(
        self,
        doi: str,
        formula_id: str,
        revision: int,
        inputs: Mapping[str, Sequence[float]],
    ) -> dict[str, Any]:
        try:
            proposals = self.methods.formulas(doi)
            item = next(
                (
                    x
                    for x in proposals
                    if (x["formula_id"] == formula_id and x["revision"] == revision)
                ),
                None,
            )
            if item is None:
                raise FormulaCalculatorError("formula version not found")
            latest = self.methods.latest_review(doi)
            if latest is None or item["method_review_hash"] != latest["review_hash"]:
                raise FormulaCalculatorError("stale method review for formula version")
            # Method/provenance claims remain unverified. This is numerical research ONLY.
            proposal = _parse_draft(item)
            data = _input(proposal, inputs)
            actual = evaluate_formula(proposal, data)
            independent = independent_formula_reference(proposal, data)
            if not _same(actual, independent):
                raise FormulaCalculatorError("independent numerical reference mismatch")
            n = len(actual)
            prefix_points = sorted(set([1, min(n, proposal.lookback + 1), max(1, n // 2), n]))
            for m in prefix_points:
                segment = {key: values[:m] for key, values in data.items()}
                if not _same(evaluate_formula(proposal, segment), actual[:m]):
                    raise FormulaCalculatorError("causal prefix computation mismatch")
            if not any(x is not None for x in actual):
                raise FormulaCalculatorError("no computable output for proposed lookback")
            body: dict[str, Any] = {
                "doi": proposal.doi,
                "formula_id": proposal.formula_id,
                "formula_revision": proposal.revision,
                "formula_hash": item["formula_hash"],
                "method_review_hash": proposal.method_review_hash,
                "calculator_version": CALCULATOR_VERSION,
                "input_hash": content_hash(data),
                "output_hash": content_hash(actual),
                "input_bars": n,
                "finite_outputs": sum(v is not None for v in actual),
                "warmup_bars": next((k for k, x in enumerate(actual) if x is not None), n),
                "math_reference_match": True,
                "prefix_causal_check": True,
                "earliest_execution_delay_bars": 1,
                "status": "RESEARCH_NUMERIC_CROSSCHECK_ONLY",
                "calculator_approved": False,
                "broker_executable": False,
                "independent_oos_approved": False,
            }
            digest = content_hash(body)
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                prior = db.execute(
                    "SELECT * FROM formula_numeric_proofs "
                    "WHERE doi=? AND formula_id=? AND revision=? AND input_hash=?",
                    (proposal.doi, proposal.formula_id, proposal.revision, body["input_hash"]),
                ).fetchone()
                if prior is not None:
                    existing = self._decode(prior)
                    if existing != body:
                        raise FormulaCalculatorError("conflicting formula proof for same inputs")
                    return existing
                db.execute(
                    "INSERT INTO formula_numeric_proofs VALUES (?,?,?,?,?,?)",
                    (
                        proposal.doi,
                        proposal.formula_id,
                        proposal.revision,
                        body["input_hash"],
                        json.dumps(body, sort_keys=True),
                        digest,
                    ),
                )
            return body
        except PaperMethodologyError as exc:
            raise FormulaCalculatorError("untrusted formula or review integrity failure") from exc
