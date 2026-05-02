import { describe, expect, test } from "vitest";

import { type BacktestMetrics, type TradeRecord } from "../../src/contracts/types.js";
import { buildLocalTvParity } from "../../src/research/autonomous/divergence-update-phase.js";

function createMetrics(overrides?: Partial<BacktestMetrics>): BacktestMetrics {
  return {
    netProfitPercent: 20,
    postFeeNetProfitPercent: 18,
    profitFactor: 1.5,
    maxStrategyDrawdownPercent: 8,
    percentProfitable: 55,
    totalTrades: 2,
    avgTradePercent: 0.35,
    ...overrides,
  };
}

function createTrades(): TradeRecord[] {
  return [
    {
      entryComment: "B1",
      entryPrice: 100,
      entryTime: "2024-01-01T14:30:00.000Z",
      exitComment: "exit",
      exitPrice: 102,
      exitTime: "2024-01-02T14:30:00.000Z",
      qty: 1,
      profitValue: 2,
      profitPercent: 2,
      runupPercent: 2.5,
      drawdownPercent: 0.5,
    },
    {
      entryComment: "B2",
      entryPrice: 103,
      entryTime: "2024-01-03T14:30:00.000Z",
      exitComment: "exit",
      exitPrice: 101,
      exitTime: "2024-01-04T14:30:00.000Z",
      qty: 1,
      profitValue: -2,
      profitPercent: -1.94,
      runupPercent: 0.5,
      drawdownPercent: 2,
    },
  ];
}

describe("local/TradingView parity", () => {
  test("marks metric and trade parity as matched when trades align", () => {
    const parity = buildLocalTvParity({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localTrades: createTrades(),
      tvTrades: createTrades(),
    });

    expect(parity.status).toBe("matched");
    expect(parity.tradeParity).toMatchObject({
      status: "matched",
      entryTimeMatchRatio: 1,
      exitTimeMatchRatio: 1,
      profitSignMatchRatio: 1,
      orderCountDelta: 0,
    });
  });

  test("promotes trade-level drift to major parity drift", () => {
    const shiftedTrades = createTrades().map((trade, index) => ({
      ...trade,
      entryTime: `2024-02-0${index + 1}T14:30:00.000Z`,
      exitTime: `2024-02-0${index + 2}T14:30:00.000Z`,
      profitValue: -(trade.profitValue ?? 0),
    }));

    const parity = buildLocalTvParity({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localTrades: createTrades(),
      tvTrades: shiftedTrades,
    });

    expect(parity.status).toBe("major_drift");
    expect(parity.tradeParity?.status).toBe("major_drift");
    expect(parity.tradeParity?.entryTimeMatchRatio).toBe(0);
  });
});
