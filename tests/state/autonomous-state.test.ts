import { describe, expect, test } from "vitest";

import {
  autonomousExperimentSchema,
  type HeadEventRecord,
  type AutonomousExperimentRecord,
} from "../../src/contracts/autonomous.js";
import { type ExperimentRecord } from "../../src/contracts/types.js";
import {
  AUTORESEARCH_CONTRACT_VERSION,
  STRATEGY_SPEC_MUTATION_AUTHORITY,
} from "../../src/policy/autoresearch-contract.js";
import {
  findActiveChampionRecord,
  findActiveVerifiedChampionRecord,
  findBootstrapSeedRecord,
  selectBestChampionCandidate,
  selectBestTvVerifiedCandidate,
} from "../../src/state/autonomous-state.js";

function createLocalRecord(
  overrides?: Partial<AutonomousExperimentRecord>,
): AutonomousExperimentRecord {
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
    contractVersion: AUTORESEARCH_CONTRACT_VERSION,
    mutationAuthority: STRATEGY_SPEC_MUTATION_AUTHORITY,
    specPath: "C:\\tmp\\cand-a.json",
    specHash: "spec-hash-a",
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
    ...overrides,
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
    executorRole: "primary_local_backtest",
    evidenceAuthority: "local_model",
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
      tradeParity: {
        status: "matched",
        entryTimeMatchRatio: 1,
        exitTimeMatchRatio: 1,
        profitSignMatchRatio: 1,
        orderCountDelta: 0,
      },
      eventParity: {
        status: "matched",
        eventMatchRatio: 1,
        entryPassMatchRatio: 1,
        exitReasonMatchRatio: 1,
      },
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
      minimumCoverageDays: 730,
      coverageDays: 800,
      coverageStartTime: "2023-05-25T00:00:00.000Z",
      coverageEndTime: "2025-08-02T00:00:00.000Z",
      passed: true,
      gateReasons: [],
      failedFoldRegimeSummary: [],
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

function createHeadEvent(
  overrides?: Partial<HeadEventRecord>,
): HeadEventRecord {
  return {
    runId: "run-head",
    iteration: 1,
    eventKind: "champion_updated",
    candidateId: "cand-a",
    previousChampionId: null,
    selectedBy: "auto_policy",
    policyVersion: "autonomous-tv-verified/v4",
    headAuthority: "verified_promotion",
    selectionPhase: "steady_state",
    bootstrapSource: null,
    bootstrapReason: null,
    researchMaturity: "steady_state",
    performanceScore: 0.72,
    objectiveScore: 0.6,
    noveltyScore: 0,
    robustnessScore: 0,
    autoSelectionScore: 0.72,
    diversityScore: 0,
    diversityContribution: 0,
    localConfidenceBonus: 0,
    riskPenalty: 0,
    overfitPenalty: 0,
    duplicatePenalty: 0,
    divergencePenalty: 0,
    complexityPenalty: 0,
    selectionReason: "test",
    selectionEvidenceHash: "evidence",
    humanOverride: false,
    recordedAt: "2026-05-03T02:00:00.000Z",
    ...overrides,
  };
}

describe("autonomous champion selectors", () => {
  test("promotes eligible local-only candidates", () => {
    const selected = selectBestChampionCandidate(asExperimentRecords([createLocalRecord()]));

    expect(selected?.candidateId).toBe("cand-a");
    expect(selected?.recordKind).toBe("local_evaluation");
    expect(selected?.autoSelectionScore).toBe(2);
  });

  test("does not promote ineligible local-only candidates", () => {
    expect(
      selectBestChampionCandidate(asExperimentRecords([
        createLocalRecord({
          eligibility: {
            autoSelectionEligible: false,
            bootstrapEligible: false,
            archiveEligible: true,
            calibrationEligible: false,
            blockingReasons: [
              {
                kind: "robustness_fail",
                message: "objective gate failed",
                suggestedRepairKind: null,
              },
            ],
          },
          autoSelectionBreakdown: {
            baseObjectiveScore: 0,
            robustnessScore: 0,
            noveltyScore: 0,
            diversityScore: 0,
            localConfidenceBonus: 0,
            riskPenalty: 0,
            overfitPenalty: 0,
            duplicatePenalty: 0,
            divergencePenalty: 0,
            complexityPenalty: 0,
            totalScore: 0,
            eligible: false,
            rejectionReasons: ["objective_gate_failed"],
          },
        }),
      ])),
    ).toBeNull();
  });

  test("requires verified match, non-major parity, and matching candidate hash", () => {
    const localRecord = createLocalRecord();

    expect(
      selectBestTvVerifiedCandidate(asExperimentRecords([
        localRecord,
        createTvRecord({ tvCalibrationStatus: "verified_diverged" }),
      ])),
    ).toBeNull();
    expect(
      selectBestTvVerifiedCandidate(asExperimentRecords([
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
      selectBestTvVerifiedCandidate(asExperimentRecords([
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
      selectBestTvVerifiedCandidate(asExperimentRecords([
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
            minimumCoverageDays: 730,
            coverageDays: 800,
            coverageStartTime: "2023-05-25T00:00:00.000Z",
            coverageEndTime: "2025-08-02T00:00:00.000Z",
            passed: false,
            gateReasons: ["positive_oos_fold_count"],
            failedFoldRegimeSummary: [],
            folds: [],
          },
        }),
      ])),
    ).toBeNull();
  });

  test("rejects metric-only verified records when AFTRACE parity is missing", () => {
    const selected = selectBestTvVerifiedCandidate(asExperimentRecords([
      createLocalRecord(),
      createTvRecord({
        localTvParity: {
          status: "matched",
          tradeCountDelta: 0,
          netProfitPctDelta: 0,
          maxDrawdownPctDelta: 0,
          profitFactorDelta: 0,
          winRateDelta: 0,
          tradeParity: {
            status: "matched",
            entryTimeMatchRatio: 1,
            exitTimeMatchRatio: 1,
            profitSignMatchRatio: 1,
            orderCountDelta: 0,
          },
          eventParity: {
            status: "not_comparable",
            eventMatchRatio: null,
            entryPassMatchRatio: null,
            exitReasonMatchRatio: null,
          },
        },
      }),
    ]));

    expect(selected).toBeNull();
  });

  test("selects verified promotion candidates", () => {
    const selected = selectBestChampionCandidate(asExperimentRecords([
      createLocalRecord(),
      createTvRecord(),
    ]));

    expect(selected?.candidateId).toBe("cand-a");
    expect(selected?.verifiedPromotionScore).toBe(0.72);
  });

  test("rejects verified records when the spec authority does not match local evidence", () => {
    const selected = selectBestTvVerifiedCandidate(asExperimentRecords([
      createLocalRecord(),
      createTvRecord({
        specHash: "different-spec-hash",
      }),
    ]));

    expect(selected).toBeNull();
  });

  test("active champion lookup accepts local promotion heads", () => {
    const active = findActiveChampionRecord({
      records: asExperimentRecords([createLocalRecord()]),
      headEvents: [
        createHeadEvent({
          headAuthority: "local_promotion",
          selectionPhase: "steady_state",
          candidateId: "cand-a",
        }),
      ],
    });

    expect(active?.candidateId).toBe("cand-a");
  });

  test("bootstrap seed lookup only accepts local-compatible bootstrap records", () => {
    const bootstrapRecord = createLocalRecord({
      selectionPhase: "bootstrap",
      bootstrapSource: "local_compatible_seed",
      bootstrapReason: "fresh state",
      eligibility: {
        autoSelectionEligible: true,
        bootstrapEligible: true,
        archiveEligible: true,
        calibrationEligible: true,
        blockingReasons: [],
      },
    });
    const headEvents = [
      createHeadEvent({
        headAuthority: "bootstrap_seed",
        selectionPhase: "bootstrap",
        bootstrapSource: "local_compatible_seed",
        bootstrapReason: "fresh state",
        candidateId: "cand-a",
      }),
    ];

    expect(
      findBootstrapSeedRecord({
        records: asExperimentRecords([bootstrapRecord]),
        headEvents,
      })?.candidateId,
    ).toBe("cand-a");
    expect(
      findActiveChampionRecord({
        records: asExperimentRecords([bootstrapRecord]),
        headEvents,
      })?.candidateId,
    ).toBe("cand-a");
  });

  test("verified champion lookup supersedes bootstrap fallback", () => {
    const bootstrapRecord = createLocalRecord({
      selectionPhase: "bootstrap",
      bootstrapSource: "local_compatible_seed",
      bootstrapReason: "fresh state",
      eligibility: {
        autoSelectionEligible: true,
        bootstrapEligible: true,
        archiveEligible: true,
        calibrationEligible: true,
        blockingReasons: [],
      },
    });
    const verified = createTvRecord();
    const headEvents = [
      createHeadEvent({
        headAuthority: "bootstrap_seed",
        selectionPhase: "bootstrap",
        bootstrapSource: "local_compatible_seed",
        bootstrapReason: "fresh state",
        candidateId: "cand-a",
        recordedAt: "2026-05-03T03:00:00.000Z",
      }),
      createHeadEvent({
        headAuthority: "verified_promotion",
        selectionPhase: "steady_state",
        candidateId: "cand-a",
        recordedAt: "2026-05-03T01:00:00.000Z",
      }),
    ];

    expect(
      findActiveVerifiedChampionRecord({
        records: asExperimentRecords([bootstrapRecord, verified]),
        headEvents,
      })?.recordKind,
    ).toBe("tv_verification");
    expect(
      findActiveChampionRecord({
        records: asExperimentRecords([bootstrapRecord, verified]),
        headEvents,
      })?.recordKind,
    ).toBe("tv_verification");
  });
});
