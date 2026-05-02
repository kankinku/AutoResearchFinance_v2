import { z } from "zod";

import {
  artifactValidationResultSchema,
  artifactBundleSchema,
  backtestMetricsSchema,
  conditionInventoryItemSchema,
  conditionContributionSchema,
  localTvParitySummarySchema,
  mutationBriefSchema,
  mutationProvenanceSchema,
  objectiveBreakdownSchema,
  recordMetaSchema,
  tradeRecordSchema,
  equitySummarySchema,
  mutationAuthoritySchema,
  branchKindSchema,
} from "./types.js";

export const autonomousRecordKindSchema = z.enum([
  "local_evaluation",
  "tv_verification",
]);

export const autonomousExecutorRoleSchema = z.enum([
  "primary_local_backtest",
  "external_calibration",
  "legacy_authoritative_verification",
  "external_tv_validation",
  "tv_failure_fallback_local",
]);

export const autonomousEvidenceAuthoritySchema = z.enum([
  "local_model",
  "external_tv",
  "hybrid_calibrated",
]);

export const autonomousEvaluationModeSchema = z.enum([
  "local_primary",
  "tv_calibration",
  "tv_failure_fallback",
]);

export const tvCalibrationStatusSchema = z.enum([
  "not_requested",
  "queued",
  "verified_match",
  "verified_diverged",
  "surface_failure",
  "executor_failure",
  "artifact_failure",
  "portability_failure",
]);

export const duplicateClassificationSchema = z.enum([
  "unique",
  "exact_duplicate",
  "structural_duplicate",
]);

export const autonomousSelectionPhaseSchema = z.enum([
  "bootstrap",
  "steady_state",
]);

export const autonomousBootstrapSourceSchema = z.enum([
  "local_compatible_seed",
]);

export const autonomousResearchStageSchema = z.enum([
  "candidate",
  "local_pass",
  "frontier",
  "archive",
  "calibration_queued",
  "tv_verified",
  "promotion_candidate",
  "champion",
  "quarantined",
]);

export const duplicateStatusSchema = z.object({
  classification: duplicateClassificationSchema,
  exactDuplicateCandidateId: z.string().nullable().default(null),
  structuralDuplicateCandidateId: z.string().nullable().default(null),
  duplicateFingerprint: z.string().nullable().default(null),
});

export const noveltyFingerprintSchema = z.object({
  fingerprint: z.string().min(1),
  fingerprintFamily: z.string().min(1),
  inventorySignature: z.string().min(1),
  structureSignature: z.string().min(1),
  featureFlags: z.array(z.string()).default([]),
  configBuckets: z.record(z.string(), z.string()).default({}),
  tokens: z.array(z.string()).default([]),
});

export const splitMetricsSchema = z.object({
  metrics: backtestMetricsSchema.nullable().default(null),
  objectiveBreakdown: objectiveBreakdownSchema.nullable().default(null),
  trades: z.array(tradeRecordSchema).default([]),
  equity: equitySummarySchema.nullable().default(null),
});

export const splitEvaluationSchema = z.object({
  splitMethod: z.literal("chronological_70_30"),
  fullSample: splitMetricsSchema,
  inSample: splitMetricsSchema,
  outOfSample: splitMetricsSchema,
  minimumOosTrades: z.number().int().positive(),
  oosEligible: z.boolean(),
  oosPassed: z.boolean(),
  hardGatesPassed: z.boolean(),
  gateReasons: z.array(z.string()).default([]),
});

export const walkForwardFoldSchema = z.object({
  foldId: z.string().min(1),
  index: z.number().int().nonnegative(),
  trainStartTime: z.string().nullable().default(null),
  trainEndTime: z.string().nullable().default(null),
  testStartTime: z.string().nullable().default(null),
  testEndTime: z.string().nullable().default(null),
  embargoBars: z.number().int().nonnegative(),
  metrics: backtestMetricsSchema.nullable().default(null),
  objectiveBreakdown: objectiveBreakdownSchema.nullable().default(null),
  passed: z.boolean(),
  gateReasons: z.array(z.string()).default([]),
  regimeSummary: z
    .object({
      totalBars: z.number().int().nonnegative(),
      counts: z.record(z.string(), z.number().int().nonnegative()).default({}),
      dominantRegime: z.string().nullable().default(null),
      concentration: z.number().min(0).max(1).default(0),
    })
    .optional(),
});

export const walkForwardEvaluationSchema = z.object({
  policyVersion: z.string().min(1).default("walk-forward-oos/v1"),
  canaryHoldout: z
    .object({
      policyVersion: z.string().min(1).default("canary-holdout/v1"),
      mode: z.enum(["sealed", "manual_review_only"]),
      exposed: z.boolean().default(false),
      reason: z.string().min(1),
    })
    .optional(),
  foldCount: z.number().int().positive(),
  requiredPositiveOosFolds: z.number().int().positive(),
  positiveOosFoldCount: z.number().int().nonnegative(),
  minimumTradesPerFold: z.number().int().positive(),
  minimumTotalOosTrades: z.number().int().positive(),
  totalOosTrades: z.number().int().nonnegative(),
  worstFoldDrawdownPercent: z.number().nullable().default(null),
  medianOosProfitFactor: z.number().nullable().default(null),
  medianOosPostFeeNetProfitPercent: z.number().nullable().default(null),
  embargoBars: z.number().int().nonnegative(),
  minimumCoverageDays: z.number().int().nonnegative().default(0),
  coverageDays: z.number().nonnegative().nullable().default(null),
  coverageStartTime: z.string().nullable().default(null),
  coverageEndTime: z.string().nullable().default(null),
  regimeSummary: z
    .object({
      totalBars: z.number().int().nonnegative(),
      counts: z.record(z.string(), z.number().int().nonnegative()).default({}),
      dominantRegime: z.string().nullable().default(null),
      concentration: z.number().min(0).max(1).default(0),
    })
    .optional(),
  failedFoldRegimeSummary: z
    .array(
      z.object({
        foldId: z.string().min(1),
        dominantRegime: z.string().nullable().default(null),
        concentration: z.number().min(0).max(1).default(0),
        gateReasons: z.array(z.string()).default([]),
      }),
    )
    .default([]),
  passed: z.boolean(),
  gateReasons: z.array(z.string()).default([]),
  folds: z.array(walkForwardFoldSchema).default([]),
});

export const autoSelectionBreakdownSchema = z.object({
  performanceScore: z.number().optional(),
  baseObjectiveScore: z.number(),
  robustnessScore: z.number(),
  noveltyScore: z.number(),
  diversityScore: z.number().default(0),
  localConfidenceBonus: z.number().default(0),
  riskPenalty: z.number(),
  overfitPenalty: z.number().default(0),
  duplicatePenalty: z.number(),
  divergencePenalty: z.number().default(0),
  complexityPenalty: z.number(),
  autoSelectionScore: z.number().optional(),
  totalScore: z.number(),
  eligible: z.boolean(),
  rejectionReasons: z.array(z.string()).default([]),
});

export const verifiedPromotionScoreBreakdownSchema = z.object({
  tvPerformanceScore: z.number(),
  walkForwardRobustnessScore: z.number(),
  foldConsistencyScore: z.number(),
  tradeDensityScore: z.number(),
  parityScore: z.number(),
  simplicityScore: z.number(),
  trialBudgetPenalty: z.number(),
  regimeConcentrationPenalty: z.number().default(0),
  complexityPenalty: z.number(),
  totalScore: z.number(),
  minimumRequiredScore: z.number(),
});

export const trialLedgerStatsSchema = z.object({
  totalCandidatesTried: z.number().int().nonnegative(),
  totalLocalPass: z.number().int().nonnegative(),
  totalTvVerified: z.number().int().nonnegative(),
  totalPromotionCandidates: z.number().int().nonnegative(),
  familyTrials: z.number().int().nonnegative(),
  fingerprintFamilyTrials: z.number().int().nonnegative(),
  parameterNeighborhoodTrials: z.number().int().nonnegative(),
  oosExposureCount: z.number().int().nonnegative(),
  canaryExposureCount: z.number().int().nonnegative(),
});

export const verifiedPromotionEvidenceSchema = z.object({
  eligible: z.boolean(),
  score: z.number().nullable().default(null),
  scoreBreakdown: verifiedPromotionScoreBreakdownSchema.nullable().default(null),
  rejectionReasons: z.array(z.string()).default([]),
  localCandidateHash: z.string().nullable().default(null),
  tvCandidateHash: z.string().nullable().default(null),
  structureFamilyHash: z.string().nullable().default(null),
  fingerprintFamily: z.string().nullable().default(null),
  parameterNeighborhood: z.string().nullable().default(null),
  trialLedgerStats: trialLedgerStatsSchema.nullable().default(null),
  localRecordKind: z.literal("local_evaluation").nullable().default(null),
  tvRecordKind: z.literal("tv_verification").nullable().default(null),
  policyVersion: z.string().min(1).default("verified-promotion/v1"),
});

export const localEvaluationBlockingReasonKindSchema = z.enum([
  "local_unsupported",
  "missing_strategy_spec",
  "spec_hash_mismatch",
  "missing_required_function",
  "missing_required_input",
  "unsupported_strategy_family",
  "low_trade_count",
  "drawdown_limit_fail",
  "oos_trade_count_fail",
  "robustness_fail",
  "duplicate_candidate",
  "complexity_penalty_high",
  "unknown",
]);

export const localEvaluationBlockingReasonSchema = z.object({
  kind: localEvaluationBlockingReasonKindSchema,
  message: z.string().min(1),
  evidence: z.record(z.string(), z.unknown()).optional(),
  suggestedRepairKind: z
    .enum([
      "schema_repair",
      "local_compatibility_repair",
      "risk_logic_repair",
      "entry_frequency_repair",
      "novelty_redirect",
      "skip",
    ])
    .nullable()
    .default(null),
});

export const autonomousLocalCompatibilitySchema = z.object({
  compatible: z.boolean(),
  unsupportedReason: z.string().nullable().default(null),
  missingFunctions: z.array(z.string()).default([]),
  missingInputs: z.array(z.string()).default([]),
  unsupportedPatterns: z.array(z.string()).default([]),
});

export const autonomousEligibilitySchema = z.object({
  autoSelectionEligible: z.boolean(),
  bootstrapEligible: z.boolean().default(false),
  archiveEligible: z.boolean(),
  calibrationEligible: z.boolean(),
  blockingReasons: z.array(localEvaluationBlockingReasonSchema).default([]),
});

export const autonomousExperimentSchema = z.object({
  runId: z.string().min(1),
  iteration: z.number().int().positive(),
  candidateId: z.string().min(1),
  parentCandidateId: z.string().nullable(),
  branchId: z.string().min(1),
  candidatePath: z.string().min(1),
  candidateHash: z.string().min(1),
  contractVersion: z.string().nullable().default(null),
  mutationAuthority: mutationAuthoritySchema.nullable().default(null),
  specPath: z.string().nullable().default(null),
  specHash: z.string().nullable().default(null),
  studyTitle: z.string().nullable().default(null),
  candidateScore: z.number().nullable().default(null),
  decision: z.string().min(1),
  status: z.string().min(1),
  recordKind: autonomousRecordKindSchema,
  executorRole: autonomousExecutorRoleSchema,
  evidenceAuthority: autonomousEvidenceAuthoritySchema,
  evaluationMode: autonomousEvaluationModeSchema,
  mutationBriefSummary: z.string().optional(),
  conditionInventory: z.array(conditionInventoryItemSchema).default([]),
  conditionContributions: z.array(conditionContributionSchema).default([]),
  mutationProvenance: mutationProvenanceSchema.nullable().default(null),
  artifactValidation: artifactValidationResultSchema.nullable().default(null),
  artifactBundle: artifactBundleSchema.nullable().default(null),
  testerMetrics: backtestMetricsSchema.nullable().default(null),
  objectiveBreakdown: objectiveBreakdownSchema.nullable().default(null),
  splitEvaluation: splitEvaluationSchema.nullable().default(null),
  noveltyFingerprint: noveltyFingerprintSchema.nullable().default(null),
  structureFamilyHash: z.string().nullable().default(null),
  fingerprintFamily: z.string().nullable().default(null),
  parameterNeighborhood: z.string().nullable().default(null),
  duplicateStatus: duplicateStatusSchema.nullable().default(null),
  localFrontierScore: z.number().nullable().default(null),
  autoSelectionScore: z.number().nullable().default(null),
  autoSelectionBreakdown: autoSelectionBreakdownSchema.nullable().default(null),
  walkForwardEvaluation: walkForwardEvaluationSchema.nullable().default(null),
  verifiedPromotionScore: z.number().nullable().default(null),
  verifiedPromotion: verifiedPromotionEvidenceSchema.nullable().default(null),
  objectivePolicyVersion: z.string().min(1),
  selectionPolicyVersion: z.string().min(1),
  selectionPhase: autonomousSelectionPhaseSchema.default("steady_state"),
  bootstrapSource: autonomousBootstrapSourceSchema.nullable().default(null),
  bootstrapReason: z.string().nullable().default(null),
  researchStage: autonomousResearchStageSchema.default("candidate"),
  localConfidence: z.number().min(0).max(1).nullable().default(null),
  tvCalibrationStatus: tvCalibrationStatusSchema.default("not_requested"),
  localTvParity: localTvParitySummarySchema.nullable().default(null),
  localCompatibility: autonomousLocalCompatibilitySchema.nullable().default(null),
  eligibility: autonomousEligibilitySchema.nullable().default(null),
  artifactPaths: z.record(z.string(), z.string()).default({}),
  recordMeta: recordMetaSchema,
  recordedAt: z.string().datetime(),
});

export const headEventKindSchema = z.enum([
  "auto_selected_head",
  "champion_updated",
]);

export const headAuthoritySchema = z.enum([
  "bootstrap_seed",
  "verified_promotion",
]);

export const autonomousBranchStatusSchema = z.enum([
  "active",
  "exhausted",
  "closed",
]);

export const autonomousBranchRecordSchema = z.object({
  branchId: z.string().min(1),
  branchKind: branchKindSchema,
  budgetPct: z.number().min(0).max(100),
  parentCandidateId: z.string().nullable().default(null),
  followUpRemaining: z.number().int().nonnegative(),
  createdAt: z.string().datetime(),
  lastCandidateId: z.string().nullable().default(null),
  status: autonomousBranchStatusSchema,
});

export const headEventRecordSchema = z.object({
  runId: z.string().min(1),
  iteration: z.number().int().positive(),
  eventKind: headEventKindSchema,
  candidateId: z.string().min(1),
  previousChampionId: z.string().nullable().default(null),
  selectedBy: z.literal("auto_policy"),
  policyVersion: z.string().min(1),
  headAuthority: headAuthoritySchema.nullable().default(null),
  selectionPhase: autonomousSelectionPhaseSchema.default("steady_state"),
  bootstrapSource: autonomousBootstrapSourceSchema.nullable().default(null),
  bootstrapReason: z.string().nullable().default(null),
  researchMaturity: autonomousSelectionPhaseSchema.default("steady_state"),
  performanceScore: z.number().nullable().default(null).optional(),
  objectiveScore: z.number().nullable().default(null),
  noveltyScore: z.number().nullable().default(null),
  robustnessScore: z.number().nullable().default(null),
  autoSelectionScore: z.number().nullable().default(null).optional(),
  diversityScore: z.number().default(0).optional(),
  diversityContribution: z.number().default(0),
  localConfidenceBonus: z.number().default(0).optional(),
  riskPenalty: z.number().default(0),
  overfitPenalty: z.number().default(0),
  duplicatePenalty: z.number().default(0).optional(),
  divergencePenalty: z.number().default(0).optional(),
  complexityPenalty: z.number().default(0),
  selectionReason: z.string().min(1),
  selectionEvidenceHash: z.string().min(1),
  humanOverride: z.literal(false),
  recordedAt: z.string().datetime().optional(),
});

export const archiveEventKindSchema = z.enum([
  "archive_added",
  "novelty_frontier_added",
  "robustness_frontier_added",
  "failure_archive_added",
]);

export const archiveEventRecordSchema = z.object({
  runId: z.string().min(1),
  iteration: z.number().int().positive(),
  eventKind: archiveEventKindSchema,
  candidateId: z.string().min(1),
  score: z.number().nullable().default(null),
  noveltyScore: z.number().nullable().default(null),
  robustnessScore: z.number().nullable().default(null),
  reason: z.string().min(1),
  recordedAt: z.string().datetime().optional(),
});

export const calibrationEventKindSchema = z.enum([
  "calibration_candidate_added",
  "calibration_queue_status_updated",
  "local_tv_divergence_measured",
]);

export const calibrationQueueStateSchema = z.enum([
  "queued",
  "processed",
  "skipped",
  "failed",
]);

export const calibrationEventRecordSchema = z.object({
  calibrationEventId: z.string().nullable().default(null).optional(),
  runId: z.string().min(1),
  iteration: z.number().int().positive(),
  eventKind: calibrationEventKindSchema,
  candidateId: z.string().min(1),
  structureFamilyHash: z.string().nullable().default(null).optional(),
  fingerprintFamily: z.string().nullable().default(null),
  queueState: calibrationQueueStateSchema.default("queued"),
  queueReason: z.string().nullable().default(null),
  tvHealthAtQueueTime: z
    .enum(["healthy", "degraded", "unavailable"])
    .nullable()
    .default(null),
  localConfidenceBefore: z.number().min(0).max(1).nullable().default(null),
  localConfidenceAfter: z.number().min(0).max(1).nullable().default(null),
  parity: localTvParitySummarySchema.nullable().default(null),
  tvDecision: z.string().nullable().default(null),
  recordedAt: z.string().datetime().optional(),
});

export const divergenceSeveritySchema = z.enum(["low", "medium", "high"]);

export const localConfidenceEventRecordSchema = z.object({
  confidenceEventId: z.string().min(1),
  runId: z.string().min(1),
  iteration: z.number().int().positive(),
  eventKind: z.literal("local_confidence_updated"),
  candidateId: z.string().min(1),
  sourceCalibrationEventId: z.string().nullable().default(null),
  structureFamilyHash: z.string().min(1),
  divergenceSeverity: divergenceSeveritySchema,
  previousConfidence: z.number().min(0).max(1),
  nextConfidence: z.number().min(0).max(1),
  localConfidenceBonus: z.number().default(0),
  divergencePenalty: z.number().default(0),
  reason: z.string().min(1),
  recordedAt: z.string().datetime().optional(),
});

export const problemKindSchema = z.enum([
  "llm_schema_fail",
  "mutation_generation_fail",
  "pine_preflight_fail",
  "local_unsupported",
  "local_backtest_fail",
  "tv_surface_failure",
  "artifact_failure",
  "duplicate_candidate",
  "local_tv_divergence",
  "bootstrap_failed",
]);

export const repairKindSchema = z.enum([
  "schema_repair",
  "schema_regenerate",
  "pine_source_repair",
  "local_compatibility_repair",
  "entry_frequency_repair",
  "risk_logic_repair",
  "mutation_prompt_adjustment",
  "archive_gap_redirect",
]);

export const repairAttemptResultSchema = z.enum([
  "success",
  "failed",
  "deferred",
]);

export const problemEventRecordSchema = z.object({
  problemEventId: z.string().min(1),
  runId: z.string().min(1),
  iteration: z.number().int().nonnegative(),
  candidateId: z.string().nullable().default(null),
  problemKind: problemKindSchema,
  diagnosis: z.string().min(1),
  evidenceHash: z.string().min(1),
  suggestedRepairKind: repairKindSchema,
  failureSignatureHash: z.string().nullable().default(null).optional(),
  structureFamily: z.string().nullable().default(null).optional(),
  recordedAt: z.string().datetime().optional(),
});

export const repairAttemptRecordSchema = z.object({
  repairAttemptId: z.string().min(1),
  problemEventId: z.string().min(1),
  runId: z.string().min(1),
  iteration: z.number().int().nonnegative(),
  candidateId: z.string().nullable().default(null),
  repairedCandidateId: z.string().nullable().default(null),
  repairKind: repairKindSchema,
  llmPromptHash: z.string().min(1),
  llmResponseHash: z.string().min(1),
  result: repairAttemptResultSchema,
  failureReason: z.string().nullable().default(null),
  summary: z.string().min(1),
  failureSignatureHash: z.string().nullable().default(null).optional(),
  structureFamily: z.string().nullable().default(null).optional(),
  recordedAt: z.string().datetime().optional(),
});

export const autonomousMutationInputSchema = z.object({
  brief: mutationBriefSchema,
  baselinePine: z.string().min(1),
});

export type AutonomousRecordKind = z.infer<typeof autonomousRecordKindSchema>;
export type AutonomousExecutorRole = z.infer<typeof autonomousExecutorRoleSchema>;
export type AutonomousEvidenceAuthority = z.infer<typeof autonomousEvidenceAuthoritySchema>;
export type AutonomousEvaluationMode = z.infer<typeof autonomousEvaluationModeSchema>;
export type TvCalibrationStatus = z.infer<typeof tvCalibrationStatusSchema>;
export type DuplicateStatus = z.infer<typeof duplicateStatusSchema>;
export type NoveltyFingerprint = z.infer<typeof noveltyFingerprintSchema>;
export type SplitEvaluation = z.infer<typeof splitEvaluationSchema>;
export type WalkForwardFold = z.infer<typeof walkForwardFoldSchema>;
export type WalkForwardEvaluation = z.infer<typeof walkForwardEvaluationSchema>;
export type AutoSelectionBreakdown = z.infer<typeof autoSelectionBreakdownSchema>;
export type VerifiedPromotionScoreBreakdown = z.infer<
  typeof verifiedPromotionScoreBreakdownSchema
>;
export type VerifiedPromotionEvidence = z.infer<
  typeof verifiedPromotionEvidenceSchema
>;
export type LocalEvaluationBlockingReason = z.infer<
  typeof localEvaluationBlockingReasonSchema
>;
export type AutonomousLocalCompatibility = z.infer<
  typeof autonomousLocalCompatibilitySchema
>;
export type AutonomousEligibility = z.infer<typeof autonomousEligibilitySchema>;
export type AutonomousExperimentRecord = z.infer<typeof autonomousExperimentSchema>;
export type AutonomousResearchStage = z.infer<typeof autonomousResearchStageSchema>;
export type HeadEventRecord = z.infer<typeof headEventRecordSchema>;
export type HeadAuthority = z.infer<typeof headAuthoritySchema>;
export type AutonomousBranchStatus = z.infer<typeof autonomousBranchStatusSchema>;
export type AutonomousBranchRecord = z.infer<typeof autonomousBranchRecordSchema>;
export type ArchiveEventRecord = z.infer<typeof archiveEventRecordSchema>;
export type CalibrationEventRecord = z.infer<typeof calibrationEventRecordSchema>;
export type DivergenceSeverity = z.infer<typeof divergenceSeveritySchema>;
export type LocalConfidenceEventRecord = z.infer<
  typeof localConfidenceEventRecordSchema
>;
export type ProblemKind = z.infer<typeof problemKindSchema>;
export type RepairKind = z.infer<typeof repairKindSchema>;
export type RepairAttemptResult = z.infer<typeof repairAttemptResultSchema>;
export type ProblemEventRecord = z.infer<typeof problemEventRecordSchema>;
export type RepairAttemptRecord = z.infer<typeof repairAttemptRecordSchema>;
