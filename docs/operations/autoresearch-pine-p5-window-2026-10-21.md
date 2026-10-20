# PineCode P5 — BOSWaves historical warmup window reference test

2026-10-21 KST · S9/T4 dependency · Q05/Q06/Q08/Q10/Q11/Q12/Q17/Q18/Q20.
Decision: docs/decisions/2026-10-20-pinecode-internalization-5q-user-confirmed.md.

## Existing safety and frozen scope

The original 350 generations, ChatGPT↔MCP/OAuth endpoint, protected data/backtest/evaluator/costs/integrity, sealed OOS and live-orders-disabled policy remain unchanged. Source Pine is not executed by the research engine. Frozen overarching sequence V05→T4→V01–V04→V06→V07 remains unchanged; this is a required P5 parity-support subtask only.

## Exact discrepancy and reference

Original BOSWaves Trend Target Ribbon Pine v6 uses a historical full-window structural stop:
- Bull: ta.lowest(low, stopLookback)[1].
- Bear: ta.highest(high, stopLookback)[1].
- Before that lookback exists, the returned value is na; risk falls back to minStopAtr * ATR using nz(rawRisk, minimumRisk).
- Then min(max(value, minimumRisk), maximumRisk) clips the result.

The prior Python port used low[max(0,i-lookback):i] and high analog, silently calculating a **partial window** when the specified lookback was unavailable. On the provided synthetic fixture with lookback=50 at an entry flip on bar 36, the Python port's risk distance was **6.0**, while source semantics require **1.5** (ATR=2, minimum risk=0.75*ATR).

Official TradingView execution model explicitly states ta.highest(high,20) has na for the first 19 historical bars: https://www.tradingview.com/pine-script-docs/language/execution-model/ . Fix: only build structure low/high at i >= lookback, else use the Pine nz minimum-risk fallback. This is a **source formula / official specification** comparison, not a verified TradingView bar-series export.

## RED→GREEN evidence

1. Added test test_pine_ta_lowest_not_ready_does_not_use_partial_history to the existing BOSWaves regression file. Observed **RED: 6.0 versus 1.5**.
2. Fixed the warmup window behavior; rerun **GREEN**.
3. Added tests/research/test_pine_reference_math_p5.py: independent statistics.pstdev, weighted ALMA, Wilder ATR witnesses over 130 synthetic dynamic bars for BOSWaves and Shaakuni; 2 standalone tests passed.
4. Previous BOSWaves flip-bar target visual correction remains covered.

## Actual test ledger

- Pine + Shaakuni + typed expression + scope lock: **29/29 pytest PASS**.
- Repository-wide Ruff: **PASS**.
- Repository-wide Mypy: **PASS (294 source files)**.
- Repository-wide pytest: **INTERRUPTED after 185-second timeout**; NOT PASS. Separately, pytest --collect-only -q **collected 1,904 tests with exit 0**. Collection success is not execution success.
- Independent TradingView exported original event-by-event visual/indicator outputs and fill-by-fill Pine strategy parity: **NOT RUN**.
- P6 operating feature registry and P7 live GPT/MCP S7/autonomous succession: **NOT RUN**.

Checks ran on isolated Moon workspace /shared/moon-workspace/AutoResearchFinance_v2-pine-internalization-20261020, using its own .venv after restoring declared runtime dependencies. No credential, remote deployment or official research state change.

## Next gates

P5 needs actual TradingView reference export or separately validated source-of-truth fixtures for output parity, including BOSWaves flip, SL, same-bar targetHit, Shaakuni OB creation/mitigation, session and bar time semantics. Until P5 is accepted, no Pine source is promoted to GPT operational catalog. Exact current full internalization **0/11**. After accepted P5, opt-in typed P6 integration then P7 actual GPT S7 research, diagnosis, successor evidence; preserve existing G350 and sealed data.

## Commit and next gate

Source commit 271175dbb8d6c56de0dcf4a5dd311946d6e975f2 pushed on the existing feature branch. A future full test attempt should shard suites with explicit time budgets. Next P5 reference-export comparisons then P6 opt-in typed registry and P7 actual GPT/MCP S7 research, all behind independent tests.
