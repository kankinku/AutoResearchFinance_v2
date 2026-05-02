import { describe, expect, test } from "vitest";

import { buildConditionFoldImpact } from "../../src/evaluation/af-condition-attribution.js";
import {
  DEFAULT_WALK_FORWARD_POLICY,
  buildWalkForwardEvaluationFromFoldMetrics,
} from "../../src/evaluation/walkforward.js";
import { type BacktestMetrics } from "../../src/contracts/types.js";

function foldMetrics(overrides?: Partial<BacktestMetrics>): BacktestMetrics {
  return {
    netProfitPercent: 7,
    postFeeNetProfitPercent: 5,
    profitFactor: 1.35,
    maxStrategyDrawdownPercent: 8,
    percentProfitable: 55,
    totalTrades: 14,
    avgTradePercent: 0.25,
    ...overrides,
  };
}

describe("AF condition attribution", () => {
  test("derives oosFoldDelta from actual walk-forward fold outcomes", () => {
    const policy = {
      ...DEFAULT_WALK_FORWARD_POLICY,
      minimumCoverageDays: 0,
      canaryHoldout: {
        ...DEFAULT_WALK_FORWARD_POLICY.canaryHoldout,
        exposed: false,
      },
    };
    const baseEvaluation = buildWalkForwardEvaluationFromFoldMetrics({
      foldMetrics: [
        foldMetrics(),
        foldMetrics(),
        foldMetrics(),
        foldMetrics(),
        foldMetrics(),
      ],
      policy,
    });
    const ablatedEvaluation = buildWalkForwardEvaluationFromFoldMetrics({
      foldMetrics: [
        foldMetrics(),
        foldMetrics({ postFeeNetProfitPercent: -1, avgTradePercent: -0.05 }),
        foldMetrics(),
        foldMetrics({ totalTrades: 4 }),
        foldMetrics(),
      ],
      policy,
    });

    const impact = buildConditionFoldImpact({
      baseEvaluation,
      ablatedEvaluation,
    });

    expect(impact.oosFoldDelta).toBe(2);
    expect(impact.failedFoldImpact).toEqual(
      expect.objectContaining({
        baseFailedFoldCount: 0,
        ablatedFailedFoldCount: 2,
        changedFoldIds: ["wf-2", "wf-4"],
      }),
    );
    expect(impact.failedFoldImpact.summary).toContain("condition_removal_changed_folds");
  });
});
