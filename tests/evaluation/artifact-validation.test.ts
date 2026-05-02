import { describe, expect, test } from "vitest";

import {
  type ArtifactBundle,
  type ExecutorCapability,
} from "../../src/contracts/types.js";
import {
  isArtifactPromotionReady,
  isArtifactVerificationReady,
  validateArtifactBundle,
} from "../../src/evaluation/artifact-validation.js";
import { derivePromotionReadiness } from "../../src/evaluation/decision.js";

const tradingViewCapability: ExecutorCapability = {
  kind: "tradingview-live",
  authoritative: true,
  supportedSymbols: ["QQQ"],
  supportedTimeframes: ["120m"],
  supportedStrategyFamilies: ["Pine"],
  confidenceLevel: "verification",
};

function createArtifactBundle(
  overrides: Partial<ArtifactBundle> = {},
): ArtifactBundle {
  return {
    strategy: {
      netProfitPercent: 12,
      postFeeNetProfitPercent: 10,
      profitFactor: 1.8,
      maxStrategyDrawdownPercent: 8,
      percentProfitable: 55,
      totalTrades: 42,
      avgTradePercent: 0.3,
    },
    trades: [],
    equity: {
      available: false,
      unavailableReason: null,
      pointsAvailable: false,
      pointCount: 0,
      finalEquity: null,
      maxDrawdownPercent: null,
      points: [],
    },
    rawReportHash: "report-hash",
    state: {
      reportDiagnostics: {
        hasNetProfit: true,
        hasTotalTrades: true,
        hasMaxDrawdown: true,
        hasProfitFactor: true,
        hasWinRate: true,
        hasTrades: true,
        hasEquitySummary: false,
        hasRawReport: true,
        missingFields: ["equity_summary"],
        parseWarnings: ["report.equity_summary_missing"],
        parserVersion: "tradingview-report/v2",
      },
    },
    ...overrides,
  };
}

describe("artifact validation", () => {
  test("passes authoritative verification with core metrics and raw report hash", () => {
    const validation = validateArtifactBundle({
      artifactBundle: createArtifactBundle(),
      executorCapability: tradingViewCapability,
    });

    expect(validation.hasNetProfit).toBe(true);
    expect(validation.hasTotalTrades).toBe(true);
    expect(validation.hasMaxDrawdown).toBe(true);
    expect(validation.hasProfitFactor).toBe(true);
    expect(validation.hasWinRate).toBe(true);
    expect(validation.hasRawReport).toBe(true);
    expect(validation.hasEquitySummary).toBe(false);
    expect(isArtifactVerificationReady(validation)).toBe(true);
    expect(isArtifactPromotionReady(validation)).toBe(false);
    expect(
      derivePromotionReadiness({
        decision: "verified_improvement",
        artifactValidation: validation,
      }),
    ).toBe(false);
  });

  test("marks artifacts incomplete when a required TradingView metric is missing", () => {
    const validation = validateArtifactBundle({
      artifactBundle: createArtifactBundle({
        state: {
          reportDiagnostics: {
            hasNetProfit: true,
            hasTotalTrades: false,
            hasMaxDrawdown: true,
            hasProfitFactor: true,
            hasWinRate: true,
            hasTrades: false,
            hasEquitySummary: false,
            hasRawReport: true,
            missingFields: ["total_trades", "trades", "equity_summary"],
            parseWarnings: ["report.trade_list_missing", "report.equity_summary_missing"],
            parserVersion: "tradingview-report/v2",
          },
        },
      }),
      executorCapability: tradingViewCapability,
    });

    expect(validation.hasTotalTrades).toBe(false);
    expect(validation.missingFields).toContain("total_trades");
    expect(isArtifactVerificationReady(validation)).toBe(false);
    expect(isArtifactPromotionReady(validation)).toBe(false);
  });

  test("allows verified artifacts that are not promotion-ready when trade coverage is missing", () => {
    const validation = validateArtifactBundle({
      artifactBundle: createArtifactBundle({
        state: {
          reportDiagnostics: {
            hasNetProfit: true,
            hasTotalTrades: true,
            hasMaxDrawdown: true,
            hasProfitFactor: true,
            hasWinRate: true,
            hasTrades: false,
            hasEquitySummary: false,
            hasRawReport: true,
            missingFields: ["trades", "equity_summary"],
            parseWarnings: ["report.trade_list_missing", "report.equity_summary_missing"],
            parserVersion: "tradingview-report/v2",
          },
        },
      }),
      executorCapability: tradingViewCapability,
    });

    expect(isArtifactVerificationReady(validation)).toBe(true);
    expect(isArtifactPromotionReady(validation)).toBe(false);
  });
});
