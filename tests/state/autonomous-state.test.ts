import { describe, expect, test } from "vitest";

import {
  autonomousExperimentSchema,
  type AutonomousExperimentRecord,
} from "../../src/contracts/autonomous.js";
import { type ExperimentRecord } from "../../src/contracts/types.js";
import { selectBestChampionCandidate } from "../../src/state/autonomous-state.js";

function createLocalRecord(): AutonomousExperimentRecord {
  return autonomousExperimentSchema.parse({
    runId: "run-local",
    iteration: 1,
    candidateId: "cand-a",
    parentCandidateId: null,
    branchId: "main",
    acceptedHeadCandidateId: null,
    baselineCandidateId: null,
    candidatePath: "C:\\tmp\\cand-a.pine",
    candidateHash: "hash-a",
    studyTitle: "Cand A",
    candidateScore: 2,
    decision: "local_candidate_eligible",
    status: "evaluated",
    recordKind: "local_evaluation",
    executorRole: "primary_local_backtest",
    evidenceAuthority: "local_model",
    evaluationMode: "local_primary",
    mutationProvenance: null,
    localFrontierScore: 2,
    autoSelectionScore: 2,
    objectivePolicyVersion: "objective.qqq-120m/v1",
    selectionPolicyVersion: "autonomous-tv-verified/v4",
    tvCalibrationStatus: "not_requested",
    eligibility: {
      autoSelectionEligible: true,
      bootstrapEligible: false,
      archiveEligible: true,
      calibrationEligible: true,
      blockingReasons: [],
    },
    artifactPaths: {},
    recordMeta: {
      schemaVersion: "experiment/v3",
      recordHash: "record-local",
      candidateHash: "hash-a",
      baselineHash: null,
      artifactBundleHash: null,
      pipelineVersion: "af-autonomous-local-first/v3",
    },
    recordedAt: "2026-05-03T00:00:00.000Z",
  });
}

function createTvRecord(
  overrides?: Partial<AutonomousExperimentRecord>,
): AutonomousExperimentRecord {
  return autonomousExperimentSchema.parse({
    ...createLocalRecord(),
    runId: "run-tv",
    iteration: 2,
    decision: "tv_verified",
    status: "verified",
    recordKind: "tv_verification",
    executorRole: "external_calibration",
    evidenceAuthority: "external_tv",
    evaluationMode: "tv_calibration",
    candidateScore: 0.72,
    localFrontierScore: 2,
    autoSelectionScore: 0.72,
    tvCalibrationStatus: "verified_match",
    localTvParity: {
      status: "matched",
      tradeCountDelta: 0,
      netProfitPctDelta: 0,
      maxDrawdownPctDelta: 0,
      profitFactorDelta: 0,
      winRateDelta: 0,
    },
    walkForwardEvaluation: {
      policyVersion: "walk-forward-oos/v1",
      foldCount: 5,
      requiredPositiveOosFolds: 4,
      positiveOosFoldCount: 5,
      minimumTradesPerFold: 12,
      minimumTotalOosTrades: 60,
      totalOosTrades: 80,
      worstFoldDrawdownPercent: 10,
      medianOosProfitFactor: 1.4,
      medianOosPostFeeNetProfitPercent: 8,
      embargoBars: 5,
      passed: true,
      gateReasons: [],
      folds: [],
    },
    verifiedPromotionScore: 0.72,
    verifiedPromotion: {
      eligible: true,
      score: 0.72,
      scoreBreakdown: {
        tvPerformanceScore: 0.3,
        walkForwardRobustnessScore: 0.18,
        foldConsistencyScore: 0.15,
        tradeDensityScore: 0.1,
        parityScore: 0.1,
        simplicityScore: 0.04,
        trialBudgetPenalty: 0,
        regimeConcentrationPenalty: 0,
        complexityPenalty: 0.15,
        totalScore: 0.72,
        minimumRequiredScore: 0.62,
      },
      rejectionReasons: [],
      localCandidateHash: "hash-a",
      tvCandidateHash: "hash-a",
      localRecordKind: "local_evaluation",
      tvRecordKind: "tv_verification",
      policyVersion: "verified-promotion/v1",
    },
    recordMeta: {
      schemaVersion: "experiment/v3",
      recordHash: "record-tv",
      candidateHash: "hash-a",
      baselineHash: null,
      artifactBundleHash: null,
      pipelineVersion: "af-autonomous-local-first/v3",
    },
    recordedAt: "2026-05-03T01:00:00.000Z",
    ...overrides,
  });
}

function asExperimentRecords(
  records: AutonomousExperimentRecord[],
): ExperimentRecord[] {
  return records as unknown as ExperimentRecord[];
}

describe("autonomous champion selectors", () => {
  test("does not promote local-only candidates", () => {
    expect(selectBestChampionCandidate(asExperimentRecords([createLocalRecord()]))).toBeNull();
  });

  test("requires verified match, non-major parity, and matching candidate hash", () => {
    const localRecord = createLocalRecord();

    expect(
      selectBestChampionCandidate(asExperimentRecords([
        localRecord,
        createTvRecord({ tvCalibrationStatus: "verified_diverged" }),
      ])),
    ).toBeNull();
    expect(
      selectBestChampionCandidate(asExperimentRecords([
        localRecord,
        createTvRecord({
          localTvParity: {
            status: "major_drift",
            tradeCountDelta: 2,
            netProfitPctDelta: 4,
            maxDrawdownPctDelta: 0,
            profitFactorDelta: 0,
            winRateDelta: 0,
          },
        }),
      ])),
    ).toBeNull();
    expect(
      selectBestChampionCandidate(asExperimentRecords([
        localRecord,
        createTvRecord({
          candidateHash: "hash-b",
          recordMeta: {
            schemaVersion: "experiment/v3",
            recordHash: "record-tv-mismatch",
            candidateHash: "hash-b",
            baselineHash: null,
            artifactBundleHash: null,
            pipelineVersion: "af-autonomous-local-first/v3",
          },
        }),
      ])),
    ).toBeNull();
    expect(
      selectBestChampionCandidate(asExperimentRecords([
        localRecord,
        createTvRecord({
          walkForwardEvaluation: {
            policyVersion: "walk-forward-oos/v1",
            foldCount: 5,
            requiredPositiveOosFolds: 4,
            positiveOosFoldCount: 3,
            minimumTradesPerFold: 12,
            minimumTotalOosTrades: 60,
            totalOosTrades: 55,
            worstFoldDrawdownPercent: 19,
            medianOosProfitFactor: 1.05,
            medianOosPostFeeNetProfitPercent: 2,
            embargoBars: 5,
            passed: false,
            gateReasons: ["positive_oos_fold_count"],
            folds: [],
          },
        }),
      ])),
    ).toBeNull();
  });

  test("selects verified promotion candidates", () => {
    const selected = selectBestChampionCandidate(asExperimentRecords([
      createLocalRecord(),
      createTvRecord(),
    ]));

    expect(selected?.candidateId).toBe("cand-a");
    expect(selected?.verifiedPromotionScore).toBe(0.72);
  });
});
