"""Offline, *development-only* S7 child full-period risk replay sidecar.

All inputs are frozen copies except the user-supplied read-only Parquet. Never
write original cycles/gateway, advance generations, or authorize an order.
Replaying S7 is not proof of alpha, causality, PIT accuracy or external OOS.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from core.data.parquet import ParquetDataProvider
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from evaluation.academic_campaign_audit import _read_generations, _read_reports, _validate_snapshot
from evaluation.metrics import calculate_metrics
from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.controlled_experiments import compare_controlled_experiments
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.inherited_experiments import compare_inherited_experiments
from research.indicator_engine.strategy_adapter import evaluate_compiled_development
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent
from strategy_ir.schema import StrategyIR


def fill_exposure(trades: Sequence[Any], bars: Sequence[Any]) -> tuple[int, float]:
    """Match the canonical QQQ long-only lineage exposure accounting."""
    if not bars:
        raise ValueError("empty market bars")
    allowed = {bar.timestamp.isoformat() for bar in bars}
    changes: dict[str, bool] = {}
    held = False
    completed = 0
    for trade in trades:
        if trade.timestamp not in allowed:
            raise ValueError("fill outside market timestamps")
        if trade.timestamp in changes:
            raise ValueError("multiple fills on one bar are unsupported")
        if trade.side == "buy" and not held:
            held = True
        elif trade.side == "sell" and held:
            held = False
            completed += 1
        else:
            raise ValueError("unpaired or unsupported fill")
        changes[trade.timestamp] = held
    held = False
    invested = 0
    for bar in bars:
        held = changes.get(bar.timestamp.isoformat(), held)
        invested += int(held)
    return completed, invested / len(bars)


def validate_child_replay(result: Any, reported: dict[str, Any]) -> None:
    """Do not trust a claimed child hash, fill count, equity or cost."""
    delta = reported.get("execution_delta") or {}
    if (
        result.strategy_hash != reported.get("child_strategy_hash")
        or result.trades_count != reported.get("child_fill_count")
        or abs(result.final_equity - float(reported.get("child_final_equity", -1))) > 1e-6
        or abs(result.total_paid_costs - float(delta.get("child_costs", -1))) > 1e-6
    ):
        raise ValueError("S7 child replay hash, equity, fills or cost mismatch")


def _build_diagnostic(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "context_hash": evidence["diagnostic_context_hash"],
        "audit_hash": evidence["audit_hash"],
        "strategy_hash": evidence["strategy_hash"],
        "dataset_hash": evidence["dataset_hash"],
        "summary": evidence["analysis_summary"],
        "hypotheses": [
            {
                "hypothesis_id": h["hypothesis_id"],
                "observed_ids": h["observed_ids"],
                "mechanism": h["mechanism"],
                "alternative": h["alternative"],
                "expected_metric": h["expected_metric"],
                "predicted_direction": h["predicted_direction"],
                "test_design": h["test_design"],
                "control": h["control"],
                "next_intent": h["proposed_intent"],
            }
            for h in evidence["experiments"]
        ],
    }


def _existing_risk_reviews(
    gateway: sqlite3.Connection, session: str
) -> dict[tuple[int, str], dict[str, Any]]:
    rows: dict[tuple[int, str], dict[str, Any]] = {}
    for (raw,) in gateway.execute(
        "SELECT selection_json FROM parent_selections WHERE session_id=?", (session,)
    ):
        body = json.loads(raw)
        if body.get("selection_hash") != content_hash(
            {k: v for k, v in body.items() if k != "selection_hash"}
        ):
            raise ValueError("parent selection proof checksum mismatch")
        for x in body.get("candidate_review", {}).get("comparisons", []):
            if x.get("replay_verified") is not True:
                continue
            key = (x["source_generation"], x["child_strategy_hash"])
            if key in rows and any(
                rows[key].get(k) != x.get(k)
                for k in ("total_return", "max_drawdown", "closed_trades", "market_exposure")
            ):
                raise ValueError("conflicting selected child risk histories")
            rows[key] = x
    return rows


def replay_missing_children(
    *, snapshot: Path, catalog_path: Path, market_path: Path, session_id: str
) -> dict[str, Any]:
    """Fill ONLY missing whole-period metrics; existing replayed reviews stay intact."""
    _validate_snapshot(snapshot)
    if catalog_path.resolve() == market_path.resolve():
        raise ValueError("invalid research inputs")
    market = ParquetDataProvider.read(market_path)
    # This catalog must be an offline COPIED catalog. Never initialize a
    # ResearchCatalog against the operational database in this workflow.
    if not catalog_path.resolve().is_relative_to(snapshot.resolve()):
        raise ValueError("catalog must be a copied file inside the frozen snapshot")
    catalog = ResearchCatalog(catalog_path)
    with (
        sqlite3.connect(
            (snapshot / "cycles.sqlite").resolve().as_uri() + "?mode=ro", uri=True
        ) as cycles,
        sqlite3.connect(
            (snapshot / "gateway.sqlite").resolve().as_uri() + "?mode=ro", uri=True
        ) as gateway,
    ):
        evidences = _read_generations(cycles, session_id)
        reports = _read_reports(gateway, session_id)
        stored = cycles.execute(
            "SELECT completed,dataset_hash FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if stored is None or set(evidences) != set(reports) or len(evidences) != stored[0]:
            raise ValueError("incomplete research freeze")
        if stored[1] != market.dataset_hash:
            raise ValueError("live market data hash does not match frozen evidence")
        reviewed = _existing_risk_reviews(gateway, session_id)
        new_metrics: list[dict[str, Any]] = []
        prior_rows: list[dict[str, Any]] = []
        for number in sorted(evidences):
            evidence = evidences[number]
            original = reports[number]
            s7_rows = original["report"]["experiments"]
            if len(s7_rows) != 1:
                raise ValueError("only single-hypothesis bounded S7 studies supported")
            row = s7_rows[0]
            hash_key = (number, row["child_strategy_hash"])
            original_hash = cycles.execute(
                "SELECT evidence_hash FROM generations WHERE session_id=? AND generation=?",
                (session_id, number),
            ).fetchone()[0]
            s7_hash = gateway.execute(
                "SELECT report_hash FROM experiment_reports WHERE session_id=? AND generation=?",
                (session_id, number),
            ).fetchone()[0]
            if content_hash(original) != s7_hash:
                raise ValueError("S7 report record checksum mismatch")
            if original["original_generation_evidence_hash"] != original_hash:
                raise ValueError("S7 origin hash mismatch")
            selection = reviewed.get(hash_key)
            if selection is not None and all(
                selection.get(x) is not None
                for x in ("total_return", "max_drawdown", "market_exposure", "closed_trades")
            ):
                if abs(selection["total_return"] - (row["child_final_equity"] / 10000 - 1)) > 1e-6:
                    raise ValueError("selected replay return conflicts with S7 equity")
                prior_rows.append(
                    {
                        "generation": number,
                        "child_strategy_hash": row["child_strategy_hash"],
                        "origin_evidence_hash": original_hash,
                        "s7_report_hash": s7_hash,
                        "total_return": selection["total_return"],
                        "max_drawdown": selection["max_drawdown"],
                        "market_exposure": selection["market_exposure"],
                        "closed_trades": selection["closed_trades"],
                        "source": "EXISTING_VERIFIED_PARENT_SELECTION",
                    }
                )
                continue
            if evidence.get("dataset_hash") != market.dataset_hash:
                raise ValueError("evidence dataset mismatch")

            if evidence.get("inherited_strategy_ir") is not None:
                base = compile_algorithm_plan(
                    catalog, AlgorithmPlan.model_validate(evidence["base_algorithm_plan"]), market
                )
                inherited = StrategyIR.model_validate(evidence["inherited_strategy_ir"])
                digest = content_hash(inherited.model_dump(mode="json", by_alias=True))
                if digest != evidence["strategy_hash"]:
                    raise ValueError("inherited strategy evidence hash mismatch")
                compiled = replace(base.compiled, strategy=inherited, strategy_hash=digest)
                inherited_audit = audit_inherited_decisions(compiled, market)
                if (
                    inherited_audit.trace_hash != evidence["audit_hash"]
                    or abs(
                        inherited_audit.evaluation.final_equity - evidence["measured_final_equity"]
                    )
                    > 1e-6
                ):
                    raise ValueError("inherited parent replay mismatch")
                recomputed = compare_inherited_experiments(
                    compiled,
                    market,
                    _build_diagnostic(evidence),
                    parent_proof_hash=evidence["inherited_parent"]["parent_selection_hash"],
                )
            else:
                plan = AlgorithmPlan.model_validate(evidence["algorithm_plan"])
                parent_plan = compile_algorithm_plan(catalog, plan, market)
                if (
                    parent_plan.compiled.strategy_hash != evidence["strategy_hash"]
                    or parent_plan.plan_hash != evidence["plan_hash"]
                ):
                    raise ValueError("algorithm source plan hash mismatch")
                compiled = parent_plan.compiled
                recomputed = compare_controlled_experiments(
                    catalog, parent_plan, market, _build_diagnostic(evidence)
                )
            if json.loads(json.dumps(asdict(recomputed))) != original["report"]:
                raise ValueError(f"S7 canonical replay mismatch at generation {number}")
            h = evidence["experiments"][0]
            ir = apply_intent(
                compiled.strategy,
                ResearchIntent.model_validate(h["proposed_intent"]),
                research_feature_specs(),
            )
            digest = content_hash(ir.model_dump(mode="json", by_alias=True))
            if digest != row["child_strategy_hash"]:
                raise ValueError("child StrategyIR hash mismatch")
            actual = evaluate_compiled_development(
                replace(compiled, strategy=ir, strategy_hash=digest), market
            )
            validate_child_replay(actual, row)
            metrics = calculate_metrics(actual.equity_curve, (), periods_per_year=252)
            completed, exposure = fill_exposure(actual.trades, market.bars)
            body = {
                "generation": number,
                "child_strategy_hash": digest,
                "origin_evidence_hash": original_hash,
                "s7_report_hash": s7_hash,
                "total_return": metrics.total_return,
                "max_drawdown": metrics.max_drawdown,
                "market_exposure": exposure,
                "closed_trades": completed,
                "equity_curve_hash": actual.equity_hash,
                "total_paid_costs": actual.total_paid_costs,
                "source": "CANONICAL_S7_REPLAY_FROM_FROZEN_DEVELOPMENT",
            }
            new_metrics.append({**body, "replay_proof_hash": content_hash(body)})
            print(
                f"replayed G{100 + number}: MDD {metrics.max_drawdown:.4%}, "
                f"exposure {exposure:.2%}",
                flush=True,
            )
    return {
        "schema": "academic-s7-full-period-risk-sidecar-v1",
        "session_id": session_id,
        "dataset_hash": market.dataset_hash,
        "source_scope": "REUSED_DEVELOPMENT_ONLY_NOT_OOS",
        "sealed_oos_approved": False,
        "broker_executable": False,
        "expected_generations": len(evidences),
        "preexisting_verified": len(prior_rows),
        "newly_replayed": len(new_metrics),
        "full_period_coverage": len(prior_rows) + len(new_metrics),
        "preexisting_records": prior_rows,
        "replay_records": new_metrics,
    }
