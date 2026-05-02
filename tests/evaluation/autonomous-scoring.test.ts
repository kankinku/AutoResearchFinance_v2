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
    minimumCoverageDays: 730,
    coverageDays: 800,
    coverageStartTime: "2023-05-25T00:00:00.000Z",
    coverageEndTime: "2025-08-02T00:00:00.000Z",
    passed: true,
    gateReasons: [],
    failedFoldRegimeSummary: [],
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
    eventParity: {
      status: "matched" as const,
      eventMatchRatio: 1,
      entryPassMatchRatio: 1,
      exitReasonMatchRatio: 1,
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
        eventParity: {
          status: "major_drift",
          eventMatchRatio: 0.5,
          entryPassMatchRatio: 0.5,
          exitReasonMatchRatio: 0.5,
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
        "trace_parity_major_drift",
      ]),
    );
  });

  test("rejects metric-only parity when trace evidence is not comparable", () => {
    const result = buildVerifiedPromotionScore({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localCandidateHash: "hash-a",
      tvCandidateHash: "hash-a",
      tvCalibrationStatus: "verified_match",
      localTvParity: {
        ...createMatchedParity(),
        status: "not_comparable",
        eventParity: {
          status: "not_comparable",
          eventMatchRatio: null,
          entryPassMatchRatio: null,
          exitReasonMatchRatio: null,
        },
      },
      walkForwardEvaluation: createWalkForwardPass(),
      config: null,
      referenceExperiments: [],
    });

    expect(result.eligible).toBe(false);
    expect(result.rejectionReasons).toContain("parity_not_comparable");
    expect(result.rejectionReasons).toContain("trace_parity_not_comparable");
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
      structureFamilyHash: "family-a",
      fingerprintFamily: "fp-a",
      parameterNeighborhood: "neighborhood-a",
    });

    expect(result.eligible).toBe(true);
    expect(result.score).toBeGreaterThanOrEqual(0.62);
    expect(result.structureFamilyHash).toBe("family-a");
    expect(result.fingerprintFamily).toBe("fp-a");
    expect(result.parameterNeighborhood).toBe("neighborhood-a");
    expect(result.trialLedgerStats?.parameterNeighborhoodTrials).toBe(0);
  });

  test("rejects promotion when sealed canary evidence has been exposed", () => {
    const result = buildVerifiedPromotionScore({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localCandidateHash: "hash-a",
      tvCandidateHash: "hash-a",
      tvCalibrationStatus: "verified_match",
      localTvParity: createMatchedParity(),
      walkForwardEvaluation: {
        ...createWalkForwardPass(),
        canaryHoldout: {
          policyVersion: "canary-holdout/v1",
          mode: "manual_review_only",
          exposed: true,
          reason: "test exposure",
        },
      },
      config: null,
      referenceExperiments: [],
    });

    expect(result.eligible).toBe(false);
    expect(result.rejectionReasons).toContain("canary_holdout_exposed");
  });

  test("raises the minimum verified score threshold as trial count grows", () => {
    expect(computeMinimumVerifiedPromotionScore(createReferences(0))).toBe(0.62);
    expect(computeMinimumVerifiedPromotionScore(createReferences(100))).toBe(0.68);
    expect(computeMinimumVerifiedPromotionScore(createReferences(1_000))).toBe(0.74);
  });

  test("applies family-aware trial pressure to verified promotion evidence", () => {
    const references = Array.from({ length: 100 }, (_, index) => ({
      ...createReferences(1)[0],
      iteration: index + 1,
      candidateId: `family-${index}`,
      candidateHash: `family-hash-${index}`,
      structureFamilyHash: "family-a",
      fingerprintFamily: "fp-a",
      parameterNeighborhood: "neighborhood-a",
    })) as ExperimentRecord[];

    const result = buildVerifiedPromotionScore({
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localCandidateHash: "hash-a",
      tvCandidateHash: "hash-a",
      tvCalibrationStatus: "verified_match",
      localTvParity: createMatchedParity(),
      walkForwardEvaluation: createWalkForwardPass(),
      config: null,
      referenceExperiments: references,
      structureFamilyHash: "family-a",
      fingerprintFamily: "fp-a",
      parameterNeighborhood: "neighborhood-a",
    });

    expect(result.trialLedgerStats?.totalCandidatesTried).toBe(100);
    expect(result.trialLedgerStats?.familyTrials).toBe(100);
    expect(result.trialLedgerStats?.fingerprintFamilyTrials).toBe(100);
    expect(result.trialLedgerStats?.parameterNeighborhoodTrials).toBe(100);
    expect(result.scoreBreakdown?.trialBudgetPenalty).toBeGreaterThan(0);
    expect(result.scoreBreakdown?.minimumRequiredScore).toBeGreaterThan(0.68);
  });

  test("does not use novelty or diversity as verified champion score inputs", () => {
    const lowNoveltyReferences = createReferences(10).map((record, index) => ({
      ...record,
      noveltyFingerprint: {
        fingerprint: `low-${index}`,
        fingerprintFamily: "low-family",
        inventorySignature: "inventory",
        structureSignature: "structure",
        featureFlags: [],
        configBuckets: {},
        tokens: ["same"],
      },
    })) as ExperimentRecord[];
    const highNoveltyReferences = createReferences(10).map((record, index) => ({
      ...record,
      noveltyFingerprint: {
        fingerprint: `high-${index}`,
        fingerprintFamily: `unique-family-${index}`,
        inventorySignature: `inventory-${index}`,
        structureSignature: `structure-${index}`,
        featureFlags: [`flag-${index}`],
        configBuckets: {},
        tokens: [`unique-${index}`],
      },
    })) as ExperimentRecord[];

    const baseInput = {
      localMetrics: createMetrics(),
      tvMetrics: createMetrics(),
      localCandidateHash: "hash-a",
      tvCandidateHash: "hash-a",
      tvCalibrationStatus: "verified_match" as const,
      localTvParity: createMatchedParity(),
      walkForwardEvaluation: createWalkForwardPass(),
      config: null,
      structureFamilyHash: "family-a",
      fingerprintFamily: "fp-a",
      parameterNeighborhood: "neighborhood-a",
    };

    const lowNoveltyScore = buildVerifiedPromotionScore({
      ...baseInput,
      referenceExperiments: lowNoveltyReferences,
    }).scoreBreakdown?.totalScore;
    const highNoveltyScore = buildVerifiedPromotionScore({
      ...baseInput,
      referenceExperiments: highNoveltyReferences,
    }).scoreBreakdown?.totalScore;

    expect(highNoveltyScore).toBe(lowNoveltyScore);
  });
});
