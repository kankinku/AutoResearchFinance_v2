"""Read-only, one-shot 2026 chronological holdout of frozen G248 and G431.

Never calls academic checkpoint submit/extend/evaluate APIs, mutates session
state, or labels this non-PIT Yahoo data sealed out-of-sample validation.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    _plan_vectors,
    _source_names,
    compile_algorithm_plan,
)
from research.indicator_engine.signals import calculate_signal
from research.indicator_engine.strategy_adapter import _COST
from strategy_ir.schema import StrategyIR

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state/moon-http/fresh-20261021"
OUT = STATE / "oos-forward-2026"
START = date(2026, 1, 2)
END = date(2026, 10, 20)
DEV_LAST = date(2025, 12, 31)
CAPITAL = 10000.0
FROZEN = {
    248: (
        "d77f2d50ec1a3cce7c683141a5b96fdeb9a203ee5f6b2ba52fa0d42d134e448d",
        "087717ce3b126194844cacb119879032569e57fa7d466bb7ff5c307e4df6d2a0",
    ),
    431: (
        "6ab6744fb2b8de5f9021ef8cd657245f339aca2267f4dd93907a22b844ce6a1b",
        "fedf935bc7e4ef2c456ce05a0b5d3ce8bbb78ed78b721c759b7805b1409630d3",
    ),
}


def closed_yahoo_bars() -> tuple[list[Bar], dict]:
    # Require an explicit frozen period to avoid lookahead or current-day
    # partial bars. Yahoo OHLCV uses regular session US exchange timestamps.
    p1 = int(datetime(2025, 12, 29, tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(2026, 10, 22, tzinfo=timezone.utc).timestamp())
    url = "https://query1.finance.yahoo.com/v8/finance/chart/QQQ"
    resp = requests.get(
        url,
        params={"period1": p1, "period2": p2, "interval": "1d", "events": "div,splits"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=25,
    )
    resp.raise_for_status()
    source_json = resp.json()
    if source_json["chart"]["error"] is not None:
        raise RuntimeError("SOURCE_PROVIDER_ERROR")
    result = source_json["chart"]["result"][0]
    assert result["meta"]["symbol"] == "QQQ"
    quote = result["indicators"]["quote"][0]
    timestamps = result["timestamp"]
    quotes = list(
        zip(
            timestamps,
            quote["open"],
            quote["high"],
            quote["low"],
            quote["close"],
            quote["volume"],
            strict=True,
        )
    )
    trading_dates = []
    bars = []
    for ts, opened, high, low, close, volume in quotes:
        d = datetime.fromtimestamp(ts, tz=ZoneInfo("America/New_York")).date()
        if d == DEV_LAST:
            assert close is not None, "DEV_OVERLAP_CLOSE_MISSING"
            trading_dates.append((d, float(close)))
        if not START <= d <= END:
            continue
        if any(
            v is None or not math.isfinite(float(v)) for v in (opened, high, low, close, volume)
        ):
            raise RuntimeError("MISSING_FORWARD_OHLCV")
        bars.append(
            Bar(
                timestamp=datetime.combine(d, time.min, timezone.utc),
                symbol="QQQ",
                open=float(opened),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(volume),
            )
        )
    if len(bars) < 150 or bars[0].timestamp.date() != START or bars[-1].timestamp.date() != END:
        raise RuntimeError("FORWARD_DATA_RANGE_INCOMPLETE")
    if len({bar.timestamp for bar in bars}) != len(bars):
        raise RuntimeError("FORWARD_DUPLICATE_DATES")
    if len(trading_dates) != 1:
        raise RuntimeError("NO_VENDOR_TRAINING_OVERLAP")
    return bars, {
        "source_uri": resp.url,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "response_sha256": hashlib.sha256(resp.content).hexdigest(),
        "2025_12_31_vendor_close": trading_dates[0][1],
        "unadjusted_price_only": True,
        "forward_first_date": bars[0].timestamp.date().isoformat(),
        "forward_last_date": bars[-1].timestamp.date().isoformat(),
        "forward_bar_count": len(bars),
        "forward_bars_sha256": content_hash([b.record() for b in bars]),
    }


def max_drawdown(curve: list[float] | tuple[float, ...]) -> float:
    peak = CAPITAL
    dd = 0.0
    for x in curve:
        peak = max(peak, x)
        dd = max(dd, 1 - x / peak)
    return dd


def execute():
    sid = (STATE / "session-id.txt").read_text(encoding="utf-8").strip()
    svc = AcademicMCPCheckpointService(project_root=ROOT, state_dir=STATE / "research")
    # Frozen original strategy evidence, without reading the future market.
    with svc._connect() as db:
        _, cat, development, run_state = svc._state(db, sid)
        assert run_state["completed_generations"] == 452
        assert (
            development.dataset_hash
            == "f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e"
        )
        assert development.bars[-1].timestamp.date() == DEV_LAST
        histories = {g: run_state["history"][g - 1] for g in FROZEN}
        frozen = {}
        for g, evidence in histories.items():
            expected_evidence, expected_ir = FROZEN[g]
            assert evidence["evidence_hash"] == expected_evidence
            assert evidence["strategy_hash"] == expected_ir
            frozen_ir = StrategyIR.model_validate(evidence["inherited_strategy_ir"])
            assert content_hash(frozen_ir.model_dump(mode="json", by_alias=True)) == expected_ir
            assert frozen_ir.risk.position_size_pct == 100
            assert frozen_ir.risk.stop_loss_pct == frozen_ir.risk.take_profit_pct == 0
            plan = AlgorithmPlan.model_validate(evidence["base_algorithm_plan"])
            ref = compile_algorithm_plan(cat, plan, development)
            # Reproduce the in-sample performance with EXACT frozen StrategyIR
            dev_result = BacktestEngine().run(
                BacktestRequest(
                    run_id=f"frozen-dev-replay-{g}",
                    strategy_hash=expected_ir,
                    dataset=development,
                    initial_cash=CAPITAL,
                    strategy=frozen_ir,
                    cost_model=_COST,
                    feature_values=ref.compiled.feature_values,
                )
            )
            dev_ret = dev_result.equity_curve[-1] / CAPITAL - 1
            if not math.isclose(
                dev_ret, evidence["metrics"]["total_return"], rel_tol=1e-9, abs_tol=1e-9
            ):
                raise RuntimeError(f"DEVELOPMENT_PNL_REPRODUCIBILITY_FAILED_G{g}: {dev_ret}")
            print(
                "REPLAY_ORDER_COUNTS",
                g,
                len(dev_result.trades),
                sum(t.side == "sell" for t in dev_result.trades),
                evidence["metrics"]["trade_count"],
                flush=True,
            )
            if (
                sum(t.side == "sell" for t in dev_result.trades)
                != evidence["metrics"]["trade_count"]
            ):
                raise RuntimeError(f"DEVELOPMENT_TRADE_REPRODUCIBILITY_FAILED_G{g}")
            frozen[g] = (frozen_ir, plan, ref.compiled.feature_values)
            print(
                "DEVELOPMENT_REPLAY_OK",
                g,
                round(dev_ret * 100, 4),
                len(dev_result.trades),
                flush=True,
            )

        # Pull ONLY after the candidate selection and replay is frozen.
        bars, source = closed_yahoo_bars()
        if abs(source["2025_12_31_vendor_close"] - development.bars[-1].close) > 0.05:
            raise RuntimeError("RAW_SOURCE_OVERLAP_PRICE_MISMATCH")
        validation = MarketDataSet(
            version="g248-g431-forward-2026-10-21-v1",
            zone=DataZone.VALIDATION,
            bars=development.bars + tuple(bars),
            provenance=MarketSourceProvenance(
                source_id="yahoo-direct-2026:QQQ, original-yahoo-derived-2020-2025-warmup",
                retrieved_at=datetime.now(timezone.utc),
                revision_policy="latest",
                universe_policy="single_symbol",
                corporate_action_policy="raw",
                corporate_action_reference=source["source_uri"],
                includes_delisted=False,
            ),
        )
        assert len(validation.bars) == len(development.bars) + len(bars)
        source["validation_dataset_hash"] = validation.dataset_hash
        source["original_development_dataset_hash"] = development.dataset_hash
        report = {
            "study_type": "ONE_SHOT_CHRONOLOGICAL_HOLDOUT_NOT_SEALED_PIT",
            "verified_research_state_hash": run_state["history"][-1]["evidence_hash"],
            "session_id": sid,
            "asset": "QQQ",
            "period_start": START.isoformat(),
            "period_end": END.isoformat(),
            "starting_cash": CAPITAL,
            "cost_per_side_basis_points": 8,
            "source": source,
            "strategies": {},
        }
        inputs = {
            k: tuple(float(getattr(b, k)) for b in validation.bars)
            for k in ("open", "high", "low", "close")
        }
        for g, (ir, plan, original_values) in frozen.items():
            src = {
                name: calculate_signal(cat.get_indicator(name), inputs)
                for name in _source_names(plan)
            }
            allvals = {**src, **_plan_vectors(plan, src, len(validation.bars))}
            assert set(allvals) == set(original_values)
            for key, vals in original_values.items():
                if tuple(allvals[key][: len(vals)]) != tuple(vals):
                    raise RuntimeError(f"CAUSAL_WARMUP_MISMATCH_G{g}_{key}")
            actual = BacktestEngine().run(
                BacktestRequest(
                    run_id=f"precommitted-2026-forward-g{g}",
                    strategy_hash=FROZEN[g][1],
                    dataset=validation,
                    initial_cash=CAPITAL,
                    strategy=ir,
                    cost_model=_COST,
                    feature_values=allvals,
                    signal_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                )
            )
            forward_equity = list(actual.equity_curve[-len(bars) :])
            forward_trades = [t for t in actual.trades if t.timestamp[:10] >= START.isoformat()]
            assert all(t.timestamp[:10] >= START.isoformat() for t in actual.trades)
            result = {
                "generation": g,
                "original_strategy_hash": FROZEN[g][1],
                "original_evidence_hash": FROZEN[g][0],
                "in_sample_return_pct": round(histories[g]["metrics"]["total_return"] * 100, 4),
                "in_sample_mdd_pct": round(histories[g]["metrics"]["max_drawdown"] * 100, 4),
                "forward_return_pct": round((forward_equity[-1] / CAPITAL - 1) * 100, 4),
                "forward_mdd_pct": round(max_drawdown(forward_equity) * 100, 4),
                "forward_orders": len(forward_trades),
                "forward_buy_orders": sum(t.side == "buy" for t in forward_trades),
                "forward_sell_orders": sum(t.side == "sell" for t in forward_trades),
                "forward_marked_final_equity_usd": round(forward_equity[-1], 4),
                "forward_costs_usd": round(sum(t.cost for t in forward_trades), 4),
                "end_position_open": sum(t.side == "buy" for t in forward_trades)
                > sum(t.side == "sell" for t in forward_trades),
                "forward_equity_curve_sha256": content_hash(forward_equity),
                "forward_daily_equity": [
                    {"date": d.timestamp.date().isoformat(), "equity": round(e, 6)}
                    for d, e in zip(bars, forward_equity, strict=True)
                ],
                "orders": [
                    {
                        "date": t.timestamp[:10],
                        "side": t.side,
                        "price": round(t.price, 4),
                        "cost": round(t.cost, 4),
                    }
                    for t in forward_trades
                ],
            }
            report["strategies"][f"G{g}"] = result
            print(
                "FORWARD_SCORE",
                g,
                result["forward_return_pct"],
                result["forward_mdd_pct"],
                result["forward_orders"],
                flush=True,
            )

    # Price-only fully invested QQQ buy/hold with same research cost.
    first_open = bars[0].open
    benchmark_buy_cost = _COST.calculate(CAPITAL, side="buy", stress_multiplier=1.0).total
    units = (CAPITAL - benchmark_buy_cost) / first_open
    bench = [units * b.close for b in bars]
    buyhold = {
        "entry_date": START.isoformat(),
        "entry_price": first_open,
        "ending_price": bars[-1].close,
        "entry_cost_usd": benchmark_buy_cost,
        "return_pct": round((bench[-1] / CAPITAL - 1) * 100, 4),
        "max_drawdown_pct": round(max_drawdown(bench) * 100, 4),
        "note": "Price only, excludes dividends and liquidation exit cost.",
    }
    report["qqq_buy_hold"] = buyhold
    for score in report["strategies"].values():
        score["qqq_excess_percentage_points"] = round(
            score["forward_return_pct"] - buyhold["return_pct"], 4
        )
    report["result_interpretation"] = (
        "One-shot temporal holdout of two predeclared development-selected rules. "
        "Non-PIT vendor latest OHLCV, no dividends, insufficient independent "
        "statistical evidence of sustained edge. Do not retune on forward dataset."
    )
    OUT.mkdir(parents=True, exist_ok=True)
    file = OUT / "g248_g431_one_shot_validation_20260102_20261020.json"
    if file.exists():
        raise RuntimeError("HOLDOUT_ALREADY_UNBLINDED_ONE_SHOT_DO_NOT_OVERWRITE")
    file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("BENCHMARK", buyhold, flush=True)
    print("FINAL_REPORT", file, content_hash(report), flush=True)


if __name__ == "__main__":
    execute()
