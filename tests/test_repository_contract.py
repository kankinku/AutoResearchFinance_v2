from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_contract_files_and_directories_exist() -> None:
    required_files = {
        "AGENTS.md",
        "README.md",
        "pyproject.toml",
        "research/program.md",
        "research/policy.yaml",
        "research/objectives.yaml",
        "state/champion.json",
        "state/frontier.json",
        "state/knowledge.json",
        "state/rescue_pool.json",
    }
    required_directories = {
        "strategies/primitives",
        "strategies/templates",
        "strategies/imported",
        "strategies/normalized",
        "strategies/generated",
        "strategies/champions",
        "strategy_ir",
        "mutation",
        "experiments",
        "runtime",
        "core/data",
        "core/backtest",
        "core/evaluator",
        "core/validation",
        "core/costs",
        "core/integrity",
        "evaluation",
        "memory",
        "integrations/kis",
        "deployment/paper",
        "deployment/live",
        "tests",
    }

    assert all((ROOT / path).is_file() for path in required_files)
    assert all((ROOT / path).is_dir() for path in required_directories)


def test_protected_paths_are_declared() -> None:
    contract = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for protected_path in (
        "core/data",
        "core/backtest",
        "core/evaluator",
        "core/validation",
        "core/costs",
        "core/integrity",
    ):
        assert protected_path in contract


def test_generated_and_secret_paths_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "credentials/", "runs/", "state/results/", ".worktrees/"):
        assert pattern in gitignore


def test_tracked_files_do_not_contain_secret_like_names() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    forbidden_fragments = (".env", ".pem", ".key", "credentials", "secrets")
    safe_examples = {".env.example"}
    assert not any(
        path.lower() not in safe_examples
        and any(fragment in path.lower() for fragment in forbidden_fragments)
        for path in tracked
    )
