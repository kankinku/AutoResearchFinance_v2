import { describe, expect, test } from "vitest";

import {
  buildCriterionDirective,
  buildCriterionOutcome,
} from "../../src/research/autonomous/criterion-analysis-phase.js";
import { type ExperimentRecord, type ObjectiveConfig } from "../../src/contracts/types.js";
import { type CalibrationEventRecord } from "../../src/contracts/autonomous.js";

const objective: ObjectiveConfig = {
  symbol: "QQQ",
  timeframe: "120",
  hardGates: {
    minimumTotalTrades: 50,
    minimumPostFeeNetProfitPercent: 0,
  },
  softGuardrails: {
    maximumStrategyDrawdownPercent: 15,
    softGuardrailPenalty: 0.1,
  },
  weights: {
    netProfitPercent: 1,
    profitFactor: 1,
    inverseMaxDrawdown: 1,
    percentProfitable: 1,
    totalTrades: 1,
    avgTradePercent: 1,
  },
  normalizationCaps: {
    netProfitPercent: 100,
    profitFactor: 5,
    maxStrategyDrawdownPercent: 50,
    percentProfitable: 100,
    totalTrades: 200,
    avgTradePercent: 2,
  },
};

describe("criterion analysis phase", () => {
  test("builds trade-count focused repair guidance from a low-trade candidate", () => {
    const directive = buildCriterionDirective({
      criterion: "trade_count",
      objective,
      calibrationEvents: [],
      problemEvents: [],
      experiments: [
        experiment({
          testerMetrics: { totalTrades: 31 },
          eligibility: {
            blockingReasons: [
              {
                kind: "low_trade_count",
                message: "too few trades",
              },
            ],
          },
        }),
      ],
    });

    expect(directive).toEqual(
      expect.objectContaining({
        criterion: "trade_count",
        metricBefore: 31,
        metricDirection: "increase",
        branchBias: "exploration_breakout",
      }),
    );
    expect(directive.repairPriorities).toContain("recover_trade_count");
    expect(directive.nextMutationDirection).toMatch(/trade_count/i);
  });

  test("auto-selects local TV parity when major drift exceeds matches", () => {
    const directive = buildCriterionDirective({
      objective,
      experiments: [experiment({})],
      problemEvents: [],
      calibrationEvents: [
        calibration("matched"),
        calibration("major_drift"),
        calibration("major_drift"),
      ],
    });

    expect(directive.criterion).toBe("local_tv_parity");
    expect(directive.forbiddenPatterns.join(" ")).toMatch(/major_drift/i);
  });

  test("records criterion outcome directionally", () => {
    const directive = buildCriterionDirective({
      criterion: "drawdown",
      objective,
      calibrationEvents: [],
      problemEvents: [],
      experiments: [
        experiment({
          testerMetrics: { maxStrategyDrawdownPercent: 18 },
        }),
      ],
    });

    expect(
      buildCriterionOutcome({
        directive,
        record: experiment({
          testerMetrics: { maxStrategyDrawdownPercent: 12 },
        }),
      }),
    ).toEqual(
      expect.objectContaining({
        criterionBefore: 18,
        criterionAfter: 12,
        criterionDelta: -6,
        criterionVerdict: "improved",
      }),
    );
  });
});

function experiment(input: {
  testerMetrics?: Partial<NonNullable<ExperimentRecord["testerMetrics"]>>;
  eligibility?: { blockingReasons: Array<{ kind: string; message: string }> };
}): ExperimentRecord {
  return {
    runId: "run",
    iteration: 1,
    candidateId: "cand-test",
    parentCandidateId: null,
    branchId: "branch",
    acceptedHeadCandidateId: null,
    baselineCandidateId: null,
    decision: "local_candidate_rejected",
    status: "rejected",
    testerMetrics: {
      netProfitPercent: 0,
      postFeeNetProfitPercent: 0,
      profitFactor: 1,
      maxStrategyDrawdownPercent: 10,
      percentProfitable: 50,
      totalTrades: 50,
      avgTradePercent: 0,
      ...input.testerMetrics,
    },
    eligibility: input.eligibility,
  } as ExperimentRecord;
}

function calibration(status: "matched" | "major_drift"): CalibrationEventRecord {
  return {
    runId: "run",
    iteration: 1,
    eventKind: "local_tv_divergence_measured",
    candidateId: `cand-${status}`,
    fingerprintFamily: status,
    queueState: "processed",
    parity: {
      status,
      tradeCountDelta: null,
      netProfitPctDelta: null,
      maxDrawdownPctDelta: null,
      profitFactorDelta: null,
      winRateDelta: null,
    },
  } as unknown as CalibrationEventRecord;
}
