import {
  type EnrichedTradeRecord,
  type MarketContextBar,
  type TradeRecord,
} from "../contracts/types.js";

function findNearestBar(
  timestamp: string | null,
  bars: MarketContextBar[],
): MarketContextBar | null {
  if (!timestamp || bars.length === 0) {
    return null;
  }

  const target = Date.parse(timestamp);
  if (Number.isNaN(target)) {
    return null;
  }

  let best: MarketContextBar | null = null;
  let bestDelta = Number.POSITIVE_INFINITY;
  for (const bar of bars) {
    const current = Date.parse(bar.time);
    if (Number.isNaN(current)) {
      continue;
    }
    const delta = Math.abs(current - target);
    if (delta < bestDelta) {
      best = bar;
      bestDelta = delta;
    }
  }
  return best;
}

export function enrichTradesWithMarketContext(
  trades: TradeRecord[],
  bars: MarketContextBar[],
): EnrichedTradeRecord[] {
  return trades.map((trade) => {
    const entryContext = findNearestBar(trade.entryTime, bars);
    const exitContext = findNearestBar(trade.exitTime, bars);

    return {
      ...trade,
      entryContext,
      exitContext,
      flags: {
        counterTrendEntry: Boolean(entryContext) && entryContext?.regime === "trend_down",
        overextendedEntry:
          Boolean(entryContext?.ema20) &&
          Boolean(trade.entryPrice) &&
          (trade.entryPrice as number) > (entryContext?.ema20 as number) * 1.03,
        lateEntry:
          (entryContext?.ret3 ?? 0) > 0.03 ||
          (entryContext?.rsi14 ?? 0) > 65,
        weakExit:
          (trade.profitPercent ?? 0) < 0 &&
          ((trade.drawdownPercent ?? 0) > 1 || exitContext?.regime === "trend_down"),
      },
    };
  });
}
