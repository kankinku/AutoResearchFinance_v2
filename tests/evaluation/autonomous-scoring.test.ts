import { describe, expect, test } from "vitest";

import {
  buildVerifiedPromotionScore,
  computeMinimumVerifiedPromotionScore,
} from "../../src/evaluation/autonomous-scoring.js";
import { type BacktestMetrics, type ExperimentRecord } from "../../src/contracts/types.js";
import { type WalkForwardEvaluation } from "../../src/contracts/autonomous.js";

function createMetrics(overrides?: Partial<BacktestMetrics>): BacktestMetrics {
  return {
    netProfitPercent: 32,
    postFeeNetProfitPercent: 30,
    profitFactor: 1.8,
    maxStrategyDrawdownPercent: 9,
    percentProfitable: 58,
    totalTrades: 84,
    avgTradePercent: 0.4,
    ...overrides,
  };
}

function createWalkForwardPass(): WalkForwardEvaluation {
  return {
    policyVersion: "walk-forward-oos/v1",
    foldCount: 5,
    requiredPositiveOosFolds: 4,
    positiveOosFoldCount: 5,
    minimumTradesPerFold: 12,
    minimumTotalOosTrades: 60,
    totalOosTrades: 80,
    worstFoldDrawdownPercent: 10,
    medianOosProfitFactor: 1.4,
    medianOosPostFeeNetProfitPercent: 15,
    embargoBars: 5,
    passed: true,
    gateReasons: [],
    folds: [],
  };
}

function createMatchedParity() {
  return {
    status: "matched" as const,
    tradeCountDelta: 0,
    netProfitPctDelta: 0,
    maxDrawdownPctDelta: 0,
    profitFactorDelta: 0,
    winRateDelta: 0,
    tradeParity: {
      status: "matched" as const,
      entryTimeMatchRatio: 1,
      exitTimeMatchRatio: 1,
      profitSignMatchRatio: 1,
      orderCountDelta: 0,
    },
  };
}

function createReferences(count: number): ExperimentRecord[] {
  return Array.from({ length: count }, (_, index) => ({
    runId: "run-ref",
    iteration: index + 1,
    candidateId: `cand-${index}`,
    parentCandidateId: null,
    branchId: "main",
    acceptedHeadCandidateId: null,
    baselineCandidateId: null,
    candidatePath: `cand-${index}.pine`,
    candidateHash: `hash-${index}`,
    candidateScore: 0.1,
    decision: "local_candidate_eligible",
    status: "evaluated",
  }));
}

describe("verified promotion scoring", () => {
  test("requires walk-forward evidence even when local 70/30 evidence exists elsewhere", () => {
    const result = buildVerifiedPromotionScore({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localCandidateHash: "hash-a",
      tvCandidateHash: "hash-a",
      tvCalibrationStatus: "verified_match",
      localTvParity: createMatchedParity(),
      walkForwardEvaluation: null,
      config: null,
      referenceExperiments: [],
    });

    expect(result.eligible).toBe(false);
    expect(result.score).toBeNull();
    expect(result.rejectionReasons).toContain("walk_forward_missing");
  });

  test("rejects parity drift and candidate hash mismatch", () => {
    const result = buildVerifiedPromotionScore({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics({ totalTrades: 90, postFeeNetProfitPercent: 35 }),
      localCandidateHash: "hash-a",
      tvCandidateHash: "hash-b",
      tvCalibrationStatus: "verified_match",
      localTvParity: {
        status: "major_drift",
        tradeCountDelta: 6,
        netProfitPctDelta: 5,
        maxDrawdownPctDelta: 0,
        profitFactorDelta: 0,
        winRateDelta: 0,
        tradeParity: {
          status: "major_drift",
          entryTimeMatchRatio: 0.5,
          exitTimeMatchRatio: 0.5,
          profitSignMatchRatio: 0.5,
          orderCountDelta: 6,
        },
      },
      walkForwardEvaluation: createWalkForwardPass(),
      config: null,
      referenceExperiments: [],
    });

    expect(result.eligible).toBe(false);
    expect(result.rejectionReasons).toEqual(
      expect.arrayContaining([
        "candidate_hash_mismatch",
        "local_tv_major_drift",
        "parity_trade_count_delta",
        "parity_net_profit_delta",
      ]),
    );
  });

  test("returns an eligible verified score when TV, parity, and walk-forward gates pass", () => {
    const result = buildVerifiedPromotionScore({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localCandidateHash: "hash-a",
      tvCandidateHash: "hash-a",
      tvCalibrationStatus: "verified_match",
      localTvParity: createMatchedParity(),
      walkForwardEvaluation: createWalkForwardPass(),
      config: null,
      referenceExperiments: [],
    });

    expect(result.eligible).toBe(true);
    expect(result.score).toBeGreaterThanOrEqual(0.62);
  });

  test("raises the minimum verified score threshold as trial count grows", () => {
    expect(computeMinimumVerifiedPromotionScore(createReferences(0))).toBe(0.62);
    expect(computeMinimumVerifiedPromotionScore(createReferences(100))).toBe(0.68);
    expect(computeMinimumVerifiedPromotionScore(createReferences(1_000))).toBe(0.74);
  });
});
