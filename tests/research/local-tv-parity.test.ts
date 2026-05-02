import { describe, expect, test } from "vitest";

import {
  type BacktestMetrics,
  type TraceEventV1,
  type TradeRecord,
} from "../../src/contracts/types.js";
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

function createTrace(): TraceEventV1[] {
  return [
    {
      barIndex: 10,
      time: "2024-01-01T14:30:00.000Z",
      orderAction: "entry",
      finalBullEvent: 1,
      finalBearEvent: 0,
      entryPass: true,
      entryRank: 1,
      exitReason: null,
      slotCount: 1,
    },
    {
      barIndex: 20,
      time: "2024-01-02T14:30:00.000Z",
      orderAction: "exit",
      finalBullEvent: 0,
      finalBearEvent: 1,
      entryPass: false,
      entryRank: 0,
      exitReason: "exit",
      slotCount: 0,
    },
  ];
}

describe("local/TradingView parity", () => {
  test("marks metric, trade, and trace parity as matched when evidence aligns", () => {
    const parity = buildLocalTvParity({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localTrades: createTrades(),
      tvTrades: createTrades(),
      localEventTrace: createTrace(),
      tvEventTrace: createTrace(),
    });

    expect(parity.status).toBe("matched");
    expect(parity.tradeParity).toMatchObject({
      status: "matched",
      entryTimeMatchRatio: 1,
      exitTimeMatchRatio: 1,
      profitSignMatchRatio: 1,
      orderCountDelta: 0,
    });
    expect(parity.eventParity).toMatchObject({
      status: "matched",
      eventMatchRatio: 1,
      entryPassMatchRatio: 1,
      exitReasonMatchRatio: 1,
    });
  });

  test("treats metric-only parity as not comparable when AFTRACE evidence is missing", () => {
    const parity = buildLocalTvParity({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localTrades: createTrades(),
      tvTrades: createTrades(),
    });

    expect(parity.status).toBe("not_comparable");
    expect(parity.tradeParity?.status).toBe("matched");
    expect(parity.eventParity?.status).toBe("not_comparable");
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
      localEventTrace: createTrace(),
      tvEventTrace: createTrace(),
    });

    expect(parity.status).toBe("major_drift");
    expect(parity.tradeParity?.status).toBe("major_drift");
    expect(parity.tradeParity?.entryTimeMatchRatio).toBe(0);
  });

  test("promotes trace-level drift to major parity drift", () => {
    const driftedTrace = createTrace().map((event, index) => ({
      ...event,
      finalBullEvent: index === 0 ? 0 : event.finalBullEvent,
      entryPass: false,
      exitReason: index === 1 ? "late_exit" : event.exitReason,
    }));

    const parity = buildLocalTvParity({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localTrades: createTrades(),
      tvTrades: createTrades(),
      localEventTrace: createTrace(),
      tvEventTrace: driftedTrace,
    });

    expect(parity.status).toBe("major_drift");
    expect(parity.eventParity?.status).toBe("major_drift");
    expect(parity.eventParity?.entryPassMatchRatio).toBe(0.5);
  });
});
