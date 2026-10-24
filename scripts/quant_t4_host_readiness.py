"""Inspect existing T4 session host readiness. No LLM or orders are invoked.

Example:
  python scripts/quant_t4_host_readiness.py --project-root ROOT \
      --state-dir STATE --session-file STATE/p5_session_id.txt
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from application.t4_model_host_preflight import audit_t4_model_host


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only ChatGPT/MCP host readiness probe")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--session-file", type=Path, required=True)
    args = parser.parse_args()

    session = args.session_file.read_text(encoding="ascii").strip()
    if len(session) != 32 or any(x not in "0123456789abcdef" for x in session):
        parser.error("expected a 32-character lowercase session ID file")
    service = AcademicMCPCheckpointService(
        project_root=args.project_root,
        state_dir=args.state_dir,
        parent_portfolio_v2=True,
        generalization_parent_v1=True,
        p4_quality_gate_v1=True,
        p4_s7_quality_v1=True,
    )
    report = audit_t4_model_host(service, session_id=session)
    print(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2))
    return 0 if report["can_advance_genuine_generations"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
