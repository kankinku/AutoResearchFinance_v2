import { describe, expect, test } from "vitest";

import {
  attemptLocalRuntimeRecovery,
  classifyLocalRuntimeFailure,
  summarizeLocalTvParity,
} from "../../src/research/verification-fallback.js";
import { type PineEvaluationExecutor } from "../../src/automation/common/executor.js";

function createRecoveryExecutor(input: {
  onPrepareChart?: () => Promise<void> | void;
  onRecoverSurface?: (action: string) => Promise<void> | void;
}): PineEvaluationExecutor {
  return {
    role: "primary_local_backtest",
    evidenceAuthority: "local_model",
    supportedStrategyFamilies: ["AF"],
    supportedSymbols: ["QQQ"],
    supportedTimeframes: ["120"],
    getCapability() {
      return {
        kind: "local-af-backtest",
        authoritative: true,
        supportedSymbols: ["QQQ"],
        supportedTimeframes: ["120"],
        supportedStrategyFamilies: ["AF"],
        confidenceLevel: "verification",
      };
    },
    async healthCheck() {
      return {
        healthy: true,
        status: "ready",
        detail: null,
      };
    },
    async prepareChart() {
      await input.onPrepareChart?.();
    },
    async updateStrategySource() {
      return;
    },
    async compileStrategy() {
      return { ok: true, errors: [] };
    },
    async applyStrategy() {
      return { ok: true, message: "ok", fallbackActions: [] };
    },
    async readArtifactBundle() {
      return {
        strategy: null,
        trades: [],
        equity: {
          available: false,
          unavailableReason: "test",
          pointsAvailable: false,
          pointCount: 0,
          finalEquity: null,
          maxDrawdownPercent: null,
          points: [],
        },
        rawReportHash: null,
        state: {},
      };
    },
    async recoverSurface(recoveryInput) {
      await input.onRecoverSurface?.(recoveryInput.action);
    },
  };
}

describe("verification fallback helpers", () => {
  test("classifies explicit Pine source loading timeouts as local runtime failures", () => {
    expect(
      classifyLocalRuntimeFailure(
        new Error(
          "Pine source panel open timeout after 15000ms while loading the local runtime.",
        ),
      ),
    ).toBe("pine_editor_open_timeout");
    expect(
      classifyLocalRuntimeFailure(
        new Error(
          "Monaco editor attach timeout: Monaco editor ready timed out after 15000ms.",
        ),
      ),
    ).toBe("monaco_attach_timeout");
    expect(
      classifyLocalRuntimeFailure(
        new Error(
          "Local runtime prepareChart timed out after 30000ms.",
        ),
      ),
    ).toBe("chart_load_timeout");
    expect(
      classifyLocalRuntimeFailure(
        new Error("Active chart widget is not available."),
      ),
    ).toBe("chart_load_timeout");
  });

  test("uses executor-specific recoverSurface action when available", async () => {
    const observedActions: string[] = [];

    const result = await attemptLocalRuntimeRecovery({
      executorFactory: () =>
        createRecoveryExecutor({
          onRecoverSurface: async (action) => {
            observedActions.push(action);
          },
        }),
      chartTarget: {
        symbol: "QQQ",
        timeframe: "120",
        chartType: "candles",
      },
      failureKind: "monaco_attach_timeout",
      attempt: 1,
    });

    expect(result.recovered).toBe(true);
    expect(result.recoveryAttempt.action).toBe("reattach_monaco");
    expect(observedActions).toEqual(["reattach_monaco"]);
  });

  test("falls back to prepareChart when executor-specific recovery is unavailable", async () => {
    let prepareChartCalls = 0;

    const result = await attemptLocalRuntimeRecovery({
      executorFactory: () => ({
        ...createRecoveryExecutor({
          onPrepareChart: async () => {
            prepareChartCalls += 1;
          },
        }),
        recoverSurface: undefined,
      }),
      chartTarget: {
        symbol: "QQQ",
        timeframe: "120",
        chartType: "candles",
      },
      failureKind: "chart_load_timeout",
      attempt: 1,
    });

    expect(result.recovered).toBe(true);
    expect(result.recoveryAttempt.action).toBe("soft_reload_chart");
    expect(prepareChartCalls).toBe(1);
  });

  test("computes local vs authoritative parity deltas once verification later succeeds", () => {
    const parity = summarizeLocalTvParity({
      fallbackEvaluation: {
        role: "fallback_evidence",
        executorKind: "local-af-screening",
        executorAuthoritative: false,
        promotionEligible: false,
        status: "succeeded",
        reason: "local_fallback_completed",
        artifactId: "fallback-1",
        artifactHash: "hash-1",
        metrics: {
          netProfitPercent: 10,
          postFeeNetProfitPercent: 8,
          profitFactor: 1.5,
          maxStrategyDrawdownPercent: 9,
          percentProfitable: 55,
          totalTrades: 60,
          avgTradePercent: 0.25,
        },
        objectiveBreakdown: null,
        artifactValidation: null,
        decisionIfScreeningOnly: "screening_improvement",
        compatibility: {
          symbol: "QQQ",
          timeframe: "120",
          strategyFamily: "AF",
          compatible: true,
          reasons: [],
        },
        evidenceUse: "mutation_context_only",
        confidence: "very_low",
        caveats: [],
        parity: {
          status: "not_comparable",
          tradeCountDelta: null,
          netProfitPctDelta: null,
          maxDrawdownPctDelta: null,
          profitFactorDelta: null,
          winRateDelta: null,
        },
      },
      authoritativeMetrics: {
        netProfitPercent: 11,
        postFeeNetProfitPercent: 9,
        profitFactor: 1.58,
        maxStrategyDrawdownPercent: 10,
        percentProfitable: 57,
        totalTrades: 61,
        avgTradePercent: 0.27,
      },
    });

    expect(parity.status).toBe("matched");
    expect(parity.tradeCountDelta).toBe(1);
    expect(parity.netProfitPctDelta).toBe(1);
    expect(parity.maxDrawdownPctDelta).toBe(1);
    expect(parity.profitFactorDelta).toBeCloseTo(0.08, 6);
    expect(parity.winRateDelta).toBe(2);
  });
});
