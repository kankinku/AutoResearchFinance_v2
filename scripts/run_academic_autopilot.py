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
from core.backtest.p2_policy import ChildRiskBudget
from research.llm.checkpoint_autopilot import AcademicCheckpointAutopilot
from research.llm.execution_policy import (
    DEFAULT_RESEARCH_EXECUTION_MODE,
    research_execution_policy,
)
from research.llm.inherited_checkpoint_autopilot import (
    ModelProposalAudit,
    P3InheritedCheckpointAutopilot,
)
from research.llm.openai_response_transport import OpenAIResponsesResearcher


def main() -> None:
    parser = argparse.ArgumentParser(description="Foreground, bounded LLM research cycles")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument(
        "--execution-mode",
        choices=("mcp", "openai-api"),
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
        "--p3-inherited", action="store_true", help="Explicit opt-in P3 inherited model research"
    )
    parser.add_argument("--confirm-paid-model-calls", action="store_true")
    parser.add_argument("--p3-model-receipts", type=Path)
    parser.add_argument("--p3-resume-receipts", action="store_true")
    parser.add_argument("--p3-max-plan-attempts", type=int, default=12)
    parser.add_argument("--p3-max-child-mdd-pct", type=float, default=30.0)
    parser.add_argument("--p3-max-relative-mdd-pp", type=float, default=15.0)
    parser.add_argument("--p3-min-closed-trades", type=int, default=30)
    args = parser.parse_args()
    if args.p3_inherited:
        if args.execution_mode != "openai-api" or not args.confirm_paid_model_calls:
            parser.error(
                "P3 model research requires explicit openai-api and paid-call confirmation"
            )
        if args.session_id is None or args.p3_model_receipts is None:
            parser.error("P3 requires a waiting session ID and new model-receipts path")
        if not 1 <= args.max_generations_this_call <= 20:
            parser.error("P3 batch size must be 1..20")
    elif (
        args.confirm_paid_model_calls
        or args.p3_model_receipts is not None
        or args.p3_resume_receipts
    ):
        parser.error("P3-only options require --p3-inherited")
    if args.execution_mode == "mcp":
        if args.model is not None:
            parser.error("--model requires explicit --execution-mode openai-api")
        # MCP's LLM is the connected ChatGPT client. A server CLI cannot
        # silently invoke that client; it must return its existing tool flow.
        # Do not open state DBs or create sessions in this information path.
        print(
            json.dumps(
                {
                    "status": "USE_EXISTING_CHATGPT_MCP_CONNECTOR",
                    "execution_mode": "mcp",
                    "research_execution_policy": research_execution_policy(),
                    "next_step": (
                        "In the already connected Quant Autoresearch ChatGPT app, call "
                        "start_algorithm_research, then submit_algorithm_plan, "
                        "submit_algorithm_diagnosis, evaluate_algorithm_experiments "
                        "and repeat using get_algorithm_research."
                    ),
                    "session_created": False,
                    "external_model_called": False,
                },
                ensure_ascii=False,
            )
        )
        return
    if args.model is None:
        parser.error("--model required with --execution-mode openai-api")
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY missing: no model call and no session created")
    provider = OpenAIResponsesResearcher(model=args.model)
    if args.p3_inherited:
        try:
            risk = ChildRiskBudget(
                max_child_mdd_pct=args.p3_max_child_mdd_pct,
                max_mdd_increase_pp=args.p3_max_relative_mdd_pp,
                min_closed_trades=args.p3_min_closed_trades,
            )
        except ValueError as exc:
            parser.error(f"invalid P3 risk budget: {exc}")
        service = AcademicMCPCheckpointService(
            project_root=args.project_root,
            state_dir=args.state_dir,
            parent_portfolio_v2=True,
            child_risk_budget=risk,
            precommit_child_risk_budget=risk,
        )
        state = service.get({"session_id": args.session_id})
        if state["checkpoint_phase"] not in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
            parser.error("P3 requires an explicitly extended waiting session")
        runner = P3InheritedCheckpointAutopilot(
            service,
            provider,
            receipts=ModelProposalAudit(
                args.p3_model_receipts,
                session_id=args.session_id,
                resume=args.p3_resume_receipts,
            ),
            max_plan_attempts=args.p3_max_plan_attempts,
        )
        print(
            json.dumps(
                {
                    "session_id": args.session_id,
                    "status": "P3_EXPLICIT_FOREGROUND_START",
                    "model_provenance": "OPERATOR_CONFIGURED_API",
                    "broker_executable": False,
                }
            ),
            flush=True,
        )
        outcome = runner.run(
            args.session_id,
            max_generations=args.max_generations_this_call,
        )
        print(json.dumps(outcome, ensure_ascii=False, sort_keys=True), flush=True)
        return
    service = AcademicMCPCheckpointService(
        project_root=args.project_root,
        state_dir=args.state_dir,
    )
    if args.data_path:
        session_id = service.start(
            {
                "data_path": args.data_path,
                "generations": args.generations,
            }
        )["session_id"]
    else:
        session_id = args.session_id
    # Print the exact resume identifier before the first external API call.
    print(json.dumps({"session_id": session_id, "status": "STARTED_OR_RESUMED"}), flush=True)
    result = AcademicCheckpointAutopilot(service, provider).run(
        session_id,
        max_generations=args.max_generations_this_call,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
