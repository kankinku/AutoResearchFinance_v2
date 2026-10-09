"""Detached bounded local research worker. It NEVER invokes an LLM provider."""

from __future__ import annotations

import argparse
from pathlib import Path

from application.research_batch_service import ResearchBatchService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    ResearchBatchService(project_root=args.project_root, state_dir=args.state_dir).execute(
        args.job_id
    )


if __name__ == "__main__":
    main()
