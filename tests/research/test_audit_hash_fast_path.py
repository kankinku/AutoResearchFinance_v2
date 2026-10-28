"""Regression: optimized S2/S7 audit hashing must preserve all signed v2 bytes."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from core.backtest.engine import Trade
from core.integrity.hashes import content_hash
from research.indicator_engine.decision_audit import (
    ClosedResearchTrade,
    DecisionObservation,
    FillObservation,
    calculate_audit_hash,
)
from research.indicator_engine.strategy_adapter import AcademicDevelopmentResult


def test_audit_hash_fast_path_is_byte_identical_to_legacy_asdict():
    t = datetime(2024, 3, 14, tzinfo=timezone.utc)
    sale = Trade(timestamp=(t + timedelta(days=1)).isoformat(), side="sell",
                 price=112.75, quantity=5.0, notional=563.75,
                 cost=1.2775, symbol="QQQ")
    purchase = Trade(timestamp=t.isoformat(), side="buy",
                     price=100.2, quantity=5.0, notional=501.0,
                     cost=1.102, symbol="QQQ")
    observation = DecisionObservation(
        decision_id="test-D-1", symbol="QQQ", bar_index=2,
        signal_time=t-timedelta(days=1), earliest_execution=t,
        action="REQUEST_ENTRY", entry_signal=1.0, regime_signal=None,
        evaluated_gates=(("entry", True), ("exit", False), ("regime", None)),
        indicator_values=(("adx_14", 24.9), ("rsi_14", None)),
        fill_id="test-F-0",
    )
    buy = FillObservation(
        fill_id="test-F-0", trade_id="test-T-0", decision_id="test-D-1",
        bar_index=3, execution_time=t, side="buy", price=100.2, trade=purchase,
    )
    sell = FillObservation(
        fill_id="test-F-1", trade_id="test-T-0", decision_id="test-D-2",
        bar_index=4, execution_time=t + timedelta(days=1), side="sell",
        price=112.75, trade=sale,
    )
    closed = ClosedResearchTrade("test-T-0", buy, sell, 60.3705)
    evaluation = AcademicDevelopmentResult(
        hypothesis_hash="hyp", dataset_hash="data", strategy_hash="strat",
        replay_hash="replay", equity_hash="equity",
        equity_curve=(10000., 9998.8, 10059.2),
        initial_cash=10000., final_equity=10059.2,
        trades_count=2, trades=(purchase, sale),
        total_paid_costs=2.3795,
    )
    packet = {"metrics": {"return": 0.00592}, "audit_hash": "self-ref"}
    old = content_hash({
        "schema": "research-decision-audit-evidence-v2",
        "evaluation": {
            "strategy": evaluation.strategy_hash,
            "dataset": evaluation.dataset_hash,
            "replay": evaluation.replay_hash,
            "equity_hash": evaluation.equity_hash,
            "equity_curve": evaluation.equity_curve,
            "trades": [asdict(v) for v in evaluation.trades],
            "initial_cash": evaluation.initial_cash,
            "final_equity": evaluation.final_equity,
            "paid_costs": evaluation.total_paid_costs,
        },
        "decisions": [
            {**asdict(v), "signal_time": v.signal_time.isoformat(),
             "earliest_execution": v.earliest_execution.isoformat()
             if v.earliest_execution else None}
            for v in (observation,)
        ],
        "fills": [
            {**asdict(v), "execution_time": v.execution_time.isoformat()}
            for v in (buy, sell)
        ],
        "round_trips": [(closed.trade_id, closed.entry_fill.fill_id,
                         closed.exit_fill.fill_id, closed.net_pnl)],
        "analysis_packet": {"metrics": packet["metrics"]},
    })
    assert calculate_audit_hash(
        evaluation, (observation,), (buy, sell), (closed,), packet
    ) == old
