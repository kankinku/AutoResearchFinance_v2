from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from tests.support import build_subprocess_env


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


def wait_for_status(
    db_path: Path,
    *,
    project_state: str,
    pipeline_state: str | None = None,
    autoresearch_state: str | None = None,
    timeout_seconds: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        store = SQLiteStateStore(db_path=db_path, project_id="finance")
        try:
            status = store.get_status()
        finally:
            store.close()
        if status.project_state != project_state:
            time.sleep(0.2)
            continue
        if pipeline_state is not None and status.pipeline_state != pipeline_state:
            time.sleep(0.2)
            continue
        if (
            autoresearch_state is not None
            and status.autoresearch_state != autoresearch_state
        ):
            time.sleep(0.2)
            continue
        return
    raise AssertionError(
        f"timed out waiting for status {project_state}/{pipeline_state}/{autoresearch_state}"
    )


def test_python_module_start_pipeline_launches_worker_and_reaches_success(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    state_db_path = tmp_path / "runtime" / "state.db"
    mutation_handler, analysis_handler = write_openclaw_handlers(tmp_path)
    write_cached_market_pack(workspace_root)
    write_workspace_strategy(workspace_root, baseline_strategy_source())
    SQLiteStateStore(db_path=state_db_path, project_id="finance").close()

    env = build_subprocess_env(
        {
            "FINANCE_AUTORESEARCH_PROJECT_ID": "finance",
            "FINANCE_AUTORESEARCH_WORKSPACE_ROOT": str(workspace_root),
            "FINANCE_AUTORESEARCH_STATE_DB_PATH": str(state_db_path),
            "FINANCE_AUTORESEARCH_MARKET_PACK_MODE": "cached",
            "FINANCE_AUTORESEARCH_OPENCLAW_ROLES_PATH": str(
                CODE_ROOT / "config" / "openclaw.roles.example.yaml"
            ),
            "FINANCE_AUTORESEARCH_OPENCLAW_GATEWAY_URL": "http://127.0.0.1:18789",
            "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH": str(mutation_handler),
            "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH": str(analysis_handler),
            "FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_TOKEN": "control-token",
            "FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_CHAT_ID": "control-chat",
            "FINANCE_AUTORESEARCH_TELEGRAM_REPORT_TOKEN": "report-token",
            "FINANCE_AUTORESEARCH_TELEGRAM_REPORT_CHAT_ID": "report-chat",
            "FINANCE_AUTORESEARCH_TELEGRAM_REPORT_DRY_RUN": "true",
        }
    )

    process = subprocess.run(
        [sys.executable, "-m", "finance_autoresearch", "start_pipeline"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
        cwd=str(CODE_ROOT),
    )

    assert process.returncode == 0
    response = json.loads(process.stdout)
    assert response["accepted"] is True
    assert response["project_state"] == "active"
    assert response["pipeline_state"] == "running"

    wait_for_status(
        state_db_path,
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )

    store = SQLiteStateStore(db_path=state_db_path, project_id="finance")
    try:
        assert store.list_pending_outbox() == []
    finally:
        store.close()


def test_python_module_start_autoresearch_launches_worker_and_rolls_back_candidate(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    state_db_path = tmp_path / "runtime" / "state.db"
    mutation_handler, analysis_handler = write_openclaw_handlers(tmp_path)
    write_cached_market_pack(workspace_root)
    baseline_path = write_workspace_strategy(workspace_root, baseline_strategy_source())
    baseline_source = baseline_path.read_text(encoding="utf-8")
    SQLiteStateStore(db_path=state_db_path, project_id="finance").close()

    env = build_subprocess_env(
        {
            "FINANCE_AUTORESEARCH_PROJECT_ID": "finance",
            "FINANCE_AUTORESEARCH_WORKSPACE_ROOT": str(workspace_root),
            "FINANCE_AUTORESEARCH_STATE_DB_PATH": str(state_db_path),
            "FINANCE_AUTORESEARCH_MARKET_PACK_MODE": "cached",
            "FINANCE_AUTORESEARCH_AUTORESEARCH_MAX_ITERATIONS": "1",
            "FINANCE_AUTORESEARCH_OPENCLAW_ROLES_PATH": str(
                CODE_ROOT / "config" / "openclaw.roles.example.yaml"
            ),
            "FINANCE_AUTORESEARCH_OPENCLAW_GATEWAY_URL": "http://127.0.0.1:18789",
            "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH": str(mutation_handler),
            "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH": str(analysis_handler),
            "FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_TOKEN": "control-token",
            "FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_CHAT_ID": "control-chat",
            "FINANCE_AUTORESEARCH_TELEGRAM_REPORT_TOKEN": "report-token",
            "FINANCE_AUTORESEARCH_TELEGRAM_REPORT_CHAT_ID": "report-chat",
            "FINANCE_AUTORESEARCH_TELEGRAM_REPORT_DRY_RUN": "true",
        }
    )

    pipeline = subprocess.run(
        [sys.executable, "-m", "finance_autoresearch", "start_pipeline"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
        cwd=str(CODE_ROOT),
    )
    assert pipeline.returncode == 0
    wait_for_status(
        state_db_path,
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )

    process = subprocess.run(
        [sys.executable, "-m", "finance_autoresearch", "start_autoresearch"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
        cwd=str(CODE_ROOT),
    )

    assert process.returncode == 0
    response = json.loads(process.stdout)
    assert response["accepted"] is True
    assert isinstance(response["run_id"], str)
    assert response["run_id"]
    assert response["autoresearch_state"] == "running"

    wait_for_status(
        state_db_path,
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="success",
    )

    store = SQLiteStateStore(db_path=state_db_path, project_id="finance")
    try:
        experiment = store.get_latest_experiment()
        assert experiment is not None
        assert experiment.decision == "rollback"
        assert store.list_pending_outbox() == []
    finally:
        store.close()

    assert baseline_path.read_text(encoding="utf-8") == baseline_source
