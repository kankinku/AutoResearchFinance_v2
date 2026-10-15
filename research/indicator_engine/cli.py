"""Local-only CLI for P0 academic research catalog (no brokerage orders)."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import httpx

from core.data.parquet import ParquetDataProvider
from research.indicator_engine.algorithm_plan import AlgorithmPlan
from research.indicator_engine.benchmark_reconciliation import reconcile_development_benchmark
from research.indicator_engine.capture_integrity import verify_nasdaq_capture
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.citations import CitationFetchError, fetch_crossref
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.corporate_actions import verify_dividend_snapshot
from research.indicator_engine.corporate_asof_gate import audit_qqq_corporate_asof
from research.indicator_engine.databento_cutover_audit import compare_condition_vintages
from research.indicator_engine.databento_metadata_preflight import probe_qqq_xnas_metadata
from research.indicator_engine.formula_calculator import FormulaCalculatorError, FormulaPreviewStore
from research.indicator_engine.literature_discovery import (
    DEFAULT_LITERATURE_TOPICS,
    LiteratureDiscoveryError,
    LiteratureStore,
    discover_crossref_literature,
    sweep_crossref_literature,
)
from research.indicator_engine.multi_asset_development import (
    MultiAssetResearchError,
    compile_parallel_plan,
    evaluate_parallel_plan,
)
from research.indicator_engine.nasdaq_append_only_archive import archive_nasdaq_qqq_snapshot
from research.indicator_engine.nasdaq_archive_inventory import audit_nasdaq_qqq_archive
from research.indicator_engine.nasdaq_capture import capture_nasdaq_qqq
from research.indicator_engine.nasdaq_daily_collector import collect_nasdaq_qqq_daily
from research.indicator_engine.paper_methodology import (
    FormulaDraft,
    MethodReview,
    PaperMethodologyError,
    PaperMethodologyStore,
)
from research.indicator_engine.publication_evidence_matrix import audit_publication_coverage
from research.indicator_engine.publisher_evidence_intake import audit_publisher_evidence
from research.indicator_engine.sealed_oos_precommit import (
    record_development_precommit,
    verify_development_precommit,
)
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices
from research.indicator_engine.verified_capture_vintages import (
    CapturedPriceVintage,
    compare_verified_nasdaq_vintages,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        required=False,
        help="Development SQLite path required for catalog commands; not for audit-benchmark",
    )
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("seed", help="Idempotent reviewed-paper and research-signal seed")
    subs.add_parser("status", help="Inspect research provenance and verification states")
    subs.add_parser(
        "probe-databento-qqq-metadata",
        help="Read-only historical entitlement, schema range, estimate and revision metadata",
    )
    condition_compare = subs.add_parser(
        "compare-databento-condition-vintages",
        help="Offline reverify two retained dataset-condition snapshots, never PIT",
    )
    condition_compare.add_argument("--earlier", type=Path, required=True)
    condition_compare.add_argument("--later", type=Path, required=True)
    verify = subs.add_parser("verify", help="Verify one whitelisted causal calculator")
    verify.add_argument("signal_id")
    compose = subs.add_parser("compose", help="Generate non-executable, bounded hypotheses")
    compose.add_argument("signal_ids", nargs="+")
    compose.add_argument("--limit", type=int, default=100)
    citations = subs.add_parser(
        "refresh-citations",
        help="Explicit read-only Crossref DOI lookup; append date-stamped verified counts",
    )
    citations.add_argument("--limit", type=int, default=6)
    citations.add_argument("--doi", default=None, help="Exact DOI registered in paper database")
    literature = subs.add_parser(
        "discover-academic-papers",
        help="Find bounded Crossref DOI metadata and queue review candidates (NON-EXECUTABLE)",
    )
    literature.add_argument("--query", required=True)
    literature.add_argument("--limit", type=int, default=10)
    literature_sweep = subs.add_parser(
        "sweep-academic-papers", help="Discover multiple fixed academic topics (review queue only)"
    )
    literature_sweep.add_argument("--limit-per-topic", type=int, default=8)
    literature_sweep.add_argument(
        "--topic", action="append", default=None,
        help="Run only explicitly named topics; repeat for a bounded subset",
    )
    literature_list = subs.add_parser("list-discovered-papers", help="Read DOI review queue")
    literature_list.add_argument("--limit", type=int, default=30)
    literature_stage = subs.add_parser(
        "stage-discovered-paper", help="Manually accept a reviewed DOI as a paper only"
    )
    literature_stage.add_argument("--doi", required=True)
    literature_stage.add_argument("--source-scope", required=True)
    literature_stage.add_argument("--replication-note", required=True)
    review_queue = subs.add_parser(
        "list-paper-review-queue",
        help="Show DOI method/rights review queue (nothing is verified or executable)",
    )
    review_queue.add_argument("--limit", type=int, default=30)
    method_review = subs.add_parser(
        "record-paper-method-review",
        help="Record manually reviewed method/rights note from bounded JSON; not approval",
    )
    method_review.add_argument("--json-file", type=Path, required=True)
    formula_draft = subs.add_parser(
        "propose-paper-formula",
        help="Store a typed non-executable formula AST from bounded JSON",
    )
    formula_draft.add_argument("--json-file", type=Path, required=True)
    formula_list = subs.add_parser(
        "list-paper-formulas", help="Inspect non-executable formula versions"
    )
    formula_list.add_argument("--doi", required=True)
    formula_preview = subs.add_parser(
        "preview-paper-calculation",
        help="Numerically cross-check a versioned research formula; NEVER enable execution",
    )
    formula_preview.add_argument("--doi", required=True)
    formula_preview.add_argument("--formula-id", required=True)
    formula_preview.add_argument("--revision", type=int, required=True)
    formula_preview.add_argument("--input-json-file", type=Path, required=True)
    formula_proofs = subs.add_parser(
        "list-paper-calculation-proofs", help="Inspect offline non-executable numeric evidence"
    )
    formula_proofs.add_argument("--doi", required=True)
    for command, description in (
        ("freeze-development-selection", "One-shot candidate precommit from DEVELOPMENT only"),
        ("verify-development-freeze", "Replay frozen candidate hash without opening OOS"),
    ):
        freezing = subs.add_parser(command, help=description)
        freezing.add_argument("--market-parquet", type=Path, required=True)
        freezing.add_argument("--plan-json-file", type=Path, required=True)
        freezing.add_argument("--study-id", required=True)
        freezing.add_argument("--receipt", type=Path, required=True)
    parallel = subs.add_parser(
        "preview-parallel-algorithm",
        help="Offline bounded multi-ETF typed StrategyIR comparison; no portfolio orders",
    )
    parallel.add_argument("--market-parquet", type=Path, required=True)
    parallel.add_argument("--plan-json-file", type=Path, required=True)
    audit = subs.add_parser(
        "audit-benchmark",
        help="Offline, two-source price-only reconciliation; never PIT certification",
    )
    audit.add_argument("primary_path", type=Path)
    audit.add_argument("reference_path", type=Path)
    audit.add_argument("--initial-cash", type=float, default=10_000.0)
    capture = subs.add_parser(
        "capture-nasdaq-qqq", help="Manual latest-revision public Nasdaq quote capture (NON-PIT)"
    )
    capture.add_argument("--from-date", type=date.fromisoformat, required=True)
    capture.add_argument("--to-date", type=date.fromisoformat, required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--raw", type=Path, required=True)
    capture.add_argument("--manifest", type=Path, required=True)
    action_gate = subs.add_parser(
        "audit-qqq-corporate-asof",
        help="Retrospective QQQ dividends/splits/as-of input gate; no PIT promotion",
    )
    action_gate.add_argument("--raw-parquet", type=Path, required=True)
    action_gate.add_argument("--adjusted-parquet", type=Path)
    action_gate.add_argument("--dividend-raw", type=Path, required=True)
    action_gate.add_argument("--dividend-manifest", type=Path, required=True)
    action_gate.add_argument("--decision-at", type=datetime.fromisoformat, required=True)
    archival = subs.add_parser(
        "archive-nasdaq-qqq",
        help="Capture and replay a NEW private Nasdaq QQQ snapshot (NON-PIT, append-only)",
    )
    archival.add_argument("--from-date", type=date.fromisoformat, required=True)
    archival.add_argument("--to-date", type=date.fromisoformat, required=True)
    archival.add_argument("--archive-root", type=Path, default=Path("state/vintages"))
    daily = subs.add_parser(
        "collect-nasdaq-qqq-daily",
        help="Audit, then collect QQQ at most once per UTC date (NON-PIT, opt-in)",
    )
    daily.add_argument("--from-date", type=date.fromisoformat, required=True)
    daily.add_argument("--to-date", type=date.fromisoformat, required=True)
    daily.add_argument("--archive-root", type=Path, default=Path("state/vintages"))
    publication = subs.add_parser(
        "audit-qqq-publication-coverage",
        help="Replay all captures and publisher evidence; historical PIT always unapproved",
    )
    publication.add_argument("--from-date", type=date.fromisoformat, required=True)
    publication.add_argument("--to-date", type=date.fromisoformat, required=True)
    publication.add_argument("--archive-root", type=Path, default=Path("state/vintages"))
    publication.add_argument("--decision-at", type=datetime.fromisoformat)
    inventory = subs.add_parser(
        "audit-nasdaq-archive",
        help="Replay every QQQ capture and report multi-date cadence/revisions (NON-PIT)",
    )
    inventory.add_argument("--from-date", type=date.fromisoformat, required=True)
    inventory.add_argument("--to-date", type=date.fromisoformat, required=True)
    inventory.add_argument("--archive-root", type=Path, default=Path("state/vintages"))
    integrity = subs.add_parser(
        "verify-nasdaq-capture",
        help="Offline SHA and parquet replay for a saved Nasdaq snapshot (NON-PIT)",
    )
    integrity.add_argument("--output", type=Path, required=True)
    integrity.add_argument("--raw", type=Path, required=True)
    integrity.add_argument("--manifest", type=Path, required=True)
    publisher = subs.add_parser(
        "audit-publisher-evidence",
        help="Verify detached publisher claim against pinned key; NEVER historical PIT approval",
    )
    publisher.add_argument("--output", type=Path, required=True)
    publisher.add_argument("--raw", type=Path, required=True)
    publisher.add_argument("--manifest", type=Path, required=True)
    publisher.add_argument("--publisher-proof", type=Path)
    publisher.add_argument("--publisher-signature", type=Path)
    publisher.add_argument("--decision-at", type=datetime.fromisoformat)
    pair = subs.add_parser(
        "compare-nasdaq-vintages",
        help="Offline replay of two archived Nasdaq source vintages, revisions only (NON-PIT)",
    )
    for label in ("earlier", "later"):
        pair.add_argument(f"--{label}-output", type=Path, required=True)
        pair.add_argument(f"--{label}-raw", type=Path, required=True)
        pair.add_argument(f"--{label}-manifest", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "compare-databento-condition-vintages":
        try:
            compared = compare_condition_vintages(args.earlier, args.later)
        except (OSError, ValueError, ResearchCatalogError):
            print(json.dumps({
                "status": "CONDITION_VINTAGE_UNVERIFIABLE",
                "historical_pit_verified": False,
                "broker_executable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(compared.record(), sort_keys=True))
        return 0

    if args.command == "probe-databento-qqq-metadata":
        inspected = probe_qqq_xnas_metadata(api_key=os.environ.get("DATABENTO_API_KEY"))
        print(json.dumps(inspected.record(), sort_keys=True, allow_nan=False))
        return 0 if inspected.status != "METADATA_UNAVAILABLE" else 2

    if args.command == "audit-publisher-evidence":
        try:
            evidence_result = audit_publisher_evidence(
                CapturedPriceVintage(args.output, args.raw, args.manifest),
                args.publisher_proof,
                args.publisher_signature,
                decision_at=args.decision_at,
            )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "PUBLISHER_EVIDENCE_INTAKE_FAILED", "type": type(exc).__name__,
                "publisher_available_at_proven": False,
                "independent_historical_pit_verified": False,
                "broker_executable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(evidence_result.record(), sort_keys=True))
        return 0

    if args.command == "audit-qqq-publication-coverage":
        try:
            publisher_matrix = audit_publication_coverage(
                args.archive_root, args.from_date, args.to_date,
                decision_at=args.decision_at,
            )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "PUBLICATION_COVERAGE_INTEGRITY_FAILED",
                "type": type(exc).__name__,
                "point_in_time_verified": False,
                "broker_executable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(publisher_matrix, sort_keys=True))
        return 0

    if args.command == "audit-qqq-corporate-asof":
        try:
            for path in (args.raw_parquet, args.adjusted_parquet,
                         args.dividend_raw, args.dividend_manifest):
                if path is not None and (path.is_symlink() or not path.is_file()):
                    raise ResearchCatalogError("invalid corporate action source path")
            market_raw = ParquetDataProvider.read(args.raw_parquet)
            market_adj = (
                ParquetDataProvider.read(args.adjusted_parquet)
                if args.adjusted_parquet else None
            )
            dividend_events = verify_dividend_snapshot(
                args.dividend_raw, args.dividend_manifest,
            )
            action_report = audit_qqq_corporate_asof(
                market_raw, dividend_events,
                decision_at=args.decision_at, adjusted=market_adj,
            )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "CORPORATE_ASOF_AUDIT_REJECTED",
                "type": type(exc).__name__,
                "historical_point_in_time_verified": False,
                "broker_executable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(action_report, sort_keys=True, allow_nan=False))
        return 0

    if args.command == "audit-nasdaq-archive":
        try:
            audited_inventory = audit_nasdaq_qqq_archive(
                args.archive_root, args.from_date, args.to_date
            )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "ARCHIVE_INTEGRITY_FAILED",
                "type": type(exc).__name__,
                "point_in_time_verified": False,
                "broker_executable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(audited_inventory.record(), sort_keys=True))
        return 0

    if args.command == "collect-nasdaq-qqq-daily":
        try:
            daily_report = collect_nasdaq_qqq_daily(
                args.archive_root, args.from_date, args.to_date,
            )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "DAILY_CAPTURE_FAILED", "type": type(exc).__name__,
                "point_in_time_verified": False, "broker_executable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(daily_report, sort_keys=True))
        return 0

    if args.command == "archive-nasdaq-qqq":
        try:
            captured_archive = archive_nasdaq_qqq_snapshot(
                args.archive_root, args.from_date, args.to_date,
            )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "ARCHIVE_CAPTURE_FAILED", "type": type(exc).__name__,
                "point_in_time_verified": False,
                "broker_executable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(captured_archive.record(), sort_keys=True))
        return 0

    if args.command == "compare-nasdaq-vintages":
        try:
            pair_result = compare_verified_nasdaq_vintages(
                CapturedPriceVintage(
                    args.earlier_output, args.earlier_raw, args.earlier_manifest
                ),
                CapturedPriceVintage(
                    args.later_output, args.later_raw, args.later_manifest
                ),
            )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "CAPTURE_VINTAGE_PAIR_INVALID", "type": type(exc).__name__,
                "point_in_time_price_verified": False,
                "independent_historical_publication_verified": False,
                "broker_executable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(pair_result.record(), sort_keys=True, allow_nan=False))
        return 0

    if args.command == "verify-nasdaq-capture":
        try:
            checked = verify_nasdaq_capture(args.output, args.raw, args.manifest)
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "CAPTURE_INTEGRITY_FAILED", "type": type(exc).__name__,
                "point_in_time_verified": False,
                "independent_benchmark_verified": False,
                "candidate_promotable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(asdict(checked), sort_keys=True))
        return 0

    if args.command == "capture-nasdaq-qqq":
        try:
            report = capture_nasdaq_qqq(
                args.from_date, args.to_date, args.output, args.raw, args.manifest
            )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({"status": "CAPTURE_FAILED", "type": type(exc).__name__,
                              "point_in_time_verified": False,
                              "independent_benchmark_verified": False}))
            return 2
        print(json.dumps(asdict(report), sort_keys=True))
        return 0

    if args.command == "audit-benchmark":
        try:
            primary = ParquetDataProvider.read(args.primary_path)
            reference = ParquetDataProvider.read(args.reference_path)
            audit_result = reconcile_development_benchmark(
                primary, reference, initial_cash=args.initial_cash
            )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "RECONCILIATION_ERROR",
                "type": type(exc).__name__,
                "independent_benchmark_verified": False,
                "point_in_time_verified": False,
                "candidate_promotable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(asdict(audit_result), sort_keys=True, allow_nan=False))
        return 0 if audit_result.status == "CROSS_SOURCE_DEVELOPMENT_ONLY" else 2

    if args.database is None:
        parser.error("--database is required for catalog commands")
    db = ResearchCatalog(args.database)
    if args.command in {"freeze-development-selection", "verify-development-freeze"}:
        try:
            for source in (args.market_parquet, args.plan_json_file):
                if (source.is_symlink() or not source.is_file()
                        or source.stat().st_size > 64 * 1024 * 1024):
                    raise ResearchCatalogError("invalid development precommit source")
            if args.plan_json_file.stat().st_size > 32768:
                raise ResearchCatalogError("oversized frozen plan")
            frozen_market = ParquetDataProvider.read(args.market_parquet)
            frozen_plan = AlgorithmPlan.model_validate_json(
                args.plan_json_file.read_text(encoding="utf-8")
            )
            if args.command == "freeze-development-selection":
                freeze_result = record_development_precommit(
                    db, frozen_plan, frozen_market, study_id=args.study_id,
                    evidence_path=args.receipt,
                )
            else:
                freeze_result = verify_development_precommit(
                    db, frozen_plan, frozen_market, study_id=args.study_id,
                    evidence_path=args.receipt,
                )
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "DEVELOPMENT_FREEZE_REJECTED",
                "type": type(exc).__name__,
                "oos_access_performed": False,
                "sealed_oos_approved": False,
                "broker_executable": False,
            }, sort_keys=True))
            return 2
        print(json.dumps(freeze_result, sort_keys=True, allow_nan=False))
        return 0

    if args.command == "preview-parallel-algorithm":
        try:
            if (args.market_parquet.is_symlink()
                    or args.market_parquet.stat().st_size > 64 * 1024 * 1024
                    or args.plan_json_file.is_symlink()
                    or args.plan_json_file.stat().st_size > 32768):
                raise MultiAssetResearchError("untrusted or oversized research file")
            market = ParquetDataProvider.read(args.market_parquet)
            model = AlgorithmPlan.model_validate_json(
                args.plan_json_file.read_text(encoding="utf-8")
            )
            compiled = compile_parallel_plan(db, model, market)
            parallel_result = evaluate_parallel_plan(db, compiled, market)
            print(json.dumps({
                "status": parallel_result.status, "result": asdict(parallel_result),
                "portfolio_pnl_approved": False,
                "independent_oos_approved": False,
                "broker_executable": False,
                "orders_enabled": False,
            }, sort_keys=True, allow_nan=False))
            return 0
        except (OSError, ValueError, ResearchCatalogError) as exc:
            print(json.dumps({
                "status": "PARALLEL_RESEARCH_REJECTED", "type": type(exc).__name__,
                "portfolio_pnl_approved": False,
                "broker_executable": False, "orders_enabled": False,
            }, sort_keys=True))
            return 2
    if args.command in {"preview-paper-calculation", "list-paper-calculation-proofs"}:
        try:
            methods = PaperMethodologyStore(args.database)
            previews = FormulaPreviewStore(methods)
            calculation_output: object
            if args.command == "list-paper-calculation-proofs":
                calculation_output = previews.list_reports(args.doi)
            else:
                source = args.input_json_file
                if source.is_symlink() or source.stat().st_size > 256 * 1024:
                    raise FormulaCalculatorError("input market JSON file is symlinked or oversized")
                market_payload = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(market_payload, dict):
                    raise FormulaCalculatorError("input OHLCV must be a JSON object")
                calculation_output = previews.evaluate(
                    args.doi, args.formula_id, args.revision, market_payload,
                )
            print(json.dumps({
                "result": calculation_output, "status": "RESEARCH_NUMERIC_CROSSCHECK_ONLY",
                "calculator_approved": False, "independent_oos_approved": False,
                "orders_enabled": False,
            }, sort_keys=True))
            return 0
        except (OSError, ValueError) as exc:
            print(json.dumps({
                "status": "FORMULA_PREVIEW_REJECTED", "reason": type(exc).__name__,
                "calculator_approved": False, "independent_oos_approved": False,
                "orders_enabled": False,
            }, sort_keys=True))
            return 2
    if args.command in {
        "list-paper-review-queue", "record-paper-method-review",
        "propose-paper-formula", "list-paper-formulas",
    }:
        try:
            methods = PaperMethodologyStore(args.database)
            review_output: object
            if args.command == "list-paper-review-queue":
                review_output = methods.review_queue(limit=args.limit)
            elif args.command == "list-paper-formulas":
                review_output = methods.formulas(args.doi)
            else:
                payload_path = args.json_file
                if payload_path.is_symlink() or payload_path.stat().st_size > 16384:
                    raise PaperMethodologyError("review input is symlinked or oversized")
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise PaperMethodologyError("review input must be a JSON object")
                if args.command == "record-paper-method-review":
                    review_output = methods.record_review(MethodReview.model_validate(payload))
                else:
                    review_output = methods.propose_formula(FormulaDraft.model_validate(payload))
            print(json.dumps({
                "result": review_output, "status": "RESEARCH_NOT_EXECUTABLE",
                "calculator_approved": False, "license_independently_verified": False,
                "orders_enabled": False,
            }, sort_keys=True))
            return 0
        except (OSError, ValueError) as exc:
            print(json.dumps({
                "status": "PAPER_METHOD_INTAKE_REJECTED", "reason": type(exc).__name__,
                "calculator_approved": False, "orders_enabled": False,
            }, sort_keys=True))
            return 2
    if args.command in {
        "discover-academic-papers", "list-discovered-papers", "stage-discovered-paper",
        "sweep-academic-papers",
    }:
        literature_store = LiteratureStore(args.database)
        try:
            if args.command == "list-discovered-papers":
                found = literature_store.list_candidates(limit=args.limit)
                print(json.dumps({
                    "candidates": [item.record() for item in found],
                    "count": len(found), "status": "REVIEW_REQUIRED",
                    "orders_enabled": False,
                }, sort_keys=True))
                return 0
            if args.command == "stage-discovered-paper":
                staged = literature_store.stage_paper(
                    args.doi, catalog=db, source_scope=args.source_scope,
                    replication_note=args.replication_note,
                )
                print(json.dumps({
                    "paper": staged.model_dump(mode="json"),
                    "status": "PAPER_ONLY_NO_CALCULATOR_APPROVAL",
                    "orders_enabled": False,
                }, sort_keys=True))
                return 0
            headers = {
                "User-Agent": "Quant-Autoresearch-Literature/0.1 (metadata-only)",
            }
            with httpx.Client(
                timeout=httpx.Timeout(10.0, connect=3.0),
                follow_redirects=False, trust_env=False, headers=headers,
            ) as client:
                if args.command == "sweep-academic-papers":
                    summary = sweep_crossref_literature(
                        literature_store, client=client,
                        topics=tuple(args.topic) if args.topic else DEFAULT_LITERATURE_TOPICS,
                        limit_per_topic=args.limit_per_topic,
                    )
                    print(json.dumps(summary, sort_keys=True))
                    return 0 if summary["status"] == "SWEEP_COMPLETE" else 2
                discovered = discover_crossref_literature(
                    args.query, limit=args.limit, client=client,
                )
            inserted = literature_store.capture_batch(discovered)
            print(json.dumps({
                **discovered.record(), "new_observations": inserted,
            }, sort_keys=True))
            return 0
        except (LiteratureDiscoveryError, ResearchCatalogError, OSError, ValueError) as exc:
            print(json.dumps({
                "status": "LITERATURE_RESEARCH_FAILED", "type": type(exc).__name__,
                "orders_enabled": False, "calculator_approved": False,
            }, sort_keys=True))
            return 2
    if args.command == "seed":
        seed_approved_references(db)
    elif args.command == "verify":
        indicator = db.get_indicator(args.signal_id)
        result = verify_signal_on_synthetic_prices(indicator)
        if not result.passed:
            print(result.model_dump_json(indent=2))
            return 2
        db.verify_and_register(indicator.signal_id, result)
    elif args.command == "refresh-citations":
        if not 1 <= args.limit <= 50:
            parser.error("--limit must be in [1, 50]")
        papers = (db.get_paper(args.doi),) if args.doi else db.list_papers()[: args.limit]
        contact = os.environ.get("CROSSREF_CONTACT_EMAIL", "")
        headers = {"User-Agent": "Quant-Autoresearch-IndicatorResearch/0.1 (metadata-only)"}
        if contact and "@" in contact and "\r" not in contact and "\n" not in contact:
            headers["User-Agent"] += f" (mailto:{contact})"
        accepted = 0
        unchanged = 0
        failed: list[dict[str, str]] = []
        with httpx.Client(
            timeout=httpx.Timeout(8.0, connect=3.0),
            follow_redirects=False,
            trust_env=False,
            headers=headers,
        ) as client:
            for paper in papers:
                try:
                    evidence = fetch_crossref(paper, client=client)
                    if db.capture_citation(evidence):
                        accepted += 1
                    else:
                        unchanged += 1
                except (CitationFetchError, ResearchCatalogError) as exc:
                    failed.append({"doi": paper.doi, "reason": type(exc).__name__})
        print(
            json.dumps(
                {
                    "provider": "Crossref",
                    "attempted": len(papers),
                    "inserted": accepted,
                    "unchanged": unchanged,
                    "failures": failed,
                    "research_only": True,
                    "orders_enabled": False,
                },
                sort_keys=True,
            )
        )
        return 2 if failed else 0
    elif args.command == "compose":
        hypotheses = compose_hypotheses(
            db, signal_ids=tuple(args.signal_ids), max_results=args.limit
        )
        print(json.dumps([x.model_dump(mode="json") for x in hypotheses], indent=2))
        return 0
    summary = {
        "paper_count": len(db.list_papers()),
        "proposed_signals": sum(x.status == "PROPOSED" for x in db.list_indicators()),
        "verified_math_signals": len(db.list_indicators(eligible_only=True)),
        "quarantined_signals": sum(x.status == "QUARANTINED" for x in db.list_indicators()),
        "orders_enabled": False,
        "sealed_oos": "NOT_MEASURED",
        "economic_significance": "NOT_MEASURED",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
