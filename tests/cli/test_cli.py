from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_init_creates_state_and_status_returns_json(tmp_path: Path) -> None:
    initialized = run_cli("init", "--state-dir", str(tmp_path / "state"), cwd=ROOT)
    status = run_cli("status", "--state-dir", str(tmp_path / "state"), cwd=ROOT)

    assert initialized.returncode == 0
    assert status.returncode == 0
    payload = json.loads(status.stdout)
    assert payload["champion"] == "EMPTY"
    assert (tmp_path / "state" / "frontier.json").is_file()


def test_import_and_validate_commands_report_normalized_strategy(tmp_path: Path) -> None:
    source = tmp_path / "strategy.yaml"
    source.write_text(
        "schema_version: 1\n"
        "id: cli-test\n"
        "family: trend\n"
        "generation: 0\n"
        "indicators:\n"
        "  fast: {type: SMA, period: 2}\n"
        "entry: {logic: AND, conditions: [{op: greater_than, left: close, value: 1}]}\n"
        "exit: {logic: OR, conditions: [{op: less_than, left: close, value: 1}]}\n"
        "risk: {stop_loss_pct: 1, take_profit_pct: 2}\n",
        encoding="utf-8",
    )

    imported = run_cli("import-strategy", "--source", str(source), cwd=ROOT)
    validated = run_cli("validate-strategy", "--source", str(source), cwd=ROOT)

    assert imported.returncode == 0
    assert json.loads(imported.stdout)["strategy_id"] == "cli-test"
    assert validated.returncode == 0
    assert json.loads(validated.stdout)["status"] == "VALID"


def test_plan_generation_emits_explicit_search_plan() -> None:
    planned = run_cli(
        "plan-generation",
        "--parent",
        "champion-1",
        "--method",
        "random",
        "--count",
        "4",
        "--seed",
        "7",
        cwd=ROOT,
    )

    assert planned.returncode == 0
    payload = json.loads(planned.stdout)
    assert payload["parent_ids"] == ["champion-1"]
    assert payload["count"] == 4
