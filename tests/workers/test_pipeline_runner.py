from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from finance_autoresearch.settings import Settings
from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from finance_autoresearch.workers.pipeline_runner import PipelineRunner


def make_canonical_frame(
    symbol: str,
    timeframe: str,
    timestamps: pd.DatetimeIndex,
) -> pd.DataFrame:
    values = list(range(len(timestamps)))
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + value for value in values],
            "high": [101.0 + value for value in values],
            "low": [99.0 + value for value in values],
            "close": [100.5 + value for value in values],
            "volume": [1_000 + value for value in values],
            "symbol": [symbol] * len(timestamps),
            "timeframe": [timeframe] * len(timestamps),
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStateStore:
    repository = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    yield repository
    repository.close()


def test_pipeline_runner_emits_outbox_events_and_resets_idle_state_on_success(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    timestamps = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    market_pack = {
        ("QQQ", "1d"): make_canonical_frame("QQQ", "1d", timestamps),
        ("QQQ", "2h"): make_canonical_frame("QQQ", "2h", timestamps),
        ("IWM", "1d"): make_canonical_frame("IWM", "1d", timestamps),
        ("IWM", "2h"): make_canonical_frame("IWM", "2h", timestamps),
        ("BTC-USD", "1d"): make_canonical_frame("BTC-USD", "1d", timestamps),
        ("BTC-USD", "2h"): make_canonical_frame("BTC-USD", "2h", timestamps),
    }
    baseline_snapshot = tmp_path / "accepted-baseline.py"
    baseline_strategy = tmp_path / "strategy_candidate.py"
    baseline_strategy.write_text("def build_strategy(context):\n    return context\n", encoding="utf-8")
    settings = Settings(
        telegram_control_token="control-token",
        telegram_control_chat_id="control-chat",
        telegram_report_token="report-token",
        telegram_report_chat_id="report-chat",
        dashboard_host="127.0.0.1",
        dashboard_port=8000,
    )

    store.set_status(
        project_state="degraded",
        pipeline_state="failed",
        autoresearch_state="stale",
    )

    runner = PipelineRunner(
        state_store=store,
        settings=settings,
        market_pack_builder=lambda: market_pack,
        market_pack_validator=lambda pack: None,
        baseline_strategy_path=baseline_strategy,
        baseline_snapshot_path=baseline_snapshot,
        openclaw_check=lambda: None,
    )

    result = runner.run()
    persisted_state = store.get_status()
    pending_outbox = store.list_pending_outbox()

    assert result.succeeded is True
    assert result.stage == "completed"
    assert sorted(result.market_pack_keys) == sorted(market_pack.keys())
    assert persisted_state.project_state == "idle"
    assert persisted_state.pipeline_state == "success"
    assert persisted_state.autoresearch_state == "idle"
    assert persisted_state.current_stage is None
    assert persisted_state.pipeline_heartbeat_at is None
    assert baseline_snapshot.exists() is True
    assert [message.event_type for message in pending_outbox] == [
        "pipeline_started",
        "pipeline_succeeded",
    ]
    assert pending_outbox[1].payload["market_pack_keys"] == [
        "BTC-USD:1d",
        "BTC-USD:2h",
        "IWM:1d",
        "IWM:2h",
        "QQQ:1d",
        "QQQ:2h",
    ]


def test_pipeline_runner_requires_telegram_control_credentials_by_default(
    tmp_path: Path,
    store: SQLiteStateStore,
) -> None:
    timestamps = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    market_pack = {
        ("QQQ", "1d"): make_canonical_frame("QQQ", "1d", timestamps),
        ("QQQ", "2h"): make_canonical_frame("QQQ", "2h", timestamps),
        ("IWM", "1d"): make_canonical_frame("IWM", "1d", timestamps),
        ("IWM", "2h"): make_canonical_frame("IWM", "2h", timestamps),
        ("BTC-USD", "1d"): make_canonical_frame("BTC-USD", "1d", timestamps),
        ("BTC-USD", "2h"): make_canonical_frame("BTC-USD", "2h", timestamps),
    }
    baseline_strategy = tmp_path / "strategy_candidate.py"
    baseline_strategy.write_text("def build_strategy(context):\n    return context\n", encoding="utf-8")
    settings = Settings(
        telegram_report_token="report-token",
        telegram_report_chat_id="report-chat",
        dashboard_host="127.0.0.1",
        dashboard_port=8000,
    )

    runner = PipelineRunner(
        state_store=store,
        settings=settings,
        market_pack_builder=lambda: market_pack,
        market_pack_validator=lambda pack: None,
        baseline_strategy_path=baseline_strategy,
        baseline_snapshot_path=tmp_path / "accepted-baseline.py",
        openclaw_check=lambda: None,
    )

    result = runner.run()
    persisted_state = store.get_status()
    pending_outbox = store.list_pending_outbox()

    assert result.succeeded is False
    assert result.stage == "check_telegram_control"
    assert "telegram control" in result.message
    assert persisted_state.project_state == "degraded"
    assert persisted_state.pipeline_state == "failed"
    assert persisted_state.current_stage is None
    assert [message.event_type for message in pending_outbox] == [
        "pipeline_started",
        "pipeline_failed",
    ]
    assert pending_outbox[1].payload["stage"] == "check_telegram_control"
