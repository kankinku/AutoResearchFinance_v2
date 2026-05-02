import { readFile } from "node:fs/promises";

import {
  type ExperimentRecord,
  type AutonomousIterationLearningRecord,
  type LocalCompatibilityIssue,
  type LocalCompatibilityContract,
  type MutationBrief,
  type MutationBriefRecord,
  type MutationProvenance,
  type ObjectiveConfig,
  type ParsedMutationResponse,
  type SeedStrategyReference,
} from "../../contracts/types.js";
import {
  type ArchiveEventRecord,
  type CalibrationEventRecord,
  type HeadEventRecord,
  type LocalConfidenceEventRecord,
  type ProblemEventRecord,
  type RepairAttemptRecord,
  type RepairKind,
} from "../../contracts/autonomous.js";
import {
  getAfLocalCompatibilityContract,
  summarizeAfCompatibilityIssues,
} from "../../automation/local-backtest/af-config.js";
import { persistCandidateArtifact } from "../../mutation/candidate-store.js";
import { type MutationLlmClient } from "../../mutation/llm-client.js";
import {
  parseMutationResponseStrict,
  parseMutationResponseWithRecovery,
} from "../../mutation/parser.js";
import {
  formatPreflightIssuesForRepair,
  inspectGeneratedMutation,
  repairTimeBoxedVariantPreflightIssues,
} from "../../mutation/preflight.js";
import { writeMutationRuntimeArtifact } from "../../mutation/runtime-artifact.js";
import { loadSeedStrategyReference, readActiveBaseline } from "../seed-strategy.js";
import {
  appendCandidateLedgerRecord,
  appendIncidentRecord,
  appendMutationBriefRecord,
  appendProblemEventRecord,
  appendRepairAttemptRecord,
} from "../../state/jsonl-store.js";
import { findActiveChampionRecord } from "../../state/autonomous-state.js";
import { createCandidateId, sha256 } from "../../utils/fs.js";
import {
  AUTORESEARCH_CONTRACT_VERSION,
  STRATEGY_SPEC_MUTATION_AUTHORITY,
} from "../../policy/autoresearch-contract.js";
import { buildLocalConfidenceSummary } from "./divergence-update-phase.js";
import {
  buildSchemaHardeningSummary,
  buildSchemaRegenerateBrief,
} from "./llm-repair-phase.js";
import { type MutationSchemaMode } from "../../policy/autoresearch-contract.js";

const RESPONSE_SCHEMA_VERSION = "parsed-mutation-response/v2";
const STAGNATION_MIN_ITERATIONS_WITHOUT_CHAMPION = 24;
const STAGNATION_MIN_RECENT_EVALUATIONS = 10;
const STAGNATION_MIN_RECENT_ELIGIBLE = 3;
const STAGNATION_SCORE_EPSILON = 0.0005;
const BREAKOUT_OUTCOME_WINDOW = 80;
const SPARSE_PATTERN_WINDOW = 20;
const SPARSE_CLUSTER_MIN_COUNT = 8;
const ROUTE_SUPPRESSION_MIN_FAILURES = 3;
const DEFAULT_BREAKOUT_FALLBACK_ROUTE_ID = "time_boxed_event_rotation";
const TIME_BOXED_ROUTE_ID = "time_boxed_event_rotation";
const TIME_BOXED_VARIANT_ESCALATION_MIN_COUNT = 4;
const DEFAULT_EXPLORATION_BUDGET = {
  championExploitPct: 50,
  frontierExploitPct: 20,
  breakoutPct: 20,
  nearMissRepairPct: 5,
  simplificationPct: 5,
} as const;

const EXPLORATION_BREAKOUT_ROUTES = [
  {
    routeId: "event_reclaim_reversal",
    routeSummary:
      "Build a new event-reclaim reversal family: enter only after a fresh failed breakdown or bullish reclaim event, avoid BCONF/rank carry-forward, and use simple time or weakness exits.",
  },
  {
    routeId: "momentum_continuation_pullback",
    routeSummary:
      "Build a new momentum-continuation pullback family: enter after expansion plus a short pullback/reclaim, allow at most one lightweight regime filter, and avoid stacked confirmations.",
  },
  {
    routeId: "mean_reversion_reentry",
    routeSummary:
      "Build a new mean-reversion reentry family: enter after an oversold or weak-range reset reclaims the AF baseline, without preserving the accepted-head slot/rank scaffold.",
  },
  {
    routeId: "volatility_compression_release",
    routeSummary:
      "Build a new volatility-compression release family: enter on compression release with broad trade opportunity density, no cooldown-heavy entry stack, and simple exits.",
  },
  {
    routeId: "time_boxed_event_rotation",
    routeSummary:
      "Build a new time-boxed event rotation family: open across broad post-event windows with explicit time exits, zero or low cooldown, and no weak-exit-only or supertrend-only mutation.",
  },
] as const;

const TIME_BOXED_EVENT_ROTATION_VARIANTS = [
  {
    variantId: "dual_event_age_windows",
    summary:
      "Use two broad event-age windows: one after fresh bullish exhaustion and one rebound window after fresh bearish exhaustion.",
    forcedRules: [
      "Define eventFloorBars with default 4 or 5 and derive earlyBullEvent and earlyBearEvent from bull/bear progress reaching that floor; feed the event windows from these dense early events.",
      "Define separate postBullEventWindow and postBearReboundWindow booleans and combine them with OR as the only primary entry trigger.",
      "Use broad event-age windows of at least 10 bars and do not require breakout above a band, reclaim of a recent high, L1/L2/L3, or BCONF confirmation.",
      "Open event-age windows from age 0; do not require bullEventAge or bearEventAge to be greater than or equal to eventFloorBars before entry.",
      "After primaryEntryTrigger, allow at most one lightweight risk-off exclusion; remove trend, supertrend, overextension, rank, and confirmation stacks from entryPass.",
      "Keep entry cooldown at zero or one bar and use a simple slot age time exit of 4 to 8 bars.",
    ],
    forbiddenPatterns: [
      "Do not use AF L1/L2/L3, bullCandidate, bullStrong, or bullConfirmed as the only event source.",
      "Do not delay the entry window with bullEventAge >= eventFloorBars or bearEventAge >= eventFloorBars.",
      "Do not use a single narrow event window that reproduces the 31/7 trade profile.",
      "Do not require Bollinger-band expansion, compression release, high reclaim, or stacked confirmation for the primary entry.",
      "Do not define entryPass as primaryEntryTrigger plus multiple filters such as trendPass, riskPass, supertrendEntryPass, and overextended.",
    ],
  },
  {
    variantId: "thresholdless_event_age_rotation",
    summary:
      "Remove price-threshold reclaims from the primary entry and rotate purely on event age plus one lightweight risk-off exclusion.",
    forcedRules: [
      "Define eventFloorBars with default 4 or 5 and trigger event age from earlyBullEvent and earlyBearEvent before L1/L2/L3 milestones.",
      "Make the primary entry an event-age condition with no close-over-high, no close-over-band, and no volatility expansion requirement.",
      "Open event-age windows from age 0; do not require bullEventAge or bearEventAge to be greater than or equal to eventFloorBars before entry.",
      "After primaryEntryTrigger, allow at most one lightweight risk-off exclusion; remove trend, supertrend, overextension, rank, and confirmation stacks from entryPass.",
      "Allow both bullish-event continuation and bearish-event rebound participation unless riskOff is active.",
      "Exit primarily by fixed time-in-slot and seed bearish reductions; do not add a profit-only or weak-exit-only dependency.",
    ],
    forbiddenPatterns: [
      "Do not use AF L1/L2/L3, bullCandidate, bullStrong, or bullConfirmed as the only event source.",
      "Do not delay the entry window with bullEventAge >= eventFloorBars or bearEventAge >= eventFloorBars.",
      "Do not gate the primary entry behind close > high[1], close > upperBand, compression release, or a reclaim threshold.",
      "Do not add a new EMA stack, ADX filter, supertrend filter, or multi-stage confirmation to recover robustness.",
      "Do not define entryPass as primaryEntryTrigger plus multiple filters such as trendPass, riskPass, supertrendEntryPass, and overextended.",
    ],
  },
  {
    variantId: "slot_turnover_rotation",
    summary:
      "Increase turnover by allowing rotation entries while stale slots are retired by simple slot age rules.",
    forcedRules: [
      "Define eventFloorBars with default 4 or 5 and trigger rotation from earlyBullEvent and earlyBearEvent before L1/L2/L3 milestones.",
      "Keep the event entry broad, retire stale slots by age, and permit replacement without waiting for rank or weak-range confirmation.",
      "Open event-age windows from age 0; do not require bullEventAge or bearEventAge to be greater than or equal to eventFloorBars before entry.",
      "After primaryEntryTrigger, allow at most one lightweight risk-off exclusion; remove trend, supertrend, overextension, rank, and confirmation stacks from entryPass.",
      "Use max one lightweight participation filter and keep cooldown effectively off.",
      "Use deterministic time exits before optimizing profit thresholds, so trade count cannot remain pinned near 31/7.",
    ],
    forbiddenPatterns: [
      "Do not use AF L1/L2/L3, bullCandidate, bullStrong, or bullConfirmed as the only event source.",
      "Do not delay the entry window with bullEventAge >= eventFloorBars or bearEventAge >= eventFloorBars.",
      "Do not rely on replacement rank, weak-range cleanup, or supertrend state as the main source of entry frequency.",
      "Do not preserve a sparse fixed slot lifecycle that keeps full-sample trades near 31.",
      "Do not define entryPass as primaryEntryTrigger plus multiple filters such as trendPass, riskPass, supertrendEntryPass, and overextended.",
    ],
  },
] as const;

type ExplorationBreakoutRoute = (typeof EXPLORATION_BREAKOUT_ROUTES)[number];
type ExplorationBreakoutRouteId = ExplorationBreakoutRoute["routeId"];

interface MonitorLike {
  log: (
    event: string,
    message: string,
    details?: Record<string, unknown>,
  ) => Promise<void>;
}

interface PendingSuccessfulRepairAttempt {
  problemEventId: string;
  candidateId: string | null;
  repairKind: RepairKind;
  llmPromptHash: string;
  llmResponseHash: string;
  summary: string;
  failureSignatureHash?: string | null;
  structureFamily?: string | null;
}

export interface AutonomousMutationPlan {
  brief: MutationBrief;
  briefHash: string;
  baselinePine: string;
  baselineCandidateId: string | null;
  parentCandidateId: string | null;
  seedStrategy: SeedStrategyReference & { candidateHash: string };
  activeChampion: ReturnType<typeof findActiveChampionRecord>;
}

export interface AutonomousMutationOutput {
  parsedMutation: ParsedMutationResponse;
  candidateArtifact: Awaited<ReturnType<typeof persistCandidateArtifact>>;
  mutationProvenance: MutationProvenance;
  brief: MutationBrief;
  briefHash: string;
}

export async function prepareAutonomousMutationPlan(input: {
  workspaceRoot: string;
  objective: ObjectiveConfig;
  experiments: ExperimentRecord[];
  headEvents: HeadEventRecord[];
  archiveEvents: ArchiveEventRecord[];
  calibrationEvents: CalibrationEventRecord[];
  confidenceEvents?: LocalConfidenceEventRecord[];
  problemEvents?: ProblemEventRecord[];
  repairAttempts?: RepairAttemptRecord[];
  mutationBriefs?: MutationBriefRecord[];
  iterationRecords?: AutonomousIterationLearningRecord[];
  ignoreCalibrationGuidance?: boolean;
}): Promise<AutonomousMutationPlan> {
  const seedStrategy = await loadSeedStrategyReference(input.workspaceRoot);
  const localCompatibilityContract = getAfLocalCompatibilityContract();
  const minimumOosTrades = calculateMinimumOosTradeTarget(
    input.objective.hardGates.minimumTotalTrades,
  );
  const activeChampion = findActiveChampionRecord({
    records: input.experiments,
    headEvents: input.headEvents,
  });

  const recentFailures = summarizeRecentFailures(
    input.experiments,
    input.calibrationEvents,
    input.problemEvents ?? [],
  );
  const failureSignatureSummary = summarizeFailureSignatures(
    input.problemEvents ?? [],
  );
  const failureEscalation = summarizeFailureEscalation(
    input.problemEvents ?? [],
    input.repairAttempts ?? [],
  );
  const duplicatePressure = input.archiveEvents.filter(
    (event) => event.eventKind === "archive_added",
  ).length;
  const recentRepairOutcomes = summarizeRecentRepairOutcomes(
    input.repairAttempts ?? [],
    input.problemEvents ?? [],
  );
  const unsupportedPatternMemory = summarizeUnsupportedPatternMemory(
    input.problemEvents ?? [],
  );
  const localCompatibleRate = calculateLocalCompatibleRate(input.experiments);
  const repeatedLocalUnsupported =
    (input.problemEvents ?? [])
      .slice(-3)
      .filter((event) => event.problemKind === "local_unsupported").length >= 2;
  const problemPressure = summarizeProblemPressure(
    input.experiments,
    input.problemEvents ?? [],
  );
  const repeatedTradeRetentionCluster =
    problemPressure.repeatedLowTradeCount && problemPressure.repeatedOosFailure;
  const archiveGapSummary = summarizeArchiveGap(
    input.archiveEvents,
    problemPressure,
  );
  const rawConfidenceSummary = buildLocalConfidenceSummary(
    input.confidenceEvents ?? [],
  );
  const ignoreCalibrationGuidance = input.ignoreCalibrationGuidance === true;
  const confidenceSummary = ignoreCalibrationGuidance
    ? buildCalibrationSkippedConfidenceSummary(rawConfidenceSummary)
    : rawConfidenceSummary;
  const stagnationSummary = summarizeAutonomousStagnation({
    experiments: input.experiments,
    activeChampion,
  });
  const breakoutOutcomeMemory = buildBreakoutOutcomeMemory({
    experiments: input.experiments,
    mutationBriefs: input.mutationBriefs ?? [],
    minimumOosTrades,
  });
  const iterationRecordMemory = buildIterationRecordMemory(
    input.iterationRecords ?? [],
  );
  const promotionDiagnostics = buildPromotionDiagnostics(input.experiments);
  const explorationDirective = resolveExplorationDirective({
    experiments: input.experiments,
    activeChampion,
    problemPressure,
    repeatedTradeRetentionCluster,
    failureEscalation,
    stagnationSummary,
    breakoutOutcomeMemory,
    ignoreCalibrationGuidance,
  });
  const explorationBreakoutActive = explorationDirective != null;
  const breakoutVariantDirective = buildBreakoutVariantDirective({
    experiments: input.experiments,
    mutationBriefs: input.mutationBriefs ?? [],
    minimumOosTrades,
    breakoutOutcomeMemory,
    explorationDirective,
  });
  const calibrationBaselineCandidate =
    explorationBreakoutActive || ignoreCalibrationGuidance
      ? null
      : selectCalibrationGuidedBaselineCandidate({
          experiments: input.experiments,
          confidenceSummary,
        });
  const baselineCandidate = explorationBreakoutActive
    ? null
    : calibrationBaselineCandidate ??
      (activeChampion?.candidatePath != null ? activeChampion : null);
  const baselineCandidateId = baselineCandidate?.candidateId ?? null;
  const baselinePine =
    baselineCandidate?.candidatePath != null
      ? await readFile(baselineCandidate.candidatePath, "utf8")
      : await readActiveBaseline(input.workspaceRoot);
  const divergenceSummary = summarizeDivergencePressure(confidenceSummary);
  const schemaHardeningRequired = (input.problemEvents ?? [])
    .slice(-3)
    .some(
      (event) =>
        event.problemKind === "mutation_generation_fail" ||
        event.problemKind === "llm_schema_fail",
    );
  const unsupportedReasonSummary = summarizeUnsupportedReasons(
    input.problemEvents ?? [],
  );
  const candidateBehaviorChangeSummary = buildCandidateBehaviorChangeSummary({
    confidenceSummary,
    unsupportedReasonSummary,
    repeatedLocalUnsupported,
    repeatedTradeRetentionCluster,
    repeatedDuplicate: problemPressure.repeatedDuplicate,
    schemaHardeningRequired,
    explorationBreakoutActive,
  });
  const baseNextMutationDirection = explorationDirective
    ? [
        "Use only ledger-derived evidence. Exploration breakout mode is active because recent autonomous search is stagnant or repeatedly collapsing trade count.",
        `Selected breakout route ${explorationDirective.routeId}: ${explorationDirective.routeSummary}`,
        "Do not recover by reverting to the current champion family, loosening the same entry gates, or tuning the same weak-exit/rank/supertrend neighborhood.",
        `Generate a materially different AF-compatible structure that still clears at least ${input.objective.hardGates.minimumTotalTrades} full-sample trades and ${minimumOosTrades} out-of-sample trades with positive OOS post-fee profit.`,
        "Coordinated entry, exit, risk, and replacement changes are allowed when needed for the new family.",
        explorationDirective.ignoredCalibrationGuidance
          ? "TradingView calibration guidance is intentionally skipped for this route; do not use low-divergence carry-forward as a parent-selection constraint."
          : "",
      ].filter(Boolean).join(" ")
    : activeChampion
      ? failureEscalation.redirectStructureFamily
      ? `Use only ledger-derived evidence. Stop repairing the repeated failure family ${failureEscalation.redirectStructureFamily} and redirect toward an underexplored AF structure with different entry logic, while preserving the local compatibility contract.`
      : repeatedLocalUnsupported
      ? "Use only ledger-derived evidence. Prioritize strict AF local compatibility first, then preserve champion strengths while changing only one localized behavior block."
      : repeatedTradeRetentionCluster
        ? `Use only ledger-derived evidence. Recent AF candidates keep collapsing into sparse trade profiles near the OOS floor. Force a materially simpler, trade-retentive structure with one primary entry trigger, lighter confirmation pressure, shorter cooldown or lookback friction, and broader trade retention. Remove secondary filters instead of adding new ones. Target at least ${input.objective.hardGates.minimumTotalTrades} full-sample trades and ${minimumOosTrades} out-of-sample trades while keeping OOS post-fee profit positive.`
      : problemPressure.repeatedLowTradeCount
        ? `Use only ledger-derived evidence. Increase trade frequency without breaking the AF contract by reducing over-filtering, shortening confirmation or cooldown pressure, and avoiding low-trade structures. Target at least ${input.objective.hardGates.minimumTotalTrades} full-sample trades and ${minimumOosTrades} out-of-sample trades.`
        : problemPressure.repeatedDuplicate
          ? "Use only ledger-derived evidence. Force a materially different fingerprint family from recent archive and rejection memory instead of tuning the same structure."
          : problemPressure.repeatedOosFailure
            ? "Use only ledger-derived evidence. Preserve candidate viability but redesign toward stronger out-of-sample retention and fewer fragile filters."
      : schemaHardeningRequired
        ? "Use only ledger-derived evidence. Harden response structure and field completeness first so the next candidate is strict-schema, AF-compatible, and materially different from recent failures."
        : "Use only ledger-derived evidence. Preserve empirical strengths of the current champion, but force a materially different structure or condition mix that improves robustness and avoids duplicate fingerprints."
    : failureEscalation.redirectStructureFamily
      ? `Use only ledger-derived evidence. Abandon the repeated failure family ${failureEscalation.redirectStructureFamily} and redirect to a new AF structure with simpler, trade-retentive behavior.`
      : repeatedLocalUnsupported
      ? "Use only ledger-derived evidence. First restore AF local compatibility by emitting the required AF inputs/functions exactly, then explore a materially distinct structure."
      : repeatedTradeRetentionCluster
        ? `Use only ledger-derived evidence. Recent candidates repeatedly stall around a sparse trade-retention cluster. Start from a materially different AF structure that uses one primary entry trigger, lighter confirmation pressure, and simpler exits. Remove secondary filters or cooldown-heavy logic, and target at least ${input.objective.hardGates.minimumTotalTrades} full-sample trades plus ${minimumOosTrades} out-of-sample trades before optimizing profit.`
      : problemPressure.repeatedLowTradeCount
        ? `Use only ledger-derived evidence. Recover sufficient trade count first by simplifying entry gating and avoiding sparse trade structures before optimizing profit. Target at least ${input.objective.hardGates.minimumTotalTrades} full-sample trades and ${minimumOosTrades} out-of-sample trades.`
        : problemPressure.repeatedDuplicate
          ? "Use only ledger-derived evidence. Avoid the recent duplicate fingerprint family entirely and redirect toward an underexplored AF structure."
      : problemPressure.repeatedOosFailure
        ? "Use only ledger-derived evidence. Improve out-of-sample stability and post-fee profitability before adding more feature complexity."
      : "Use only ledger-derived evidence. Explore a materially distinct AF-compatible structure from the seed and optimize for novelty plus robustness without relying on generic trading heuristics.";
  const nextMutationDirection = [
    baseNextMutationDirection,
    buildPromotionDiagnosticInstruction(promotionDiagnostics),
    `Exploration budget is fixed for planner reasoning: champion exploit ${DEFAULT_EXPLORATION_BUDGET.championExploitPct}%, frontier exploit ${DEFAULT_EXPLORATION_BUDGET.frontierExploitPct}%, breakout ${DEFAULT_EXPLORATION_BUDGET.breakoutPct}%, near-miss repair ${DEFAULT_EXPLORATION_BUDGET.nearMissRepairPct}%, simplification ${DEFAULT_EXPLORATION_BUDGET.simplificationPct}%.`,
    explorationBreakoutActive
      ? "Use the AF seed/core source as the implementation starting point and treat the active champion only as a score guardrail, not as a structure to preserve."
      : baselineCandidateId
        ? ignoreCalibrationGuidance
          ? `Mutate from active local baseline candidate ${baselineCandidateId}; TradingView calibration carry-forward is disabled for this plan.`
          : `Mutate from calibration-guided baseline candidate ${baselineCandidateId} unless duplicate pressure or failure memory requires a family redirect.`
        : null,
    explorationBreakoutActive
      ? "Calibration carry-forward is disabled during exploration breakout; local-first diversity and trade-count guardrails take precedence."
      : buildCalibrationFamilyDirective(confidenceSummary),
    explorationBreakoutActive
      ? buildBreakoutOutcomeDirective(breakoutOutcomeMemory)
      : null,
    breakoutVariantDirective
      ? buildBreakoutVariantDirectiveText(breakoutVariantDirective)
      : null,
    iterationRecordMemory.directive,
    unsupportedReasonSummary
      ? `Local compatibility memory: ${unsupportedReasonSummary}`
      : null,
  ]
    .filter((value): value is string => typeof value === "string" && value.length > 0)
    .join(" ");

  const brief: MutationBrief = {
    objective:
      "Autonomous local-first research. Optimize the existing objective score while increasing novelty and out-of-sample robustness. Use only ledger-derived evidence from the provided context; do not rely on generic human trading intuition.",
    guardrails: {
      minimumTotalTrades: input.objective.hardGates.minimumTotalTrades,
      minimumPostFeeNetProfitPercent:
        input.objective.hardGates.minimumPostFeeNetProfitPercent,
      maximumStrategyDrawdownPercent:
        input.objective.softGuardrails.maximumStrategyDrawdownPercent,
    },
    repairMode:
      explorationBreakoutActive
        ? "exploration_breakout"
        : repeatedLocalUnsupported || problemPressure.repeatedLowTradeCount
        ? "entry_recovery"
        : problemPressure.repeatedOosFailure
          ? "exit_profit_repair"
          : "balanced",
    acceptedHead: activeChampion
      ? {
          candidateId: activeChampion.candidateId,
          score: activeChampion.candidateScore ?? activeChampion.autoSelectionScore ?? 0,
          summary: activeChampion.mutationBriefSummary ?? "Current autonomous champion.",
          metrics: activeChampion.testerMetrics ?? undefined,
          tradeRetentionTarget:
            activeChampion.testerMetrics?.totalTrades != null
              ? Math.max(
                  input.objective.hardGates.minimumTotalTrades,
                  Math.floor(activeChampion.testerMetrics.totalTrades * 0.75),
                )
              : undefined,
        }
      : null,
    seedStrategy,
    improvementSource: activeChampion ? "accepted_head" : "seed",
    recentFailures,
    localCompatibilityContract,
    localCompatibilityContractHash: sha256(
      JSON.stringify(localCompatibilityContract),
    ),
    unsupportedPatternMemory,
    failureSignatureSummary: failureSignatureSummary.summaries,
    failureSignatureHashes: failureSignatureSummary.hashes,
    recentRepairOutcomes,
    localCompatibleRate,
    archiveGapSummary,
    archiveGapSummaryHash: sha256(archiveGapSummary),
    divergenceSummary,
    recentCalibrationSummary: confidenceSummary.recentCalibrationSummary,
    highDivergenceFamilies: confidenceSummary.highDivergenceFamilies,
    lowDivergenceFamilies: confidenceSummary.lowDivergenceFamilies,
    confidenceAdjustmentSummary: confidenceSummary.confidenceAdjustmentSummary,
    calibrationAwareInstruction: confidenceSummary.calibrationAwareInstruction,
    unsupportedReasonSummary,
    schemaHardeningSummary: buildSchemaHardeningSummary(
      input.problemEvents ?? [],
    ),
    explorationDirective: explorationDirective ?? undefined,
    breakoutOutcomeMemory,
    breakoutVariantDirective,
    candidateBehaviorChangeSummary,
    explorationBudget: DEFAULT_EXPLORATION_BUDGET,
    promotionDiagnostics,
    recentCompileErrors: [],
    recentCompileFailureClasses: [],
    recentLossAnalysis: {
      status: "market_context_unavailable",
      summary:
        "Use recent empirical failures, duplicates, and calibration drift as negative memory. Do not overfit to a single period or a tiny number of trades.",
      topLossZones: [],
      repairPriorities: [],
    },
    researchContext: {
      status: "none",
      summary:
        "No external human research context is available. Use only local ledger evidence, archive diversity gaps, failure memory, and calibration drift.",
      matchedProblemTags: [],
      relevantKnowledgeIds: [],
      insights: [],
    },
    lossHotZones: [],
    repairPriorities: [
      ...(explorationBreakoutActive
        ? [
            "exploration_breakout",
            "rotate_structure_family",
            "ignore_calibration_carry_forward",
            "avoid_champion_family_repair",
            ...(breakoutVariantDirective
              ? [
                  "time_boxed_variant_escalation",
                  "force_broader_event_windows",
                ]
              : []),
          ]
        : []),
      ...(schemaHardeningRequired ? ["schema_prompt_hardening"] : []),
      ...(repeatedLocalUnsupported
        ? ["restore_local_compatibility", "emit_required_af_contract"]
        : []),
      ...(problemPressure.repeatedLowTradeCount
        ? ["recover_trade_count", "reduce_over_filtering"]
        : []),
      ...(problemPressure.repeatedOosFailure
        ? ["improve_oos_retention", "reduce_fragile_filters"]
        : []),
      ...(repeatedTradeRetentionCluster
        ? [
            "stabilize_trade_retention_cluster",
            "lift_oos_trade_floor",
            "remove_secondary_entry_gates",
          ]
        : []),
      ...(problemPressure.repeatedDuplicate
        ? ["avoid_duplicate_fingerprint_family", "redirect_archive_gap"]
        : []),
      ...(failureEscalation.preferredRepairKind === "entry_frequency_repair"
        ? ["repair_repeated_trade_count_failure"]
        : []),
      ...(failureEscalation.preferredRepairKind === "risk_logic_repair"
        ? ["repair_repeated_oos_robustness_failure"]
        : []),
      ...(failureEscalation.redirectStructureFamily
        ? ["redirect_repeated_failure_family", "increase_structure_delta"]
        : []),
    ],
    stagnationSignals:
      [
        ...(stagnationSummary.championPlateau ? ["champion_plateau"] : []),
        ...(explorationBreakoutActive ? ["exploration_breakout_active"] : []),
        ...(ignoreCalibrationGuidance ? ["calibration_guidance_skipped"] : []),
        ...(breakoutOutcomeMemory.dominantSparsePatterns.some((pattern) =>
          pattern.startsWith("31/7"),
        ) ||
        breakoutOutcomeMemory.dominantSparsePatterns.length >= 2
          ? ["sparse_oos_trade_cluster"]
          : []),
        ...(breakoutVariantDirective ? ["time_boxed_variant_escalation"] : []),
        ...(duplicatePressure >= 3 ? ["duplicate_pressure_high", "force_structure_delta"] : []),
        ...(problemPressure.repeatedLowTradeCount ? ["trade_count_collapse"] : []),
        ...(problemPressure.repeatedOosFailure ? ["oos_failure_cluster"] : []),
        ...(repeatedTradeRetentionCluster
          ? ["repeated_trade_retention_cluster"]
          : []),
        ...(schemaHardeningRequired ? ["mutation_generation_instability"] : []),
        ...(failureEscalation.repeatedSignatureDetected
          ? ["repeated_failure_signature"]
          : []),
        ...(failureEscalation.redirectStructureFamily
          ? ["redirect_same_family_repairs"]
          : []),
      ],
    iterationRecordMemory:
      iterationRecordMemory.recentRecordCount > 0 ? iterationRecordMemory : undefined,
    nextMutationDirection,
    analysisGuidance: {
      hypothesis:
        explorationBreakoutActive
          ? "Generate a compile-ready AF mutation from a materially different structure family while keeping sufficient trade count, local compatibility, and positive post-fee profitability."
          : "Generate a compile-ready AF mutation that is measurably different from recent archive entries while keeping sufficient trade count, local compatibility, and positive post-fee profitability.",
      expectedEffect:
        explorationBreakoutActive
          ? "Break out of the current plateau by increasing structural diversity before returning to score exploitation."
          : "Increase autonomous selection score through better OOS robustness and structural novelty.",
      invalidIf:
        "The candidate repeats a recent fingerprint family, collapses trade count below the objective floor, violates the AF local contract, or relies on generic human trading narratives.",
      preserveConditions: explorationBreakoutActive
        ? []
        : activeChampion?.conditionInventory
          .slice(0, 2)
          .map((condition) => condition.conditionId) ?? [],
      weakenConditions: [],
      lossZoneGuidance: promotionDiagnostics.lossZones,
      fallbackEvidenceGuidance: {
        available: false,
        source: null,
        authoritative: false,
        summary: "No fallback evidence is required in autonomous local-first mode.",
        suggestedHypothesis:
          "If external calibration is unavailable, continue local-first exploration without treating executor failures as strategy failures.",
        forbiddenInterpretation: "do_not_treat_as_verified",
      },
    },
    forbiddenPatterns: [
      "Do not rely on generic human trading advice or conventional chartist narratives.",
      "Do not emit a near-duplicate of the current champion or recent archive fingerprints.",
      "Do not sacrifice out-of-sample trade count below the configured minimum.",
      "Do not omit any required AF input or helper function needed by the local executor.",
      ...(problemPressure.repeatedLowTradeCount
        ? [
            `Do not return a candidate with fewer than ${input.objective.hardGates.minimumTotalTrades} full-sample trades or fewer than ${minimumOosTrades} out-of-sample trades.`,
            explorationBreakoutActive
              ? "Do not respond to low trade count by reverting to the accepted-head entry family; choose a different AF-compatible route with broader opportunity density."
              : "Do not add new filters, new confirmations, or new regime gates while entry_recovery is active.",
          ]
        : []),
      ...(explorationBreakoutActive
        ? [
            "Do not preserve the same accepted-head entry family, slot/rank scaffold, or weak-exit-only mutation as the primary strategy.",
            "Do not use TradingView calibration low-divergence carry-forward to select the parent or structure family in exploration breakout mode.",
            "Do not make a cosmetic threshold edit; the entry architecture must be materially different from the recent archive neighborhood.",
            ...buildBreakoutOutcomeForbiddenPatterns(breakoutOutcomeMemory),
            ...(breakoutVariantDirective
              ? buildBreakoutVariantForbiddenPatterns(breakoutVariantDirective)
              : []),
          ]
        : []),
      ...(failureEscalation.redirectStructureFamily
        ? [
            `Do not generate another candidate in fingerprint family ${failureEscalation.redirectStructureFamily}.`,
          ]
        : []),
      ...(schemaHardeningRequired
        ? [
            "Do not omit required JSON fields or rely on loosely structured narrative output.",
          ]
        : []),
    ],
  };

  return {
    brief,
    briefHash: sha256(JSON.stringify(brief)),
    baselinePine,
    baselineCandidateId,
    parentCandidateId: explorationBreakoutActive
      ? null
      : baselineCandidateId ?? activeChampion?.candidateId ?? null,
    seedStrategy,
    activeChampion,
  };
}

export async function generateAutonomousCandidate(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  llmClient: MutationLlmClient;
  plan: AutonomousMutationPlan;
  parentCandidateId: string | null;
  branchId?: string;
  mutationSchemaMode?: MutationSchemaMode;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}): Promise<AutonomousMutationOutput> {
  await input.monitor?.log("autonomous.mutation.request", "Sending autonomous mutation request", {
    iteration: input.iteration,
    baselineLength: input.plan.baselinePine.length,
    parentCandidateId: input.parentCandidateId,
  });

  let response = await input.llmClient.generateMutation({
    brief: input.plan.brief,
    baselinePine: input.plan.baselinePine,
    signal: input.signal,
  });
  throwIfAborted(input.signal);
  const generationPromptHash = sha256(
    JSON.stringify({
      operation: "generateMutation",
      payload: {
        brief: input.plan.brief,
        baselinePine: input.plan.baselinePine,
      },
    }),
  );
  throwIfAborted(input.signal);
  await appendMutationBriefRecord(input.stateRoot, {
    runId: input.runId,
    iteration: input.iteration,
    acceptedHeadCandidateId: input.plan.activeChampion?.candidateId ?? null,
    briefHash: input.plan.briefHash,
    promptHash: generationPromptHash,
    responseHash: sha256(response),
    brief: input.plan.brief,
  });

  let schemaRepair = await parseWithSchemaRepair({
    workspaceRoot: input.workspaceRoot,
    stateRoot: input.stateRoot,
    runId: input.runId,
    iteration: input.iteration,
    llmClient: input.llmClient,
    brief: input.plan.brief,
    baselinePine: input.plan.baselinePine,
    response,
    candidateId: input.parentCandidateId,
    mutationSchemaMode: input.mutationSchemaMode ?? "strict",
    signal: input.signal,
    monitor: input.monitor,
  });
  response = schemaRepair.response;
  let parsed = schemaRepair.parsed;
  const pendingRepairAttempts = [...schemaRepair.pendingRepairAttempts];

  let preflight = inspectGeneratedMutation(parsed, {
    breakoutVariantDirective: input.plan.brief.breakoutVariantDirective,
    recentCompileErrors: input.plan.brief.recentCompileErrors,
    recentCompileFailureClasses: input.plan.brief.recentCompileFailureClasses,
  });

  if (preflight.blockingIssues.length > 0) {
    const preflightIssueCodes = preflight.blockingIssues.map((issue) => issue.code);
    await input.monitor?.log(
      "autonomous.mutation.preflight_blocked",
      "Blocking mutation preflight issues detected",
      {
        iteration: input.iteration,
        issueCodes: preflightIssueCodes,
      },
    );
    const problemEvent = await appendProblemEventRecord(input.stateRoot, {
      problemEventId: createCandidateId("problem"),
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.parentCandidateId,
      problemKind: "pine_preflight_fail",
      diagnosis: preflightIssueCodes.join(", "),
      evidenceHash: sha256(
        JSON.stringify({
          issueCodes: preflightIssueCodes,
          candidateSummary: parsed.candidateSummary,
        }),
      ),
      suggestedRepairKind: "pine_source_repair",
    });
    const deterministicRepair = repairTimeBoxedVariantPreflightIssues(
      parsed,
      preflight.blockingIssues,
      input.plan.brief.breakoutVariantDirective,
    );
    if (deterministicRepair) {
      parsed = deterministicRepair;
      response = JSON.stringify(parsed);
      preflight = inspectGeneratedMutation(parsed, {
        breakoutVariantDirective: input.plan.brief.breakoutVariantDirective,
        recentCompileErrors: input.plan.brief.recentCompileErrors,
        recentCompileFailureClasses: input.plan.brief.recentCompileFailureClasses,
      });
      await input.monitor?.log(
        "autonomous.mutation.preflight_deterministic_repair",
        "Applied deterministic time-boxed mutation preflight repair",
        {
          iteration: input.iteration,
          remainingIssueCodes: preflight.blockingIssues.map((issue) => issue.code),
        },
      );
      if (preflight.blockingIssues.length > 0) {
        const artifactPath = await writeMutationRuntimeArtifact({
          workspaceRoot: input.workspaceRoot,
          stateRoot: input.stateRoot,
          iteration: input.iteration,
          stage: "autonomous-preflight-deterministic-repair-remaining",
          payload: {
            issues: preflight.blockingIssues,
            candidateSummary: parsed.candidateSummary,
            breakoutVariantDirective: input.plan.brief.breakoutVariantDirective,
            pineScript: parsed.pineScript,
          },
        });
        await input.monitor?.log(
          "autonomous.mutation.preflight_deterministic_repair_remaining",
          "Deterministic time-boxed mutation repair left blocking issues",
          {
            iteration: input.iteration,
            issueCodes: preflight.blockingIssues.map((issue) => issue.code),
            artifactPath,
          },
        );
      }
      if (preflight.blockingIssues.length === 0) {
        pendingRepairAttempts.push({
          problemEventId: problemEvent.problemEventId,
          candidateId: input.parentCandidateId,
          repairKind: "pine_source_repair",
          llmPromptHash: sha256(
            JSON.stringify({
              operation: "deterministicTimeBoxedPreflightRepair",
              brief: input.plan.brief,
              issueCodes: preflightIssueCodes,
            }),
          ),
          llmResponseHash: sha256(response),
          summary:
            "Applied deterministic time-boxed preflight repair after blocking sparse event-source issues.",
        });
      }
    }
    if (preflight.blockingIssues.length === 0) {
      // The deterministic repair cleared the preflight block; skip the slower LLM repair path.
    } else {
      response = await input.llmClient.repairMutation({
        brief: input.plan.brief,
        candidatePine: parsed.pineScript,
        compileErrors: formatPreflightIssuesForRepair(preflight.blockingIssues),
        candidateSummary: parsed.candidateSummary,
        inventory: parsed.inventory,
        signal: input.signal,
      });
      throwIfAborted(input.signal);
      const repairPromptHash = sha256(
        JSON.stringify({
          brief: input.plan.brief,
          candidatePine: parsed.pineScript,
          compileErrors: formatPreflightIssuesForRepair(preflight.blockingIssues),
        }),
      );
      try {
        throwIfAborted(input.signal);
        schemaRepair = await parseWithSchemaRepair({
          workspaceRoot: input.workspaceRoot,
          stateRoot: input.stateRoot,
          runId: input.runId,
          iteration: input.iteration,
          llmClient: input.llmClient,
          brief: input.plan.brief,
          baselinePine: parsed.pineScript,
          response,
          candidateId: input.parentCandidateId,
          mutationSchemaMode: input.mutationSchemaMode ?? "strict",
          signal: input.signal,
          monitor: input.monitor,
        });
        response = schemaRepair.response;
        parsed = schemaRepair.parsed;
        pendingRepairAttempts.push(...schemaRepair.pendingRepairAttempts);
        preflight = inspectGeneratedMutation(parsed, {
          breakoutVariantDirective: input.plan.brief.breakoutVariantDirective,
          recentCompileErrors: input.plan.brief.recentCompileErrors,
          recentCompileFailureClasses: input.plan.brief.recentCompileFailureClasses,
        });
        if (preflight.blockingIssues.length > 0) {
          throwIfAborted(input.signal);
          const artifactPath = await writeMutationRuntimeArtifact({
            workspaceRoot: input.workspaceRoot,
            stateRoot: input.stateRoot,
            iteration: input.iteration,
            stage: "autonomous-preflight-failed",
            payload: {
              issues: preflight.blockingIssues,
              candidateSummary: parsed.candidateSummary,
              pineScript: parsed.pineScript,
            },
          });
          await appendIncidentRecord(input.stateRoot, {
            runId: input.runId,
            iteration: input.iteration,
            candidateId: `autonomous-${input.iteration}`,
            incidentType: "autonomous_mutation_preflight_failed",
            detail: `Blocking Pine generation issues remained after repair | artifact=${artifactPath}`,
          });
          throw new Error(
            "Blocking Pine generation issues remained after autonomous preflight repair.",
          );
        }
        pendingRepairAttempts.push({
          problemEventId: problemEvent.problemEventId,
          candidateId: input.parentCandidateId,
          repairKind: "pine_source_repair",
          llmPromptHash: repairPromptHash,
          llmResponseHash: sha256(response),
          summary: "Requested Pine preflight repair after blocking issues.",
        });
      } catch (error) {
        throwIfAborted(input.signal);
        await appendRepairAttemptRecord(input.stateRoot, {
          repairAttemptId: createCandidateId("repair"),
          problemEventId: problemEvent.problemEventId,
          runId: input.runId,
          iteration: input.iteration,
          candidateId: input.parentCandidateId,
          repairedCandidateId: null,
          repairKind: "pine_source_repair",
          llmPromptHash: repairPromptHash,
          llmResponseHash: sha256(response),
          result: "failed",
          failureReason: error instanceof Error ? error.message : String(error),
          summary: "Pine preflight repair did not clear blocking issues.",
        });
        throw error;
      }
    }
  }

  const generatedCandidate = await persistGeneratedCandidate({
    workspaceRoot: input.workspaceRoot,
    stateRoot: input.stateRoot,
    runId: input.runId,
    iteration: input.iteration,
    parsed,
    branchId: input.branchId ?? "autonomous-main",
    parentCandidateId: input.parentCandidateId,
    baselinePine: input.plan.baselinePine,
    brief: input.plan.brief,
    briefHash: input.plan.briefHash,
    response,
    signal: input.signal,
  });
  await appendPendingSuccessfulRepairAttempts({
    stateRoot: input.stateRoot,
    runId: input.runId,
    iteration: input.iteration,
    repairedCandidateId: generatedCandidate.candidateArtifact.candidateId,
    attempts: pendingRepairAttempts,
    signal: input.signal,
  });
  return generatedCandidate;
}

export async function repairAutonomousCandidateForCompatibility(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  llmClient: MutationLlmClient;
  plan: AutonomousMutationPlan;
  candidateId: string;
  parsedMutation: ParsedMutationResponse;
  compatibilityIssues: LocalCompatibilityIssue[];
  problemEvent?: ProblemEventRecord | null;
  branchId?: string;
  mutationSchemaMode?: MutationSchemaMode;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}): Promise<AutonomousMutationOutput> {
  const compatibilityContract = input.plan.brief.localCompatibilityContract ??
    getAfLocalCompatibilityContract();
  const issueSummary = summarizeAfCompatibilityIssues(input.compatibilityIssues);
  throwIfAborted(input.signal);
  const problemEvent =
    input.problemEvent ??
    (await appendProblemEventRecord(input.stateRoot, {
      problemEventId: createCandidateId("problem"),
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.candidateId,
      problemKind: "local_unsupported",
      diagnosis: input.compatibilityIssues.map((issue) => issue.detail).join(" | "),
      evidenceHash: sha256(JSON.stringify(input.compatibilityIssues)),
      suggestedRepairKind: "local_compatibility_repair",
      failureSignatureHash: null,
      structureFamily: null,
    }));
  throwIfAborted(input.signal);
  return repairAutonomousCandidateForProblemEvent({
    workspaceRoot: input.workspaceRoot,
    stateRoot: input.stateRoot,
    runId: input.runId,
    iteration: input.iteration,
    llmClient: input.llmClient,
    plan: input.plan,
    candidateId: input.candidateId,
    parsedMutation: input.parsedMutation,
    problemEvent,
    repairKind: "local_compatibility_repair",
    compileErrors: buildLocalCompatibilityRepairInstructions(
      compatibilityContract,
      issueSummary,
    ),
    summary: `Requested local compatibility repair for ${input.compatibilityIssues.map((issue) => issue.code).join(", ")}`,
    branchId: input.branchId,
    mutationSchemaMode: input.mutationSchemaMode,
    signal: input.signal,
    monitor: input.monitor,
  });
}

export async function repairAutonomousCandidateForProblemEvent(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  llmClient: MutationLlmClient;
  plan: AutonomousMutationPlan;
  candidateId: string;
  parsedMutation: ParsedMutationResponse;
  problemEvent: ProblemEventRecord;
  repairKind: Exclude<RepairKind, "schema_repair">;
  compileErrors: string[];
  summary: string;
  branchId?: string;
  mutationSchemaMode?: MutationSchemaMode;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}): Promise<AutonomousMutationOutput> {
  const repairBrief = buildRepairBriefForProblemEvent({
    brief: input.plan.brief,
    problemEvent: input.problemEvent,
    compileErrors: input.compileErrors,
  });
  const repairBriefHash = sha256(JSON.stringify(repairBrief));
  const repairPromptHash = sha256(
    JSON.stringify({
      brief: repairBrief,
      candidatePine: input.parsedMutation.pineScript,
      compileErrors: input.compileErrors,
      candidateSummary: input.parsedMutation.candidateSummary,
      inventory: input.parsedMutation.inventory,
    }),
  );
  const response = await input.llmClient.repairMutation({
    brief: repairBrief,
    candidatePine: input.parsedMutation.pineScript,
    compileErrors: input.compileErrors,
    candidateSummary: input.parsedMutation.candidateSummary,
    inventory: input.parsedMutation.inventory,
    signal: input.signal,
  });
  throwIfAborted(input.signal);

  try {
    throwIfAborted(input.signal);
    await appendMutationBriefRecord(input.stateRoot, {
      runId: input.runId,
      iteration: input.iteration,
      acceptedHeadCandidateId: input.plan.activeChampion?.candidateId ?? null,
      briefHash: repairBriefHash,
      promptHash: repairPromptHash,
      responseHash: sha256(response),
      brief: repairBrief,
    });
    const schemaRepair = await parseWithSchemaRepair({
      workspaceRoot: input.workspaceRoot,
      stateRoot: input.stateRoot,
      runId: input.runId,
      iteration: input.iteration,
      llmClient: input.llmClient,
      brief: repairBrief,
      baselinePine: input.parsedMutation.pineScript,
      response,
      candidateId: input.candidateId,
      mutationSchemaMode: input.mutationSchemaMode ?? "strict",
      signal: input.signal,
      monitor: input.monitor,
    });
    throwIfAborted(input.signal);
    const generatedCandidate = await persistGeneratedCandidate({
      workspaceRoot: input.workspaceRoot,
      stateRoot: input.stateRoot,
      runId: input.runId,
      iteration: input.iteration,
      parsed: schemaRepair.parsed,
      branchId: input.branchId ?? "autonomous-main",
      parentCandidateId: input.candidateId,
      baselinePine: input.parsedMutation.pineScript,
      brief: repairBrief,
      briefHash: repairBriefHash,
      response: schemaRepair.response,
      signal: input.signal,
    });
    await appendPendingSuccessfulRepairAttempts({
      stateRoot: input.stateRoot,
      runId: input.runId,
      iteration: input.iteration,
      repairedCandidateId: generatedCandidate.candidateArtifact.candidateId,
      attempts: schemaRepair.pendingRepairAttempts,
      signal: input.signal,
    });
    throwIfAborted(input.signal);
    await appendRepairAttemptRecord(input.stateRoot, {
      repairAttemptId: createCandidateId("repair"),
      problemEventId: input.problemEvent.problemEventId,
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.candidateId,
      repairedCandidateId: generatedCandidate.candidateArtifact.candidateId,
      repairKind: input.repairKind,
      llmPromptHash: repairPromptHash,
      llmResponseHash: sha256(response),
      result: "success",
      failureReason: null,
      summary: input.summary,
      failureSignatureHash: input.problemEvent.failureSignatureHash,
      structureFamily: input.problemEvent.structureFamily,
    });
    return generatedCandidate;
  } catch (error) {
    throwIfAborted(input.signal);
    await appendRepairAttemptRecord(input.stateRoot, {
      repairAttemptId: createCandidateId("repair"),
      problemEventId: input.problemEvent.problemEventId,
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.candidateId,
      repairedCandidateId: null,
      repairKind: input.repairKind,
      llmPromptHash: repairPromptHash,
      llmResponseHash: sha256(response),
      result: "failed",
      failureReason: error instanceof Error ? error.message : String(error),
      summary: input.summary,
      failureSignatureHash: input.problemEvent.failureSignatureHash,
      structureFamily: input.problemEvent.structureFamily,
    });
    throw error;
  }
}

function calculateMinimumOosTradeTarget(minimumTotalTrades: number): number {
  return Math.max(15, Math.ceil(minimumTotalTrades * 0.25));
}

export function buildRepairBriefForProblemEvent(input: {
  brief: MutationBrief;
  problemEvent: ProblemEventRecord;
  compileErrors: string[];
}): MutationBrief {
  const joinedInstructions = input.compileErrors.join(" ");
  const stagnationSignals = input.brief.stagnationSignals ?? [];
  const needsTradeRecovery =
    input.problemEvent.suggestedRepairKind === "entry_frequency_repair" ||
    joinedInstructions.includes("minimumTotalTrades") ||
    joinedInstructions.includes("minimumOosTrades") ||
    joinedInstructions.includes("entry_frequency_repair") ||
    joinedInstructions.includes("low_trade_count") ||
    joinedInstructions.includes("oos_trade_count_fail");
  const needsExitProfitRepair =
    input.problemEvent.suggestedRepairKind === "risk_logic_repair" ||
    !needsTradeRecovery &&
    (joinedInstructions.includes("risk_logic_repair") ||
      joinedInstructions.includes("oosPostFeeNetProfitPercent") ||
      joinedInstructions.includes("positive_oos_post_fee_profit") ||
      joinedInstructions.includes("robustness_fail"));
  const aggressiveTradeRecovery =
    needsTradeRecovery &&
    (stagnationSignals.includes("trade_count_collapse") ||
      stagnationSignals.includes("oos_failure_cluster") ||
      stagnationSignals.includes("repeated_trade_retention_cluster"));
  const keepExplorationBreakout =
    input.brief.repairMode === "exploration_breakout" &&
    (needsTradeRecovery ||
      aggressiveTradeRecovery ||
      stagnationSignals.includes("exploration_breakout_active"));
  const escapePreferredSparseRoute =
    keepExplorationBreakout &&
    shouldEscapePreferredSparseRoute({
      currentRouteId: input.brief.explorationDirective?.routeId,
      memory: input.brief.breakoutOutcomeMemory,
      problemEvent: input.problemEvent,
      joinedInstructions,
      stagnationSignals,
    });
  const reroutedExplorationDirective = keepExplorationBreakout
    ? selectReroutedExplorationDirective(
        input.brief.explorationDirective,
        input.brief.breakoutOutcomeMemory,
        {
          escapePreferredSparseRoute,
          problemIteration: input.problemEvent.iteration,
        },
      )
    : input.brief.explorationDirective;
  const reroutedFromRoute =
    keepExplorationBreakout &&
    input.brief.explorationDirective?.routeId &&
    reroutedExplorationDirective?.routeId !== input.brief.explorationDirective.routeId
      ? input.brief.explorationDirective.routeId
      : null;
  const stayedOnPreferredRouteBecauseAlternatesSuppressed =
    keepExplorationBreakout &&
    input.brief.explorationDirective?.routeId != null &&
    reroutedExplorationDirective?.routeId === input.brief.explorationDirective.routeId &&
    shouldStayOnPreferredRouteBecauseAlternatesAreSuppressed({
      routeId: input.brief.explorationDirective.routeId,
      memory: input.brief.breakoutOutcomeMemory,
    });
  const effectiveBreakoutVariantDirective =
    reroutedExplorationDirective?.routeId ===
    input.brief.breakoutVariantDirective?.routeId
      ? input.brief.breakoutVariantDirective
      : undefined;

  return {
    ...input.brief,
    repairMode: keepExplorationBreakout
      ? "exploration_breakout"
      : needsTradeRecovery
      ? "entry_recovery"
      : needsExitProfitRepair
        ? "exit_profit_repair"
        : input.brief.repairMode,
    nextMutationDirection: [
      `Repair target: ${input.problemEvent.problemKind}.`,
      ...(input.problemEvent.structureFamily
        ? [`Previous repeated structure family: ${input.problemEvent.structureFamily}.`]
        : []),
      ...(aggressiveTradeRecovery
        ? [
            "Recent AF evidence shows repeated sparse trade retention across multiple families.",
            "Do not make cosmetic edits.",
            keepExplorationBreakout
              ? reroutedFromRoute
                ? escapePreferredSparseRoute
                  ? `Preferred route ${reroutedFromRoute} just reproduced a sparse OOS profile; temporarily reopen an alternate route and use ${reroutedExplorationDirective?.routeId} even if that route was previously suppressed.`
                  : `Do not repair by returning to the previous entry family or by simply loosening the same gates; reroute away from failed breakout route ${reroutedFromRoute}.`
                : stayedOnPreferredRouteBecauseAlternatesSuppressed
                  ? `All alternate breakout routes are suppressed by OOS-floor memory; stay on preferred route ${reroutedExplorationDirective?.routeId} but treat the failed sparse implementation as forbidden.`
                : "Do not repair by returning to the previous entry family or by simply loosening the same gates; keep rotating to a different breakout route with broader opportunity density."
              : "Remove secondary confirmations, cooldown-heavy logic, and narrow gating until the candidate clears both total-trade and OOS-trade floors.",
            keepExplorationBreakout
              ? "Use the exploration directive as the controlling route, while preserving AF compatibility and the full-sample/OOS trade floors."
              : "Prefer one primary entry trigger, one lightweight regime filter at most, and simpler exits that preserve OOS trade retention.",
          ]
        : []),
      input.brief.nextMutationDirection,
      reroutedFromRoute
        ? escapePreferredSparseRoute
          ? `Exploration repair escape: previous preferred route ${reroutedFromRoute} is forbidden for this repair because it repeated the sparse OOS profile. Use alternate route ${reroutedExplorationDirective?.routeId} and make a structurally different attempt.`
          : `Exploration repair reroute: previous route ${reroutedFromRoute} is forbidden for this repair because it missed the OOS trade floor. Use route ${reroutedExplorationDirective?.routeId}.`
        : null,
      stayedOnPreferredRouteBecauseAlternatesSuppressed
        ? `Exploration repair fallback: every alternate breakout route is suppressed, so keep preferred route ${reroutedExplorationDirective?.routeId}; the previous sparse implementation is forbidden and must be replaced with broader post-event windows, zero or low cooldown, and simple time exits.`
        : null,
      effectiveBreakoutVariantDirective
        ? `Breakout variant directive remains mandatory during repair: ${buildBreakoutVariantDirectiveText(effectiveBreakoutVariantDirective)}`
        : null,
      ...input.compileErrors,
    ]
      .filter((value): value is string => value != null && value.length > 0)
      .join(" "),
    explorationDirective: reroutedExplorationDirective,
    breakoutVariantDirective: effectiveBreakoutVariantDirective,
    repairPriorities: Array.from(
      new Set([
        ...input.brief.repairPriorities,
        ...(reroutedFromRoute ? ["reroute_after_sparse_oos_failure"] : []),
        ...(escapePreferredSparseRoute ? ["escape_preferred_sparse_route"] : []),
        ...(stayedOnPreferredRouteBecauseAlternatesSuppressed
          ? ["preferred_route_variant_after_sparse_oos_failure"]
          : []),
        ...(effectiveBreakoutVariantDirective
          ? [
              "time_boxed_variant_escalation",
              "force_broader_event_windows",
            ]
          : []),
        ...(aggressiveTradeRecovery
          ? [
              "aggressive_trade_recovery",
              "lift_oos_trade_floor",
              keepExplorationBreakout
                ? "rotate_structure_family_after_low_trade_failure"
                : "remove_secondary_entry_gates",
            ]
          : []),
      ]),
    ),
    forbiddenPatterns: [
      ...input.brief.forbiddenPatterns,
      ...(needsTradeRecovery
        ? [
            keepExplorationBreakout
              ? "Do not recover trade count by reverting to the same champion-derived entry family."
              : "Do not add new filters, new cooldowns, or stricter confirmations while recovering trade count.",
            keepExplorationBreakout
              ? "Prefer a materially different AF-compatible entry route with broad opportunity density over loosening the failed route."
              : "Prefer loosening or removing sparse entry gates before adding new subsystems.",
          ]
        : []),
      ...(aggressiveTradeRecovery
        ? [
            "Do not preserve a sparse trade profile near the OOS trade floor.",
            "Do not keep multi-stage confirmation stacks or cooldown-heavy entries when repeated low-trade/OOS failures are active.",
          ]
        : []),
      ...(reroutedFromRoute
        ? [
            escapePreferredSparseRoute
              ? `Do not use breakout route ${reroutedFromRoute} again in this repair; it just repeated the sparse OOS profile.`
              : `Do not use breakout route ${reroutedFromRoute} again in this repair; it just failed the OOS trade floor.`,
          ]
        : []),
      ...(stayedOnPreferredRouteBecauseAlternatesSuppressed
        ? [
            `Do not repeat the failed sparse implementation of ${reroutedExplorationDirective?.routeId}; keep the route family only with broader participation and simpler time exits.`,
          ]
        : []),
      ...(input.brief.breakoutOutcomeMemory
        ? buildBreakoutOutcomeForbiddenPatterns(input.brief.breakoutOutcomeMemory)
        : []),
      ...(effectiveBreakoutVariantDirective
        ? buildBreakoutVariantForbiddenPatterns(effectiveBreakoutVariantDirective)
        : []),
      ...(needsExitProfitRepair
        ? [
            "Do not use broad entry expansion as the primary repair when the problem is OOS robustness or post-fee profit.",
          ]
        : []),
      ...(input.problemEvent.suggestedRepairKind === "archive_gap_redirect" &&
      input.problemEvent.structureFamily
        ? [
            `Do not emit another candidate in fingerprint family ${input.problemEvent.structureFamily}.`,
          ]
        : []),
    ],
    recentFailures: [
      ...input.brief.recentFailures,
      input.problemEvent.problemKind,
      ...(aggressiveTradeRecovery ? ["repeated_trade_retention_cluster"] : []),
      ...(input.problemEvent.failureSignatureHash
        ? [input.problemEvent.failureSignatureHash]
        : []),
      ...input.compileErrors,
    ].slice(-12),
  };
}

function summarizeRecentFailures(
  experiments: ExperimentRecord[],
  calibrationEvents: CalibrationEventRecord[],
  problemEvents: ProblemEventRecord[],
): string[] {
  const recentLocalRejections = experiments
    .filter((record) => record.decision.startsWith("local_"))
    .slice(-5)
    .map((record) => record.decision);
  const calibrationFailures = calibrationEvents
    .filter((event) => event.tvDecision)
    .slice(-3)
    .map((event) => event.tvDecision as string);
  const problemKinds = problemEvents.slice(-5).map((event) => event.problemKind);
  return [...recentLocalRejections, ...calibrationFailures, ...problemKinds];
}

function summarizeUnsupportedPatternMemory(
  problemEvents: ProblemEventRecord[],
): string[] {
  return problemEvents
    .filter((event) => event.problemKind === "local_unsupported")
    .slice(-5)
    .map((event) => event.diagnosis);
}

function summarizeFailureSignatures(problemEvents: ProblemEventRecord[]): {
  summaries: string[];
  hashes: string[];
} {
  const recent = problemEvents
    .filter((event) => event.failureSignatureHash != null)
    .slice(-5);
  return {
    summaries: recent.map(
      (event) =>
        `${event.problemKind}:${event.failureSignatureHash}${event.structureFamily ? `:${event.structureFamily}` : ""}`,
    ),
    hashes: recent
      .map((event) => event.failureSignatureHash)
      .filter((value): value is string => typeof value === "string"),
  };
}

function summarizeRecentRepairOutcomes(
  repairAttempts: RepairAttemptRecord[],
  problemEvents: ProblemEventRecord[],
): MutationBrief["recentRepairOutcomes"] {
  const problemKindById = new Map(
    problemEvents.map((event) => [event.problemEventId, event.problemKind] as const),
  );
  return repairAttempts.slice(-5).map((attempt) => ({
    problemKind:
      problemKindById.get(attempt.problemEventId) ?? "local_backtest_fail",
    repairKind: attempt.repairKind,
    result: attempt.result,
    summary: attempt.summary,
  }));
}

function calculateLocalCompatibleRate(experiments: ExperimentRecord[]): number | null {
  const localRecords = experiments.filter((record) => record.decision.startsWith("local_"));
  if (localRecords.length === 0) {
    return null;
  }

  const compatible = localRecords.filter(
    (record) => record.decision !== "local_unsupported",
  ).length;
  return compatible / localRecords.length;
}

function summarizeProblemPressure(
  experiments: ExperimentRecord[],
  problemEvents: ProblemEventRecord[],
): {
  repeatedLowTradeCount: boolean;
  repeatedOosFailure: boolean;
  repeatedDuplicate: boolean;
} {
  const recentLocalRecords = experiments
    .filter((record) => record.decision.startsWith("local_"))
    .slice(-5);
  const recentProblemDiagnoses = problemEvents
    .filter((event) => event.problemKind === "local_backtest_fail")
    .slice(-5)
    .map((event) => event.diagnosis);
  const repeatedLowTradeCount =
    recentLocalRecords.filter((record) =>
      getRejectionReasons(record).includes("minimum_oos_trades"),
    ).length >= 2 ||
    recentProblemDiagnoses.filter((diagnosis) => diagnosis.includes("minimum_oos_trades"))
      .length >= 2;
  const repeatedOosFailure =
    recentLocalRecords.filter((record) =>
      getRejectionReasons(record).includes("oos_hard_gate_fail"),
    ).length >= 2 ||
    recentProblemDiagnoses.filter((diagnosis) => diagnosis.includes("oos_hard_gate_fail"))
      .length >= 2;
  const repeatedDuplicate =
    recentLocalRecords.filter((record) =>
      getRejectionReasons(record).some((reason) =>
        reason === "exact_duplicate" || reason === "structural_duplicate",
      ),
    ).length >= 2 ||
    recentProblemDiagnoses.filter(
      (diagnosis) =>
        diagnosis.includes("exact_duplicate") || diagnosis.includes("structural_duplicate"),
    ).length >= 2;
  return {
    repeatedLowTradeCount,
    repeatedOosFailure,
    repeatedDuplicate,
  };
}

function summarizeFailureEscalation(
  problemEvents: ProblemEventRecord[],
  repairAttempts: RepairAttemptRecord[],
): {
  repeatedSignatureDetected: boolean;
  preferredRepairKind: RepairKind | null;
  redirectStructureFamily: string | null;
} {
  const latestRelevantProblem = [...problemEvents]
    .reverse()
    .find(
      (event) =>
        (event.problemKind === "local_backtest_fail" ||
          event.problemKind === "local_unsupported") &&
        event.failureSignatureHash,
    );
  if (!latestRelevantProblem?.failureSignatureHash) {
    return {
      repeatedSignatureDetected: false,
      preferredRepairKind: null,
      redirectStructureFamily: null,
    };
  }

  const matchingProblems = problemEvents.filter(
    (event) =>
      event.failureSignatureHash === latestRelevantProblem.failureSignatureHash,
  );
  const matchingProblemIds = new Set(
    matchingProblems.map((event) => event.problemEventId),
  );
  const matchingRepairs = repairAttempts.filter((attempt) =>
    matchingProblemIds.has(attempt.problemEventId),
  );
  const signatureCount = matchingProblems.length;
  const repeatedSignatureDetected = signatureCount >= 2;
  const redirectStructureFamily =
    signatureCount >= 3 ? latestRelevantProblem.structureFamily ?? null : null;

  if (!repeatedSignatureDetected) {
    return {
      repeatedSignatureDetected: false,
      preferredRepairKind: null,
      redirectStructureFamily,
    };
  }

  const diagnosis = latestRelevantProblem.diagnosis;
  const preferredRepairKind =
    redirectStructureFamily != null
      ? "archive_gap_redirect"
      : diagnosis.includes("minimum_oos_trades") ||
          diagnosis.includes("low_trade_count") ||
          diagnosis.includes("oos_trade_count_fail") ||
          (matchingRepairs.length > 0 && diagnosis.includes("full_sample_trades"))
        ? "entry_frequency_repair"
        : diagnosis.includes("oos_hard_gate_fail") ||
            diagnosis.includes("positive_oos_post_fee_profit") ||
            diagnosis.includes("drawdown_limit_fail")
          ? "risk_logic_repair"
          : "mutation_prompt_adjustment";

  return {
    repeatedSignatureDetected,
    preferredRepairKind,
    redirectStructureFamily,
  };
}

function summarizeArchiveGap(
  archiveEvents: ArchiveEventRecord[],
  problemPressure: ReturnType<typeof summarizeProblemPressure>,
): string {
  const archivedCandidateCount = archiveEvents.filter(
    (event) => event.eventKind === "archive_added",
  ).length;
  const noveltyFrontierCount = archiveEvents.filter(
    (event) => event.eventKind === "novelty_frontier_added",
  ).length;
  const robustnessFrontierCount = archiveEvents.filter(
    (event) => event.eventKind === "robustness_frontier_added",
  ).length;
  if (problemPressure.repeatedDuplicate) {
    return "Recent iterations are colliding with duplicate families. Explore an underrepresented fingerprint family instead of tuning the same structure.";
  }
  if (problemPressure.repeatedLowTradeCount) {
    return "Recent archive evidence overweights sparse-trade families. Redirect toward simpler, trade-retentive AF structures.";
  }
  return `Archive coverage summary: ${archivedCandidateCount} archived candidates, ${noveltyFrontierCount} novelty frontier entries, ${robustnessFrontierCount} robustness frontier entries. Prefer underexplored AF structures with local-compatible evidence.`;
}

function buildIterationRecordMemory(
  records: AutonomousIterationLearningRecord[],
): NonNullable<MutationBrief["iterationRecordMemory"]> {
  const recent = [...records]
    .sort(compareIterationLearningRecordedAtAscending)
    .slice(-12);
  const latestLessons = uniqueStrings(
    recent
      .slice(-6)
      .map((record) => truncateMemoryText(record.lessonForNextHypothesis, 260)),
  ).slice(-5);
  const successfulHypothesisSignals = uniqueStrings(
    recent
      .filter((record) => record.championChanged || record.eligible === true)
      .slice(-4)
      .map((record) =>
        truncateMemoryText(
          `${record.hypothesis} => ${record.resultSummary}`,
          260,
        ),
      ),
  );
  const failedHypothesisSignals = uniqueStrings(
    recent
      .filter(
        (record) =>
          record.eligible === false ||
          record.decision?.includes("rejected") === true ||
          record.decision?.includes("fail") === true,
      )
      .slice(-4)
      .map((record) =>
        truncateMemoryText(
          `${record.hypothesis} => ${record.lessonForNextHypothesis}`,
          260,
        ),
      ),
  );
  const directive =
    recent.length === 0
      ? null
      : truncateMemoryText(
          [
            `Iteration record memory is available for ${recent.length} recent completed loops.`,
            latestLessons.length > 0
              ? `Latest lessons: ${latestLessons.join(" / ")}.`
              : null,
            successfulHypothesisSignals.length > 0
              ? `Positive hypothesis signals: ${successfulHypothesisSignals.join(" / ")}.`
              : null,
            failedHypothesisSignals.length > 0
              ? `Negative hypothesis signals: ${failedHypothesisSignals.join(" / ")}.`
              : null,
            "Read this record before forming the next hypothesis; do not repeat a method with a negative lesson unless the route or primary entry architecture changes materially.",
          ]
            .filter((value): value is string => Boolean(value))
            .join(" "),
          1400,
        );

  return {
    recentRecordCount: recent.length,
    latestLessons,
    successfulHypothesisSignals,
    failedHypothesisSignals,
    directive,
  };
}

function buildBreakoutOutcomeMemory(input: {
  experiments: ExperimentRecord[];
  mutationBriefs: MutationBriefRecord[];
  minimumOosTrades: number;
}): NonNullable<MutationBrief["breakoutOutcomeMemory"]> {
  const outcomes = collectBreakoutOutcomes(input).slice(-BREAKOUT_OUTCOME_WINDOW);
  const statsByRoute = new Map<
    ExplorationBreakoutRouteId,
    {
      routeId: ExplorationBreakoutRouteId;
      localCount: number;
      eligibleCount: number;
      minimumOosFailureCount: number;
      sparseCount: number;
      totalTrades: number;
      totalOosTrades: number;
      bestEligibleScore: number | null;
    }
  >();

  for (const outcome of outcomes) {
    const stats = statsByRoute.get(outcome.routeId) ?? {
      routeId: outcome.routeId,
      localCount: 0,
      eligibleCount: 0,
      minimumOosFailureCount: 0,
      sparseCount: 0,
      totalTrades: 0,
      totalOosTrades: 0,
      bestEligibleScore: null,
    };
    stats.localCount += 1;
    stats.eligibleCount += outcome.eligible ? 1 : 0;
    stats.minimumOosFailureCount += outcome.minimumOosFailed ? 1 : 0;
    stats.sparseCount += outcome.sparsePattern != null ? 1 : 0;
    stats.totalTrades += outcome.totalTrades ?? 0;
    stats.totalOosTrades += outcome.oosTrades ?? 0;
    if (outcome.eligible && outcome.score != null) {
      stats.bestEligibleScore = Math.max(
        stats.bestEligibleScore ?? Number.NEGATIVE_INFINITY,
        outcome.score,
      );
    }
    statsByRoute.set(outcome.routeId, stats);
  }

  const suppressedRoutes = [...statsByRoute.values()]
    .filter(
      (stats) =>
        stats.localCount >= ROUTE_SUPPRESSION_MIN_FAILURES &&
        stats.eligibleCount === 0 &&
        stats.minimumOosFailureCount >= ROUTE_SUPPRESSION_MIN_FAILURES,
    )
    .map((stats) => stats.routeId);
  const eligibleOutcomes = outcomes.filter((outcome) => outcome.eligible);
  const bestEligible = [...eligibleOutcomes].sort(
    (left, right) =>
      (right.score ?? Number.NEGATIVE_INFINITY) -
      (left.score ?? Number.NEGATIVE_INFINITY),
  )[0];
  const preferredRoutes = [...statsByRoute.values()]
    .filter((stats) => stats.eligibleCount > 0)
    .sort(
      (left, right) =>
        (right.bestEligibleScore ?? Number.NEGATIVE_INFINITY) -
        (left.bestEligibleScore ?? Number.NEGATIVE_INFINITY),
    )
    .map((stats) => stats.routeId);
  const dominantSparsePatterns = summarizeDominantSparsePatterns(
    outcomes.slice(-SPARSE_PATTERN_WINDOW),
  );

  return {
    suppressedRoutes,
    preferredRoutes,
    dominantSparsePatterns,
    bestBreakoutCandidateId: bestEligible?.candidateId ?? null,
    bestBreakoutRoute: bestEligible?.routeId ?? null,
  };
}

function buildBreakoutVariantDirective(input: {
  experiments: ExperimentRecord[];
  mutationBriefs: MutationBriefRecord[];
  minimumOosTrades: number;
  breakoutOutcomeMemory: NonNullable<MutationBrief["breakoutOutcomeMemory"]>;
  explorationDirective:
    | NonNullable<MutationBrief["explorationDirective"]>
    | null;
}): NonNullable<MutationBrief["breakoutVariantDirective"]> | undefined {
  if (input.explorationDirective?.routeId !== TIME_BOXED_ROUTE_ID) {
    return undefined;
  }
  if (
    input.breakoutOutcomeMemory.bestBreakoutRoute !== TIME_BOXED_ROUTE_ID ||
    !input.breakoutOutcomeMemory.preferredRoutes.includes(TIME_BOXED_ROUTE_ID)
  ) {
    return undefined;
  }

  const recentSparseCount = collectBreakoutOutcomes(input)
    .slice(-SPARSE_PATTERN_WINDOW)
    .filter(
      (outcome) =>
        outcome.routeId === TIME_BOXED_ROUTE_ID &&
        outcome.sparsePattern != null &&
        (outcome.sparsePattern === "31/7" ||
          input.breakoutOutcomeMemory.dominantSparsePatterns.includes(
            outcome.sparsePattern,
          )),
    ).length;
  const dominantSparseCluster =
    input.breakoutOutcomeMemory.dominantSparsePatterns.includes("31/7");
  if (
    recentSparseCount < TIME_BOXED_VARIANT_ESCALATION_MIN_COUNT &&
    !dominantSparseCluster
  ) {
    return undefined;
  }

  const variant =
    TIME_BOXED_EVENT_ROTATION_VARIANTS[
      (recentSparseCount + input.experiments.length) %
        TIME_BOXED_EVENT_ROTATION_VARIANTS.length
    ];
  return {
    routeId: TIME_BOXED_ROUTE_ID,
    variantId: variant.variantId,
    escalationLevel: Math.max(
      1,
      Math.min(3, Math.ceil(recentSparseCount / TIME_BOXED_VARIANT_ESCALATION_MIN_COUNT)),
    ),
    recentSparseCount,
    summary: variant.summary,
    forcedRules: [...variant.forcedRules],
    forbiddenPatterns: [...variant.forbiddenPatterns],
  };
}

function collectBreakoutOutcomes(input: {
  experiments: ExperimentRecord[];
  mutationBriefs: MutationBriefRecord[];
  minimumOosTrades: number;
}): Array<{
  candidateId: string;
  iteration: number;
  routeId: ExplorationBreakoutRouteId;
  eligible: boolean;
  score: number | null;
  totalTrades: number | null;
  oosTrades: number | null;
  minimumOosFailed: boolean;
  sparsePattern: string | null;
}> {
  const routesByIteration = buildBreakoutRoutesByIteration(input.mutationBriefs);
  const routeIndexByIteration = new Map<number, number>();
  const localRecords = input.experiments
    .filter((record) => String(record.decision).startsWith("local_"))
    .sort(compareExperimentRecordedAtAscending);

  return localRecords.flatMap((record) => {
    const routeId =
      consumeRouteForExperiment(record, routesByIteration, routeIndexByIteration) ??
      inferBreakoutRouteFromExperiment(record);
    if (!routeId) {
      return [];
    }

    const oosTrades = getOosTradeCount(record);
    const totalTrades = getTotalTradeCount(record);
    const minimumOosFailed =
      getRejectionReasons(record).includes("minimum_oos_trades") ||
      (oosTrades != null && oosTrades < input.minimumOosTrades);
    const sparsePattern =
      totalTrades != null && oosTrades != null && oosTrades < input.minimumOosTrades
        ? `${totalTrades}/${oosTrades}`
        : null;

    return [
      {
        candidateId: record.candidateId,
        iteration: record.iteration,
        routeId,
        eligible: isAutoSelectionEligibleLike(record),
        score: getAutoSelectionScore(record),
        totalTrades,
        oosTrades,
        minimumOosFailed,
        sparsePattern,
      },
    ];
  });
}

function buildBreakoutRoutesByIteration(
  mutationBriefs: MutationBriefRecord[],
): Map<number, ExplorationBreakoutRouteId[]> {
  const routesByIteration = new Map<number, ExplorationBreakoutRouteId[]>();
  for (const record of [...mutationBriefs].sort(compareMutationBriefRecordedAtAscending)) {
    if (record.brief.repairMode !== "exploration_breakout") {
      continue;
    }
    const routeId = record.brief.explorationDirective?.routeId;
    if (!isExplorationBreakoutRouteId(routeId)) {
      continue;
    }
    const routes = routesByIteration.get(record.iteration) ?? [];
    routes.push(routeId);
    routesByIteration.set(record.iteration, routes);
  }
  return routesByIteration;
}

function consumeRouteForExperiment(
  record: ExperimentRecord,
  routesByIteration: Map<number, ExplorationBreakoutRouteId[]>,
  routeIndexByIteration: Map<number, number>,
): ExplorationBreakoutRouteId | null {
  const routes = routesByIteration.get(record.iteration);
  if (!routes || routes.length === 0) {
    return null;
  }
  const currentIndex = routeIndexByIteration.get(record.iteration) ?? 0;
  routeIndexByIteration.set(record.iteration, currentIndex + 1);
  return routes[Math.min(currentIndex, routes.length - 1)] ?? null;
}

function inferBreakoutRouteFromExperiment(
  record: ExperimentRecord,
): ExplorationBreakoutRouteId | null {
  const text = `${record.mutationBriefSummary ?? ""} ${
    (record as Record<string, unknown>).candidateSummary ?? ""
  }`.toLowerCase();
  if (!text.includes("exploration-breakout") && !text.includes("structure-breakout")) {
    return null;
  }
  if (
    text.includes("time-boxed") ||
    text.includes("time boxed") ||
    text.includes("event rotation")
  ) {
    return "time_boxed_event_rotation";
  }
  if (text.includes("momentum-continuation") || text.includes("pullback")) {
    return "momentum_continuation_pullback";
  }
  if (text.includes("mean-reversion") || text.includes("mean reversion")) {
    return "mean_reversion_reentry";
  }
  if (text.includes("volatility-compression") || text.includes("compression release")) {
    return "volatility_compression_release";
  }
  if (
    text.includes("event-reclaim") ||
    text.includes("reclaim reversal") ||
    text.includes("failed-breakdown")
  ) {
    return "event_reclaim_reversal";
  }
  return null;
}

function summarizeDominantSparsePatterns(
  outcomes: Array<{ sparsePattern: string | null }>,
): string[] {
  const counts = new Map<string, number>();
  for (const outcome of outcomes) {
    if (!outcome.sparsePattern) {
      continue;
    }
    counts.set(outcome.sparsePattern, (counts.get(outcome.sparsePattern) ?? 0) + 1);
  }

  return [...counts.entries()]
    .filter(([pattern, count]) => {
      if (pattern === "31/7") {
        return count >= SPARSE_CLUSTER_MIN_COUNT;
      }
      return count >= 2 && (pattern === "7/1" || pattern === "3/1");
    })
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([pattern]) => pattern)
    .slice(0, 5);
}

function buildBreakoutOutcomeDirective(
  memory: NonNullable<MutationBrief["breakoutOutcomeMemory"]>,
): string | null {
  const parts = [
    memory.suppressedRoutes.length > 0
      ? `Breakout outcome memory: suppress failed routes ${memory.suppressedRoutes.join(", ")} because they repeatedly missed the OOS trade floor.`
      : null,
    memory.preferredRoutes.length > 0
      ? `Prefer breakout routes with recent eligible evidence first: ${memory.preferredRoutes.join(", ")}.`
      : null,
    memory.dominantSparsePatterns.length > 0
      ? `Dominant sparse OOS profiles are forbidden: ${memory.dominantSparsePatterns.join(", ")}.`
      : null,
    memory.bestBreakoutCandidateId && memory.bestBreakoutRoute
      ? `Best breakout evidence so far is ${memory.bestBreakoutCandidateId} on ${memory.bestBreakoutRoute}; preserve its broad trade-retention properties, not its exact source.`
      : null,
  ].filter((value): value is string => value != null && value.length > 0);
  return parts.length > 0 ? parts.join(" ") : null;
}

function buildBreakoutOutcomeForbiddenPatterns(
  memory: NonNullable<MutationBrief["breakoutOutcomeMemory"]>,
): string[] {
  return [
    ...(memory.suppressedRoutes.length > 0
      ? [
          `Do not generate another candidate on suppressed breakout routes: ${memory.suppressedRoutes.join(", ")}.`,
        ]
      : []),
    ...(memory.dominantSparsePatterns.length > 0
      ? [
          `Do not repeat sparse OOS trade profiles ${memory.dominantSparsePatterns.join(", ")}; these are treated as failed local route families.`,
        ]
      : []),
  ];
}

function buildBreakoutVariantDirectiveText(
  directive: NonNullable<MutationBrief["breakoutVariantDirective"]>,
): string {
  return [
    `Time-boxed variant escalation is active for ${directive.routeId} because recent candidates still repeat sparse OOS profiles.`,
    `Use variant ${directive.variantId} at escalation level ${directive.escalationLevel}: ${directive.summary}`,
    `Forced implementation rules: ${directive.forcedRules.join(" ")}`,
    `Forbidden implementation patterns: ${directive.forbiddenPatterns.join(" ")}`,
    "This variant directive overrides generic route wording; implement the forced rules literally before optimizing score.",
  ].join(" ");
}

function buildBreakoutVariantForbiddenPatterns(
  directive: NonNullable<MutationBrief["breakoutVariantDirective"]>,
): string[] {
  return [
    `Do not ignore breakoutVariantDirective ${directive.variantId}; it is mandatory for ${directive.routeId}.`,
    ...directive.forbiddenPatterns,
  ];
}

function isExplorationBreakoutRouteId(
  value: unknown,
): value is ExplorationBreakoutRouteId {
  return (
    typeof value === "string" &&
    EXPLORATION_BREAKOUT_ROUTES.some((route) => route.routeId === value)
  );
}

function getTotalTradeCount(record: ExperimentRecord): number | null {
  const totalTrades = record.testerMetrics?.totalTrades;
  return typeof totalTrades === "number" ? totalTrades : null;
}

function getOosTradeCount(record: ExperimentRecord): number | null {
  const splitEvaluation = (record as Record<string, unknown>).splitEvaluation;
  if (!splitEvaluation || typeof splitEvaluation !== "object") {
    return null;
  }
  const outOfSample = (splitEvaluation as { outOfSample?: unknown }).outOfSample;
  if (!outOfSample || typeof outOfSample !== "object") {
    return null;
  }
  const metrics = (outOfSample as { metrics?: unknown }).metrics;
  if (!metrics || typeof metrics !== "object") {
    return null;
  }
  const totalTrades = (metrics as { totalTrades?: unknown }).totalTrades;
  return typeof totalTrades === "number" ? totalTrades : null;
}

function buildCalibrationSkippedConfidenceSummary(
  confidenceSummary: ReturnType<typeof buildLocalConfidenceSummary>,
): ReturnType<typeof buildLocalConfidenceSummary> {
  return {
    ...confidenceSummary,
    recentCalibrationSummary:
      confidenceSummary.totalUpdates === 0
        ? "TradingView calibration is disabled or unavailable. Continue local-first exploration without waiting for calibration."
        : `TradingView calibration is disabled or unavailable. Ignore ${confidenceSummary.totalUpdates} historical confidence updates for parent and family selection in this local-first plan.`,
    highDivergenceFamilies: [],
    lowDivergenceFamilies: [],
    confidenceAdjustmentSummary:
      "Calibration confidence adjustments are intentionally disabled for this plan.",
    calibrationAwareInstruction:
      "Do not prefer or penalize structure families from TradingView calibration history; use only local ledger failures, archive diversity, and objective scores.",
  };
}

function summarizeAutonomousStagnation(input: {
  experiments: ExperimentRecord[];
  activeChampion: ReturnType<typeof findActiveChampionRecord>;
}): {
  championPlateau: boolean;
  iterationsSinceChampion: number | null;
  recentEvaluationCount: number;
  recentEligibleCount: number;
  championScore: number | null;
  bestRecentScore: number | null;
} {
  const currentIteration = input.experiments.reduce(
    (maxIteration, record) => Math.max(maxIteration, record.iteration),
    0,
  );
  if (!input.activeChampion) {
    return {
      championPlateau: false,
      iterationsSinceChampion: null,
      recentEvaluationCount: 0,
      recentEligibleCount: 0,
      championScore: null,
      bestRecentScore: null,
    };
  }

  const recentRecords = input.experiments.filter(
    (record) =>
      record.iteration > input.activeChampion!.iteration &&
      typeof record.decision === "string" &&
      record.decision.startsWith("local_"),
  );
  const recentEligibleRecords = recentRecords.filter(isAutoSelectionEligibleLike);
  const championScore = getAutoSelectionScore(input.activeChampion);
  const bestRecentScore =
    recentEligibleRecords
      .map(getAutoSelectionScore)
      .filter((score): score is number => score != null)
      .sort((left, right) => right - left)[0] ?? null;
  const iterationsSinceChampion = Math.max(
    0,
    currentIteration - input.activeChampion.iteration,
  );
  const recentBestDidNotImprove =
    championScore == null ||
    bestRecentScore == null ||
    bestRecentScore <= championScore + STAGNATION_SCORE_EPSILON;

  return {
    championPlateau:
      iterationsSinceChampion >= STAGNATION_MIN_ITERATIONS_WITHOUT_CHAMPION &&
      recentRecords.length >= STAGNATION_MIN_RECENT_EVALUATIONS &&
      recentEligibleRecords.length >= STAGNATION_MIN_RECENT_ELIGIBLE &&
      recentBestDidNotImprove,
    iterationsSinceChampion,
    recentEvaluationCount: recentRecords.length,
    recentEligibleCount: recentEligibleRecords.length,
    championScore,
    bestRecentScore,
  };
}

function resolveExplorationDirective(input: {
  experiments: ExperimentRecord[];
  activeChampion: ReturnType<typeof findActiveChampionRecord>;
  problemPressure: ReturnType<typeof summarizeProblemPressure>;
  repeatedTradeRetentionCluster: boolean;
  failureEscalation: ReturnType<typeof summarizeFailureEscalation>;
  stagnationSummary: ReturnType<typeof summarizeAutonomousStagnation>;
  breakoutOutcomeMemory: NonNullable<MutationBrief["breakoutOutcomeMemory"]>;
  ignoreCalibrationGuidance: boolean;
}): NonNullable<MutationBrief["explorationDirective"]> | null {
  const lowTradePressure =
    input.problemPressure.repeatedLowTradeCount ||
    input.repeatedTradeRetentionCluster;
  const repeatedFailurePressure =
    input.failureEscalation.repeatedSignatureDetected ||
    input.failureEscalation.redirectStructureFamily != null;
  const shouldBreakout =
    input.repeatedTradeRetentionCluster ||
    (lowTradePressure &&
      (input.stagnationSummary.championPlateau || repeatedFailurePressure)) ||
    (input.stagnationSummary.championPlateau &&
      (input.problemPressure.repeatedDuplicate ||
        input.problemPressure.repeatedOosFailure));

  if (!shouldBreakout) {
    return null;
  }

  const route = selectExplorationBreakoutRoute({
    experiments: input.experiments,
    memory: input.breakoutOutcomeMemory,
  });
  const reasonParts = [
    input.stagnationSummary.championPlateau
      ? `champion_plateau:${input.stagnationSummary.iterationsSinceChampion ?? 0}_iterations`
      : null,
    input.repeatedTradeRetentionCluster ? "repeated_trade_retention_cluster" : null,
    input.problemPressure.repeatedLowTradeCount ? "low_trade_count_pressure" : null,
    input.problemPressure.repeatedDuplicate ? "duplicate_pressure" : null,
    repeatedFailurePressure ? "repeated_failure_pressure" : null,
  ].filter((value): value is string => value != null);

  return {
    mode: "structure_breakout",
    routeId: route.routeId,
    routeSummary: route.routeSummary,
    reason: reasonParts.join(", "),
    ignoredCalibrationGuidance:
      input.ignoreCalibrationGuidance || input.stagnationSummary.championPlateau,
  };
}

function selectExplorationBreakoutRoute(
  input: {
    experiments: ExperimentRecord[];
    memory: NonNullable<MutationBrief["breakoutOutcomeMemory"]>;
    avoidRouteId?: string | null;
  },
): (typeof EXPLORATION_BREAKOUT_ROUTES)[number] {
  const suppressedRoutes = new Set(input.memory.suppressedRoutes);
  const preferredRoute = input.memory.preferredRoutes
    .filter((routeId) => routeId !== input.avoidRouteId)
    .find((routeId) => isExplorationBreakoutRouteId(routeId) && !suppressedRoutes.has(routeId));
  if (preferredRoute) {
    return resolveExplorationRoute(preferredRoute);
  }

  const allowedRoutes = EXPLORATION_BREAKOUT_ROUTES.filter(
    (route) =>
      route.routeId !== input.avoidRouteId && !suppressedRoutes.has(route.routeId),
  );
  if (allowedRoutes.length === 0) {
    return resolveExplorationRoute(DEFAULT_BREAKOUT_FALLBACK_ROUTE_ID);
  }

  const nextIteration =
    input.experiments.reduce(
      (maxIteration, record) => Math.max(maxIteration, record.iteration),
      0,
    ) + 1;
  return allowedRoutes[(nextIteration - 1) % allowedRoutes.length];
}

function selectReroutedExplorationDirective(
  currentDirective:
    | NonNullable<MutationBrief["explorationDirective"]>
    | undefined,
  memory: NonNullable<MutationBrief["breakoutOutcomeMemory"]> | undefined,
  options?: {
    escapePreferredSparseRoute?: boolean;
    problemIteration?: number;
  },
): NonNullable<MutationBrief["explorationDirective"]> | undefined {
  if (!currentDirective || !memory) {
    return currentDirective;
  }
  const nextRoute = options?.escapePreferredSparseRoute
    ? selectSuppressionEscapeRoute({
        currentRouteId: currentDirective.routeId,
        iteration: options.problemIteration,
      })
    : selectExplorationBreakoutRoute({
        experiments: [],
        memory,
        avoidRouteId: currentDirective.routeId,
      });
  return {
    ...currentDirective,
    routeId: nextRoute.routeId,
    routeSummary: nextRoute.routeSummary,
    reason: [
      currentDirective.reason,
      options?.escapePreferredSparseRoute
        ? `suppression_escape_after_preferred_sparse_oos_failure_from:${currentDirective.routeId}`
        : `rerouted_after_sparse_oos_failure_from:${currentDirective.routeId}`,
    ].join(", "),
  };
}

function shouldEscapePreferredSparseRoute(input: {
  currentRouteId: string | undefined;
  memory: NonNullable<MutationBrief["breakoutOutcomeMemory"]> | undefined;
  problemEvent: ProblemEventRecord;
  joinedInstructions: string;
  stagnationSignals: string[];
}): boolean {
  if (input.currentRouteId !== TIME_BOXED_ROUTE_ID) {
    return false;
  }
  const combinedEvidence = [
    input.problemEvent.diagnosis,
    input.joinedInstructions,
    ...(input.memory?.dominantSparsePatterns ?? []),
  ]
    .join(" ")
    .toLowerCase();
  const sparseProfileDetected =
    combinedEvidence.includes("31/7") ||
    combinedEvidence.includes("7/1") ||
    combinedEvidence.includes("3/1") ||
    combinedEvidence.includes("full_sample_trades=31") ||
    combinedEvidence.includes("oos_trades=7") ||
    combinedEvidence.includes("minimum_oos_trades") ||
    combinedEvidence.includes("oos_trade_count_fail");
  const pressureDetected =
    input.stagnationSignals.includes("sparse_oos_trade_cluster") ||
    input.stagnationSignals.includes("oos_failure_cluster") ||
    input.stagnationSignals.includes("trade_count_collapse") ||
    input.stagnationSignals.includes("repeated_trade_retention_cluster") ||
    input.memory?.preferredRoutes.includes(TIME_BOXED_ROUTE_ID) === true;

  return sparseProfileDetected && pressureDetected;
}

function selectSuppressionEscapeRoute(input: {
  currentRouteId: string;
  iteration?: number;
}): ExplorationBreakoutRoute {
  const alternateRoutes = EXPLORATION_BREAKOUT_ROUTES.filter(
    (route) => route.routeId !== input.currentRouteId,
  );
  if (alternateRoutes.length === 0) {
    return resolveExplorationRoute(DEFAULT_BREAKOUT_FALLBACK_ROUTE_ID);
  }
  const routeIndex = Math.abs((input.iteration ?? 1) - 1) % alternateRoutes.length;
  return alternateRoutes[routeIndex];
}

function shouldStayOnPreferredRouteBecauseAlternatesAreSuppressed(input: {
  routeId: string;
  memory: NonNullable<MutationBrief["breakoutOutcomeMemory"]> | undefined;
}): boolean {
  if (!isExplorationBreakoutRouteId(input.routeId) || !input.memory) {
    return false;
  }
  if (!input.memory.preferredRoutes.includes(input.routeId)) {
    return false;
  }
  const suppressedRoutes = new Set(input.memory.suppressedRoutes);
  return EXPLORATION_BREAKOUT_ROUTES.every(
    (route) => route.routeId === input.routeId || suppressedRoutes.has(route.routeId),
  );
}

function resolveExplorationRoute(
  routeId: string,
): ExplorationBreakoutRoute {
  return (
    EXPLORATION_BREAKOUT_ROUTES.find((route) => route.routeId === routeId) ??
    EXPLORATION_BREAKOUT_ROUTES.find(
      (route) => route.routeId === DEFAULT_BREAKOUT_FALLBACK_ROUTE_ID,
    ) ??
    EXPLORATION_BREAKOUT_ROUTES[0]
  );
}

function isAutoSelectionEligibleLike(record: ExperimentRecord): boolean {
  const breakdown = (record as Record<string, unknown>).autoSelectionBreakdown;
  if (breakdown && typeof breakdown === "object") {
    return (breakdown as { eligible?: unknown }).eligible === true;
  }
  const eligibility = (record as Record<string, unknown>).eligibility;
  return (
    eligibility != null &&
    typeof eligibility === "object" &&
    (eligibility as { autoSelectionEligible?: unknown }).autoSelectionEligible === true
  );
}

function getAutoSelectionScore(record: unknown): number | null {
  const recordLike = record as Record<string, unknown>;
  if (typeof recordLike.autoSelectionScore === "number") {
    return recordLike.autoSelectionScore;
  }
  if (typeof recordLike.candidateScore === "number") {
    return recordLike.candidateScore;
  }
  const breakdown = recordLike.autoSelectionBreakdown;
  if (!breakdown || typeof breakdown !== "object") {
    return null;
  }
  const autoSelectionScore = (breakdown as { autoSelectionScore?: unknown })
    .autoSelectionScore;
  if (typeof autoSelectionScore === "number") {
    return autoSelectionScore;
  }
  const totalScore = (breakdown as { totalScore?: unknown }).totalScore;
  return typeof totalScore === "number" ? totalScore : null;
}

function summarizeDivergencePressure(
  confidenceSummary: ReturnType<typeof buildLocalConfidenceSummary>,
): string {
  return [
    confidenceSummary.recentCalibrationSummary,
    confidenceSummary.confidenceAdjustmentSummary,
    confidenceSummary.calibrationAwareInstruction,
  ].join(" ");
}

function summarizeUnsupportedReasons(
  problemEvents: ProblemEventRecord[],
): string | undefined {
  const recentUnsupported = problemEvents
    .filter((event) => event.problemKind === "local_unsupported")
    .slice(-5)
    .map((event) => event.diagnosis.trim())
    .filter((diagnosis) => diagnosis.length > 0);
  if (recentUnsupported.length === 0) {
    return undefined;
  }

  return Array.from(new Set(recentUnsupported)).join(" | ");
}

function selectCalibrationGuidedBaselineCandidate(input: {
  experiments: ExperimentRecord[];
  confidenceSummary: ReturnType<typeof buildLocalConfidenceSummary>;
}): ExperimentRecord | null {
  const preferredFamilies = new Set(input.confidenceSummary.lowDivergenceFamilies);
  if (preferredFamilies.size === 0) {
    return null;
  }

  const candidates = [...input.experiments]
    .filter((record) => {
      const structureFamilyHash = (record as Record<string, unknown>)
        .structureFamilyHash;
      const candidatePath = typeof record.candidatePath === "string"
        ? record.candidatePath
        : null;
      const decision = typeof (record as Record<string, unknown>).decision === "string"
        ? ((record as Record<string, unknown>).decision as string)
        : null;
      return (
        candidatePath != null &&
        typeof structureFamilyHash === "string" &&
        preferredFamilies.has(structureFamilyHash) &&
        (decision === "local_candidate_eligible" || decision === "local_candidate_rejected")
      );
    })
    .sort(compareExperimentRecordedAtDescending);

  return candidates.at(0) ?? null;
}

function buildCalibrationFamilyDirective(
  confidenceSummary: ReturnType<typeof buildLocalConfidenceSummary>,
): string | null {
  if (confidenceSummary.lowDivergenceFamilies.length > 0) {
    return `Calibration carry-forward: prefer the recently low-divergence structure families ${confidenceSummary.lowDivergenceFamilies.join(", ")} unless failure memory or duplicate pressure forces a redirect.`;
  }
  if (confidenceSummary.highDivergenceFamilies.length > 0) {
    return `Calibration carry-forward: avoid the recently high-divergence structure families ${confidenceSummary.highDivergenceFamilies.join(", ")} unless no local-compatible alternative exists.`;
  }
  return null;
}

function buildCandidateBehaviorChangeSummary(input: {
  confidenceSummary: ReturnType<typeof buildLocalConfidenceSummary>;
  unsupportedReasonSummary?: string;
  repeatedLocalUnsupported: boolean;
  repeatedTradeRetentionCluster: boolean;
  repeatedDuplicate: boolean;
  schemaHardeningRequired: boolean;
  explorationBreakoutActive: boolean;
}): NonNullable<MutationBrief["candidateBehaviorChangeSummary"]> {
  const influencedBy: NonNullable<
    MutationBrief["candidateBehaviorChangeSummary"]
  >["influencedBy"] = [];
  const avoidedPatterns: string[] = [];
  const addedConstraints: string[] = [];

  if (
    input.confidenceSummary.lowDivergenceFamilies.length > 0 ||
    input.confidenceSummary.highDivergenceFamilies.length > 0
  ) {
    influencedBy.push("calibration_divergence");
  }
  if (input.repeatedLocalUnsupported || input.unsupportedReasonSummary) {
    influencedBy.push("local_compatibility_contract");
  }
  if (input.repeatedDuplicate) {
    influencedBy.push("duplicate_pressure");
    influencedBy.push("archive_gap");
  }
  if (input.repeatedTradeRetentionCluster || input.schemaHardeningRequired) {
    influencedBy.push("failure_memory");
  }
  if (input.explorationBreakoutActive) {
    influencedBy.push("stagnation_breakout");
    influencedBy.push("archive_gap");
  }

  if (input.confidenceSummary.highDivergenceFamilies.length > 0) {
    avoidedPatterns.push(
      `high_divergence:${input.confidenceSummary.highDivergenceFamilies.join(",")}`,
    );
  }
  if (input.repeatedDuplicate) {
    avoidedPatterns.push("recent_duplicate_family");
  }
  if (input.explorationBreakoutActive) {
    avoidedPatterns.push("accepted_head_family_repair");
    avoidedPatterns.push("calibration_carry_forward_parenting");
  }
  if (input.repeatedLocalUnsupported && input.unsupportedReasonSummary) {
    avoidedPatterns.push(input.unsupportedReasonSummary);
  }

  if (input.confidenceSummary.lowDivergenceFamilies.length > 0) {
    addedConstraints.push(
      `prefer_low_divergence_family:${input.confidenceSummary.lowDivergenceFamilies.join(",")}`,
    );
  }
  if (input.repeatedLocalUnsupported) {
    addedConstraints.push("strict_af_local_compatibility");
  }
  if (input.repeatedTradeRetentionCluster) {
    addedConstraints.push("lift_oos_trade_floor");
  }
  if (input.schemaHardeningRequired) {
    addedConstraints.push("strict_schema_only");
  }
  if (input.explorationBreakoutActive) {
    addedConstraints.push("rotate_structure_family");
    addedConstraints.push("local_first_breakout_without_tv_calibration");
  }

  return {
    influencedBy: Array.from(new Set(influencedBy)),
    avoidedPatterns: Array.from(new Set(avoidedPatterns)),
    addedConstraints: Array.from(new Set(addedConstraints)),
    changedEntryLogic: input.explorationBreakoutActive
      ? "Rotate into a materially different AF-compatible entry family instead of repairing the current champion family."
      : input.repeatedTradeRetentionCluster
        ? "Reduce entry gating and confirmation pressure to recover trade retention."
      : input.confidenceSummary.lowDivergenceFamilies.length > 0
        ? "Preserve the recently low-divergence structure family unless stronger failure memory overrides it."
        : undefined,
    changedExitLogic: input.confidenceSummary.highDivergenceFamilies.length > 0
      ? "Avoid drift-prone exit logic from recently high-divergence families."
      : undefined,
    changedRiskLogic: input.schemaHardeningRequired
      ? "Keep response structure strict before adding new risk-side complexity."
      : undefined,
  };
}

function buildPromotionDiagnostics(
  experiments: ExperimentRecord[],
): NonNullable<MutationBrief["promotionDiagnostics"]> {
  const recentRecords = [...experiments]
    .sort(compareExperimentRecordedAtDescending)
    .slice(0, 30);
  const conditionContribution = recentRecords.flatMap((record) =>
    readConditionContributions(record),
  );
  const lossZones = recentRecords.flatMap((record) => {
    const raw = record as Record<string, unknown>;
    const directZones = Array.isArray(raw.topLossZones)
      ? raw.topLossZones.filter((zone): zone is string => typeof zone === "string")
      : [];
    const lossAnalysis = raw.lossAnalysisSummary as
      | { topLossZones?: unknown; repairPriorities?: unknown }
      | undefined;
    const analyzedZones = Array.isArray(lossAnalysis?.topLossZones)
      ? lossAnalysis.topLossZones.filter((zone): zone is string => typeof zone === "string")
      : [];
    const repairPriorities = Array.isArray(lossAnalysis?.repairPriorities)
      ? lossAnalysis.repairPriorities.filter((priority): priority is string => typeof priority === "string")
      : [];
    return [...directZones, ...analyzedZones, ...repairPriorities];
  });
  const tradeLifecycle = recentRecords
    .map((record) => {
      const metrics = record.testerMetrics;
      if (!metrics) {
        return null;
      }
      return `${record.candidateId}: trades=${metrics.totalTrades}, avgTrade=${metrics.avgTradePercent}, drawdown=${metrics.maxStrategyDrawdownPercent}, pf=${metrics.profitFactor}`;
    })
    .filter((value): value is string => value != null)
    .slice(0, 8);
  const foldFailureMap = recentRecords.flatMap((record) => {
    const walkForward = (record as Record<string, unknown>)
      .walkForwardEvaluation as
      | {
          passed?: unknown;
          gateReasons?: unknown;
          folds?: unknown;
        }
      | undefined;
    if (!walkForward || walkForward.passed === true) {
      return [];
    }
    const folds = Array.isArray(walkForward.folds)
      ? walkForward.folds
      : [];
    const failedFolds = folds
      .map((fold) => fold as { foldId?: unknown; passed?: unknown })
      .filter((fold) => fold.passed === false && typeof fold.foldId === "string")
      .map((fold) => fold.foldId as string);
    const gateReasons = Array.isArray(walkForward.gateReasons)
      ? walkForward.gateReasons.filter((reason): reason is string => typeof reason === "string")
      : [];
    return [
      {
        candidateId: record.candidateId,
        failedFolds,
        gateReasons,
        summary: `walk_forward_failed:${record.candidateId}:${gateReasons.join("+") || "fold_failure"}`,
      },
    ];
  });

  return {
    conditionContribution: conditionContribution.slice(0, 12),
    lossZones: uniqueStrings(lossZones).slice(0, 12),
    tradeLifecycle,
    foldFailureMap: foldFailureMap.slice(0, 8),
  };
}

function buildPromotionDiagnosticInstruction(
  diagnostics: NonNullable<MutationBrief["promotionDiagnostics"]>,
): string | null {
  const parts = [
    diagnostics.foldFailureMap.length > 0
      ? `Fold failure map: ${diagnostics.foldFailureMap.map((entry) => entry.summary).join(" | ")}.`
      : null,
    diagnostics.lossZones.length > 0
      ? `Loss-zone guidance: ${diagnostics.lossZones.slice(0, 4).join(" | ")}.`
      : null,
    diagnostics.tradeLifecycle.length > 0
      ? `Trade lifecycle memory: ${diagnostics.tradeLifecycle.slice(0, 3).join(" | ")}.`
      : null,
    diagnostics.conditionContribution.length > 0
      ? `Condition attribution: ${diagnostics.conditionContribution
          .slice(0, 3)
          .map(
            (entry) =>
              `${entry.conditionId} scoreDelta=${entry.scoreDelta} profitDelta=${entry.profitDelta ?? 0} drawdownDelta=${entry.drawdownDelta ?? 0}`,
          )
          .join(" | ")}.`
      : null,
  ].filter((part): part is string => part != null && part.length > 0);

  return parts.length === 0 ? null : parts.join(" ");
}

function readConditionContributions(
  record: ExperimentRecord,
): NonNullable<MutationBrief["promotionDiagnostics"]>["conditionContribution"] {
  const raw = record as Record<string, unknown>;
  const values = Array.isArray(raw.conditionContributions)
    ? raw.conditionContributions
    : Array.isArray(raw.topConditionContributions)
      ? raw.topConditionContributions
      : [];
  return values
    .map((value) => value as Record<string, unknown>)
    .filter(
      (value) =>
        typeof value.conditionId === "string" &&
        typeof value.scoreDelta === "number" &&
        typeof value.ablatedScore === "number" &&
        typeof value.ablatedDecision === "string",
    )
    .map((value) => ({
      conditionId: value.conditionId as string,
      scoreDelta: value.scoreDelta as number,
      ablatedScore: value.ablatedScore as number,
      ablatedDecision: value.ablatedDecision as string,
      tradesAdded:
        typeof value.tradesAdded === "number" ? (value.tradesAdded as number) : 0,
      tradesRemoved:
        typeof value.tradesRemoved === "number" ? (value.tradesRemoved as number) : 0,
      profitDelta:
        typeof value.profitDelta === "number" ? (value.profitDelta as number) : 0,
      drawdownDelta:
        typeof value.drawdownDelta === "number" ? (value.drawdownDelta as number) : 0,
      oosFoldDelta:
        typeof value.oosFoldDelta === "number" ? (value.oosFoldDelta as number) : 0,
    }));
}

function getRejectionReasons(record: ExperimentRecord): string[] {
  const breakdown = (record as Record<string, unknown>).autoSelectionBreakdown;
  if (!breakdown || typeof breakdown !== "object") {
    return [];
  }
  const reasons = (breakdown as { rejectionReasons?: unknown }).rejectionReasons;
  return Array.isArray(reasons)
    ? reasons.filter((reason): reason is string => typeof reason === "string")
    : [];
}

async function parseWithSchemaRepair(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  llmClient: MutationLlmClient;
  brief: MutationBrief;
  baselinePine: string;
  response: string;
  candidateId: string | null;
  mutationSchemaMode: MutationSchemaMode;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}): Promise<{
  parsed: ParsedMutationResponse;
  response: string;
  pendingRepairAttempts: PendingSuccessfulRepairAttempt[];
}> {
  try {
    return {
      parsed: parseMutationResponseStrict(input.response),
      response: input.response,
      pendingRepairAttempts: [],
    };
  } catch (error) {
    const diagnosis = error instanceof Error ? error.message : String(error);
    const failureSignatureHash = sha256(
      JSON.stringify({
        problemKind: "llm_schema_fail",
        diagnosis,
      }),
    );
    await input.monitor?.log("autonomous.mutation.schema_fail", "Strict mutation schema parse failed", {
      iteration: input.iteration,
      candidateId: input.candidateId,
      diagnosis,
    });
    throwIfAborted(input.signal);
    const problemEvent = await appendProblemEventRecord(input.stateRoot, {
      problemEventId: createCandidateId("problem"),
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.candidateId,
      problemKind: "llm_schema_fail",
      diagnosis,
      evidenceHash: sha256(input.response),
      suggestedRepairKind: "schema_repair",
      failureSignatureHash,
    });
    if (input.mutationSchemaMode === "legacy-recovery-test-only") {
      try {
        const recovered = parseMutationResponseWithRecovery(input.response);
        const promptHash = sha256(
          JSON.stringify({
            operation: "schemaRepairLocalRecovery",
            brief: input.brief,
            rawFailedResponse: input.response,
          }),
        );
        const pendingRepairAttempt: PendingSuccessfulRepairAttempt = {
          problemEventId: problemEvent.problemEventId,
          candidateId: input.candidateId,
          repairKind: "schema_repair",
          llmPromptHash: promptHash,
          llmResponseHash: sha256(input.response),
          summary:
            "Recovered strict JSON schema failure with the local mutation parser recovery path.",
          failureSignatureHash,
        };
        await input.monitor?.log(
          "autonomous.mutation.schema_recovered",
          "Recovered strict mutation schema failure locally without an extra LLM round trip",
          {
            iteration: input.iteration,
            candidateId: input.candidateId,
            diagnosis,
          },
        );
        return {
          parsed: recovered,
          response: input.response,
          pendingRepairAttempts: [pendingRepairAttempt],
        };
      } catch {
        // Fall through to LLM-driven schema repair when local salvage is impossible.
      }
    }
    const schemaRepairErrors = [
      `Previous autonomous mutation failed strict JSON schema validation. ${diagnosis}`,
      "Do not change the strategy idea. Re-emit strict JSON only with required keys candidateSummary, nextMutationHints, strategySpec, specPatch, inventory.",
      "Use rawFailedResponse only as intent context; do not fall back to hand-written Pine.",
    ];
    const repairResponse = await input.llmClient.repairMutation({
      brief: input.brief,
      candidatePine: input.response,
      compileErrors: schemaRepairErrors,
      rawFailedResponse: input.response,
      signal: input.signal,
    });
    throwIfAborted(input.signal);
    const repairPromptHash = sha256(
      JSON.stringify({
        operation: "repairMutation",
        brief: input.brief,
        candidatePine: input.response,
        compileErrors: schemaRepairErrors,
        rawFailedResponse: input.response,
      }),
    );
    try {
      const parsed = parseMutationResponseStrict(repairResponse);
      const pendingRepairAttempt: PendingSuccessfulRepairAttempt = {
        problemEventId: problemEvent.problemEventId,
        candidateId: input.candidateId,
        repairKind: "schema_repair",
        llmPromptHash: repairPromptHash,
        llmResponseHash: sha256(repairResponse),
        summary: "Requested strict JSON schema repair for autonomous mutation.",
        failureSignatureHash,
      };
      return {
        parsed,
        response: repairResponse,
        pendingRepairAttempts: [pendingRepairAttempt],
      };
    } catch (repairError) {
      throwIfAborted(input.signal);
      await appendRepairAttemptRecord(input.stateRoot, {
        repairAttemptId: createCandidateId("repair"),
        problemEventId: problemEvent.problemEventId,
        runId: input.runId,
        iteration: input.iteration,
        candidateId: input.candidateId,
        repairedCandidateId: null,
        repairKind: "schema_repair",
        llmPromptHash: repairPromptHash,
        llmResponseHash: sha256(repairResponse),
        result: "failed",
        failureReason:
          repairError instanceof Error ? repairError.message : String(repairError),
        summary: "Strict JSON schema repair response was still invalid.",
        failureSignatureHash,
      });
      const regenerateBrief = buildSchemaRegenerateBrief(input.brief, diagnosis);
      const regenerateResponse = await input.llmClient.generateMutation({
        brief: regenerateBrief,
        baselinePine: input.baselinePine,
        signal: input.signal,
      });
      throwIfAborted(input.signal);
      const regeneratePromptHash = sha256(
        JSON.stringify({
          operation: "generateMutation",
          brief: regenerateBrief,
          baselinePine: input.baselinePine,
        }),
      );
      try {
        const parsed = parseMutationResponseStrict(regenerateResponse);
        const pendingRepairAttempt: PendingSuccessfulRepairAttempt = {
          problemEventId: problemEvent.problemEventId,
          candidateId: input.candidateId,
          repairKind: "schema_regenerate",
          llmPromptHash: regeneratePromptHash,
          llmResponseHash: sha256(regenerateResponse),
          summary:
            "Requested strict schema regenerate after schema repair remained invalid.",
          failureSignatureHash,
        };
        return {
          parsed,
          response: regenerateResponse,
          pendingRepairAttempts: [pendingRepairAttempt],
        };
      } catch (regenerateError) {
        throwIfAborted(input.signal);
        await appendRepairAttemptRecord(input.stateRoot, {
          repairAttemptId: createCandidateId("repair"),
          problemEventId: problemEvent.problemEventId,
          runId: input.runId,
          iteration: input.iteration,
          candidateId: input.candidateId,
          repairedCandidateId: null,
          repairKind: "schema_regenerate",
          llmPromptHash: regeneratePromptHash,
          llmResponseHash: sha256(regenerateResponse),
          result: "failed",
          failureReason:
            regenerateError instanceof Error
              ? regenerateError.message
              : String(regenerateError),
          summary:
            "Strict schema regenerate also failed to produce a valid mutation payload.",
          failureSignatureHash,
        });
        throw regenerateError;
      }
    }
  }
}

async function appendPendingSuccessfulRepairAttempts(input: {
  stateRoot: string;
  runId: string;
  iteration: number;
  repairedCandidateId: string;
  attempts: PendingSuccessfulRepairAttempt[];
  signal?: AbortSignal;
}): Promise<void> {
  for (const attempt of input.attempts) {
    throwIfAborted(input.signal);
    await appendRepairAttemptRecord(input.stateRoot, {
      repairAttemptId: createCandidateId("repair"),
      problemEventId: attempt.problemEventId,
      runId: input.runId,
      iteration: input.iteration,
      candidateId: attempt.candidateId,
      repairedCandidateId: input.repairedCandidateId,
      repairKind: attempt.repairKind,
      llmPromptHash: attempt.llmPromptHash,
      llmResponseHash: attempt.llmResponseHash,
      result: "success",
      failureReason: null,
      summary: attempt.summary,
      failureSignatureHash: attempt.failureSignatureHash,
      structureFamily: attempt.structureFamily,
    });
  }
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (!signal?.aborted) {
    return;
  }
  const reason = signal.reason;
  throw reason instanceof Error ? reason : new Error("Autonomous phase was aborted.");
}


function buildLocalCompatibilityRepairInstructions(
  contract: LocalCompatibilityContract,
  issueSummary: ReturnType<typeof summarizeAfCompatibilityIssues>,
): string[] {
  const instructions = [
    "The previous candidate failed the local AF compatibility contract.",
    `Required AF inputs: ${contract.requiredInputs.join(", ")}`,
    `Required helper functions: ${contract.requiredFunctions.join(", ")}`,
  ];
  if (issueSummary.missingInputs.length > 0) {
    instructions.push(`Missing inputs: ${issueSummary.missingInputs.join(", ")}`);
  }
  if (issueSummary.missingFunctions.length > 0) {
    instructions.push(`Missing helper functions: ${issueSummary.missingFunctions.join(", ")}`);
  }
  if (issueSummary.unsupportedPatterns.length > 0) {
    instructions.push(
      `Unsupported patterns to remove: ${issueSummary.unsupportedPatterns.join(", ")}`,
    );
  }
  instructions.push(
    "Keep the strategy idea, but rewrite it so the local AF backtester can parse and execute it without compatibility errors.",
  );
  return instructions;
}

function compareExperimentRecordedAtDescending(
  left: ExperimentRecord,
  right: ExperimentRecord,
): number {
  const leftTime = Date.parse(left.recordedAt ?? "") || 0;
  const rightTime = Date.parse(right.recordedAt ?? "") || 0;
  return rightTime - leftTime;
}

function compareExperimentRecordedAtAscending(
  left: ExperimentRecord,
  right: ExperimentRecord,
): number {
  const leftTime = Date.parse(left.recordedAt ?? "") || 0;
  const rightTime = Date.parse(right.recordedAt ?? "") || 0;
  if (leftTime !== rightTime) {
    return leftTime - rightTime;
  }
  if (left.iteration !== right.iteration) {
    return left.iteration - right.iteration;
  }
  return left.candidateId.localeCompare(right.candidateId);
}

function compareMutationBriefRecordedAtAscending(
  left: MutationBriefRecord,
  right: MutationBriefRecord,
): number {
  const leftTime = Date.parse(left.recordedAt ?? "") || 0;
  const rightTime = Date.parse(right.recordedAt ?? "") || 0;
  if (leftTime !== rightTime) {
    return leftTime - rightTime;
  }
  if (left.iteration !== right.iteration) {
    return left.iteration - right.iteration;
  }
  return (left.promptHash ?? "").localeCompare(right.promptHash ?? "");
}

function compareIterationLearningRecordedAtAscending(
  left: AutonomousIterationLearningRecord,
  right: AutonomousIterationLearningRecord,
): number {
  const leftTime = Date.parse(left.recordedAt ?? "") || 0;
  const rightTime = Date.parse(right.recordedAt ?? "") || 0;
  if (leftTime !== rightTime) {
    return leftTime - rightTime;
  }
  if (left.iteration !== right.iteration) {
    return left.iteration - right.iteration;
  }
  return (left.candidateId ?? "").localeCompare(right.candidateId ?? "");
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter((value) => value.length > 0)));
}

function truncateMemoryText(value: string, maxLength: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`;
}

async function persistGeneratedCandidate(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  parsed: ParsedMutationResponse;
  branchId: string;
  parentCandidateId: string | null;
  baselinePine: string;
  brief: MutationBrief;
  briefHash: string;
  response: string;
  signal?: AbortSignal;
}): Promise<AutonomousMutationOutput> {
  throwIfAborted(input.signal);
  const artifact = await persistCandidateArtifact({
    workspaceRoot: input.workspaceRoot,
    parsedMutation: input.parsed,
    parentCandidateId: input.parentCandidateId,
    branchId: input.branchId,
  });
  throwIfAborted(input.signal);
  await appendCandidateLedgerRecord(input.stateRoot, {
    runId: input.runId,
    iteration: input.iteration,
    candidateId: artifact.candidateId,
    parentCandidateId: artifact.parentId,
    branchId: artifact.branchId,
    studyTitle: artifact.studyTitle,
    candidatePath: artifact.pinePath,
    candidateHash: artifact.pineHash,
    contractVersion: AUTORESEARCH_CONTRACT_VERSION,
    mutationAuthority: artifact.specHash
      ? STRATEGY_SPEC_MUTATION_AUTHORITY
      : null,
    specPath: artifact.specPath ?? null,
    specHash: artifact.specHash ?? null,
    candidateSummary: artifact.candidateSummary,
    nextMutationHints: artifact.nextMutationHints,
  });

  return {
    parsedMutation: input.parsed,
    candidateArtifact: artifact,
    mutationProvenance: {
      briefHash: input.briefHash,
      promptHash: sha256(
        JSON.stringify({
          operation: "generateMutation",
          payload: {
            brief: input.brief,
            baselinePine: input.baselinePine,
          },
        }),
      ),
      responseHash: sha256(input.response),
      responseSchemaVersion: RESPONSE_SCHEMA_VERSION,
      parseStatus: "valid",
      inventorySource: input.parsed.inventorySource,
      inferredFields: input.parsed.inferredFields,
      missingFields: input.parsed.missingFields,
    },
    brief: input.brief,
    briefHash: input.briefHash,
  };
}
