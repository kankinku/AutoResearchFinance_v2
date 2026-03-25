from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("FINANCE_AUTORESEARCH_AUTORESEARCH_MAX_ITERATIONS", "1")

from finance_autoresearch.state.sqlite_store import SQLiteStateStore


CODE_ROOT = Path(__file__).resolve().parents[2]
MUTABLE_TARGET_PATH = Path(
    "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"
)


def make_market_frame(
    *,
    symbol: str,
    timeframe: str,
    start: str,
    periods: int,
    freq: str,
    phase: float,
    trend: float,
) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=periods, freq=freq, tz="UTC")
    base = np.linspace(0.0, trend, periods)
    oscillation = np.sin(np.linspace(phase, phase + (64 * np.pi), periods)) * 8.0
    close = pd.Series(100.0 + base + oscillation, index=index, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": close - 0.3,
            "high": close + 0.8,
            "low": close - 0.8,
            "close": close,
            "volume": pd.Series(5_000 + np.arange(periods), index=index, dtype=float),
            "symbol": symbol,
            "timeframe": timeframe,
        }
    )


def write_cached_market_pack(workspace_root: Path) -> None:
    canonical_root = workspace_root / "data" / "market" / "canonical"
    canonical_root.mkdir(parents=True, exist_ok=True)
    market_pack = {
        ("QQQ", "1d"): make_market_frame(
            symbol="QQQ",
            timeframe="1d",
            start="2019-01-01",
            periods=14_602,
            freq="3h",
            phase=0.0,
            trend=30.0,
        ),
        ("IWM", "1d"): make_market_frame(
            symbol="IWM",
            timeframe="1d",
            start="2019-01-01",
            periods=14_602,
            freq="3h",
            phase=0.7,
            trend=20.0,
        ),
        ("BTC-USD", "1d"): make_market_frame(
            symbol="BTC-USD",
            timeframe="1d",
            start="2019-01-01",
            periods=14_602,
            freq="3h",
            phase=1.4,
            trend=45.0,
        ),
        ("QQQ", "2h"): make_market_frame(
            symbol="QQQ",
            timeframe="2h",
            start="2024-01-01",
            periods=77_762,
            freq="10min",
            phase=0.2,
            trend=25.0,
        ),
        ("IWM", "2h"): make_market_frame(
            symbol="IWM",
            timeframe="2h",
            start="2024-01-01",
            periods=77_762,
            freq="10min",
            phase=0.9,
            trend=18.0,
        ),
        ("BTC-USD", "2h"): make_market_frame(
            symbol="BTC-USD",
            timeframe="2h",
            start="2024-01-01",
            periods=77_762,
            freq="10min",
            phase=1.6,
            trend=35.0,
        ),
    }
    for (symbol, timeframe), frame in market_pack.items():
        frame.to_parquet(canonical_root / f"{symbol}_{timeframe}.parquet", index=False)


def baseline_strategy_source() -> str:
    return "\n".join(
        [
            "import pandas as pd",
            "from finance_autoresearch.strategy.base_contract import StrategyContext, StrategyDefinition",
            "",
            "def build_strategy(context: StrategyContext) -> StrategyDefinition:",
            "    regime = context.regimes.classify_ema200_regime(context.close)",
            "    regime_valid = context.indicators.ema(context.close, 200).notna()",
            "    bull = context.regimes.is_bull(context.close) & regime_valid",
            "    bear = context.regimes.is_bear(context.close) & regime_valid",
            "    bar_index = pd.Series(range(len(context.close)), index=context.close.index)",
            "    cycle = 150 if context.timeframe == '1d' else 220",
            "    cycle_entry = bar_index.mod(cycle).eq(0)",
            "    cycle_exit = bar_index.mod(cycle).eq(max(1, cycle - 5))",
            "    long_entries = bull & cycle_entry",
            "    long_exits = (bull & cycle_exit) | bear",
            "    short_entries = bear & cycle_entry",
            "    short_exits = (bear & cycle_exit) | bull",
            "    return StrategyDefinition(",
            "        long_entries=long_entries,",
            "        long_exits=long_exits,",
            "        short_entries=short_entries,",
            "        short_exits=short_exits,",
            "        regime=regime,",
            "        params={'cycle_1d': 150, 'cycle_2h': 220},",
            "        diagnostics={'cycle_1d': 150, 'cycle_2h': 220},",
            "    )",
        ]
    )


def rollback_candidate_source() -> str:
    return "\n".join(
        [
            "import pandas as pd",
            "from finance_autoresearch.strategy.base_contract import StrategyContext, StrategyDefinition",
            "",
            "def build_strategy(context: StrategyContext) -> StrategyDefinition:",
            "    regime = context.regimes.classify_ema200_regime(context.close)",
            "    regime_valid = context.indicators.ema(context.close, 200).notna()",
            "    no_signal = (context.close > (context.close + 1)) & regime_valid",
            "    return StrategyDefinition(",
            "        long_entries=no_signal,",
            "        long_exits=no_signal,",
            "        short_entries=no_signal,",
            "        short_exits=no_signal,",
            "        regime=regime,",
            "        params={'mode': 'rollback'},",
            "        diagnostics={'summary': 'rollback candidate'},",
            "    )",
        ]
    )


def write_workspace_strategy(workspace_root: Path, source: str) -> Path:
    strategy_path = workspace_root / MUTABLE_TARGET_PATH
    strategy_path.parent.mkdir(parents=True, exist_ok=True)
    strategy_path.write_text(source, encoding="utf-8")
    return strategy_path


def write_openclaw_handlers(tmp_path: Path) -> tuple[Path, Path]:
    handlers_root = tmp_path / "handlers"
    handlers_root.mkdir(parents=True, exist_ok=True)
    mutation_handler = handlers_root / "mutation-handler.ps1"
    analysis_handler = handlers_root / "analysis-handler.ps1"
    mutation_handler.write_text(
        "\n".join(
            [
                "param(",
                "    [string]$AgentId,",
                "    [string]$RequestJson,",
                "    [string]$ResponseJson",
                ")",
                "$request = Get-Content -Raw -Path $RequestJson | ConvertFrom-Json",
                "$artifact = [ordered]@{",
                "    kind = 'strategy_replacement'",
                f"    target_path = '{str(MUTABLE_TARGET_PATH).replace('\\', '/')}'",
                "    hypothesis = 'Try a no-signal fallback.'",
                "    change_summary = 'Replace the strategy with a rollback candidate.'",
                "    full_file_contents = @'",
                rollback_candidate_source(),
                "'@",
                "    expected_effects = @('Trigger a rollback while preserving baseline.')",
                "}",
                "$response = [ordered]@{",
                "    ok = $true",
                "    task_kind = 'mutation'",
                "    idempotency_key = $request.idempotency_key",
                "    artifact = $artifact",
                "    error_type = $null",
                "    message = 'ok'",
                "    retryable = $false",
                "}",
                "$response | ConvertTo-Json -Depth 10 | Set-Content -Path $ResponseJson -Encoding utf8",
            ]
        ),
        encoding="utf-8",
    )
    analysis_handler.write_text(
        "\n".join(
            [
                "param(",
                "    [string]$AgentId,",
                "    [string]$RequestJson,",
                "    [string]$ResponseJson",
                ")",
                "$request = Get-Content -Raw -Path $RequestJson | ConvertFrom-Json",
                "$artifact = [ordered]@{",
                "    strengths = @('baseline remained stable')",
                "    weaknesses = @('candidate produced no trades')",
                "    coverage_gaps = @('needs entry conditions')",
                "    regime_observations = @('bull and bear both lost exposure')",
                "    next_hypothesis_hints = @('restore directional entries')",
                "    summary = 'candidate regressed and should roll back'",
                "}",
                "$response = [ordered]@{",
                "    ok = $true",
                "    task_kind = 'analysis'",
                "    idempotency_key = $request.idempotency_key",
                "    artifact = $artifact",
                "    error_type = $null",
                "    message = 'ok'",
                "    retryable = $false",
                "}",
                "$response | ConvertTo-Json -Depth 10 | Set-Content -Path $ResponseJson -Encoding utf8",
            ]
        ),
        encoding="utf-8",
    )
    return mutation_handler, analysis_handler


def build_runtime_env(
    *,
    workspace_root: Path,
    state_db_path: Path,
    mutation_handler: Path,
    analysis_handler: Path,
) -> dict[str, str]:
    env = os.environ.copy()
    env["FINANCE_AUTORESEARCH_PROJECT_ID"] = "finance"
    env["FINANCE_AUTORESEARCH_WORKSPACE_ROOT"] = str(workspace_root)
    env["FINANCE_AUTORESEARCH_STATE_DB_PATH"] = str(state_db_path)
    env["FINANCE_AUTORESEARCH_MARKET_PACK_MODE"] = "cached"
    env["FINANCE_AUTORESEARCH_AUTORESEARCH_MAX_ITERATIONS"] = "1"
    env["FINANCE_AUTORESEARCH_OPENCLAW_ROLES_PATH"] = str(
        CODE_ROOT / "config" / "openclaw.roles.example.yaml"
    )
    env["FINANCE_AUTORESEARCH_OPENCLAW_GATEWAY_URL"] = "http://127.0.0.1:18789"
    env["FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH"] = str(mutation_handler)
    env["FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH"] = str(analysis_handler)
    env["FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_TOKEN"] = "control-token"
    env["FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_CHAT_ID"] = "control-chat"
    env["FINANCE_AUTORESEARCH_TELEGRAM_REPORT_TOKEN"] = "report-token"
    env["FINANCE_AUTORESEARCH_TELEGRAM_REPORT_CHAT_ID"] = "report-chat"
    env["FINANCE_AUTORESEARCH_TELEGRAM_REPORT_DRY_RUN"] = "true"
    return env


def test_openclaw_control_helper_and_wait_script_drive_pipeline(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    state_db_path = tmp_path / "runtime" / "state.db"
    mutation_handler, analysis_handler = write_openclaw_handlers(tmp_path)
    write_cached_market_pack(workspace_root)
    write_workspace_strategy(workspace_root, baseline_strategy_source())
    SQLiteStateStore(db_path=state_db_path, project_id="finance").close()
    env = build_runtime_env(
        workspace_root=workspace_root,
        state_db_path=state_db_path,
        mutation_handler=mutation_handler,
        analysis_handler=analysis_handler,
    )

    start_process = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(CODE_ROOT / "scripts" / "invoke-openclaw-control.ps1"),
            "-Command",
            "start_pipeline",
            "-ProjectId",
            "finance",
            "-RequestedBy",
            "skill-test",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=env,
        cwd=str(CODE_ROOT),
    )

    assert start_process.returncode == 0
    start_response = json.loads(start_process.stdout)
    assert start_response["accepted"] is True
    assert start_response["pipeline_state"] == "running"

    wait_process = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(CODE_ROOT / "scripts" / "wait-finance-status.ps1"),
            "-ProjectState",
            "idle",
            "-PipelineState",
            "success",
            "-AutoresearchState",
            "idle",
            "-TimeoutSeconds",
            "60",
            "-PollIntervalSeconds",
            "1",
            "-StopOnTerminalFailure",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=env,
        cwd=str(CODE_ROOT),
    )

    assert wait_process.returncode == 0
    waited_status = json.loads(wait_process.stdout)
    assert waited_status["project_state"] == "idle"
    assert waited_status["pipeline_state"] == "success"
    assert waited_status["autoresearch_state"] == "idle"


def test_install_openclaw_skills_script_builds_installable_archives(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "dist"
    openclaw_workspace = tmp_path / "openclaw-workspace"

    install_process = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(CODE_ROOT / "scripts" / "install-openclaw-skills.ps1"),
            "-RepositoryRoot",
            str(CODE_ROOT),
            "-OutputRoot",
            str(output_root),
            "-OpenClawWorkspace",
            str(openclaw_workspace),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        cwd=str(CODE_ROOT),
    )

    assert install_process.returncode == 0
    manifest = json.loads(install_process.stdout)
    assert len(manifest) == 2

    package_names = {entry["skill_name"] for entry in manifest}
    assert package_names == {
        "finance-autoresearch-control",
        "finance-autoresearch-status-polling",
    }

    control_package = output_root / "finance-autoresearch-control.skill"
    status_package = output_root / "finance-autoresearch-status-polling.skill"
    assert control_package.exists() is True
    assert status_package.exists() is True
    assert (openclaw_workspace / control_package.name).exists() is True
    assert (openclaw_workspace / status_package.name).exists() is True

    with zipfile.ZipFile(control_package) as archive:
        names = set(archive.namelist())
        assert "finance-autoresearch-control/SKILL.md" in names
        assert (
            "finance-autoresearch-control/scripts/invoke_finance_command.ps1" in names
        )
        script_text = archive.read(
            "finance-autoresearch-control/scripts/invoke_finance_command.ps1"
        ).decode("utf-8")
        assert "__REPOSITORY_ROOT__" not in script_text
        assert str(CODE_ROOT) in script_text

    with zipfile.ZipFile(status_package) as archive:
        names = set(archive.namelist())
        assert "finance-autoresearch-status-polling/SKILL.md" in names
        assert (
            "finance-autoresearch-status-polling/scripts/wait_finance_status.ps1"
            in names
        )
