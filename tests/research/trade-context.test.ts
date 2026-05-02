import { describe, expect, test } from "vitest";

import { enrichTradesWithMarketContext } from "../../src/research/trade-context.js";

describe("trade context", () => {
  test("matches trade timestamps to the nearest 2-hour bars", () => {
    const trades = [
      {
        entryComment: "entry",
        entryPrice: 100,
        entryTime: "2026-04-20T00:30:00.000Z",
        exitComment: "exit",
        exitPrice: 98,
        exitTime: "2026-04-20T02:10:00.000Z",
        qty: 1,
        profitValue: -2,
        profitPercent: -2,
        runupPercent: 0.5,
        drawdownPercent: 3,
      },
    ];
    const bars = [
      {
        time: "2026-04-20T00:00:00.000Z",
        regime: "trend_down",
        close: 100,
        open: 100,
        high: 101,
        low: 99,
        volume: 10,
        ema20: 101,
        ema50: 103,
        ema200: 110,
        atr14: 2,
        atrPercent: 2,
        rsi14: 40,
        bbWidth: 0.06,
        ret3: -0.03,
        ret10: -0.05,
      },
      {
        time: "2026-04-20T02:00:00.000Z",
        regime: "trend_down",
        close: 98,
        open: 99,
        high: 99,
        low: 97,
        volume: 11,
        ema20: 100,
        ema50: 102,
        ema200: 109,
        atr14: 2.4,
        atrPercent: 2.4,
        rsi14: 36,
        bbWidth: 0.07,
        ret3: -0.04,
        ret10: -0.06,
      },
    ];

    const enriched = enrichTradesWithMarketContext(trades, bars);

    expect(enriched[0]?.entryContext?.regime).toBe("trend_down");
    expect(enriched[0]?.flags.counterTrendEntry).toBe(true);
    expect(enriched[0]?.flags.weakExit).toBe(true);
  });
});
