"""Local evidence census: existing immutable Quant journals; no model or writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from application.research_handoff_builder import build_research_handoff, compact_handoff_view
from application.research_s7_readonly import read_research_bundle_readonly
from research.llm.evidence_memory_retrieval import (
    audit_evidence_grounding,
    search_evidence_memory,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-checkpoint-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--char-budget", type=int, default=20_000)
    args = parser.parse_args()
    bundle = read_research_bundle_readonly(args.academic_checkpoint_dir, args.session_id)
    handoff = build_research_handoff(
        bundle["snapshot"],
        bundle["receipts"],
        max_chars=args.char_budget,
    )
    query = search_evidence_memory(handoff, only_negative=True, limit=8)
    qa = audit_evidence_grounding(handoff, bundle["snapshot"], bundle["receipts"])
    compact_chars = None
    if handoff["delivery_status"] == "COMPACT_CANDIDATE_NOT_MODEL_VALIDATED":
        view = compact_handoff_view(handoff, bundle["snapshot"], bundle["receipts"])
        compact_chars = len(json.dumps(view, sort_keys=True, ensure_ascii=False))
    report = {
        "schema": "quant-readonly-evidence-memory-audit-m1-v1",
        "completed_generations": handoff["completed_generations"],
        "phase": handoff["checkpoint_phase"],
        "s7_complete_receipts": len(bundle["receipts"]),
        "verified_chain_head_prefix": (handoff["source_evidence_head_hash"] or "")[:16],
        "handoff_digest_prefix": handoff["handoff_hash"][:16],
        "brief_chars": handoff["brief_serialized_chars"],
        "requested_char_budget": args.char_budget,
        "delivery_status": handoff["delivery_status"],
        "compact_view_chars": compact_chars,
        "historical_negative_trial_count": query["total_matches"],
        "negative_query_more_evidence_requires_lookup": query["more_evidence_requires_lookup"],
        "grounding_field_assertions": qa["questions"],
        "grounding_field_failures": qa["failed"],
        "model_calls": 0,
        "real_model_host_auto_dispatch": "BLOCKED_MODEL_HOST_DISPATCH",
        "measured_provider_tokens": "NOT_RUN",
        "economic_research_improvement": "NOT_MEASURED",
        "production_service_updated": False,
        "orders_enabled": False,
        "independent_oos_approved": False,
    }
    print(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2))
    return 0 if qa["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
