import { describe, expect, test } from "vitest";

import { LocalExecutionLedger } from "../../src/automation/local-backtest/execution.js";

describe("LocalExecutionLedger", () => {
  test("records golden entry/exit cash, commission, realized PnL, and equity", () => {
    const ledger = new LocalExecutionLedger({
      initialCapital: 100_000,
      commissionPercent: 0.1,
      processOrdersOnClose: true,
    });

    const entry = ledger.enterSlot({
      close: 100,
      high: 101,
      low: 99,
      qty: 10,
      rank: 1,
      barIndex: 0,
      time: "2024-01-01T14:30:00.000Z",
      nextSlotNo: 1,
      reason: "entry",
    });
    ledger.updateSlotExtremes(112, 98);
    const exit = ledger.closeSlot(0, {
      close: 110,
      barIndex: 1,
      time: "2024-01-02T14:30:00.000Z",
      reason: "manual_exit",
    });
    const snapshot = ledger.recordPortfolioSnapshot({
      barIndex: 1,
      time: "2024-01-02T14:30:00.000Z",
      markPrice: 110,
      orderIds: [entry.order.orderId, exit.order.orderId],
      fillIds: [entry.fill.fillId, exit.fill.fillId],
    });

    expect(entry.fill.cost).toMatchObject({
      commissionPercent: 0.1,
      commission: 1,
      grossValue: 1_000,
      netCashChange: -1_001,
    });
    expect(exit.fill.cost).toMatchObject({
      commissionPercent: 0.1,
      commission: 1.1,
      grossValue: 1_100,
      netCashChange: 1_098.9,
    });
    expect(ledger.cash).toBeCloseTo(100_097.9, 6);
    expect(ledger.trades).toHaveLength(1);
    expect(ledger.trades[0]).toMatchObject({
      entryComment: "L_1",
      entryPrice: 100,
      exitPrice: 110,
      qty: 10,
      profitValue: 97.9,
      runupPercent: 12,
      drawdownPercent: 2,
    });
    expect(snapshot).toMatchObject({
      cash: 100_097.9,
      positionValue: 0,
      equity: 100_097.9,
      openSlotCount: 0,
      realizedPnl: 97.9,
    });
  });

  test("records replacement as sell fill before same-bar buy fill", () => {
    const ledger = new LocalExecutionLedger({
      initialCapital: 10_000,
      commissionPercent: 0,
      processOrdersOnClose: true,
    });

    ledger.enterSlot({
      close: 100,
      high: 100,
      low: 100,
      qty: 1,
      rank: 1,
      barIndex: 0,
      time: "2024-01-01T14:30:00.000Z",
      nextSlotNo: 1,
      reason: "entry",
    });
    const replacementExit = ledger.closeSlot(0, {
      close: 95,
      barIndex: 1,
      time: "2024-01-02T14:30:00.000Z",
      reason: "replacement_exit",
    });
    const replacementEntry = ledger.enterSlot({
      close: 95,
      high: 96,
      low: 94,
      qty: 1,
      rank: 3,
      barIndex: 1,
      time: "2024-01-02T14:30:00.000Z",
      nextSlotNo: 2,
      reason: "replacement_entry",
    });

    expect(replacementExit.order.side).toBe("sell");
    expect(replacementEntry.order.side).toBe("buy");
    expect(ledger.getExecutionTrace().map((entry) => entry.reason)).toEqual([
      "entry",
      "replacement_exit",
      "replacement_entry",
    ]);
    expect(ledger.getExecutionTrace().slice(1).map((entry) => entry.barIndex)).toEqual([1, 1]);
  });

  test("final close drains all open slots and links snapshot ids to fills", () => {
    const ledger = new LocalExecutionLedger({
      initialCapital: 10_000,
      commissionPercent: 0,
      processOrdersOnClose: true,
    });

    ledger.enterSlot({
      close: 100,
      high: 100,
      low: 100,
      qty: 1,
      rank: 1,
      barIndex: 0,
      time: "2024-01-01T14:30:00.000Z",
      nextSlotNo: 1,
      reason: "entry",
    });
    ledger.enterSlot({
      close: 110,
      high: 110,
      low: 110,
      qty: 1,
      rank: 2,
      barIndex: 1,
      time: "2024-01-02T14:30:00.000Z",
      nextSlotNo: 2,
      reason: "entry",
    });

    const finalClose = ledger.closeAllOpenSlots({
      close: 120,
      barIndex: 2,
      time: "2024-01-03T14:30:00.000Z",
      reason: "final_close",
    });
    const snapshot = ledger.recordPortfolioSnapshot({
      barIndex: 2,
      time: "2024-01-03T14:30:00.000Z",
      markPrice: 120,
      orderIds: finalClose.map((entry) => entry.order.orderId),
      fillIds: finalClose.map((entry) => entry.fill.fillId),
    });

    expect(finalClose).toHaveLength(2);
    expect(finalClose.map((entry) => entry.fill.side)).toEqual(["sell", "sell"]);
    expect(ledger.slots).toHaveLength(0);
    expect(ledger.trades).toHaveLength(2);
    expect(snapshot.openSlotCount).toBe(0);
    expect(snapshot.orderIds).toHaveLength(2);
    expect(snapshot.fillIds).toHaveLength(2);
  });
});
