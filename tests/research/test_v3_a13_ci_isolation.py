"""A13: CI-only deterministic proof without live session or G452 checkpoint."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone

from core.data.contracts import Bar, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.bridge import ResearchSignalReplay
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.strategy_adapter import (
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)
from strategy_ir.schema import StrategyIR


def test_import_operator_cannot_read_runtime_session_on_collection() -> None:
    code = textwrap.dedent(
        """
        from pathlib import Path
        original = Path.read_text
        def guarded(self, *args, **kwargs):
            if self.name == "session-id.txt":
                raise AssertionError("CI collection tried to read production session")
            return original(self, *args, **kwargs)
        Path.read_text = guarded
        from scripts.run_academic_cohort import atomic_json, perform_backup, run
        assert callable(run)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_lag35_is_applied_once_and_replayed_with_matching_fills() -> None:
    bars = tuple(
        Bar(
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc) + timedelta(days=i),
            symbol="QQQ",
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.0 + i,
            volume=1000.0,
        )
        for i in range(75)
    )
    dataset = MarketDataSet("a13-synthetic-lag35", "development", bars)
    # One event from source[4..12], available only after 35 completed bars.
    raw = tuple(1.0 if 4 <= i <= 12 else 0.0 for i in range(75))
    effective = (None,) * 35 + raw[:-35]
    exit_signal = tuple(1.0 if i < 47 else 0.0 for i in range(75))
    signals = (("delayed", effective), ("exit_gate", exit_signal))
    strategy = StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "a13-synthetic-35-lag",
            "family": "audit",
            "generation": 0,
            "indicators": {"_unused": {"type": "SMA", "period": 2}},
            "features": {
                "delayed": {"feature_id": "research.test.lag", "lag_bars": 35},
                "exit_gate": {"feature_id": "research.test.exit", "lag_bars": 0},
            },
            "entry": {"logic": "AND", "conditions": [
                {"op": "greater_than", "left": "delayed", "value": 0.5}
            ]},
            "exit": {"logic": "OR", "conditions": [
                {"op": "less_equal", "left": "exit_gate", "value": 0.5}
            ]},
            "risk": {"stop_loss_pct": 0.0, "take_profit_pct": 0.0},
        }
    )
    hypothesis_hash = "b" * 64
    stamps = tuple(bar.timestamp for bar in bars)
    next_stamps = stamps[1:] + (None,)
    replay = ResearchSignalReplay(
        hypothesis_hash=hypothesis_hash,
        data_hash=dataset.dataset_hash,
        signals=signals,
        timestamps=stamps,
        execution_not_before=next_stamps,
        entry_regime_observations=9,
        replay_hash=content_hash(
            {
                "hypothesis": hypothesis_hash,
                "dataset": dataset.dataset_hash,
                "signals": signals,
                "decision_timestamps": [t.isoformat() for t in stamps],
                "earliest_next_bar": [t.isoformat() if t else None for t in next_stamps],
                "research_only": True,
            }
        ),
    )
    compiled = CompiledAcademicStrategy(
        hypothesis_hash=hypothesis_hash,
        dataset_hash=dataset.dataset_hash,
        replay=replay,
        strategy=strategy,
        strategy_hash=content_hash(strategy.model_dump(mode="json", by_alias=True)),
        feature_values=dict(signals),
    )
    result = evaluate_compiled_development(compiled, dataset)
    audit = audit_inherited_decisions(compiled, dataset)
    assert audit.evaluation.equity_hash == result.equity_hash
    assert audit.evaluation.trades == result.trades
    assert len(result.trades) == 2
    # Raw source pulse begins on bar4; effective pulse starts at bar39,
    # then a buy at next bar open (40). An incorrect double lag would
    # start after bar74, so no fill could possibly occur.
    assert result.trades[0].timestamp == bars[40].timestamp.isoformat()
    assert result.trades[1].timestamp == bars[48].timestamp.isoformat()
    assert result.trades[0].side == "buy"
    assert result.trades[1].side == "sell"
    assert not compiled.broker_executable
    assert not compiled.sealed_oos_approved
