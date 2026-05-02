import { z } from "zod";
import { afStrategySpecSchema } from "../strategy-spec/schema.js";

export const specPatchOperationPathSchema = z
  .string()
  .regex(/^\/(event|regime|entry|slot|exit)(\/[A-Za-z0-9_-]+)*$/);

export const specPatchOperationSchema = z.object({
  path: specPatchOperationPathSchema,
  before: z.unknown().optional(),
  after: z.unknown(),
  reason: z.string().min(1),
});

export const specPatchSchema = z.object({
  version: z.literal("af-spec-patch/v1"),
  operations: z.array(specPatchOperationSchema).min(1),
  summary: z.string().min(1),
});

export const conditionRoleSchema = z.enum(["entry", "exit", "filter", "risk"]);

export const conditionInventoryItemSchema = z.object({
  conditionId: z.string().min(1),
  role: conditionRoleSchema,
  summary: z.string().min(1),
  pineLineHints: z.array(z.number().int().positive()).default([]),
});

export const backtestMetricsSchema = z.object({
  netProfitPercent: z.number(),
  postFeeNetProfitPercent: z.number(),
  profitFactor: z.number(),
  maxStrategyDrawdownPercent: z.number(),
  percentProfitable: z.number(),
  totalTrades: z.number(),
  avgTradePercent: z.number(),
});

export const tradeRecordSchema = z.object({
  entryComment: z.string().nullable().default(null),
  entryPrice: z.number().nullable().default(null),
  entryTime: z.string().nullable().default(null),
  exitComment: z.string().nullable().default(null),
  exitPrice: z.number().nullable().default(null),
  exitTime: z.string().nullable().default(null),
  qty: z.number().nullable().default(null),
  profitValue: z.number().nullable().default(null),
  profitPercent: z.number().nullable().default(null),
  runupPercent: z.number().nullable().default(null),
  drawdownPercent: z.number().nullable().default(null),
});

export const simulatedOrderSideSchema = z.enum(["buy", "sell"]);

export const simulatedOrderTypeSchema = z.enum(["market"]);

export const simulatedOrderStatusSchema = z.enum(["submitted", "filled", "canceled"]);

export const simulatedFillPolicySchema = z.enum(["close", "next_open"]);

export const simulatedCostBreakdownSchema = z.object({
  commissionPercent: z.number(),
  commission: z.number(),
  grossValue: z.number(),
  netCashChange: z.number(),
});

export const simulatedOrderSchema = z.object({
  orderId: z.string().min(1),
  slotId: z.string().nullable().default(null),
  parentOrderId: z.string().nullable().default(null),
  barIndex: z.number().int().nonnegative(),
  time: z.string().min(1),
  side: simulatedOrderSideSchema,
  orderType: simulatedOrderTypeSchema,
  status: simulatedOrderStatusSchema,
  quantity: z.number(),
  requestedPrice: z.number(),
  fillPolicy: simulatedFillPolicySchema,
  reason: z.string().min(1),
});

export const simulatedFillSchema = z.object({
  fillId: z.string().min(1),
  orderId: z.string().min(1),
  slotId: z.string().nullable().default(null),
  barIndex: z.number().int().nonnegative(),
  time: z.string().min(1),
  side: simulatedOrderSideSchema,
  quantity: z.number(),
  price: z.number(),
  cost: simulatedCostBreakdownSchema,
  realizedPnl: z.number().nullable().default(null),
  cashAfter: z.number(),
});

export const localPortfolioSnapshotSchema = z.object({
  snapshotId: z.string().min(1),
  barIndex: z.number().int().nonnegative(),
  time: z.string().min(1),
  cash: z.number(),
  positionValue: z.number(),
  equity: z.number(),
  openSlotCount: z.number().int().nonnegative(),
  openQuantity: z.number(),
  realizedPnl: z.number(),
  orderIds: z.array(z.string()).default([]),
  fillIds: z.array(z.string()).default([]),
});

export const localExecutionTraceEntrySchema = z.object({
  sequence: z.number().int().positive(),
  barIndex: z.number().int().nonnegative(),
  time: z.string().min(1),
  orderId: z.string().min(1),
  fillId: z.string().min(1),
  slotId: z.string().nullable().default(null),
  side: simulatedOrderSideSchema,
  reason: z.string().min(1),
  quantity: z.number(),
  price: z.number(),
  commission: z.number(),
  cashAfter: z.number(),
  realizedPnl: z.number().nullable().default(null),
});

export const traceOrderActionSchema = z.enum([
  "none",
  "entry",
  "exit",
  "replace",
  "entry_exit",
]);

export const traceEventV1Schema = z.object({
  barIndex: z.number().int().nonnegative(),
  time: z.string().min(1),
  orderAction: traceOrderActionSchema,
  finalBullEvent: z.number().int().nonnegative(),
  finalBearEvent: z.number().int().nonnegative(),
  entryPass: z.boolean(),
  entryRank: z.number(),
  exitReason: z.string().nullable().default(null),
  slotCount: z.number().int().nonnegative(),
});

export const tvTraceArtifactSchema = z.object({
  schemaVersion: z.literal("tv-trace-artifact/v1"),
  source: z.literal("tradingview-report"),
  tracePrefix: z.literal("AFTRACE|v1|"),
  events: z.array(traceEventV1Schema).default([]),
  missingReason: z.string().nullable().default(null),
});

export const lossZoneDetailSchema = z.object({
  regime: z.string().min(1),
  volatilityBucket: z.string().min(1),
  trendBucket: z.string().min(1),
  entryRoute: z.string().min(1),
  exitReason: z.string().min(1),
  slotRank: z.number().int().nullable().default(null),
  barsHeld: z.number().nullable().default(null),
  lossCount: z.number().int().nonnegative().default(0),
  averageLossPercent: z.number().nullable().default(null),
});

export const tradeLifecycleSummarySchema = z.object({
  entryRoute: z.string().min(1),
  tradeCount: z.number().int().nonnegative(),
  averageBarsHeld: z.number().nullable().default(null),
  mfeProxy: z.number().nullable().default(null),
  maeProxy: z.number().nullable().default(null),
  exitReasonDistribution: z.record(z.string(), z.number().int().nonnegative()).default({}),
  profitDistribution: z.object({
    winners: z.number().int().nonnegative(),
    losers: z.number().int().nonnegative(),
    breakeven: z.number().int().nonnegative(),
    averageProfitPercent: z.number().nullable().default(null),
    medianProfitPercent: z.number().nullable().default(null),
  }),
});

export const seedStrategyReferenceSchema = z.object({
  candidateId: z.string().min(1),
  summary: z.string().min(1),
  studyTitle: z.string().nullable(),
});

export const acceptedHeadReferenceSchema = z.object({
  candidateId: z.string().min(1),
  score: z.number(),
  summary: z.string().optional(),
  metrics: backtestMetricsSchema.optional(),
  tradeRetentionTarget: z.number().int().positive().optional(),
});

export const compileFailureClassSchema = z.enum([
  "undeclared_identifier",
  "qty_percent_argument",
  "unsupported_ta_sum",
  "function_mutates_global",
  "title_too_long",
  "na_type_assignment",
]);

export const repairModeSchema = z.enum([
  "entry_recovery",
  "exit_profit_repair",
  "exploration_breakout",
  "balanced",
]);

export const lossAnalysisSummarySchema = z.object({
  status: z.enum([
    "available",
    "unavailable_no_trades",
    "market_context_unavailable",
  ]),
  summary: z.string().min(1),
  topLossZones: z.array(z.string()).default([]),
  lossZoneDetails: z.array(lossZoneDetailSchema).optional(),
  tradeLifecycle: z.array(tradeLifecycleSummarySchema).optional(),
  repairPriorities: z.array(z.string()).default([]),
});

export const pineAnalysisSummarySchema = z.object({
  status: z.enum(["available"]),
  summary: z.string().min(1),
  changeScope: z.enum(["none", "targeted", "balanced", "broad"]),
  noOpRisk: z.enum(["low", "medium", "high"]),
  hypothesisAlignment: z.enum(["aligned", "partial", "unclear"]),
  materialChangeDetected: z.boolean(),
  conditionCount: z.number().int().nonnegative(),
  changedLineCount: z.number().int().nonnegative(),
  changedRoles: z.array(conditionRoleSchema).default([]),
  blockingIssueCodes: z.array(z.string()).default([]),
  warningIssueCodes: z.array(z.string()).default([]),
});

export const mutationParseStatusSchema = z.enum([
  "valid",
  "recovered",
  "invalid",
]);

export const inventorySourceSchema = z.enum(["llm", "inferred", "mixed"]);

export const executorConfidenceLevelSchema = z.enum([
  "screening",
  "verification",
]);

export const localCompatibilityIssueKindSchema = z.enum([
  "missing_input",
  "missing_function",
  "unsupported_pattern",
]);

export const mutationAuthoritySchema = z.enum(["strategy_spec"]);

export const executorRoleSchema = z.enum([
  "primary_local_backtest",
  "external_calibration",
  "legacy_authoritative_verification",
  "external_tv_validation",
  "tv_fallback_local_backtest",
]);

export const evidenceAuthoritySchema = z.enum([
  "local_model",
  "external_tv",
  "hybrid_calibrated",
]);

export const executorCapabilitySchema = z.object({
  kind: z.enum([
    "local-af-screening",
    "local-af-backtest",
    "tradingview-live",
    "mock",
  ]),
  authoritative: z.boolean(),
  supportedSymbols: z.array(z.string()).default([]),
  supportedTimeframes: z.array(z.string()).default([]),
  supportedStrategyFamilies: z.array(z.string()).default([]),
  confidenceLevel: executorConfidenceLevelSchema,
  role: executorRoleSchema.optional(),
  evidenceAuthority: evidenceAuthoritySchema.optional(),
});

export const localCompatibilityIssueSchema = z.object({
  kind: localCompatibilityIssueKindSchema,
  code: z.string().min(1),
  field: z.string().nullable().default(null),
  detail: z.string().min(1),
});

export const localCompatibilityContractSchema = z.object({
  strategyFamily: z.literal("AF"),
  requiredInputs: z.array(z.string()).default([]),
  requiredFunctions: z.array(z.string()).default([]),
  forbiddenPatterns: z.array(z.string()).default([]),
  supportedSymbols: z.array(z.string()).default([]),
  supportedTimeframes: z.array(z.string()).default([]),
  supportedChartTargets: z.array(z.string()).default([]),
  notes: z.array(z.string()).default([]),
  compatibleSeedCandidatePath: z.string().nullable().default(null),
});

export const artifactValidationResultSchema = z.object({
  hasMetrics: z.boolean(),
  hasNetProfit: z.boolean(),
  hasTotalTrades: z.boolean(),
  hasMaxDrawdown: z.boolean(),
  hasProfitFactor: z.boolean(),
  hasWinRate: z.boolean(),
  hasTrades: z.boolean(),
  hasEquitySummary: z.boolean(),
  hasRawReport: z.boolean(),
  verificationReady: z.boolean(),
  promotionReady: z.boolean(),
  completenessScore: z.number().min(0).max(1),
  missingFields: z.array(z.string()).default([]),
  missingForVerification: z.array(z.string()).default([]),
  missingForPromotion: z.array(z.string()).default([]),
  parseWarnings: z.array(z.string()).default([]),
  parserVersion: z.string().min(1),
});

export const executorCompatibilityResultSchema = z.object({
  supported: z.boolean(),
  reasonCode: z
    .enum(["unsupported_strategy_family", "unsupported_chart_target"])
    .nullable()
    .default(null),
  detail: z.string().nullable().default(null),
  issues: z.array(localCompatibilityIssueSchema).default([]),
});

export const verificationStatusSchema = z.enum([
  "not_requested",
  "verification_pending",
  "verified",
  "verification_failed",
]);

export const verificationFailureReasonSchema = z
  .enum([
    "verification_metric_regress",
    "verification_artifact_incomplete",
    "verification_empty_report",
    "verification_runtime_failure",
    "screening_false_positive",
  ])
  .nullable();

export const verificationRuntimeFailureKindSchema = z
  .enum([
    "pine_editor_open_timeout",
    "chart_load_timeout",
    "monaco_attach_timeout",
    "source_apply_timeout",
    "compile_panel_timeout",
    "strategy_tester_timeout",
    "report_parse_timeout",
    "tradingview_session_closed",
    "unknown_runtime_failure",
  ])
  .nullable();

export const surfaceRecoveryActionSchema = z.enum([
  "soft_reload_chart",
  "reopen_pine_editor",
  "reattach_monaco",
  "reopen_strategy_tester",
  "restart_tradingview_page",
]);

export const surfaceRecoveryAttemptSchema = z.object({
  attempt: z.number().int().positive(),
  action: surfaceRecoveryActionSchema,
  startedAt: z.string().datetime(),
  endedAt: z.string().datetime(),
  status: z.enum(["succeeded", "failed"]),
  observedFailure: verificationRuntimeFailureKindSchema.default(null),
});

export const promotionStatusSchema = z.enum([
  "not_promoted",
  "screening_only",
  "verification_pending",
  "verified_improvement",
  "verification_failed",
  "promoted_head",
]);

export const recordEraSchema = z.enum(["legacy", "v2", "v3"]);

export const normalizedDecisionCategorySchema = z.enum([
  "verified",
  "promoted",
  "screening",
  "legacy_screening_improvement",
  "legacy_valid_no_promotion",
  "failure",
  "runtime_failure",
  "artifact_failure",
]);

export const conditionContributionPolicySchema = z.object({
  maxConditions: z.number().int().positive(),
  requireCategoryCoverage: z.boolean(),
  categories: z.array(conditionRoleSchema).default(["entry", "exit", "filter", "risk"]),
  prioritizeChangedConditions: z.boolean(),
});

export const recordMetaSchema = z.object({
  schemaVersion: z.string().min(1),
  recordHash: z.string().min(1),
  candidateHash: z.string().nullable().optional(),
  baselineHash: z.string().nullable().optional(),
  artifactBundleHash: z.string().nullable().optional(),
  promotedFromRunId: z.string().nullable().optional(),
  promotedFromIteration: z.number().int().positive().nullable().optional(),
  promotedFromRecordHash: z.string().nullable().optional(),
  pipelineVersion: z.string().min(1),
});

export const metricComparisonSchema = z.object({
  metric: z.string().min(1),
  screening: z.number().nullable(),
  verification: z.number().nullable(),
});

export const fallbackEvidenceConfidenceSchema = z.enum([
  "very_low",
  "low",
  "medium",
]);

export const localTvParityStatusSchema = z.enum([
  "matched",
  "minor_drift",
  "major_drift",
  "not_comparable",
]);

export const localTvParitySummarySchema = z.object({
  status: localTvParityStatusSchema,
  tradeCountDelta: z.number().nullable().default(null),
  netProfitPctDelta: z.number().nullable().default(null),
  maxDrawdownPctDelta: z.number().nullable().default(null),
  profitFactorDelta: z.number().nullable().default(null),
  winRateDelta: z.number().nullable().default(null),
  tradeParity: z
    .object({
      status: z.enum(["matched", "minor_drift", "major_drift", "not_comparable"]),
      entryTimeMatchRatio: z.number().min(0).max(1).nullable().default(null),
      exitTimeMatchRatio: z.number().min(0).max(1).nullable().default(null),
      profitSignMatchRatio: z.number().min(0).max(1).nullable().default(null),
      orderCountDelta: z.number().nullable().default(null),
    })
    .nullable()
    .optional(),
  eventParity: z
    .object({
      status: z.enum(["matched", "minor_drift", "major_drift", "not_comparable"]),
      eventMatchRatio: z.number().min(0).max(1).nullable().default(null),
      entryPassMatchRatio: z.number().min(0).max(1).nullable().default(null),
      exitReasonMatchRatio: z.number().min(0).max(1).nullable().default(null),
    })
    .nullable()
    .optional(),
});

export const finalAnalysisSummarySchema = z.object({
  status: z.enum(["available"]),
  verdict: z.enum([
    "promising",
    "neutral",
    "risky",
    "no_op_suspected",
    "insufficient",
  ]),
  summary: z.string().min(1),
  signals: z.array(z.string()).default([]),
  recommendedAction: z.string().min(1),
});

export const researchKnowledgeSourceTypeSchema = z.enum([
  "alphaxiv_mcp",
  "manual_pdf",
  "manual_text",
  "manual_markdown",
  "manual_json",
]);

export const researchInsightSchema = z.object({
  insightId: z.string().min(1),
  summary: z.string().min(1),
  rationale: z.string().min(1),
  suggestedMutation: z.string().min(1),
  relatedFailurePatterns: z.array(z.string()).default([]),
  keywords: z.array(z.string()).default([]),
  confidence: z.number().min(0).max(1).default(0.5),
});

export const researchKnowledgeRecordSchema = z.object({
  knowledgeId: z.string().min(1),
  sourceType: researchKnowledgeSourceTypeSchema,
  title: z.string().min(1),
  sourcePath: z.string().nullable().optional(),
  sourceUrl: z.string().nullable().optional(),
  contentHash: z.string().min(1),
  rawTextPath: z.string().nullable().optional(),
  summary: z.string().min(1),
  problemTags: z.array(z.string()).default([]),
  strategyTags: z.array(z.string()).default([]),
  insights: z.array(researchInsightSchema).default([]),
  recordedAt: z.string().datetime().optional(),
});

export const mutationResearchInsightSchema = z.object({
  knowledgeId: z.string().min(1),
  title: z.string().min(1),
  sourceType: researchKnowledgeSourceTypeSchema,
  summary: z.string().min(1),
  suggestedMutation: z.string().min(1),
  confidence: z.number().min(0).max(1),
});

export const mutationResearchContextSchema = z.object({
  status: z.enum(["available", "none"]),
  summary: z.string().min(1),
  matchedProblemTags: z.array(z.string()).default([]),
  relevantKnowledgeIds: z.array(z.string()).default([]),
  insights: z.array(mutationResearchInsightSchema).default([]),
});

export const equityPointSchema = z.object({
  time: z.string(),
  value: z.number(),
});

export const equitySummarySchema = z.object({
  available: z.boolean(),
  unavailableReason: z.string().nullable().default(null),
  pointsAvailable: z.boolean(),
  pointCount: z.number().int().nonnegative(),
  finalEquity: z.number().nullable().default(null),
  maxDrawdownPercent: z.number().nullable().default(null),
  points: z.array(equityPointSchema).default([]),
});

export const attachDiagnosticsSchema = z.object({
  expectedStudyTitle: z.string().nullable(),
  detectedStudyTitle: z.string().nullable(),
  exactTitleMatched: z.boolean(),
  staleStudySuspected: z.boolean(),
  recoveryActions: z.array(z.string()).default([]),
});

export const objectiveConfigSchema = z.object({
  symbol: z.string().min(1),
  timeframe: z.string().min(1),
  hardGates: z.object({
    minimumTotalTrades: z.number().nonnegative(),
    minimumPostFeeNetProfitPercent: z.number(),
  }),
  softGuardrails: z.object({
    maximumStrategyDrawdownPercent: z.number().positive(),
    softGuardrailPenalty: z.number().nonnegative(),
  }),
  weights: z.object({
    netProfitPercent: z.number().nonnegative(),
    profitFactor: z.number().nonnegative(),
    inverseMaxDrawdown: z.number().nonnegative(),
    percentProfitable: z.number().nonnegative(),
    totalTrades: z.number().nonnegative(),
    avgTradePercent: z.number().nonnegative(),
  }),
  normalizationCaps: z.object({
    netProfitPercent: z.number().positive(),
    profitFactor: z.number().positive(),
    maxStrategyDrawdownPercent: z.number().positive(),
    percentProfitable: z.number().positive(),
    totalTrades: z.number().positive(),
    avgTradePercent: z.number().positive(),
  }),
});

export const parsedMutationResponseSchema = z.object({
  candidateSummary: z.string().min(1),
  nextMutationHints: z.array(z.string()).default([]),
  pineScript: z.string().min(1),
  strategySpec: afStrategySpecSchema.nullable().optional(),
  specPatch: specPatchSchema.nullable().optional(),
  inventory: z.array(conditionInventoryItemSchema).min(1),
  inventorySource: inventorySourceSchema.default("llm"),
  missingFields: z.array(z.string()).default([]),
  inferredFields: z.array(z.string()).default([]),
});

export const mutationProvenanceSchema = z.object({
  briefHash: z.string().nullable().default(null).optional(),
  promptHash: z.string().nullable().default(null).optional(),
  responseHash: z.string().nullable().default(null).optional(),
  responseSchemaVersion: z.string().nullable().default(null),
  parseStatus: mutationParseStatusSchema,
  inventorySource: inventorySourceSchema.nullable().default(null),
  inferredFields: z.array(z.string()).default([]),
  missingFields: z.array(z.string()).default([]),
});

export const compileResultSchema = z.object({
  ok: z.boolean(),
  errors: z.array(z.string()).default([]),
});

export const applyResultSchema = z.object({
  ok: z.boolean(),
  message: z.string(),
  attachDiagnostics: attachDiagnosticsSchema.optional(),
  fallbackActions: z.array(z.string()).default([]),
});

export const chartTargetSchema = z.object({
  symbol: z.string().min(1),
  timeframe: z.string().min(1),
  chartType: z.string().min(1).default("candles"),
});

export const syncArtifactSchema = z.object({
  chartTarget: chartTargetSchema,
  compile: compileResultSchema,
  apply: applyResultSchema.optional(),
  attachDiagnostics: attachDiagnosticsSchema.optional(),
  stateAfter: z.record(z.string(), z.unknown()).default({}),
});

export const artifactBundleSchema = z.object({
  strategy: backtestMetricsSchema.nullable(),
  trades: z.array(tradeRecordSchema).default([]),
  equity: equitySummarySchema.default({
    available: false,
    unavailableReason: null,
    pointsAvailable: false,
    pointCount: 0,
    finalEquity: null,
    maxDrawdownPercent: null,
    points: [],
  }),
  attachDiagnostics: attachDiagnosticsSchema.optional(),
  rawReportHash: z.string().nullable().optional(),
  state: z.record(z.string(), z.unknown()).default({}),
});

export const artifactBundleRefSchema = z.object({
  path: z.string().min(1),
  hash: z.string().min(1),
  storage: z.literal("file").default("file"),
  schemaVersion: z.string().min(1).default("artifact-bundle/v1"),
});

export const artifactSummarySchema = z.object({
  strategy: backtestMetricsSchema.nullable().default(null),
  tradeCount: z.number().int().nonnegative(),
  equityPointCount: z.number().int().nonnegative(),
  rawReportHash: z.string().nullable().default(null),
  hasAttachDiagnostics: z.boolean().default(false),
  stateKeys: z.array(z.string()).default([]),
});

export const compactTradeSummarySchema = z.object({
  totalTrades: z.number().int().nonnegative(),
  firstEntryTime: z.string().nullable().default(null),
  lastExitTime: z.string().nullable().default(null),
  winningTrades: z.number().int().nonnegative(),
  losingTrades: z.number().int().nonnegative(),
});

export const compactEquitySummarySchema = z.object({
  available: z.boolean(),
  unavailableReason: z.string().nullable().default(null),
  pointsAvailable: z.boolean(),
  pointCount: z.number().int().nonnegative(),
  finalEquity: z.number().nullable().default(null),
  maxDrawdownPercent: z.number().nullable().default(null),
  firstPointTime: z.string().nullable().default(null),
  lastPointTime: z.string().nullable().default(null),
});

export const objectiveComponentSchema = z.object({
  rawValue: z.number(),
  normalizedValue: z.number(),
  weight: z.number(),
  contribution: z.number(),
});

export const objectiveBreakdownSchema = z.object({
  score: z.number(),
  hardGatesPassed: z.boolean(),
  softGuardrailBreached: z.boolean(),
  hardGateReasons: z.array(z.string()),
  components: z.object({
    netProfitPercent: objectiveComponentSchema,
    profitFactor: objectiveComponentSchema,
    inverseMaxDrawdown: objectiveComponentSchema,
    percentProfitable: objectiveComponentSchema,
    totalTrades: objectiveComponentSchema,
    avgTradePercent: objectiveComponentSchema,
  }),
});

export const fallbackEvaluationCompatibilitySchema = z.object({
  symbol: z.string().min(1),
  timeframe: z.string().min(1),
  strategyFamily: z.enum(["AF", "unknown"]),
  compatible: z.boolean(),
  reasons: z.array(z.string()).default([]),
});

export const fallbackEvaluationSchema = z.object({
  role: z.literal("fallback_evidence"),
  executorKind: z.enum(["local-af-screening", "local-af-backtest"]),
  executorAuthoritative: z.literal(false),
  promotionEligible: z.literal(false),
  status: z.enum(["succeeded", "failed", "unsupported"]),
  reason: z.string().nullable().default(null),
  artifactId: z.string().nullable().default(null),
  artifactHash: z.string().nullable().default(null),
  metrics: backtestMetricsSchema.nullable().default(null),
  objectiveBreakdown: objectiveBreakdownSchema.nullable().default(null),
  artifactValidation: artifactValidationResultSchema.nullable().default(null),
  decisionIfScreeningOnly: z.string().nullable().default(null),
  compatibility: fallbackEvaluationCompatibilitySchema,
  evidenceUse: z.literal("mutation_context_only"),
  confidence: fallbackEvidenceConfidenceSchema,
  caveats: z.array(z.string()).default([]),
  parity: localTvParitySummarySchema.default({
    status: "not_comparable",
    tradeCountDelta: null,
    netProfitPctDelta: null,
    maxDrawdownPctDelta: null,
    profitFactorDelta: null,
    winRateDelta: null,
  }),
});

export const conditionContributionSchema = z.object({
  conditionId: z.string().min(1),
  scoreDelta: z.number(),
  ablatedScore: z.number(),
  ablatedDecision: z.string().min(1),
  tradesAdded: z.number().int().optional(),
  tradesRemoved: z.number().int().optional(),
  profitDelta: z.number().optional(),
  drawdownDelta: z.number().optional(),
  oosFoldDelta: z.number().optional(),
  failedFoldImpact: z
    .object({
      baseFailedFoldCount: z.number().int().nonnegative(),
      ablatedFailedFoldCount: z.number().int().nonnegative(),
      changedFoldIds: z.array(z.string()).default([]),
      summary: z.string().min(1),
    })
    .optional(),
});

export const explorationBudgetSchema = z.object({
  championExploitPct: z.number().min(0).max(100),
  frontierExploitPct: z.number().min(0).max(100),
  breakoutPct: z.number().min(0).max(100),
  nearMissRepairPct: z.number().min(0).max(100),
  simplificationPct: z.number().min(0).max(100),
});

export const branchKindSchema = z.enum([
  "champion_exploit",
  "frontier_exploit",
  "exploration_breakout",
  "near_miss_repair",
  "adversarial_simplification",
]);

export const foldFailureMapEntrySchema = z.object({
  candidateId: z.string().min(1),
  failedFolds: z.array(z.string()).default([]),
  gateReasons: z.array(z.string()).default([]),
  dominantRegime: z.string().nullable().default(null),
  suspectedFailureReason: z.string().nullable().default(null),
  suggestedMutationConstraint: z.string().nullable().default(null),
  summary: z.string().min(1),
});

export const promotionDiagnosticsSchema = z.object({
  conditionContribution: z.array(conditionContributionSchema).default([]),
  lossZones: z.array(z.string()).default([]),
  lossZoneDetails: z.array(lossZoneDetailSchema).default([]),
  tradeLifecycle: z.array(z.string()).default([]),
  tradeLifecycleDetails: z.array(tradeLifecycleSummarySchema).default([]),
  foldFailureMap: z.array(foldFailureMapEntrySchema).default([]),
});

export const mutationBriefSchema = z.object({
  objective: z.string().min(1),
  guardrails: z.object({
    minimumTotalTrades: z.number().nonnegative(),
    minimumPostFeeNetProfitPercent: z.number(),
    maximumStrategyDrawdownPercent: z.number().positive(),
  }),
  repairMode: repairModeSchema,
  acceptedHead: acceptedHeadReferenceSchema.nullable(),
  seedStrategy: seedStrategyReferenceSchema,
  improvementSource: z.enum(["seed", "accepted_head"]),
  recentFailures: z.array(z.string()),
  localCompatibilityContract: localCompatibilityContractSchema.optional(),
  localCompatibilityContractHash: z.string().nullable().default(null).optional(),
  unsupportedPatternMemory: z.array(z.string()).optional(),
  failureSignatureSummary: z.array(z.string()).default([]).optional(),
  failureSignatureHashes: z.array(z.string()).default([]).optional(),
  recentRepairOutcomes: z.array(
    z.object({
      problemKind: z.string().min(1),
      repairKind: z.string().min(1),
      result: z.enum(["success", "failed", "deferred"]),
      summary: z.string().min(1),
    }),
  ).optional(),
    localCompatibleRate: z.number().min(0).max(1).nullable().optional(),
    archiveGapSummary: z.string().optional(),
    archiveGapSummaryHash: z.string().nullable().default(null).optional(),
    divergenceSummary: z.string().optional(),
    recentCalibrationSummary: z.string().optional(),
    highDivergenceFamilies: z.array(z.string()).default([]).optional(),
    lowDivergenceFamilies: z.array(z.string()).default([]).optional(),
    confidenceAdjustmentSummary: z.string().optional(),
    calibrationAwareInstruction: z.string().optional(),
    unsupportedReasonSummary: z.string().optional(),
    schemaHardeningSummary: z.string().optional(),
    explorationDirective: z
      .object({
        mode: z.literal("structure_breakout"),
        routeId: z.string().min(1),
        routeSummary: z.string().min(1),
        reason: z.string().min(1),
        ignoredCalibrationGuidance: z.boolean().default(false),
      })
      .optional(),
    breakoutOutcomeMemory: z
      .object({
        suppressedRoutes: z.array(z.string()).default([]),
        preferredRoutes: z.array(z.string()).default([]),
        dominantSparsePatterns: z.array(z.string()).default([]),
        bestBreakoutCandidateId: z.string().nullable().default(null),
        bestBreakoutRoute: z.string().nullable().default(null),
      })
      .optional(),
    breakoutVariantDirective: z
      .object({
        routeId: z.string().min(1),
        variantId: z.string().min(1),
        escalationLevel: z.number().int().nonnegative(),
        recentSparseCount: z.number().int().nonnegative(),
        summary: z.string().min(1),
        forcedRules: z.array(z.string()).default([]),
        forbiddenPatterns: z.array(z.string()).default([]),
      })
      .optional(),
    candidateBehaviorChangeSummary: z
      .object({
        influencedBy: z
          .array(
            z.enum([
              "failure_memory",
              "local_compatibility_contract",
              "archive_gap",
              "calibration_divergence",
              "duplicate_pressure",
              "stagnation_breakout",
            ]),
          )
          .default([]),
        avoidedPatterns: z.array(z.string()).default([]),
        addedConstraints: z.array(z.string()).default([]),
        changedEntryLogic: z.string().optional(),
        changedExitLogic: z.string().optional(),
        changedRiskLogic: z.string().optional(),
      })
      .optional(),
  explorationBudget: explorationBudgetSchema.optional(),
  branchKind: branchKindSchema.optional(),
  branchGoal: z.string().min(1).optional(),
  followUpRemaining: z.number().int().nonnegative().optional(),
  promotionDiagnostics: promotionDiagnosticsSchema.optional(),
  recentCompileErrors: z.array(z.string()).default([]),
  recentCompileFailureClasses: z.array(compileFailureClassSchema).default([]),
  recentLossAnalysis: lossAnalysisSummarySchema,
  researchContext: mutationResearchContextSchema,
  lossHotZones: z.array(z.string()),
  repairPriorities: z.array(z.string()),
  stagnationSignals: z.array(z.string()).default([]),
  iterationRecordMemory: z
    .object({
      recentRecordCount: z.number().int().nonnegative(),
      latestLessons: z.array(z.string()).default([]),
      successfulHypothesisSignals: z.array(z.string()).default([]),
      failedHypothesisSignals: z.array(z.string()).default([]),
      directive: z.string().nullable().default(null),
    })
    .optional(),
  nextMutationDirection: z.string().min(1),
  analysisGuidance: z.object({
    hypothesis: z.string().min(1),
    expectedEffect: z.string().min(1),
    invalidIf: z.string().min(1),
    preserveConditions: z.array(z.string()).default([]),
    weakenConditions: z.array(z.string()).default([]),
    lossZoneGuidance: z.array(z.string()).default([]),
      fallbackEvidenceGuidance: z.object({
        available: z.boolean(),
        source: z
          .enum(["local-af-screening", "local-af-backtest"])
          .nullable()
          .default(null),
        authoritative: z.boolean(),
        summary: z.string().min(1),
        suggestedHypothesis: z.string().min(1),
      forbiddenInterpretation: z.literal("do_not_treat_as_verified"),
    }),
  }),
  forbiddenPatterns: z.array(z.string()),
});

export const candidateArtifactSchema = z.object({
  candidateId: z.string().min(1),
  parentId: z.string().nullable(),
  branchId: z.string().min(1),
  pinePath: z.string().min(1),
  pineHash: z.string().min(1),
  specPath: z.string().nullable().optional(),
  specHash: z.string().nullable().optional(),
  studyTitle: z.string().nullable(),
  inventory: z.array(conditionInventoryItemSchema),
  candidateSummary: z.string().min(1),
  nextMutationHints: z.array(z.string()),
});

export const evaluationExecutorNameSchema = z.enum([
  "local-backtest",
  "tradingview-desktop-cdp",
]);

export const runRecordSchema = z.object({
  runId: z.string().min(1),
  startedAt: z.string().datetime(),
  executor: evaluationExecutorNameSchema,
  symbol: z.string().min(1),
  timeframe: z.string().min(1),
  chartType: z.string().min(1),
  model: z.string().min(1),
});

export const mutationBriefRecordSchema = z.object({
  runId: z.string().min(1),
  iteration: z.number().int().positive(),
  acceptedHeadCandidateId: z.string().nullable(),
  briefHash: z.string().nullable().default(null),
  promptHash: z.string().nullable().default(null),
  responseHash: z.string().nullable().default(null),
  brief: mutationBriefSchema,
  recordedAt: z.string().datetime().optional(),
});

export const autonomousIterationLearningRecordSchema = z.object({
  runId: z.string().min(1),
  iteration: z.number().int().positive(),
  acceptedHeadCandidateId: z.string().nullable().default(null),
  candidateId: z.string().nullable().default(null),
  briefHash: z.string().nullable().default(null),
  repairMode: repairModeSchema.nullable().default(null),
  routeId: z.string().nullable().default(null),
  variantId: z.string().nullable().default(null),
  hypothesis: z.string().min(1),
  methodSummary: z.string().min(1),
  resultSummary: z.string().min(1),
  lessonForNextHypothesis: z.string().min(1),
  decision: z.string().nullable().default(null),
  score: z.number().nullable().default(null),
  eligible: z.boolean().nullable().default(null),
  totalTrades: z.number().nullable().default(null),
  oosTrades: z.number().nullable().default(null),
  postFeeNetProfitPercent: z.number().nullable().default(null),
  oosPostFeeNetProfitPercent: z.number().nullable().default(null),
  blockingReasons: z.array(z.string()).default([]),
  championChanged: z.boolean().default(false),
  activeChampionCandidateId: z.string().nullable().default(null),
  recordedAt: z.string().datetime().optional(),
});

export const taskHypothesisSchema = z.object({
  objective: z.string().min(1),
  nextMutationDirection: z.string().min(1),
  recentFailures: z.array(z.string()),
  acceptedHeadCandidateId: z.string().nullable(),
});

export const taskExecutionSummarySchema = z.object({
  candidateId: z.string().nullable(),
  studyTitle: z.string().nullable(),
  status: z.enum([
    "generation_failed",
    "compile_failed",
    "apply_failed",
    "backtest_empty",
    "evaluated",
    "runtime_failed",
  ]),
  decision: z.string().min(1),
  compileOk: z.boolean().nullable(),
  applyOk: z.boolean().nullable(),
  artifactPaths: z.record(z.string(), z.string()).default({}),
  executorCapability: executorCapabilitySchema.nullable().default(null),
  artifactValidation: artifactValidationResultSchema.nullable().default(null),
});

export const taskAnalysisSummarySchema = z.object({
  decision: z.string().min(1),
  score: z.number().nullable(),
  hardGatesPassed: z.boolean().nullable(),
  softGuardrailBreached: z.boolean().nullable(),
  mutationParseStatus: mutationParseStatusSchema.nullable().default(null),
  verificationStatus: verificationStatusSchema.nullable().default(null),
  verificationFailureReason: verificationFailureReasonSchema.default(null),
  verificationRuntimeFailureKind: verificationRuntimeFailureKindSchema.default(null),
  recoveryAttempts: z.array(surfaceRecoveryAttemptSchema).default([]),
  fallbackEvaluation: fallbackEvaluationSchema.nullable().default(null),
  promotionStatus: promotionStatusSchema.nullable().default(null),
  promotionReady: z.boolean().nullable().default(null),
  screeningVsVerificationDiff: z.array(metricComparisonSchema).nullable().default(null),
  recordEra: recordEraSchema.nullable().default(null),
  pineAnalysisSummary: pineAnalysisSummarySchema.nullable().default(null),
  finalAnalysisSummary: finalAnalysisSummarySchema.nullable().default(null),
  topConditionContributions: z.array(conditionContributionSchema).default([]),
  nextMutationHints: z.array(z.string()).default([]),
});

export const taskRecordSchema = z.object({
  runId: z.string().min(1),
  batchId: z.string().min(1),
  taskId: z.string().min(1),
  taskNumber: z.number().int().positive(),
  iteration: z.number().int().positive(),
  status: z.enum(["completed", "generation_failed", "runtime_failed", "stopped"]),
  hypothesis: taskHypothesisSchema,
  execution: taskExecutionSummarySchema,
  analysis: taskAnalysisSummarySchema,
  mutationParseStatus: mutationParseStatusSchema.nullable().optional(),
  mutationProvenance: mutationProvenanceSchema.nullable().optional(),
  executorCapability: executorCapabilitySchema.nullable().optional(),
  artifactValidation: artifactValidationResultSchema.nullable().optional(),
  verificationStatus: verificationStatusSchema.nullable().optional(),
  verificationFailureReason: verificationFailureReasonSchema.optional(),
  verificationRuntimeFailureKind: verificationRuntimeFailureKindSchema.optional(),
  recoveryAttempts: z.array(surfaceRecoveryAttemptSchema).optional(),
  fallbackEvaluation: fallbackEvaluationSchema.nullable().optional(),
  promotionStatus: promotionStatusSchema.nullable().optional(),
  promotionReady: z.boolean().nullable().optional(),
  localTvParity: localTvParitySummarySchema.nullable().optional(),
  screeningVsVerificationDiff: z.array(metricComparisonSchema).nullable().optional(),
  recordEra: recordEraSchema.nullable().optional(),
  recordMeta: recordMetaSchema.optional(),
  recordedAt: z.string().datetime().optional(),
});

export const taskBatchRecordSchema = z.object({
  runId: z.string().min(1),
  batchId: z.string().min(1),
  targetTaskCount: z.number().int().positive(),
  completedTaskCount: z.number().int().nonnegative(),
  runtimeFailureCount: z.number().int().nonnegative(),
  maxRuntimeFailures: z.number().int().positive(),
  status: z.enum(["running", "completed", "stopped"]),
  stopReason: z.string().nullable(),
  recordedAt: z.string().datetime().optional(),
});

export const candidateLedgerRecordSchema = z.object({
  runId: z.string().min(1),
  iteration: z.number().int().positive(),
  candidateId: z.string().min(1),
  parentCandidateId: z.string().nullable(),
  branchId: z.string().min(1),
  studyTitle: z.string().nullable(),
  candidatePath: z.string().min(1),
  candidateHash: z.string().min(1),
  contractVersion: z.string().nullable().default(null),
  mutationAuthority: mutationAuthoritySchema.nullable().default(null),
  specPath: z.string().nullable().default(null),
  specHash: z.string().nullable().default(null),
  candidateSummary: z.string().min(1),
  nextMutationHints: z.array(z.string()),
  recordedAt: z.string().datetime().optional(),
});

export const experimentRecordSchema = z
  .object({
    runId: z.string().min(1),
    iteration: z.number().int().positive(),
    candidateId: z.string().min(1),
    parentCandidateId: z.string().nullable(),
    branchId: z.string().min(1),
    acceptedHeadCandidateId: z.string().nullable(),
    baselineCandidateId: z.string().nullable(),
    seedStrategyId: z.string().optional(),
    improvementSource: z.enum(["seed", "accepted_head"]).optional(),
    candidatePath: z.string().optional(),
    candidateHash: z.string().optional(),
    studyTitle: z.string().nullable().optional(),
    candidateScore: z.number().nullable().optional(),
    decision: z.string().min(1),
    status: z.string().min(1),
    compile: compileResultSchema.optional(),
    apply: applyResultSchema.optional(),
    syncArtifact: syncArtifactSchema.optional(),
    testerMetrics: backtestMetricsSchema.optional(),
    artifactBundle: artifactBundleSchema.optional(),
    artifactBundleRef: artifactBundleRefSchema.optional(),
    artifactBundleHash: z.string().nullable().optional(),
    artifactSummary: artifactSummarySchema.optional(),
    tradeSummary: compactTradeSummarySchema.optional(),
    equitySummary: compactEquitySummarySchema.optional(),
    objectiveBreakdown: objectiveBreakdownSchema.optional(),
    conditionInventory: z.array(conditionInventoryItemSchema).optional(),
    conditionContributions: z.array(conditionContributionSchema).optional(),
    mutationBriefSummary: z.string().optional(),
    researchContextSummary: mutationResearchContextSchema.optional(),
    nextMutationHints: z.array(z.string()).optional(),
    mutationParseStatus: mutationParseStatusSchema.optional(),
    mutationProvenance: mutationProvenanceSchema.nullable().optional(),
    executorCapability: executorCapabilitySchema.optional(),
    artifactValidation: artifactValidationResultSchema.optional(),
    verificationStatus: verificationStatusSchema.optional(),
    verificationFailureReason: verificationFailureReasonSchema.optional(),
    verificationRuntimeFailureKind: verificationRuntimeFailureKindSchema.optional(),
    recoveryAttempts: z.array(surfaceRecoveryAttemptSchema).optional(),
    fallbackEvaluation: fallbackEvaluationSchema.nullable().optional(),
    promotionStatus: promotionStatusSchema.optional(),
    promotionReady: z.boolean().optional(),
    localTvParity: localTvParitySummarySchema.nullable().optional(),
    screeningVsVerificationDiff: z.array(metricComparisonSchema).nullable().optional(),
    recordEra: recordEraSchema.optional(),
    pineAnalysisSummary: pineAnalysisSummarySchema.optional(),
    finalAnalysisSummary: finalAnalysisSummarySchema.optional(),
    lossAnalysisSummary: lossAnalysisSummarySchema.optional(),
    topLossZones: z.array(z.string()).optional(),
    repairPriorities: z.array(z.string()).optional(),
    artifactPaths: z.record(z.string(), z.string()).optional(),
    recordMeta: recordMetaSchema.optional(),
    recordedAt: z.string().datetime().optional(),
  })
  .passthrough();

export const incidentRecordSchema = z
  .object({
    runId: z.string().min(1),
    iteration: z.number().int().nonnegative(),
    candidateId: z.string().min(1),
    category: z.enum(["system", "evaluation"]).default("system"),
    incidentType: z.string().min(1),
    detail: z.string().min(1),
    recordedAt: z.string().datetime().optional(),
  })
  .passthrough();

export const lineageNodeSchema = z.object({
  candidateId: z.string().min(1),
  parentCandidateId: z.string().nullable(),
  branchId: z.string().min(1),
  accepted: z.boolean(),
  score: z.number().nullable(),
  decision: z.string().min(1),
  reason: z.string().min(1),
});

export const knowledgeStorageClassSchema = z.enum([
  "policy",
  "evidence",
  "ledger",
  "view",
  "taxonomy",
  "asset",
]);

export const knowledgeCatalogEntrySchema = z.object({
  id: z.string().min(1),
  storageClass: knowledgeStorageClassSchema,
  relativePath: z.string().min(1),
  format: z.enum(["json", "jsonl", "pine", "directory"]),
  sourceOfTruth: z.boolean(),
  producer: z.string().min(1),
  consumers: z.array(z.string()),
  rebuildRule: z.string().min(1),
  retention: z.string().min(1),
  description: z.string().min(1),
});

export const knowledgeCatalogSchema = z.object({
  generatedAt: z.string().datetime(),
  entries: z.array(knowledgeCatalogEntrySchema),
});

export type ConditionInventoryItem = z.infer<typeof conditionInventoryItemSchema>;
export type ConditionRole = z.infer<typeof conditionRoleSchema>;
export type BacktestMetrics = z.infer<typeof backtestMetricsSchema>;
export type TradeRecord = z.infer<typeof tradeRecordSchema>;
export type SimulatedOrderSide = z.infer<typeof simulatedOrderSideSchema>;
export type SimulatedOrderType = z.infer<typeof simulatedOrderTypeSchema>;
export type SimulatedOrderStatus = z.infer<typeof simulatedOrderStatusSchema>;
export type SimulatedFillPolicy = z.infer<typeof simulatedFillPolicySchema>;
export type SimulatedCostBreakdown = z.infer<typeof simulatedCostBreakdownSchema>;
export type SimulatedOrder = z.infer<typeof simulatedOrderSchema>;
export type SimulatedFill = z.infer<typeof simulatedFillSchema>;
export type LocalPortfolioSnapshot = z.infer<typeof localPortfolioSnapshotSchema>;
export type LocalExecutionTraceEntry = z.infer<typeof localExecutionTraceEntrySchema>;
export type TraceOrderAction = z.infer<typeof traceOrderActionSchema>;
export type TraceEventV1 = z.infer<typeof traceEventV1Schema>;
export type TvTraceArtifact = z.infer<typeof tvTraceArtifactSchema>;
export type LossZoneDetail = z.infer<typeof lossZoneDetailSchema>;
export type TradeLifecycleSummary = z.infer<typeof tradeLifecycleSummarySchema>;
export type SeedStrategyReference = z.infer<typeof seedStrategyReferenceSchema>;
export type AcceptedHeadReference = z.infer<typeof acceptedHeadReferenceSchema>;
export type CompileFailureClass = z.infer<typeof compileFailureClassSchema>;
export type RepairMode = z.infer<typeof repairModeSchema>;
export type LossAnalysisSummary = z.infer<typeof lossAnalysisSummarySchema>;
export type PineAnalysisSummary = z.infer<typeof pineAnalysisSummarySchema>;
export type MutationParseStatus = z.infer<typeof mutationParseStatusSchema>;
export type InventorySource = z.infer<typeof inventorySourceSchema>;
export type ExecutorConfidenceLevel = z.infer<typeof executorConfidenceLevelSchema>;
export type LocalCompatibilityIssueKind = z.infer<
  typeof localCompatibilityIssueKindSchema
>;
export type MutationAuthority = z.infer<typeof mutationAuthoritySchema>;
export type ExecutorRole = z.infer<typeof executorRoleSchema>;
export type EvidenceAuthority = z.infer<typeof evidenceAuthoritySchema>;
export type ExecutorCapability = z.infer<typeof executorCapabilitySchema>;
export type LocalCompatibilityIssue = z.infer<typeof localCompatibilityIssueSchema>;
export type ArtifactValidationResult = z.infer<typeof artifactValidationResultSchema>;
export type ExecutorCompatibilityResult = z.infer<typeof executorCompatibilityResultSchema>;
export type VerificationStatus = z.infer<typeof verificationStatusSchema>;
export type VerificationFailureReason = z.infer<typeof verificationFailureReasonSchema>;
export type VerificationRuntimeFailureKind = z.infer<
  typeof verificationRuntimeFailureKindSchema
>;
export type SurfaceRecoveryAction = z.infer<typeof surfaceRecoveryActionSchema>;
export type SurfaceRecoveryAttempt = z.infer<typeof surfaceRecoveryAttemptSchema>;
export type PromotionStatus = z.infer<typeof promotionStatusSchema>;
export type RecordEra = z.infer<typeof recordEraSchema>;
export type NormalizedDecisionCategory = z.infer<
  typeof normalizedDecisionCategorySchema
>;
export type ConditionContributionPolicy = z.infer<typeof conditionContributionPolicySchema>;
export type RecordMeta = z.infer<typeof recordMetaSchema>;
export type MetricComparison = z.infer<typeof metricComparisonSchema>;
export type FallbackEvidenceConfidence = z.infer<
  typeof fallbackEvidenceConfidenceSchema
>;
export type LocalTvParityStatus = z.infer<typeof localTvParityStatusSchema>;
export type LocalTvParitySummary = z.infer<typeof localTvParitySummarySchema>;
export type FinalAnalysisSummary = z.infer<typeof finalAnalysisSummarySchema>;
export type ResearchKnowledgeSourceType = z.infer<typeof researchKnowledgeSourceTypeSchema>;
export type ResearchInsight = z.infer<typeof researchInsightSchema>;
export type ResearchKnowledgeRecord = z.infer<typeof researchKnowledgeRecordSchema>;
export type MutationResearchInsight = z.infer<typeof mutationResearchInsightSchema>;
export type MutationResearchContext = z.infer<typeof mutationResearchContextSchema>;
export type EquityPoint = z.infer<typeof equityPointSchema>;
export type EquitySummary = z.infer<typeof equitySummarySchema>;
export type ArtifactBundleRef = z.infer<typeof artifactBundleRefSchema>;
export type ArtifactSummary = z.infer<typeof artifactSummarySchema>;
export type CompactTradeSummary = z.infer<typeof compactTradeSummarySchema>;
export type CompactEquitySummary = z.infer<typeof compactEquitySummarySchema>;
export type AttachDiagnostics = z.infer<typeof attachDiagnosticsSchema>;
export type ObjectiveConfig = z.infer<typeof objectiveConfigSchema>;
export type SpecPatch = z.infer<typeof specPatchSchema>;
export type ParsedMutationResponse = z.infer<typeof parsedMutationResponseSchema>;
export type MutationProvenance = z.infer<typeof mutationProvenanceSchema>;
export type CompileResult = z.infer<typeof compileResultSchema>;
export type ApplyResult = z.infer<typeof applyResultSchema>;
export type ChartTarget = z.infer<typeof chartTargetSchema>;
export type SyncArtifact = z.infer<typeof syncArtifactSchema>;
export type ArtifactBundle = z.infer<typeof artifactBundleSchema>;
export type ObjectiveBreakdown = z.infer<typeof objectiveBreakdownSchema>;
export type FallbackEvaluationCompatibility = z.infer<
  typeof fallbackEvaluationCompatibilitySchema
>;
export type FallbackEvaluation = z.infer<typeof fallbackEvaluationSchema>;
export type ConditionContribution = z.infer<typeof conditionContributionSchema>;
export type ExplorationBudget = z.infer<typeof explorationBudgetSchema>;
export type BranchKind = z.infer<typeof branchKindSchema>;
export type FoldFailureMapEntry = z.infer<typeof foldFailureMapEntrySchema>;
export type PromotionDiagnostics = z.infer<typeof promotionDiagnosticsSchema>;
export type MutationBrief = z.infer<typeof mutationBriefSchema>;
export type CandidateArtifact = z.infer<typeof candidateArtifactSchema>;
export type EvaluationExecutorName = z.infer<typeof evaluationExecutorNameSchema>;
export type RunRecord = z.infer<typeof runRecordSchema>;
export type MutationBriefRecord = z.infer<typeof mutationBriefRecordSchema>;
export type AutonomousIterationLearningRecord = z.infer<
  typeof autonomousIterationLearningRecordSchema
>;
export type TaskHypothesis = z.infer<typeof taskHypothesisSchema>;
export type TaskExecutionSummary = z.infer<typeof taskExecutionSummarySchema>;
export type TaskAnalysisSummary = z.infer<typeof taskAnalysisSummarySchema>;
export type TaskRecord = z.infer<typeof taskRecordSchema>;
export type TaskBatchRecord = z.infer<typeof taskBatchRecordSchema>;
export type CandidateLedgerRecord = z.infer<typeof candidateLedgerRecordSchema>;
export type ExperimentRecord = z.infer<typeof experimentRecordSchema>;
export type IncidentRecord = z.infer<typeof incidentRecordSchema>;
export type LineageNode = z.infer<typeof lineageNodeSchema>;
export type KnowledgeStorageClass = z.infer<typeof knowledgeStorageClassSchema>;
export type KnowledgeCatalogEntry = z.infer<typeof knowledgeCatalogEntrySchema>;
export type KnowledgeCatalog = z.infer<typeof knowledgeCatalogSchema>;
export type LocalCompatibilityContract = z.infer<typeof localCompatibilityContractSchema>;

export type DecisionCode =
  | "mutation_generation_fail"
  | "mutation_schema_fail"
  | "preflight_fail"
  | "unsupported_strategy_family"
  | "unsupported_chart_target"
  | "compile_fail"
  | "apply_fail"
  | "artifact_incomplete"
  | "backtest_empty"
  | "hard_gate_fail"
  | "soft_regress"
  | "screening_improvement"
  | "verification_fail"
  | "verified_improvement"
  | "promoted_head"
  | "valid_no_promotion"
  | "accepted_improvement"
  | "accepted_no_improvement";

export interface MarketContextBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  atr14: number | null;
  atrPercent: number | null;
  rsi14: number | null;
  bbWidth: number | null;
  ret3: number | null;
  ret10: number | null;
  regime: string;
}

export interface TradeContextFlags {
  counterTrendEntry: boolean;
  overextendedEntry: boolean;
  lateEntry: boolean;
  weakExit: boolean;
}

export interface EnrichedTradeRecord extends TradeRecord {
  entryContext: MarketContextBar | null;
  exitContext: MarketContextBar | null;
  flags: TradeContextFlags;
}
