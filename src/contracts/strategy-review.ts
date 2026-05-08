import { z } from "zod";

import {
  backtestMetricsSchema,
  branchKindSchema,
  objectiveConfigSchema,
  objectiveBreakdownSchema,
  researchGoalModeSchema,
} from "./types.js";

export const strategyReviewDecisionSchema = z.enum([
  "exploit_parent",
  "repair_near_miss",
  "redirect_family",
  "simplify_family",
  "quarantine_family",
  "calibrate_candidate",
  "no_action",
]);

export const strategyReviewModeSchema = z.enum([
  "deterministic",
  "deep_llm",
  "llm_failed_fallback",
]);

export const strategyReviewMutationDirectiveSchema = z.object({
  branchKindBias: branchKindSchema.nullable().default(null),
  parentCandidateId: z.string().nullable().default(null),
  requiredChanges: z.array(z.string()).default([]),
  forbiddenPatterns: z.array(z.string()).default([]),
  suppressedFamilies: z.array(z.string()).default([]),
  validationFocus: z.array(z.string()).default([]),
  reason: z.string().min(1),
});

export const strategyReviewAgentReportsSchema = z.object({
  performance: z.string().default(""),
  robustness: z.string().default(""),
  risk: z.string().default(""),
  novelty: z.string().default(""),
  calibration: z.string().default(""),
  bull: z.string().default(""),
  bear: z.string().default(""),
});

export const strategyReviewEvidenceRefsSchema = z.object({
  candidatePath: z.string().nullable().default(null),
  specPath: z.string().nullable().default(null),
  artifactPaths: z.record(z.string(), z.string()).default({}),
  problemEventIds: z.array(z.string()).default([]),
  repairAttemptIds: z.array(z.string()).default([]),
  mutationBriefHashes: z.array(z.string()).default([]),
});

export const strategyReviewTriageSchema = z.object({
  deepReviewRecommended: z.boolean(),
  reasons: z.array(z.string()).default([]),
  championScore: z.number().nullable().default(null),
  scoreRatioToChampion: z.number().nullable().default(null),
  repeatedFailureSignatureCount: z.number().int().nonnegative().default(0),
});

export const strategyReviewEvidenceSchema = z.object({
  schemaVersion: z.literal("strategy-review-evidence/v1"),
  target: z.object({
    targetId: z.string().min(1),
    symbol: z.string().min(1),
    timeframe: z.string().min(1),
    goalMode: researchGoalModeSchema.optional(),
    goalProfileId: z.string().min(1).optional(),
  }),
  runId: z.string().min(1),
  iteration: z.number().int().nonnegative(),
  candidate: z.object({
    candidateId: z.string().min(1),
    parentCandidateId: z.string().nullable().default(null),
    candidateHash: z.string().nullable().default(null),
    structureFamilyHash: z.string().nullable().default(null),
    fingerprintFamily: z.string().nullable().default(null),
    decision: z.string().min(1),
    status: z.string().min(1),
    recordKind: z.string().nullable().default(null),
    researchStage: z.string().nullable().default(null),
    localConfidence: z.number().nullable().default(null),
  }),
  objective: objectiveConfigSchema,
  metrics: z.object({
    fullSample: backtestMetricsSchema.nullable().default(null),
    inSample: backtestMetricsSchema.nullable().default(null),
    outOfSample: backtestMetricsSchema.nullable().default(null),
    walkForward: z
      .object({
        passed: z.boolean().nullable().default(null),
        positiveOosFoldCount: z.number().int().nonnegative().nullable().default(null),
        requiredPositiveOosFolds: z.number().int().positive().nullable().default(null),
        totalOosTrades: z.number().int().nonnegative().nullable().default(null),
        gateReasons: z.array(z.string()).default([]),
      })
      .nullable()
      .default(null),
  }),
  objectiveBreakdown: objectiveBreakdownSchema.nullable().default(null),
  conditionContributions: z
    .array(
      z.object({
        conditionId: z.string().min(1),
        scoreDelta: z.number(),
        summary: z.string().min(1),
      }),
    )
    .default([]),
  lossAnalysis: z.object({
    summary: z.string().nullable().default(null),
    topLossZones: z.array(z.string()).default([]),
    repairPriorities: z.array(z.string()).default([]),
  }),
  novelty: z.object({
    duplicateClassification: z.string().nullable().default(null),
    duplicateFingerprint: z.string().nullable().default(null),
    featureFlags: z.array(z.string()).default([]),
    complexityPenalty: z.number().nullable().default(null),
    trialLedgerStats: z.record(z.string(), z.unknown()).nullable().default(null),
  }),
  calibration: z.object({
    tvCalibrationStatus: z.string().nullable().default(null),
    localTvParityStatus: z.string().nullable().default(null),
    verifiedPromotionEligible: z.boolean().nullable().default(null),
    verifiedPromotionScore: z.number().nullable().default(null),
    rejectionReasons: z.array(z.string()).default([]),
  }),
  problemMemory: z.object({
    recentProblems: z.array(z.string()).default([]),
    repeatedFailureSignatureHash: z.string().nullable().default(null),
    repeatedFailureSignatureCount: z.number().int().nonnegative().default(0),
  }),
  repairMemory: z.object({
    recentRepairs: z.array(z.string()).default([]),
  }),
  mutationBrief: z.object({
    latestBriefHash: z.string().nullable().default(null),
    branchKind: branchKindSchema.nullable().default(null),
    nextMutationDirection: z.string().nullable().default(null),
  }),
  evidenceRefs: strategyReviewEvidenceRefsSchema,
  triage: strategyReviewTriageSchema,
});

export const strategyReviewLlmResponseSchema = z.object({
  reviewDecision: strategyReviewDecisionSchema,
  confidence: z.number().min(0).max(1),
  agentReports: strategyReviewAgentReportsSchema,
  debateSummary: z.string().min(1),
  mutationDirective: strategyReviewMutationDirectiveSchema,
});

export const strategyReviewRecordSchema = strategyReviewLlmResponseSchema.extend({
  schemaVersion: z.literal("strategy-review-record/v1"),
  targetId: z.string().min(1),
  symbol: z.string().min(1).nullable().optional(),
  timeframe: z.string().min(1).nullable().optional(),
  goalMode: researchGoalModeSchema.optional(),
  goalProfileId: z.string().min(1).optional(),
  runId: z.string().min(1),
  iteration: z.number().int().nonnegative(),
  candidateId: z.string().min(1),
  candidateHash: z.string().nullable().default(null),
  structureFamilyHash: z.string().nullable().default(null),
  fingerprintFamily: z.string().nullable().default(null),
  reviewMode: strategyReviewModeSchema,
  triageReasons: z.array(z.string()).default([]),
  evidenceRefs: strategyReviewEvidenceRefsSchema,
  evidenceHash: z.string().min(1),
  recordedAt: z.string().datetime(),
});

export const strategyReviewBoardSchema = z.object({
  schemaVersion: z.literal("strategy-review-board/v1"),
  generatedAt: z.string().datetime(),
  targets: z.array(
    z.object({
      targetId: z.string().min(1),
      symbol: z.string().min(1).nullable().optional(),
      timeframe: z.string().min(1).nullable().optional(),
      goalMode: researchGoalModeSchema.optional(),
      goalProfileId: z.string().min(1).optional(),
      latestReview: strategyReviewRecordSchema.nullable().default(null),
      decisionCounts: z.record(z.string(), z.number().int().nonnegative()).default({}),
      suppressedFamilies: z.array(z.string()).default([]),
      nextMutationFocus: z.array(z.string()).default([]),
    }),
  ),
  recentReviews: z.array(strategyReviewRecordSchema).default([]),
});

export type StrategyReviewDecision = z.infer<typeof strategyReviewDecisionSchema>;
export type StrategyReviewMutationDirective = z.infer<
  typeof strategyReviewMutationDirectiveSchema
>;
export type StrategyReviewAgentReports = z.infer<typeof strategyReviewAgentReportsSchema>;
export type StrategyReviewEvidence = z.infer<typeof strategyReviewEvidenceSchema>;
export type StrategyReviewRecord = z.infer<typeof strategyReviewRecordSchema>;
export type StrategyReviewBoard = z.infer<typeof strategyReviewBoardSchema>;
