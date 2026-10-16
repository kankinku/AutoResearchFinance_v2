"""Explicit operator CLI for bounded full-cycle academic GPT research.

Default mode is existing ChatGPT ↔ Quant MCP, with zero API usage.
Optional paid OpenAI API research requires explicit --execution-mode openai-api,
--model and OPENAI_API_KEY. No new MCP app, secrets or live trading.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from dashboard.academic_monitor import (
    AcademicMonitorReader,
    ResearchMonitorUnavailable,
    ResearchSessionNotFound,
)
from research.llm.execution_policy import (
    DEFAULT_RESEARCH_EXECUTION_MODE,
    research_execution_policy,
)
from research.llm.openai_response_transport import OpenAIResponsesResearcher
from research.llm.supervised_checkpoint_runner import ResearchRunSupervisor


def main() -> None:
    parser = argparse.ArgumentParser(description="Foreground, bounded LLM research cycles")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument(
        "--execution-mode", choices=("mcp", "openai-api"),
        default=DEFAULT_RESEARCH_EXECUTION_MODE,
        help="Default mcp: existing ChatGPT connector. Paid external API is opt-in.",
    )
    parser.add_argument("--model", help="Required ONLY with --execution-mode openai-api")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--session-id")
    mode.add_argument("--data-path")
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--max-generations-this-call", type=int, default=10)
    parser.add_argument(
        "--max-model-proposals", type=int,
        help="Required for paid API mode: hard cap on model calls for this run.",
    )
    parser.add_argument("--control-dir", type=Path)
    parser.add_argument("--heartbeat-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.execution_mode == "mcp":
        if args.model is not None:
            parser.error("--model requires explicit --execution-mode openai-api")
        # MCP's LLM is the connected ChatGPT client. A server CLI cannot
        # silently invoke that client; it must return its existing tool flow.
        # Do not open state DBs or create sessions in this information path.
        readiness: dict[str, object] = {}
        if args.session_id:
            try:
                snapshot = AcademicMonitorReader(
                    args.state_dir / "academic-gpt-checkpoints",
                ).snapshot(args.session_id)
                readiness = {
                    "status": "EXISTING_MCP_SESSION_AWAITING_CLIENT",
                    "completed_generations": snapshot["completed"],
                    "requested_generations": snapshot["requested"],
                    "checkpoint_phase": snapshot["checkpoint"]["code"],
                    "missing_s7_count": snapshot["missing_s7_count"],
                    "next_mcp_tool": (
                        "evaluate_algorithm_experiments"
                        if snapshot["missing_s7_count"] else
                        "get_algorithm_research"
                    ),
                }
            except (ResearchMonitorUnavailable, ResearchSessionNotFound):
                readiness = {"status": "RESEARCH_STATE_UNAVAILABLE"}
        print(json.dumps({
            "status": "USE_EXISTING_CHATGPT_MCP_CONNECTOR",
            **readiness,
            "model_execution_possible_without_host": False,
            "execution_mode": "mcp",
            "research_execution_policy": research_execution_policy(),
            "next_step": (
                "Use the existing session with get_algorithm_research; "
                "submit_algorithm_plan or submit_algorithm_diagnosis according "
                "to its checkpoint phase, then evaluate_algorithm_experiments "
                "and repeat. Do not start a replacement session."
                if args.session_id else
                "In the already connected Quant Autoresearch ChatGPT app, call "
                "start_algorithm_research, then submit_algorithm_plan, "
                "submit_algorithm_diagnosis, evaluate_algorithm_experiments "
                "and repeat using get_algorithm_research."
            ),
            "session_created": False,
            "external_model_called": False,
        }, ensure_ascii=False))
        return
    if args.model is None:
        parser.error("--model required with --execution-mode openai-api")
    if (type(args.max_model_proposals) is not int
            or not 1 <= args.max_model_proposals <= 1000):
        parser.error("--max-model-proposals 1..1000 required for paid openai-api mode")
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
    # Explicit opt-in paid API only; this process remains foreground.
    control_dir = args.control_dir or (args.state_dir / "academic-supervisor-control")
    result = ResearchRunSupervisor(control_dir).run(
        session_id, service=service, provider=provider,
        max_generations=args.max_generations_this_call,
        heartbeat_interval=args.heartbeat_seconds,
        max_model_proposals=args.max_model_proposals,
        audit_path=control_dir / (session_id + ".recovery.jsonl"),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
