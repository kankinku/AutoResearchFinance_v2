"""Explicit local T4 supervisor control; read only/status or operator request.

Setting RESUME does not itself start a worker or spend model/API tokens.
Actual execution remains an operator-invoked foreground process with its
own separately approved model transport.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.llm.supervised_checkpoint_runner import ResearchRunSupervisor


def main() -> None:
    parser = argparse.ArgumentParser(description="Local T4 research execution control")
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("action", choices=("status", "pause", "stop", "resume"))
    args = parser.parse_args()
    supervisor = ResearchRunSupervisor(args.control_dir)
    if args.action == "status":
        result = supervisor.status(args.session_id)
    else:
        desired = {"pause": "PAUSE", "stop": "STOP", "resume": "RUN"}[args.action]
        result = supervisor.request(args.session_id, desired)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
