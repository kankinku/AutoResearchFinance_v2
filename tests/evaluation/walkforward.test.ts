import { describe, expect, test } from "vitest";

import {
  DEFAULT_WALK_FORWARD_POLICY,
  buildWalkForwardEvaluationFromFoldMetrics,
  buildRollingWalkForwardWindows,
  buildWalkForwardWindows,
  loadWalkForwardPolicy,
} from "../../src/evaluation/walkforward.js";
import { type BacktestMetrics } from "../../src/contracts/types.js";

function createFoldMetrics(overrides?: Partial<BacktestMetrics>): BacktestMetrics {
  return {
    netProfitPercent: 8,
    postFeeNetProfitPercent: 6,
    profitFactor: 1.4,
    maxStrategyDrawdownPercent: 9,
    percentProfitable: 56,
    totalTrades: 13,
    avgTradePercent: 0.32,
    ...overrides,
  };
}

function createPolicy(overrides?: Partial<typeof DEFAULT_WALK_FORWARD_POLICY>) {
  return {
    ...DEFAULT_WALK_FORWARD_POLICY,
    minimumCoverageDays: 730,
    ...overrides,
    canaryHoldout: {
      ...DEFAULT_WALK_FORWARD_POLICY.canaryHoldout,
      ...(overrides?.canaryHoldout ?? {}),
    },
  };
}

function coverage(days = 800) {
  return {
    coverageDays: days,
    coverageStartTime: "2023-05-25T00:00:00.000Z",
    coverageEndTime: new Date(Date.parse("2023-05-25T00:00:00.000Z") + days * 86_400_000).toISOString(),
  };
}

function bars(count: number, start = "2023-05-25T00:00:00.000Z") {
  const startMs = Date.parse(start);
  return Array.from({ length: count }, (_, index) => ({
    time: new Date(startMs + index * 2 * 60 * 60 * 1000).toISOString(),
    open: 100 + index * 0.01,
    high: 101 + index * 0.01,
    low: 99 + index * 0.01,
    close: 100 + index * 0.02,
    volume: 1000,
  }));
}

describe("walk-forward promotion gate", () => {
  test("loads the QQQ 120m walk-forward policy from config", async () => {
    const policy = await loadWalkForwardPolicy(process.cwd());

    expect(policy).toMatchObject({
      policyVersion: "walk-forward-oos/v1",
      foldCount: 5,
      embargoBars: 5,
      minimumCoverageDays: 730,
      canaryHoldout: {
        mode: "sealed",
        exposed: false,
      },
    });
  });

  test("allows one failed fold when four of five OOS folds remain positive and passed", () => {
    const evaluation = buildWalkForwardEvaluationFromFoldMetrics({
      foldMetrics: [
        createFoldMetrics(),
        createFoldMetrics({ postFeeNetProfitPercent: -1, profitFactor: 0.9, avgTradePercent: -0.05 }),
        createFoldMetrics({ profitFactor: 1.5 }),
        createFoldMetrics({ profitFactor: 1.6 }),
        createFoldMetrics({ profitFactor: 1.3 }),
      ],
      policy: createPolicy(),
      coverage: coverage(),
    });

    expect(evaluation.passed).toBe(true);
    expect(evaluation.positiveOosFoldCount).toBe(4);
    expect(evaluation.totalOosTrades).toBeGreaterThanOrEqual(60);
    expect(evaluation.coverageDays).toBe(800);
    expect(evaluation.canaryHoldout).toMatchObject({
      policyVersion: "canary-holdout/v1",
      mode: "sealed",
      exposed: false,
    });
  });

  test("rejects two failed folds", () => {
    const evaluation = buildWalkForwardEvaluationFromFoldMetrics({
      foldMetrics: [
        createFoldMetrics(),
        createFoldMetrics({ postFeeNetProfitPercent: -1, profitFactor: 0.9, avgTradePercent: -0.05 }),
        createFoldMetrics({ postFeeNetProfitPercent: -2, profitFactor: 0.8, avgTradePercent: -0.07 }),
        createFoldMetrics({ profitFactor: 1.6 }),
        createFoldMetrics({ profitFactor: 1.3 }),
      ],
      policy: createPolicy(),
      coverage: coverage(),
    });

    expect(evaluation.passed).toBe(false);
    expect(evaluation.gateReasons).toContain("positive_oos_fold_count");
    expect(evaluation.gateReasons).toContain("passed_oos_fold_count");
  });

  test("keeps embargo bars between train and test windows", () => {
    const windows = buildWalkForwardWindows({
      barCount: 600,
      foldCount: 5,
      embargoBars: 5,
    });

    expect(windows).toHaveLength(5);
    for (const window of windows) {
      expect(window.trainEnd + 5).toBeLessThanOrEqual(window.testStart);
    }
  });

  test("builds rolling chronological windows from available bar times", () => {
    const windows = buildRollingWalkForwardWindows({
      bars: bars(900),
      foldCount: 5,
      embargoBars: 5,
    });

    expect(windows).toHaveLength(5);
    for (const window of windows) {
      expect(window.trainEnd + 5).toBeLessThanOrEqual(window.testStart);
      expect(window.testStart).toBeLessThan(window.testEnd);
    }
  });

  test("rejects insufficient historical coverage", () => {
    const evaluation = buildWalkForwardEvaluationFromFoldMetrics({
      foldMetrics: [
        createFoldMetrics(),
        createFoldMetrics(),
        createFoldMetrics(),
        createFoldMetrics(),
        createFoldMetrics(),
      ],
      policy: createPolicy(),
      coverage: coverage(120),
    });

    expect(evaluation.passed).toBe(false);
    expect(evaluation.gateReasons).toContain("insufficient_historical_coverage");
  });

  test("rejects exposed canary holdout evidence", () => {
    const evaluation = buildWalkForwardEvaluationFromFoldMetrics({
      foldMetrics: [
        createFoldMetrics(),
        createFoldMetrics(),
        createFoldMetrics(),
        createFoldMetrics(),
        createFoldMetrics(),
      ],
      policy: createPolicy({
        canaryHoldout: {
          ...DEFAULT_WALK_FORWARD_POLICY.canaryHoldout,
          exposed: true,
          reason: "test exposure",
        },
      }),
      coverage: coverage(),
    });

    expect(evaluation.passed).toBe(false);
    expect(evaluation.gateReasons).toContain("canary_holdout_exposed");
  });

  test("attaches regime summaries and failed fold regime evidence", () => {
    const evaluation = buildWalkForwardEvaluationFromFoldMetrics({
      foldMetrics: [
        createFoldMetrics(),
        createFoldMetrics({ postFeeNetProfitPercent: -2, avgTradePercent: -0.1 }),
        createFoldMetrics(),
        createFoldMetrics(),
        createFoldMetrics(),
      ],
      foldMetadata: [
        { regimeSummary: { totalBars: 10, counts: { trend_up: 10 }, dominantRegime: "trend_up", concentration: 1 } },
        {
          gateReasons: ["positive_fold_post_fee_profit"],
          regimeSummary: { totalBars: 10, counts: { volatile: 8, range: 2 }, dominantRegime: "volatile", concentration: 0.8 },
        },
      ],
      policy: createPolicy(),
      coverage: coverage(),
      regimeSummary: {
        totalBars: 50,
        counts: { trend_up: 40, volatile: 10 },
        dominantRegime: "trend_up",
        concentration: 0.8,
      },
    });

    expect(evaluation.regimeSummary?.dominantRegime).toBe("trend_up");
    expect(evaluation.failedFoldRegimeSummary).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          foldId: "wf-2",
          dominantRegime: "volatile",
        }),
      ]),
    );
  });
});
