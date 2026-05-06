import { describe, expect, test } from "vitest";

import {
  ACTIVE_TV_CALIBRATION_QUEUE_LIMIT,
  selectPendingCalibrationCandidateIds,
} from "../../src/research/autonomous/tv-calibration-queue-phase.js";
import { buildAutonomousViewPayloads } from "../../src/state/autonomous-index-builder.js";
import {
  type CalibrationEventRecord,
} from "../../src/contracts/autonomous.js";
import { type ExperimentRecord } from "../../src/contracts/types.js";

describe("tv calibration queue priority", () => {
  test("keeps only the best 20 score/performance candidates active", () => {
    const calibrationEvents = Array.from({ length: 25 }, (_, index) =>
      createCalibrationEvent(index),
    );
    const experiments = Array.from({ length: 25 }, (_, index) =>
      createLocalExperiment(index, {
        autoSelectionScore: index < 5 ? 0.2 : 1,
        postFeeNetProfitPercent: index,
      }),
    );

    const selected = selectPendingCalibrationCandidateIds({
      events: calibrationEvents,
      experiments,
    });

    expect(selected).toHaveLength(ACTIVE_TV_CALIBRATION_QUEUE_LIMIT);
    expect(selected.slice(0, 3)).toEqual(["cand-24", "cand-23", "cand-22"]);
    expect(selected).not.toContain("cand-00");
    expect(selected).not.toContain("cand-04");
  });

  test("marks queued candidates outside the active top 20 as deactivated in views", () => {
    const calibrationEvents = Array.from({ length: 25 }, (_, index) =>
      createCalibrationEvent(index),
    );
    const experiments = Array.from({ length: 25 }, (_, index) =>
      createLocalExperiment(index, {
        autoSelectionScore: index,
        postFeeNetProfitPercent: index,
      }),
    );

    const views = buildAutonomousViewPayloads({
      experiments,
      headEvents: [],
      archiveEvents: [],
      calibrationEvents,
      confidenceEvents: [],
      problemEvents: [],
      repairAttempts: [],
    });

    const entries = views.tvCalibrationQueue.entries;
    expect(
      entries.filter(
        (entry) =>
          entry.derivedStatus === "pending" || entry.derivedStatus === "deferred",
      ),
    ).toHaveLength(ACTIVE_TV_CALIBRATION_QUEUE_LIMIT);
    expect(entries.filter((entry) => entry.derivedStatus === "deactivated"))
      .toHaveLength(5);
    expect(views.autonomousStateSummary.pendingCalibrationCandidateCount).toBe(
      ACTIVE_TV_CALIBRATION_QUEUE_LIMIT,
    );
  });
});

function createCalibrationEvent(index: number): CalibrationEventRecord {
  const candidateId = candidateIdFor(index);
  return {
    runId: "queue-priority-test",
    iteration: index + 1,
    eventKind: "calibration_candidate_added",
    candidateId,
    fingerprintFamily: `family-${index}`,
    structureFamilyHash: `structure-${index}`,
    queueState: "queued",
    queueReason: "test queue priority",
    tvHealthAtQueueTime: null,
    localConfidenceBefore: 1,
    localConfidenceAfter: null,
    parity: null,
    tvDecision: null,
    recordedAt: new Date(Date.UTC(2026, 0, 1, 0, index)).toISOString(),
  };
}

function createLocalExperiment(
  index: number,
  input: {
    autoSelectionScore: number;
    postFeeNetProfitPercent: number;
  },
): ExperimentRecord {
  const candidateId = candidateIdFor(index);
  const metrics = {
    netProfitPercent: input.postFeeNetProfitPercent,
    postFeeNetProfitPercent: input.postFeeNetProfitPercent,
    profitFactor: 1 + index / 100,
    maxStrategyDrawdownPercent: 20 - index / 10,
    percentProfitable: 50 + index / 10,
    totalTrades: 50 + index,
    avgTradePercent: 0.1 + index / 100,
  };
  return {
    runId: `run-${candidateId}`,
    iteration: index + 1,
    candidateId,
    parentCandidateId: null,
    branchId: "autonomous-main",
    acceptedHeadCandidateId: null,
    baselineCandidateId: null,
    candidatePath: `strategies/candidates/${candidateId}.pine`,
    candidateHash: `hash-${candidateId}`,
    studyTitle: `Candidate ${index}`,
    candidateScore: input.autoSelectionScore,
    decision: "local_candidate_eligible",
    status: "evaluated",
    recordKind: "local_evaluation",
    executorRole: "primary_local_backtest",
    evidenceAuthority: "local_model",
    evaluationMode: "local_primary",
    conditionInventory: [],
    testerMetrics: metrics,
    localFrontierScore: null,
    autoSelectionScore: input.autoSelectionScore,
    autoSelectionBreakdown: {
      performanceScore: input.postFeeNetProfitPercent,
      baseObjectiveScore: input.postFeeNetProfitPercent,
      robustnessScore: 0,
      noveltyScore: index / 100,
      diversityScore: 0,
      localConfidenceBonus: 0,
      riskPenalty: 0,
      overfitPenalty: 0,
      duplicatePenalty: 0,
      divergencePenalty: 0,
      complexityPenalty: 0,
      autoSelectionScore: input.autoSelectionScore,
      totalScore: input.autoSelectionScore,
      eligible: true,
      rejectionReasons: [],
    },
    objectivePolicyVersion: "objective.test/v1",
    selectionPolicyVersion: "autonomous-local-first/test",
    selectionPhase: "steady_state",
    researchStage: "candidate",
    localConfidence: 1,
    tvCalibrationStatus: "not_requested",
    localTvParity: null,
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
      recordHash: `record-${candidateId}`,
      candidateHash: `hash-${candidateId}`,
      baselineHash: null,
      artifactBundleHash: null,
      pipelineVersion: "af-autonomous-local-first/test",
    },
    recordedAt: new Date(Date.UTC(2026, 0, 1, 1, index)).toISOString(),
  } as ExperimentRecord;
}

function candidateIdFor(index: number): string {
  return `cand-${String(index).padStart(2, "0")}`;
}
