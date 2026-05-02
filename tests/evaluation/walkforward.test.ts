import { describe, expect, test } from "vitest";

import {
  buildWalkForwardEvaluationFromFoldMetrics,
  buildWalkForwardWindows,
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

describe("walk-forward promotion gate", () => {
  test("allows one failed fold when four of five OOS folds remain positive and passed", () => {
    const evaluation = buildWalkForwardEvaluationFromFoldMetrics({
      foldMetrics: [
        createFoldMetrics(),
        createFoldMetrics({ postFeeNetProfitPercent: -1, profitFactor: 0.9, avgTradePercent: -0.05 }),
        createFoldMetrics({ profitFactor: 1.5 }),
        createFoldMetrics({ profitFactor: 1.6 }),
        createFoldMetrics({ profitFactor: 1.3 }),
      ],
      foldCount: 5,
      embargoBars: 5,
    });

    expect(evaluation.passed).toBe(true);
    expect(evaluation.positiveOosFoldCount).toBe(4);
    expect(evaluation.totalOosTrades).toBeGreaterThanOrEqual(60);
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
      foldCount: 5,
      embargoBars: 5,
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
});
