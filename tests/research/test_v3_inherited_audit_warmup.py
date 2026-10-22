"""Regression: executable OR entry must not wait for unrelated exit feature warmup."""

from __future__ import annotations

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


def _warmup_fixture() -> tuple[CompiledAcademicStrategy, MarketDataSet]:
    bars = tuple(
        Bar(
            datetime(2024, 1, 2, tzinfo=timezone.utc) + timedelta(days=i),
            "QQQ",
            100 + i,
            101 + i,
            99 + i,
            100 + i,
            1000,
        )
        for i in range(6)
    )
    dataset = MarketDataSet("s2-regression-v3", "development", bars)
    signals = (
        ("fast", (1.0, 1.0, 0.0, 0.0, 1.0, 0.0)),
        ("slow", (None, None, 0.0, 0.0, 1.0, 1.0)),
    )
    hypothesis_hash = "a" * 64
    timestamps = tuple(b.timestamp for b in bars)
    next_bars = timestamps[1:] + (None,)
    replay = ResearchSignalReplay(
        hypothesis_hash=hypothesis_hash,
        data_hash=dataset.dataset_hash,
        signals=signals,
        timestamps=timestamps,
        execution_not_before=next_bars,
        entry_regime_observations=0,
        replay_hash=content_hash(
            {
                "hypothesis": hypothesis_hash,
                "dataset": dataset.dataset_hash,
                "signals": signals,
                "decision_timestamps": [t.isoformat() for t in timestamps],
                "earliest_next_bar": [t.isoformat() if t else None for t in next_bars],
                "research_only": True,
            }
        ),
    )
    strategy = StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "v3-warmup-regression",
            "family": "academic",
            "generation": 0,
            "indicators": {"_unused_sma": {"type": "SMA", "period": 2}},
            "features": {
                name: {"feature_id": "academic.research." + name}
                for name, _ in signals
            },
            "entry": {
                "logic": "OR",
                "conditions": [
                    {"op": "greater_than", "left": "fast", "value": 0.5},
                    {"op": "greater_than", "left": "slow", "value": 0.5},
                ],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "less_equal", "left": "slow", "value": 0.5}],
            },
            "risk": {
                "stop_loss_pct": 0.0,
                "take_profit_pct": 0.0,
                "position_size_pct": 100.0,
            },
        }
    )
    return (
        CompiledAcademicStrategy(
            hypothesis_hash=hypothesis_hash,
            dataset_hash=dataset.dataset_hash,
            replay=replay,
            strategy=strategy,
            strategy_hash=content_hash(strategy.model_dump(mode="json", by_alias=True)),
            feature_values=dict(signals),
        ),
        dataset,
    )


def test_or_entry_executes_during_unrelated_exit_warmup() -> None:
    compiled, dataset = _warmup_fixture()
    canonical = evaluate_compiled_development(compiled, dataset)
    assert [(t.side, t.timestamp) for t in canonical.trades[:2]] == [
        ("buy", dataset.bars[1].timestamp.isoformat()),
        ("sell", dataset.bars[3].timestamp.isoformat()),
    ]
    audited = audit_inherited_decisions(compiled, dataset)
    assert audited.evaluation == canonical
    assert audited.decisions[0].action == "REQUEST_ENTRY"
    assert audited.fills[0].decision_id == audited.decisions[0].decision_id
    assert len(audited.fills) == len(canonical.trades)
    assert len(audited.round_trips) == 1


def test_or_entry_one_ready_signal_even_if_other_entry_is_unready() -> None:
    compiled, dataset = _warmup_fixture()
    assert compiled.feature_values["slow"][0] is None
    audit = audit_inherited_decisions(compiled, dataset)
    assert audit.decisions[0].action == "REQUEST_ENTRY"
    assert audit.decisions[0].evaluated_gates[0] == ("entry_positive", True)
