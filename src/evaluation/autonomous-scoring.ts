import { evaluateObjective } from "./objective.js";
import {
  type ArtifactValidationResult,
  type ArtifactBundle,
  type BacktestMetrics,
  type ExperimentRecord,
  type LocalTvParitySummary,
  type ObjectiveConfig,
  type ObjectiveBreakdown,
  type ParsedMutationResponse,
} from "../contracts/types.js";
import {
  type AutoSelectionBreakdown,
  type DuplicateStatus,
  type NoveltyFingerprint,
  type SplitEvaluation,
  type TvCalibrationStatus,
  type WalkForwardEvaluation,
} from "../contracts/autonomous.js";
import {
  autoSelectionBreakdownSchema,
  duplicateStatusSchema,
  noveltyFingerprintSchema,
  splitEvaluationSchema,
  verifiedPromotionEvidenceSchema,
} from "../contracts/autonomous.js";
import { loadLocalBacktestBars } from "../automation/local-backtest/context.js";
import { parseAfStrategyConfig, type AfStrategyConfig } from "../automation/local-backtest/af-config.js";
import { simulateAfStrategy } from "../automation/local-backtest/af-simulator.js";
import { afStrategySpecToConfig } from "../strategy-spec/to-af-config.js";
import { sha256Json } from "../utils/fs.js";
import {
  buildTrialLedgerStats,
  computeMinimumVerifiedPromotionScoreFromStats,
  computeTrialBudgetPenaltyFromStats,
} from "./trial-penalty.js";
import { computeRegimeConcentrationPenalty } from "./regime-split.js";

const OBJECTIVE_POLICY_VERSION = "objective.qqq-120m/v1";
export const AUTONOMOUS_SELECTION_POLICY_VERSION = "autonomous-tv-verified/v4";
const CHRONOLOGICAL_SPLIT_RATIO = 0.7;
const VERIFIED_PROMOTION_POLICY_VERSION = "verified-promotion/v1";

export interface AutonomousScoringReferenceRecord {
  candidateId: string;
  candidateHash?: string | null;
  noveltyFingerprint?: NoveltyFingerprint | null;
}

export interface LocalSplitEvaluationInput {
  workspaceRoot: string;
  stateRoot?: string;
  pineScript: string;
  strategySpec?: unknown;
  objective: ObjectiveConfig;
  fullSampleArtifactBundle?: ArtifactBundle | null;
}

export interface AutonomousCalibrationSignal {
  currentConfidence: number | null;
  localConfidenceBonus: number;
  divergencePenalty: number;
}

export interface BuiltFingerprint {
  config: AfStrategyConfig | null;
  fingerprint: NoveltyFingerprint;
}

export function getObjectivePolicyVersion(): string {
  return OBJECTIVE_POLICY_VERSION;
}

export function getAutonomousSelectionPolicyVersion(): string {
  return AUTONOMOUS_SELECTION_POLICY_VERSION;
}

export function getVerifiedPromotionPolicyVersion(): string {
  return VERIFIED_PROMOTION_POLICY_VERSION;
}

export function buildNoveltyFingerprint(
  parsedMutation: Pick<ParsedMutationResponse, "inventory" | "pineScript" | "strategySpec">,
): BuiltFingerprint {
  const config = resolveAfConfig(parsedMutation);
  const inventoryTokens = parsedMutation.inventory
    .map((entry) => `${entry.role}:${entry.conditionId}`)
    .sort();

  const configBuckets = config ? buildConfigBuckets(config) : {};
  const featureFlags = config ? buildFeatureFlags(config) : [];
  const structureTokens = [
    ...inventoryTokens,
    ...featureFlags,
    ...Object.entries(configBuckets)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, value]) => `${key}:${value}`),
  ];

  const inventorySignature = sha256Json(inventoryTokens);
  const structureSignature = sha256Json(structureTokens);
  const fingerprintFamily = sha256Json({
    inventoryTokens,
    featureFlags,
    modes: config
      ? {
          sameBarConflictMode: config.sameBarConflictMode,
          trendMode: config.trendMode,
        }
      : {},
  });

  return {
    config,
    fingerprint: noveltyFingerprintSchema.parse({
      fingerprint: sha256Json({
        inventorySignature,
        structureSignature,
        featureFlags,
        configBuckets,
      }),
      fingerprintFamily,
      inventorySignature,
      structureSignature,
      featureFlags,
      configBuckets,
      tokens: structureTokens,
    }),
  };
}

export function classifyDuplicateStatus(input: {
  candidateId: string;
  candidateHash: string;
  noveltyFingerprint: NoveltyFingerprint;
  references: AutonomousScoringReferenceRecord[];
}): DuplicateStatus {
  const exactDuplicate = input.references.find(
    (record) =>
      record.candidateId !== input.candidateId &&
      record.candidateHash &&
      record.candidateHash === input.candidateHash,
  );
  if (exactDuplicate) {
    return duplicateStatusSchema.parse({
      classification: "exact_duplicate",
      exactDuplicateCandidateId: exactDuplicate.candidateId,
      structuralDuplicateCandidateId: null,
      duplicateFingerprint: input.noveltyFingerprint.fingerprint,
    });
  }

  const structuralDuplicate = input.references.find(
    (record) =>
      record.candidateId !== input.candidateId &&
      record.noveltyFingerprint?.fingerprintFamily ===
        input.noveltyFingerprint.fingerprintFamily,
  );
  if (structuralDuplicate) {
    return duplicateStatusSchema.parse({
      classification: "structural_duplicate",
      exactDuplicateCandidateId: null,
      structuralDuplicateCandidateId: structuralDuplicate.candidateId,
      duplicateFingerprint: input.noveltyFingerprint.fingerprintFamily,
    });
  }

  return duplicateStatusSchema.parse({
    classification: "unique",
    exactDuplicateCandidateId: null,
    structuralDuplicateCandidateId: null,
    duplicateFingerprint: null,
  });
}

export async function evaluateLocalSplit(
  input: LocalSplitEvaluationInput,
): Promise<SplitEvaluation> {
  const parsed = resolveAfConfigWithIssues({
    pineScript: input.pineScript,
    strategySpec: input.strategySpec,
  });
  if (parsed.issues.length > 0) {
    return splitEvaluationSchema.parse({
      splitMethod: "chronological_70_30",
      fullSample: emptySplitMetrics(),
      inSample: emptySplitMetrics(),
      outOfSample: emptySplitMetrics(),
      minimumOosTrades: calculateMinimumOosTrades(input.objective),
      oosEligible: false,
      oosPassed: false,
      hardGatesPassed: false,
      gateReasons: parsed.issues,
    });
  }

  const bars = await loadLocalBacktestBars(input.workspaceRoot, {
    stateRoot: input.stateRoot,
  });
  const splitIndex = Math.max(10, Math.floor(bars.length * CHRONOLOGICAL_SPLIT_RATIO));
  const boundedSplit = Math.min(Math.max(splitIndex, 10), Math.max(bars.length - 5, 10));

  const fullSample = input.fullSampleArtifactBundle
    ? buildSplitMetricsFromArtifactBundle(
        input.fullSampleArtifactBundle,
        input.objective,
      )
    : buildSplitMetrics(simulateAfStrategy(bars, parsed.config), input.objective);
  const inSampleBars = bars.slice(0, boundedSplit);
  const outOfSampleBars = bars.slice(boundedSplit);
  const inSample = buildSplitMetrics(
    simulateAfStrategy(inSampleBars, parsed.config),
    input.objective,
  );
  const minimumOosTrades = calculateMinimumOosTrades(input.objective);
  const outOfSampleObjective: ObjectiveConfig = {
    ...input.objective,
    hardGates: {
      ...input.objective.hardGates,
      minimumTotalTrades: minimumOosTrades,
    },
  };
  const outOfSample = buildSplitMetrics(
    simulateAfStrategy(outOfSampleBars, parsed.config),
    outOfSampleObjective,
  );

  const gateReasons: string[] = [];
  if (!fullSample.objectiveBreakdown?.hardGatesPassed) {
    gateReasons.push("full_sample_hard_gate_fail");
  }
  if (!outOfSample.metrics) {
    gateReasons.push("oos_metrics_missing");
  }
  if ((outOfSample.metrics?.totalTrades ?? 0) < minimumOosTrades) {
    gateReasons.push("minimum_oos_trades");
  }
  if ((outOfSample.metrics?.postFeeNetProfitPercent ?? Number.NEGATIVE_INFINITY) <= 0) {
    gateReasons.push("positive_oos_post_fee_profit");
  }
  if (!outOfSample.objectiveBreakdown?.hardGatesPassed) {
    gateReasons.push("oos_hard_gate_fail");
  }

  return splitEvaluationSchema.parse({
    splitMethod: "chronological_70_30",
    fullSample,
    inSample,
    outOfSample,
    minimumOosTrades,
    oosEligible: outOfSample.metrics != null,
    oosPassed: gateReasons.length === 0,
    hardGatesPassed: gateReasons.length === 0,
    gateReasons,
  });
}

function resolveAfConfig(
  input: Pick<ParsedMutationResponse, "pineScript" | "strategySpec">,
): AfStrategyConfig | null {
  const resolved = resolveAfConfigWithIssues(input);
  return resolved.issues.length === 0 ? resolved.config : null;
}

function resolveAfConfigWithIssues(input: {
  pineScript: string;
  strategySpec?: unknown;
}): { config: AfStrategyConfig; issues: string[] } {
  if (input.strategySpec) {
    try {
      return {
        config: afStrategySpecToConfig(input.strategySpec),
        issues: [],
      };
    } catch (error) {
      return {
        config: parseAfStrategyConfig(input.pineScript).config,
        issues: [error instanceof Error ? error.message : String(error)],
      };
    }
  }

  const parsed = parseAfStrategyConfig(input.pineScript);
  return {
    config: parsed.config,
    issues: parsed.issues,
  };
}

export function buildAutoSelectionBreakdown(input: {
  objectiveBreakdown: ObjectiveBreakdown | null;
  artifactValidation: ArtifactValidationResult | null;
  splitEvaluation: SplitEvaluation | null;
  noveltyFingerprint: NoveltyFingerprint | null;
  duplicateStatus: DuplicateStatus | null;
  referenceFingerprints: Array<NoveltyFingerprint | null | undefined>;
  referenceExperiments: ExperimentRecord[];
  config: AfStrategyConfig | null;
  candidatePathExists: boolean;
  candidateHashExists: boolean;
  mutationProvenanceValid: boolean;
  localConfidenceSignal?: AutonomousCalibrationSignal | null;
}): AutoSelectionBreakdown {
  const rejectionReasons: string[] = [];
  const baseObjectiveScore = input.objectiveBreakdown?.score ?? 0;
  if (!input.mutationProvenanceValid) {
    rejectionReasons.push("invalid_mutation_provenance");
  }
  if (!input.candidatePathExists) {
    rejectionReasons.push("candidate_source_missing");
  }
  if (!input.candidateHashExists) {
    rejectionReasons.push("candidate_hash_missing");
  }
  if (!input.artifactValidation?.hasMetrics || !input.artifactValidation?.hasTrades) {
    rejectionReasons.push("local_artifact_incomplete");
  }
  if (!input.artifactValidation?.hasEquitySummary) {
    rejectionReasons.push("equity_summary_missing");
  }
  if (!input.objectiveBreakdown?.hardGatesPassed) {
    rejectionReasons.push("objective_hard_gate_fail");
  }
  if (!input.splitEvaluation?.oosPassed) {
    rejectionReasons.push(...(input.splitEvaluation?.gateReasons ?? ["oos_gate_fail"]));
  }
  if (input.duplicateStatus?.classification === "exact_duplicate") {
    rejectionReasons.push("exact_duplicate");
  }
  if (input.duplicateStatus?.classification === "structural_duplicate") {
    rejectionReasons.push("structural_duplicate");
  }

  const robustnessScore = computeRobustnessScore(input.splitEvaluation);
  const noveltyScore = computeNoveltyScore(
    input.noveltyFingerprint,
    input.referenceFingerprints,
  );
  const diversityScore = computeDiversityScore(
    input.noveltyFingerprint,
    input.referenceFingerprints,
  );
  const familyCalibration =
    input.localConfidenceSignal == null
      ? summarizeFamilyCalibration(
          input.referenceExperiments,
          input.noveltyFingerprint?.fingerprintFamily ?? null,
        )
      : null;
  const localConfidenceBonus =
    input.localConfidenceSignal?.localConfidenceBonus ??
    computeLocalConfidenceBonus(
      familyCalibration ?? {
        averageConfidence: null,
        majorDriftCount: 0,
        totalCount: 0,
      },
    );
  const riskPenalty = input.objectiveBreakdown?.softGuardrailBreached ? 0.1 : 0;
  const overfitPenalty = computeOverfitPenalty(input.splitEvaluation);
  const duplicatePenalty =
    input.duplicateStatus?.classification === "exact_duplicate"
      ? 1
      : input.duplicateStatus?.classification === "structural_duplicate"
      ? 0.45
      : 0;
  const divergencePenalty =
    input.localConfidenceSignal?.divergencePenalty ??
    computeDivergencePenalty(
      familyCalibration ?? {
        averageConfidence: null,
        majorDriftCount: 0,
        totalCount: 0,
      },
    );
  const complexityPenalty = computeComplexityPenalty(input.config);
  const totalScore = roundScore(
    baseObjectiveScore +
      robustnessScore +
      noveltyScore +
      diversityScore +
      localConfidenceBonus -
      riskPenalty -
      overfitPenalty -
      duplicatePenalty -
      divergencePenalty -
      complexityPenalty,
  );

  return autoSelectionBreakdownSchema.parse({
    performanceScore: roundScore(baseObjectiveScore),
    baseObjectiveScore: roundScore(baseObjectiveScore),
    robustnessScore,
    noveltyScore,
    diversityScore,
    localConfidenceBonus,
    riskPenalty,
    overfitPenalty,
    duplicatePenalty,
    divergencePenalty,
    complexityPenalty,
    autoSelectionScore: totalScore,
    totalScore,
    eligible: rejectionReasons.length === 0,
    rejectionReasons,
  });
}

export function buildVerifiedPromotionScore(input: {
  localMetrics: BacktestMetrics | null | undefined;
  tvMetrics: BacktestMetrics | null | undefined;
  localCandidateHash: string | null | undefined;
  tvCandidateHash: string | null | undefined;
  tvCalibrationStatus: TvCalibrationStatus;
  localTvParity: LocalTvParitySummary | null | undefined;
  walkForwardEvaluation: WalkForwardEvaluation | null | undefined;
  config: AfStrategyConfig | null;
  referenceExperiments: ExperimentRecord[];
}) {
  const rejectionReasons: string[] = [];
  const parity = input.localTvParity ?? null;
  const walkForward = input.walkForwardEvaluation ?? null;
  const tvMetrics = input.tvMetrics ?? null;

  if (input.tvCalibrationStatus !== "verified_match") {
    rejectionReasons.push("tv_not_verified_match");
  }
  if (!input.localCandidateHash || !input.tvCandidateHash) {
    rejectionReasons.push("candidate_hash_missing");
  } else if (input.localCandidateHash !== input.tvCandidateHash) {
    rejectionReasons.push("candidate_hash_mismatch");
  }
  if (!tvMetrics) {
    rejectionReasons.push("tv_metrics_missing");
  }
  if (!parity) {
    rejectionReasons.push("parity_not_comparable");
  } else {
    if (parity.status === "not_comparable") {
      rejectionReasons.push("parity_not_comparable");
    }
    if (parity.status === "major_drift") {
      rejectionReasons.push("local_tv_major_drift");
    }
    if (Math.abs(parity.tradeCountDelta ?? Number.POSITIVE_INFINITY) > 1) {
      rejectionReasons.push("parity_trade_count_delta");
    }
    if (Math.abs(parity.netProfitPctDelta ?? Number.POSITIVE_INFINITY) > 2) {
      rejectionReasons.push("parity_net_profit_delta");
    }
    if (!parity.tradeParity || parity.tradeParity.status === "not_comparable") {
      rejectionReasons.push("trade_parity_not_comparable");
    } else {
      if (parity.tradeParity.status === "major_drift") {
        rejectionReasons.push("trade_parity_major_drift");
      }
      if ((parity.tradeParity.entryTimeMatchRatio ?? 0) < 0.95) {
        rejectionReasons.push("trade_parity_entry_time_match");
      }
      if ((parity.tradeParity.exitTimeMatchRatio ?? 0) < 0.95) {
        rejectionReasons.push("trade_parity_exit_time_match");
      }
      if ((parity.tradeParity.profitSignMatchRatio ?? 0) < 0.95) {
        rejectionReasons.push("trade_parity_profit_sign_match");
      }
      if (Math.abs(parity.tradeParity.orderCountDelta ?? Number.POSITIVE_INFINITY) > 1) {
        rejectionReasons.push("trade_parity_order_count_delta");
      }
    }
    if (!parity.eventParity || parity.eventParity.status === "not_comparable") {
      rejectionReasons.push("trace_parity_not_comparable");
    } else {
      if (parity.eventParity.status === "major_drift") {
        rejectionReasons.push("trace_parity_major_drift");
      }
      if ((parity.eventParity.eventMatchRatio ?? 0) < 0.95) {
        rejectionReasons.push("trace_parity_event_match");
      }
      if ((parity.eventParity.entryPassMatchRatio ?? 0) < 0.95) {
        rejectionReasons.push("trace_parity_entry_pass_match");
      }
      if ((parity.eventParity.exitReasonMatchRatio ?? 0) < 0.95) {
        rejectionReasons.push("trace_parity_exit_reason_match");
      }
    }
  }
  if (!walkForward) {
    rejectionReasons.push("walk_forward_missing");
  } else if (!walkForward.passed) {
    rejectionReasons.push(...walkForward.gateReasons.map((reason) => `walk_forward:${reason}`));
  }
  if (
    walkForward &&
    (walkForward as unknown as { canaryHoldout?: { exposed?: unknown } })
      .canaryHoldout?.exposed === true
  ) {
    rejectionReasons.push("canary_holdout_exposed");
  }

  const tvPerformanceScore = normalizePositive(tvMetrics?.postFeeNetProfitPercent ?? 0, 30) * 0.3;
  const walkForwardRobustnessScore =
    normalizePositive(walkForward?.medianOosPostFeeNetProfitPercent ?? 0, 15) * 0.18 +
    normalizePositive((walkForward?.medianOosProfitFactor ?? 1) - 1, 1) * 0.12;
  const foldConsistencyScore =
    walkForward && walkForward.foldCount > 0
      ? (walkForward.positiveOosFoldCount / walkForward.foldCount) * 0.15
      : 0;
  const tradeDensityScore =
    normalizePositive(walkForward?.totalOosTrades ?? 0, walkForward?.minimumTotalOosTrades ?? 60) * 0.1;
  const parityScore =
    parity?.status === "matched" &&
    parity.tradeParity?.status === "matched" &&
    parity.eventParity?.status === "matched"
      ? 0.1
      : parity?.status === "minor_drift" ||
          parity?.tradeParity?.status === "minor_drift" ||
          parity?.eventParity?.status === "minor_drift"
        ? 0.04
        : 0;
  const simplicityScore = Math.max(0, 0.05 - computeComplexityPenalty(input.config) * 0.25);
  const trialStats = buildTrialLedgerStats({
    referenceExperiments: input.referenceExperiments,
  });
  const trialBudgetPenalty = computeTrialBudgetPenaltyFromStats(trialStats);
  const complexityPenalty = computeComplexityPenalty(input.config);
  const regimeConcentrationPenalty = computeRegimeConcentrationPenalty({
    walkForwardEvaluation: walkForward,
  });
  const totalScore = roundScore(
    tvPerformanceScore +
      walkForwardRobustnessScore +
      foldConsistencyScore +
      tradeDensityScore +
      parityScore +
      simplicityScore -
      trialBudgetPenalty -
      regimeConcentrationPenalty -
      complexityPenalty,
  );
  const minimumRequiredScore = computeMinimumVerifiedPromotionScoreFromStats(trialStats);
  if (totalScore < minimumRequiredScore) {
    rejectionReasons.push("verified_score_below_threshold");
  }

  const eligible = rejectionReasons.length === 0;
  return verifiedPromotionEvidenceSchema.parse({
    eligible,
    score: eligible ? totalScore : null,
    scoreBreakdown: {
      tvPerformanceScore: roundScore(tvPerformanceScore),
      walkForwardRobustnessScore: roundScore(walkForwardRobustnessScore),
      foldConsistencyScore: roundScore(foldConsistencyScore),
      tradeDensityScore: roundScore(tradeDensityScore),
      parityScore: roundScore(parityScore),
      simplicityScore: roundScore(simplicityScore),
      trialBudgetPenalty,
      regimeConcentrationPenalty,
      complexityPenalty,
      totalScore,
      minimumRequiredScore,
    },
    rejectionReasons,
    localCandidateHash: input.localCandidateHash ?? null,
    tvCandidateHash: input.tvCandidateHash ?? null,
    localRecordKind: "local_evaluation",
    tvRecordKind: "tv_verification",
    policyVersion: VERIFIED_PROMOTION_POLICY_VERSION,
  });
}

export function computeTrialBudgetPenalty(
  referenceExperiments: ExperimentRecord[],
): number {
  return computeTrialBudgetPenaltyFromStats(
    buildTrialLedgerStats({
      referenceExperiments,
    }),
  );
}

export function computeMinimumVerifiedPromotionScore(
  referenceExperiments: ExperimentRecord[],
): number {
  return computeMinimumVerifiedPromotionScoreFromStats(
    buildTrialLedgerStats({
      referenceExperiments,
    }),
  );
}

export function buildTvFailureDecision(input: {
  failureKind: string | null | undefined;
}): "tv_surface_failure" | "tv_executor_failure" {
  return input.failureKind === "tradingview_session_closed"
    ? "tv_executor_failure"
    : "tv_surface_failure";
}

export function buildTvCalibrationStatus(input: {
  decision: string;
  parityMatched?: boolean;
}): TvCalibrationStatus {
  if (input.decision === "tv_surface_failure") {
    return "surface_failure";
  }
  if (input.decision === "tv_executor_failure") {
    return "executor_failure";
  }
  if (input.decision === "tv_artifact_failure") {
    return "artifact_failure";
  }
  if (input.decision === "tv_portability_failure") {
    return "portability_failure";
  }
  return input.parityMatched ? "verified_match" : "verified_diverged";
}

function calculateMinimumOosTrades(objective: ObjectiveConfig): number {
  return Math.max(15, Math.ceil(objective.hardGates.minimumTotalTrades * 0.25));
}

function buildSplitMetrics(
  result: ReturnType<typeof simulateAfStrategy>,
  objective: ObjectiveConfig,
) {
  const metrics = result.metrics;
  const objectiveBreakdown =
    metrics.totalTrades > 0 ? evaluateObjective(metrics, objective) : null;

  return {
    metrics,
    objectiveBreakdown,
    trades: result.artifactBundle.trades,
    equity: result.artifactBundle.equity,
  };
}

function buildSplitMetricsFromArtifactBundle(
  artifactBundle: ArtifactBundle,
  objective: ObjectiveConfig,
) {
  const metrics = artifactBundle.strategy;
  const objectiveBreakdown =
    metrics && metrics.totalTrades > 0 ? evaluateObjective(metrics, objective) : null;

  return {
    metrics,
    objectiveBreakdown,
    trades: artifactBundle.trades,
    equity: artifactBundle.equity,
  };
}

function emptySplitMetrics() {
  return {
    metrics: null,
    objectiveBreakdown: null,
    trades: [],
    equity: null,
  };
}

function buildConfigBuckets(config: AfStrategyConfig): Record<string, string> {
  return {
    trendMode: config.trendMode,
    sameBarConflictMode: config.sameBarConflictMode,
    maxSlots: bucketNumber(config.maxSlots, [6, 12, 18, 24]),
    confirmBars: bucketNumber(config.confirmBars, [1, 2, 3, 5]),
    entryCooldownBars: bucketNumber(config.entryCooldownBars, [0, 1, 3, 5]),
    riskOffRsi: bucketNumber(config.riskOffRsi, [35, 45, 55, 65]),
    slotPct: bucketNumber(config.slotPct, [5, 10, 15, 20, 25]),
    supertrendFactor: bucketNumber(config.supertrendFactor, [2, 3, 4, 5]),
    weakExitBars: bucketNumber(config.weakExitBars, [3, 5, 8, 12]),
  };
}

function buildFeatureFlags(config: AfStrategyConfig): string[] {
  return [
    config.useReplacement ? "replacement:on" : "replacement:off",
    config.useSupertrendFilter ? "supertrend:on" : "supertrend:off",
    config.enableWeakRangeExit ? "weak_exit:on" : "weak_exit:off",
    config.allowStrongCounterTrend ? "counter_trend:on" : "counter_trend:off",
    config.closeAllOnBearConfRiskOff ? "riskoff_close_all:on" : "riskoff_close_all:off",
    config.applyFilterToB1 ? "b1_filter:on" : "b1_filter:off",
    config.resetOnL3 ? "reset_on_l3:on" : "reset_on_l3:off",
    config.useRealFillSync ? "real_fill_sync:on" : "real_fill_sync:off",
  ];
}

function computeRobustnessScore(splitEvaluation: SplitEvaluation | null): number {
  if (!splitEvaluation?.outOfSample.objectiveBreakdown) {
    return 0;
  }

  const fullScore = splitEvaluation.fullSample.objectiveBreakdown?.score ?? 0;
  const oosScore = splitEvaluation.outOfSample.objectiveBreakdown.score;
  const gapPenalty = Math.min(Math.abs(fullScore - oosScore), 0.25);
  return roundScore(Math.max(0, oosScore * 0.25 - gapPenalty));
}

function computeNoveltyScore(
  fingerprint: NoveltyFingerprint | null,
  references: Array<NoveltyFingerprint | null | undefined>,
): number {
  if (!fingerprint) {
    return 0;
  }

  const comparable = references.filter(
    (entry): entry is NoveltyFingerprint => entry != null,
  );
  if (comparable.length === 0) {
    return 0.2;
  }

  const candidateTokens = new Set(fingerprint.tokens);
  const averageDistance =
    comparable.reduce((sum, reference) => {
      const referenceTokens = new Set(reference.tokens);
      const intersectionSize = [...candidateTokens].filter((token) =>
        referenceTokens.has(token),
      ).length;
      const unionSize = new Set([
        ...candidateTokens,
        ...referenceTokens,
      ]).size;
      const distance = unionSize === 0 ? 0 : 1 - intersectionSize / unionSize;
      return sum + distance;
    }, 0) / comparable.length;

  return roundScore(Math.max(0, Math.min(0.3, averageDistance * 0.3)));
}

function computeDiversityScore(
  fingerprint: NoveltyFingerprint | null,
  references: Array<NoveltyFingerprint | null | undefined>,
): number {
  if (!fingerprint) {
    return 0;
  }

  const comparable = references.filter(
    (entry): entry is NoveltyFingerprint => entry != null,
  );
  if (comparable.length === 0) {
    return 0.12;
  }

  const candidateTokens = new Set(fingerprint.tokens);
  const nearestDistance = comparable.reduce((nearest, reference) => {
    const referenceTokens = new Set(reference.tokens);
    const intersectionSize = [...candidateTokens].filter((token) =>
      referenceTokens.has(token),
    ).length;
    const unionSize = new Set([
      ...candidateTokens,
      ...referenceTokens,
    ]).size;
    const distance = unionSize === 0 ? 0 : 1 - intersectionSize / unionSize;
    return Math.min(nearest, distance);
  }, 1);

  return roundScore(Math.max(0, Math.min(0.2, nearestDistance * 0.2)));
}

function computeOverfitPenalty(splitEvaluation: SplitEvaluation | null): number {
  if (!splitEvaluation) {
    return 0;
  }

  const fullScore = splitEvaluation.fullSample.objectiveBreakdown?.score;
  const oosScore = splitEvaluation.outOfSample.objectiveBreakdown?.score;
  if (fullScore == null || oosScore == null) {
    return 0;
  }

  const scoreGap = Math.max(0, fullScore - oosScore);
  const oosTradeShortfall = Math.max(
    0,
    splitEvaluation.minimumOosTrades -
      (splitEvaluation.outOfSample.metrics?.totalTrades ?? 0),
  );
  const gatePenalty = splitEvaluation.oosPassed ? 0 : 0.05;
  return roundScore(
    Math.min(
      0.35,
      scoreGap * 0.4 + oosTradeShortfall * 0.01 + gatePenalty,
    ),
  );
}

function summarizeFamilyCalibration(
  experiments: ExperimentRecord[],
  fingerprintFamily: string | null,
): {
  averageConfidence: number | null;
  majorDriftCount: number;
  totalCount: number;
} {
  if (!fingerprintFamily) {
    return {
      averageConfidence: null,
      majorDriftCount: 0,
      totalCount: 0,
    };
  }

  const matchingTvRecords = experiments.filter((record) => {
    const candidateRecord = record as Record<string, unknown>;
    const recordKind = candidateRecord.recordKind;
    const noveltyFingerprint = candidateRecord.noveltyFingerprint as
      | { fingerprintFamily?: unknown }
      | undefined;
    return (
      recordKind === "tv_verification" &&
      noveltyFingerprint?.fingerprintFamily === fingerprintFamily
    );
  });
  if (matchingTvRecords.length === 0) {
    return {
      averageConfidence: null,
      majorDriftCount: 0,
      totalCount: 0,
    };
  }

  const confidenceValues = matchingTvRecords
    .map((record) =>
      typeof (record as Record<string, unknown>).localConfidence === "number"
        ? ((record as Record<string, unknown>).localConfidence as number)
        : null,
    )
    .filter((value): value is number => value != null);
  const averageConfidence =
    confidenceValues.length === 0
      ? null
      : confidenceValues.reduce((sum, value) => sum + value, 0) /
        confidenceValues.length;
  const majorDriftCount = matchingTvRecords.filter((record) => {
    const parity = (record as Record<string, unknown>).localTvParity as
      | { status?: unknown }
      | null
      | undefined;
    return parity?.status === "major_drift";
  }).length;
  return {
    averageConfidence,
    majorDriftCount,
    totalCount: matchingTvRecords.length,
  };
}

function computeLocalConfidenceBonus(input: {
  averageConfidence: number | null;
  majorDriftCount: number;
  totalCount: number;
}): number {
  if (input.averageConfidence == null || input.majorDriftCount > 0) {
    return 0;
  }
  return roundScore(Math.max(0, Math.min(0.12, (input.averageConfidence - 0.75) * 0.3)));
}

function computeDivergencePenalty(input: {
  averageConfidence: number | null;
  majorDriftCount: number;
  totalCount: number;
}): number {
  if (input.totalCount === 0) {
    return 0;
  }

  const majorDriftRate = input.majorDriftCount / input.totalCount;
  const confidencePenalty =
    input.averageConfidence == null ? 0 : Math.max(0, 0.8 - input.averageConfidence) * 0.2;
  return roundScore(Math.min(0.2, majorDriftRate * 0.15 + confidencePenalty));
}

export function estimateHistoricalLocalConfidence(input: {
  experiments: ExperimentRecord[];
  fingerprintFamily: string | null;
}): number {
  const familyCalibration = summarizeFamilyCalibration(
    input.experiments,
    input.fingerprintFamily,
  );
  return roundScore(
    familyCalibration.averageConfidence == null
      ? 1
      : Math.max(0.5, Math.min(1, familyCalibration.averageConfidence)),
  );
}

function computeComplexityPenalty(config: AfStrategyConfig | null): number {
  if (!config) {
    return 0.05;
  }

  const enabledFlags = [
    config.useReplacement,
    config.useSupertrendFilter,
    config.enableWeakRangeExit,
    config.allowStrongCounterTrend,
    config.applyFilterToB1,
    config.supertrendRiskOffEnabled,
    config.supertrendBlocksWeakBull,
    config.closeAllOnBearConfRiskOff,
  ].filter(Boolean).length;
  const parameterPenalty =
    (config.maxSlots > 18 ? 0.02 : 0) +
    (config.entryCooldownBars > 0 ? 0.01 : 0) +
    (config.confirmBars > 2 ? 0.01 : 0);
  return roundScore(Math.min(0.15, enabledFlags * 0.01 + parameterPenalty));
}

function normalizePositive(value: number, cap: number): number {
  if (!Number.isFinite(value) || cap <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(1, value / cap));
}

function bucketNumber(value: number, cutoffs: number[]): string {
  for (const cutoff of cutoffs) {
    if (value <= cutoff) {
      return `lte_${cutoff}`;
    }
  }
  return `gt_${cutoffs[cutoffs.length - 1] ?? 0}`;
}

function roundScore(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}
