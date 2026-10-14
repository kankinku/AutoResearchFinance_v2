"""Explicit operator CLI for bounded full-cycle academic GPT research.

Requires OPENAI_API_KEY. Uses the EXISTING QuantAuto state and server URL;
no new MCP app, secret changes, OOS access, or automatic live trading.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from research.llm.checkpoint_autopilot import AcademicCheckpointAutopilot
from research.llm.openai_response_transport import OpenAIResponsesResearcher


def main() -> None:
    parser = argparse.ArgumentParser(description="Foreground, bounded LLM research cycles")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--session-id")
    mode.add_argument("--data-path")
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--max-generations-this-call", type=int, default=10)
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY missing: no model call and no session created")
    provider = OpenAIResponsesResearcher(model=args.model)
    service = AcademicMCPCheckpointService(
        project_root=args.project_root, state_dir=args.state_dir,
    )
    if args.data_path:
        session_id = service.start({
            "data_path": args.data_path,
            "generations": args.generations,
        })["session_id"]
    else:
        session_id = args.session_id
    # Print the exact resume identifier before the first external API call.
    print(json.dumps({"session_id": session_id, "status": "STARTED_OR_RESUMED"}), flush=True)
    result = AcademicCheckpointAutopilot(service, provider).run(
        session_id, max_generations=args.max_generations_this_call,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
