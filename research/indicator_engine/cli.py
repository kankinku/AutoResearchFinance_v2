"""Local-only CLI for P0 academic research catalog (no brokerage orders)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.citations import CitationFetchError, fetch_crossref
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="Persistent development SQLite path; never an order database",
    )
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("seed", help="Idempotent reviewed-paper and research-signal seed")
    subs.add_parser("status", help="Inspect research provenance and verification states")
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
    args = parser.parse_args()

    db = ResearchCatalog(args.database)
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
