import { describe, expect, test } from "vitest";

import {
  extractBacktestMetricsFromReportData,
  extractEquitySummaryFromReportData,
  extractTradeRecordsFromReportData,
  inspectReportData,
  normalizeAttachedStudyTitle,
} from "../../src/automation/tradingview/report-data.js";

describe("report-data", () => {
  test("maps TradingView strategy report data into AF metrics", () => {
    const metrics = extractBacktestMetricsFromReportData({
      performance: {
        all: {
          netProfitPercent: 0.1234,
          profitFactor: 1.87,
          percentProfitable: 0.56,
          avgTradePercent: 0.0045,
        },
        maxStrategyDrawDownPercent: 0.091,
        sharpeRatio: 1.2,
        sortinoRatio: 1.6,
      },
      trades: [{}, {}, {}],
    });

    expect(metrics).toEqual({
      netProfitPercent: 12.34,
      postFeeNetProfitPercent: 12.34,
      profitFactor: 1.87,
      maxStrategyDrawdownPercent: 9.1,
      percentProfitable: 56,
      totalTrades: 3,
      avgTradePercent: 0.45,
    });
  });

  test("maps TradingView trade payloads into AF trade records", () => {
    const trades = extractTradeRecordsFromReportData(
      {
        trades: [
          {
            e: {
              c: "Long",
              p: 100,
              tm: Date.parse("2026-04-20T00:00:00.000Z"),
            },
            x: {
              c: "Exit",
              p: 104,
              tm: Date.parse("2026-04-20T02:00:00.000Z"),
            },
            q: 2,
            cp: {
              v: 8,
              p: 0.04,
            },
            rn: {
              v: 10,
              p: 0.05,
            },
            dd: {
              v: 2,
              p: 0.01,
            },
          },
        ],
      },
      50,
    );

    expect(trades).toHaveLength(1);
    expect(trades[0]).toEqual({
      entryComment: "Long",
      entryPrice: 100,
      entryTime: "2026-04-20T00:00:00.000Z",
      exitComment: "Exit",
      exitPrice: 104,
      exitTime: "2026-04-20T02:00:00.000Z",
      qty: 2,
      profitValue: 8,
      profitPercent: 4,
      runupPercent: 5,
      drawdownPercent: 1,
    });
  });

  test("normalizes attached study titles by removing parameter suffixes", () => {
    expect(normalizeAttachedStudyTitle("AF Candidate [cand-1] (21, 55, 14, false)")).toBe(
      "AF Candidate [cand-1]",
    );
    expect(normalizeAttachedStudyTitle("AF Candidate [cand-1]")).toBe(
      "AF Candidate [cand-1]",
    );
  });

  test("inspects TradingView report completeness and parser warnings", () => {
    const inspection = inspectReportData({
      performance: {
        all: {
          netProfitPercent: 0.12,
          profitFactor: 1.8,
          percentProfitable: 0.55,
          avgTradePercent: 0.003,
        },
        maxStrategyDrawDownPercent: 0.08,
      },
      trades: [{}, {}],
    });

    expect(inspection.hasNetProfit).toBe(true);
    expect(inspection.hasTotalTrades).toBe(true);
    expect(inspection.hasEquitySummary).toBe(false);
    expect(inspection.missingFields).toContain("equity_summary");
    expect(inspection.parseWarnings).toContain("report.equity_summary_missing");
    expect(inspection.parserVersion).toContain("tradingview-report");
  });

  test("extracts equity summary from TradingView report arrays", () => {
    const summary = extractEquitySummaryFromReportData({
      buyHold: [10000, 10200, 9900, 10500],
      buyHoldPercent: [0, 0.02, -0.01, 0.05],
    });

    expect(summary.available).toBe(true);
    expect(summary.pointsAvailable).toBe(true);
    expect(summary.pointCount).toBe(4);
    expect(summary.finalEquity).toBe(10500);
    expect(summary.maxDrawdownPercent).toBe(2.941176);
    expect(summary.points).toHaveLength(4);
  });

  test("records an explicit reason when equity data is unavailable", () => {
    const summary = extractEquitySummaryFromReportData({
      trades: [{}],
    });

    expect(summary.available).toBe(false);
    expect((summary as { unavailableReason?: string | null }).unavailableReason).toBe(
      "equity_table_not_found",
    );
  });
});
