import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  autonomousExperimentSchema,
  type AutonomousExperimentRecord,
} from "../../src/contracts/autonomous.js";
import { type ExperimentRecord, type ObjectiveConfig } from "../../src/contracts/types.js";
import { type MutationLlmClient } from "../../src/mutation/llm-client.js";
import {
  buildStrategyReviewEvidence,
  runStrategyReviewPhase,
  selectLatestStrategyReviewDirective,
} from "../../src/research/autonomous/strategy-review-phase.js";
import { readStrategyReviewRecords } from "../../src/state/jsonl-store.js";

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
    maxStrategyDrawdownPercent: 30,
    percentProfitable: 100,
    totalTrades: 200,
    avgTradePercent: 3,
  },
};

function createAutonomousRecord(input: {
  candidateId: string;
  iteration: number;
  score: number;
  eligible?: boolean;
  decision?: string;
  structureFamilyHash?: string;
  fingerprintFamily?: string;
  duplicateClassification?: "unique" | "exact_duplicate" | "structural_duplicate";
}): AutonomousExperimentRecord {
  return autonomousExperimentSchema.parse({
    targetId: "qqq-120m-af",
    runId: "run-review",
    iteration: input.iteration,
    candidateId: input.candidateId,
    parentCandidateId: null,
    branchId: "branch-review",
    candidatePath: `${input.candidateId}.pine`,
    candidateHash: `${input.candidateId}-hash`,
    contractVersion: null,
    mutationAuthority: null,
    specPath: null,
    specHash: null,
    studyTitle: null,
    candidateScore: input.score,
    decision: input.decision ?? "local_candidate_rejected",
    status: input.eligible ? "accepted" : "rejected",
    recordKind: "local_evaluation",
    executorRole: "primary_local_backtest",
    evidenceAuthority: "local_model",
    evaluationMode: "local_primary",
    mutationBriefSummary: "test candidate",
    conditionInventory: [],
    conditionContributions: [],
    mutationProvenance: null,
    artifactValidation: null,
    artifactBundle: null,
    testerMetrics: {
      netProfitPercent: input.score,
      postFeeNetProfitPercent: input.score,
      profitFactor: 1.5,
      maxStrategyDrawdownPercent: 8,
      percentProfitable: 55,
      totalTrades: input.eligible ? 80 : 42,
      avgTradePercent: 0.4,
    },
    objectiveBreakdown: null,
    splitEvaluation: null,
    noveltyFingerprint: {
      fingerprint: `${input.candidateId}-fingerprint`,
      fingerprintFamily: input.fingerprintFamily ?? "fp-a",
      inventorySignature: "inventory",
      structureSignature: "structure",
      featureFlags: ["event", "exit"],
      configBuckets: {},
      tokens: [],
    },
    structureFamilyHash: input.structureFamilyHash ?? "family-a",
    fingerprintFamily: input.fingerprintFamily ?? "fp-a",
    parameterNeighborhood: null,
    duplicateStatus: {
      classification: input.duplicateClassification ?? "unique",
      exactDuplicateCandidateId: null,
      structuralDuplicateCandidateId: null,
      duplicateFingerprint: null,
    },
    localFrontierScore: input.score,
    autoSelectionScore: input.score,
    autoSelectionBreakdown: {
      baseObjectiveScore: input.score,
      robustnessScore: 0.2,
      noveltyScore: 0.15,
      diversityScore: 0,
      localConfidenceBonus: 0,
      riskPenalty: 0,
      overfitPenalty: 0,
      duplicatePenalty: 0,
      divergencePenalty: 0,
      complexityPenalty: 0.05,
      totalScore: input.score,
      autoSelectionScore: input.score,
      eligible: input.eligible ?? false,
      rejectionReasons: input.eligible ? [] : ["minimum_total_trades"],
    },
    walkForwardEvaluation: null,
    verifiedPromotionScore: null,
    verifiedPromotion: null,
    objectivePolicyVersion: "objective/test",
    selectionPolicyVersion: "selection/test",
    selectionPhase: "steady_state",
    bootstrapSource: null,
    bootstrapReason: null,
    researchStage: input.eligible ? "frontier" : "candidate",
    localConfidence: 0.7,
    tvCalibrationStatus: "not_requested",
    localTvParity: null,
    localCompatibility: null,
    eligibility: {
      autoSelectionEligible: input.eligible ?? false,
      bootstrapEligible: false,
      archiveEligible: true,
      calibrationEligible: input.eligible ?? false,
      blockingReasons: [],
    },
    artifactPaths: {},
    recordMeta: {
      schemaVersion: "experiment/v3",
      recordHash: `${input.candidateId}-record-hash`,
      candidateHash: `${input.candidateId}-hash`,
      baselineHash: null,
      artifactBundleHash: null,
      pipelineVersion: "test",
    },
    recordedAt: "2026-05-08T00:00:00.000Z",
  });
}

describe("strategy review phase", () => {
  test("triages a rejected near-miss candidate for deep review", () => {
    const champion = createAutonomousRecord({
      candidateId: "champion",
      iteration: 1,
      score: 100,
      eligible: true,
    });
    const nearMiss = createAutonomousRecord({
      candidateId: "near",
      iteration: 2,
      score: 90,
      eligible: false,
    });

    const evidence = buildStrategyReviewEvidence({
      targetId: "qqq-120m-af",
      objective,
      record: nearMiss,
      experiments: [champion, nearMiss] as unknown as ExperimentRecord[],
      headEvents: [
        {
          runId: "run-review",
          iteration: 1,
          eventKind: "champion_updated",
          candidateId: "champion",
          previousChampionId: null,
          selectedBy: "auto_policy",
          policyVersion: "selection/test",
          headAuthority: "bootstrap_seed",
          selectionPhase: "steady_state",
          bootstrapSource: null,
          bootstrapReason: null,
          researchMaturity: "steady_state",
          objectiveScore: 100,
          noveltyScore: 0.1,
          robustnessScore: 0.1,
          diversityContribution: 0,
          riskPenalty: 0,
          overfitPenalty: 0,
          complexityPenalty: 0,
          selectionReason: "test",
          selectionEvidenceHash: "hash",
          humanOverride: false,
        },
      ],
    });

    expect(evidence.triage.reasons).toContain("near_miss_85pct_champion");
    expect(evidence.triage.deepReviewRecommended).toBe(true);
  });

  test("runs a deep review and persists a repair_near_miss directive", async () => {
    const stateRoot = await mkdtemp(path.join(tmpdir(), "af-strategy-review-"));
    const record = createAutonomousRecord({
      candidateId: "near",
      iteration: 2,
      score: 90,
      eligible: false,
    });
    const llmClient: MutationLlmClient = {
      async generateMutation() {
        throw new Error("not used");
      },
      async generateConditionAblation() {
        throw new Error("not used");
      },
      async repairMutation() {
        throw new Error("not used");
      },
      async reviewStrategy() {
        return JSON.stringify({
          reviewDecision: "repair_near_miss",
          confidence: 0.91,
          agentReports: {
            performance: "near miss",
            robustness: "needs oos repair",
            risk: "drawdown acceptable",
            novelty: "unique enough",
            calibration: "not calibrated",
            bull: "score is close",
            bear: "hard gate failed",
          },
          debateSummary: "Repair the near miss without relaxing gates.",
          mutationDirective: {
            branchKindBias: "near_miss_repair",
            parentCandidateId: "near",
            requiredChanges: ["recover_trade_count"],
            forbiddenPatterns: ["broad_rewrite"],
            suppressedFamilies: [],
            validationFocus: ["hard_gates"],
            reason: "near miss needs localized repair",
          },
        });
      },
    };

    const review = await runStrategyReviewPhase({
      stateRoot,
      runId: "run-review",
      iteration: 2,
      targetId: "qqq-120m-af",
      objective,
      record,
      experiments: [
        createAutonomousRecord({
          candidateId: "champion",
          iteration: 1,
          score: 100,
          eligible: true,
        }),
        record,
      ] as unknown as ExperimentRecord[],
      llmClient,
      mode: "all",
      deepBudget: 1,
    });

    expect(review?.reviewMode).toBe("deep_llm");
    expect(review?.reviewDecision).toBe("repair_near_miss");
    const persisted = await readStrategyReviewRecords(stateRoot);
    expect(persisted).toHaveLength(1);
    expect(
      selectLatestStrategyReviewDirective({
        records: persisted,
        targetId: "qqq-120m-af",
      })?.branchKindBias,
    ).toBe("near_miss_repair");
  });
});
