import { extractStudyTitle } from "../automation/tradingview/pine-study.js";
import { type PineEvaluationExecutor } from "../automation/common/executor.js";
import {
  type ArtifactBundle,
  type ArtifactValidationResult,
  type BacktestMetrics,
  type ChartTarget,
  type DecisionCode,
  type ExecutorCapability,
  type FallbackEvaluation,
  type LocalTvParitySummary,
  type ObjectiveBreakdown,
  type ObjectiveConfig,
  type SurfaceRecoveryAction,
  type SurfaceRecoveryAttempt,
  type SyncArtifact,
  type VerificationRuntimeFailureKind,
} from "../contracts/types.js";
import { validateArtifactBundle } from "../evaluation/artifact-validation.js";
import { classifyScreeningDecision } from "../evaluation/decision.js";
import { evaluateObjective } from "../evaluation/objective.js";
import { sha256Json } from "../utils/fs.js";

interface MonitorLike {
  log(
    event: string,
    message: string,
    details?: Record<string, unknown>,
  ): Promise<void>;
}

interface FallbackArtifactPayload extends Record<string, unknown> {
  kind: "fallbackEvaluation";
  role: "fallback_evidence";
  candidateId: string;
  source: {
    authoritativeExecutorKind: "tradingview-live";
    authoritativeFailureReason: "verification_runtime_failure";
    runtimeFailureKind: VerificationRuntimeFailureKind;
    recoveryAttempts: SurfaceRecoveryAttempt[];
  };
  fallback: {
    executorKind: "local-af-screening" | "local-af-backtest";
    executorAuthoritative: false;
    promotionEligible: false;
    status: FallbackEvaluation["status"];
    reason: string | null;
    metrics: BacktestMetrics | null;
    objectiveBreakdown: ObjectiveBreakdown | null;
    artifactValidation: ArtifactValidationResult | null;
    decisionIfScreeningOnly: string | null;
  };
  usage: {
    canPromote: false;
    canUpdateActiveHead: false;
    canEnterVerifiedLeaderboard: false;
    canInformNextMutation: true;
  };
  parity: FallbackEvaluation["parity"];
  generatedAt: string;
}

export interface FallbackEvidenceCollectionResult {
  fallbackEvaluation: FallbackEvaluation;
  artifactPayload: FallbackArtifactPayload;
  syncArtifact: SyncArtifact | null;
  artifactBundle: ArtifactBundle | null;
}

export function classifyTradingViewRuntimeFailure(
  error: unknown,
  options?: { assumeTradingView?: boolean },
): VerificationRuntimeFailureKind {
  const detail = error instanceof Error ? error.message : String(error);
  const normalized = detail.toLowerCase();

  if (/monaco|geteditors|editor ready/.test(normalized)) {
    return "monaco_attach_timeout";
  }
  if (/pine editor/.test(normalized)) {
    return "pine_editor_open_timeout";
  }
  if (/chart target|chart load|loading chart/.test(normalized)) {
    return "chart_load_timeout";
  }
  if (/setmonaco|source push|source update/.test(normalized)) {
    return "source_apply_timeout";
  }
  if (/marker|compile panel/.test(normalized)) {
    return "compile_panel_timeout";
  }
  if (/strategy tester/.test(normalized)) {
    return "strategy_tester_timeout";
  }
  if (/report parse|performance_all_missing|trade_list_missing|equity_summary_missing/.test(normalized)) {
    return "report_parse_timeout";
  }
  if (/session closed|target closed|browser has disconnected|websocket.*closed|cdp/.test(normalized)) {
    return "tradingview_session_closed";
  }
  if (
    options?.assumeTradingView ||
    /(tradingview|pine|chart|study attachment|strategy tester|report)/.test(normalized)
  ) {
    return "unknown_runtime_failure";
  }
  return null;
}

export function mapRuntimeFailureToRecoveryAction(
  failureKind: VerificationRuntimeFailureKind,
): SurfaceRecoveryAction {
  switch (failureKind) {
    case "pine_editor_open_timeout":
    case "chart_load_timeout":
      return "soft_reload_chart";
    case "monaco_attach_timeout":
      return "reattach_monaco";
    case "source_apply_timeout":
      return "reopen_pine_editor";
    case "strategy_tester_timeout":
    case "report_parse_timeout":
      return "reopen_strategy_tester";
    case "compile_panel_timeout":
    case "tradingview_session_closed":
    case "unknown_runtime_failure":
    default:
      return "restart_tradingview_page";
  }
}

export async function attemptTradingViewSurfaceRecovery(input: {
  executorFactory: () => PineEvaluationExecutor;
  chartTarget: ChartTarget;
  failureKind: VerificationRuntimeFailureKind;
  attempt: number;
  monitor?: MonitorLike;
}): Promise<{
  recovered: boolean;
  executor?: PineEvaluationExecutor;
  recoveryAttempt: SurfaceRecoveryAttempt;
}> {
  const action = mapRuntimeFailureToRecoveryAction(input.failureKind);
  const startedAt = new Date().toISOString();
  await input.monitor?.log(
    "verification.surface_recovery",
    "Attempting TradingView surface recovery",
    {
      attempt: input.attempt,
      action,
      failureKind: input.failureKind,
      symbol: input.chartTarget.symbol,
      timeframe: input.chartTarget.timeframe,
      chartType: input.chartTarget.chartType,
    },
  );

  let replacementExecutor: PineEvaluationExecutor | undefined;
  try {
    replacementExecutor = input.executorFactory();
    if (replacementExecutor.recoverSurface) {
      await replacementExecutor.recoverSurface({
        action,
        chartTarget: input.chartTarget,
        failureKind: input.failureKind,
      });
    } else {
      await replacementExecutor.prepareChart(input.chartTarget);
    }
    const recoveryAttempt: SurfaceRecoveryAttempt = {
      attempt: input.attempt,
      action,
      startedAt,
      endedAt: new Date().toISOString(),
      status: "succeeded",
      observedFailure: input.failureKind,
    };
    return {
      recovered: true,
      executor: replacementExecutor,
      recoveryAttempt,
    };
  } catch {
    await replacementExecutor?.close?.();
    return {
      recovered: false,
      recoveryAttempt: {
        attempt: input.attempt,
        action,
        startedAt,
        endedAt: new Date().toISOString(),
        status: "failed",
        observedFailure: input.failureKind,
      },
    };
  }
}

export function summarizeLocalTvParity(input: {
  fallbackEvaluation: FallbackEvaluation | null;
  authoritativeMetrics: BacktestMetrics | null;
}): LocalTvParitySummary {
  const fallbackMetrics = input.fallbackEvaluation?.metrics ?? null;
  const authoritativeMetrics = input.authoritativeMetrics;
  if (!fallbackMetrics || !authoritativeMetrics) {
    return {
      status: "not_comparable",
      tradeCountDelta: null,
      netProfitPctDelta: null,
      maxDrawdownPctDelta: null,
      profitFactorDelta: null,
      winRateDelta: null,
    };
  }

  const tradeCountDelta = authoritativeMetrics.totalTrades - fallbackMetrics.totalTrades;
  const netProfitPctDelta =
    authoritativeMetrics.postFeeNetProfitPercent - fallbackMetrics.postFeeNetProfitPercent;
  const maxDrawdownPctDelta =
    authoritativeMetrics.maxStrategyDrawdownPercent -
    fallbackMetrics.maxStrategyDrawdownPercent;
  const profitFactorDelta =
    authoritativeMetrics.profitFactor - fallbackMetrics.profitFactor;
  const winRateDelta =
    authoritativeMetrics.percentProfitable - fallbackMetrics.percentProfitable;

  const absTradeDelta = Math.abs(tradeCountDelta);
  const absNetProfitDelta = Math.abs(netProfitPctDelta);
  const absDrawdownDelta = Math.abs(maxDrawdownPctDelta);
  const absProfitFactorDelta = Math.abs(profitFactorDelta);
  const absWinRateDelta = Math.abs(winRateDelta);

  const status =
    absTradeDelta <= 2 &&
    absNetProfitDelta <= 2 &&
    absDrawdownDelta <= 2 &&
    absProfitFactorDelta <= 0.15 &&
    absWinRateDelta <= 5
      ? "matched"
      : absTradeDelta <= 10 &&
          absNetProfitDelta <= 8 &&
          absDrawdownDelta <= 5 &&
          absProfitFactorDelta <= 0.5 &&
          absWinRateDelta <= 12
        ? "minor_drift"
        : "major_drift";

  return {
    status,
    tradeCountDelta,
    netProfitPctDelta,
    maxDrawdownPctDelta,
    profitFactorDelta,
    winRateDelta,
  };
}

export function buildFallbackEvidenceFromScreening(input: {
  candidateId: string;
  chartTarget: ChartTarget;
  authoritativeFailureKind: VerificationRuntimeFailureKind;
  recoveryAttempts: SurfaceRecoveryAttempt[];
  metrics: BacktestMetrics | null;
  objectiveBreakdown: ObjectiveBreakdown | null;
  artifactValidation: ArtifactValidationResult | null;
  decisionIfScreeningOnly: DecisionCode | null;
  artifactBundle: ArtifactBundle | null;
}): FallbackEvidenceCollectionResult {
  return buildFallbackEvidenceResult({
    candidateId: input.candidateId,
    chartTarget: input.chartTarget,
    authoritativeFailureKind: input.authoritativeFailureKind,
    recoveryAttempts: input.recoveryAttempts,
    status: "succeeded",
    reason: "reused_primary_screening_result",
    metrics: input.metrics,
    objectiveBreakdown: input.objectiveBreakdown,
    artifactValidation: input.artifactValidation,
    decisionIfScreeningOnly: input.decisionIfScreeningOnly,
    artifactBundle: input.artifactBundle,
    caveats: [
      "Primary local backtest result was reused as fallback evidence after authoritative runtime failure.",
      "Do not treat reused local backtest evidence as authoritative verification.",
    ],
    confidence: "very_low",
    compatibility: {
      symbol: input.chartTarget.symbol,
      timeframe: input.chartTarget.timeframe,
      strategyFamily: "AF",
      compatible: true,
      reasons: [],
    },
  });
}

export async function collectLocalFallbackEvidence(input: {
  candidateId: string;
  pineSource: string;
  chartTarget: ChartTarget;
  objective: ObjectiveConfig;
  acceptedHeadScore: number | null;
  maxTrades?: number;
  authoritativeFailureKind: VerificationRuntimeFailureKind;
  recoveryAttempts: SurfaceRecoveryAttempt[];
  executorFactory: () => PineEvaluationExecutor;
  monitor?: MonitorLike;
}): Promise<FallbackEvidenceCollectionResult> {
  const executor = input.executorFactory();
  const executorCapability = executor.getCapability();
  const compatibility =
    (await executor.assessCompatibility?.({
      source: input.pineSource,
      chartTarget: input.chartTarget,
    })) ?? {
      supported: true,
      reasonCode: null,
      detail: null,
    };
  if (!compatibility.supported) {
    await executor.close?.();
    return buildFallbackEvidenceResult({
      candidateId: input.candidateId,
      chartTarget: input.chartTarget,
      authoritativeFailureKind: input.authoritativeFailureKind,
      recoveryAttempts: input.recoveryAttempts,
      status: "unsupported",
      reason: compatibility.detail ?? compatibility.reasonCode ?? "unsupported_local_fallback",
      metrics: null,
      objectiveBreakdown: null,
      artifactValidation: null,
      decisionIfScreeningOnly: compatibility.reasonCode ?? "unsupported_strategy_family",
      artifactBundle: null,
      caveats: [
          "Local fallback executor could not evaluate this candidate under the AF backtest constraints.",
      ],
      confidence: "very_low",
      compatibility: {
        symbol: input.chartTarget.symbol,
        timeframe: input.chartTarget.timeframe,
        strategyFamily:
          compatibility.reasonCode === "unsupported_chart_target" ? "AF" : "unknown",
        compatible: false,
        reasons: [
          compatibility.reasonCode ?? "unsupported_strategy_family",
          ...(compatibility.detail ? [compatibility.detail] : []),
        ],
      },
    });
  }

  const studyTitle = extractStudyTitle(input.pineSource);
  let compile: SyncArtifact["compile"] | null = null;
  let apply: SyncArtifact["apply"] | null = null;
  let syncArtifact: SyncArtifact | null = null;
  let artifactBundle: ArtifactBundle | null = null;
  let artifactValidation: ArtifactValidationResult | null = null;
  let objectiveBreakdown: ObjectiveBreakdown | null = null;
  let metrics: BacktestMetrics | null = null;
  let decisionIfScreeningOnly: DecisionCode | null = null;

  try {
    await input.monitor?.log(
      "fallback.local.start",
      "Collecting local fallback evidence",
      {
        candidateId: input.candidateId,
        symbol: input.chartTarget.symbol,
        timeframe: input.chartTarget.timeframe,
        executorKind: executorCapability.kind,
      },
    );
    await executor.prepareChart(input.chartTarget);
    await executor.updateStrategySource(input.pineSource);
    compile = await executor.compileStrategy();
    syncArtifact =
      (await executor.buildSyncArtifact?.({
        chartTarget: input.chartTarget,
        compile,
      })) ?? null;
    if (!compile.ok) {
      decisionIfScreeningOnly = "compile_fail";
      return buildFallbackEvidenceResult({
        candidateId: input.candidateId,
        chartTarget: input.chartTarget,
        authoritativeFailureKind: input.authoritativeFailureKind,
        recoveryAttempts: input.recoveryAttempts,
        status: "succeeded",
        reason: compile.errors.join(" | ") || "local_compile_fail",
        metrics,
        objectiveBreakdown,
        artifactValidation,
        decisionIfScreeningOnly,
        artifactBundle,
        syncArtifact,
        caveats: [
          "Local fallback compile failed; this is non-authoritative diagnostic evidence only.",
        ],
        confidence: "very_low",
        compatibility: {
          symbol: input.chartTarget.symbol,
          timeframe: input.chartTarget.timeframe,
          strategyFamily: "AF",
          compatible: true,
          reasons: [],
        },
      });
    }

    apply = await executor.applyStrategy({
      expectedStudyTitle: studyTitle,
    });
    syncArtifact =
      (await executor.buildSyncArtifact?.({
        chartTarget: input.chartTarget,
        compile,
        apply,
      })) ?? syncArtifact;
    if (!apply.ok) {
      decisionIfScreeningOnly = "apply_fail";
      return buildFallbackEvidenceResult({
        candidateId: input.candidateId,
        chartTarget: input.chartTarget,
        authoritativeFailureKind: input.authoritativeFailureKind,
        recoveryAttempts: input.recoveryAttempts,
        status: "succeeded",
        reason: apply.message || "local_apply_fail",
        metrics,
        objectiveBreakdown,
        artifactValidation,
        decisionIfScreeningOnly,
        artifactBundle,
        syncArtifact,
        caveats: [
          "Local fallback apply failed; this is non-authoritative diagnostic evidence only.",
        ],
        confidence: "very_low",
        compatibility: {
          symbol: input.chartTarget.symbol,
          timeframe: input.chartTarget.timeframe,
          strategyFamily: "AF",
          compatible: true,
          reasons: [],
        },
      });
    }

    artifactBundle = await executor.readArtifactBundle({
      expectedStudyTitle: studyTitle,
      maxTrades: input.maxTrades,
    });
    artifactValidation = validateArtifactBundle({
      artifactBundle,
      executorCapability,
    });
    metrics = artifactBundle.strategy ?? null;
    if (!metrics || metrics.totalTrades <= 0) {
      decisionIfScreeningOnly = "backtest_empty";
      return buildFallbackEvidenceResult({
        candidateId: input.candidateId,
        chartTarget: input.chartTarget,
        authoritativeFailureKind: input.authoritativeFailureKind,
        recoveryAttempts: input.recoveryAttempts,
        status: "succeeded",
        reason: "local_backtest_empty",
        metrics,
        objectiveBreakdown,
        artifactValidation,
        decisionIfScreeningOnly,
        artifactBundle,
        syncArtifact,
        caveats: [
          "Local fallback produced no trades; this remains non-authoritative evidence only.",
        ],
        confidence: "very_low",
        compatibility: {
          symbol: input.chartTarget.symbol,
          timeframe: input.chartTarget.timeframe,
          strategyFamily: "AF",
          compatible: true,
          reasons: [],
        },
      });
    }

    objectiveBreakdown = evaluateObjective(metrics, input.objective);
    decisionIfScreeningOnly = classifyScreeningDecision(
      objectiveBreakdown,
      input.acceptedHeadScore,
    );
    return buildFallbackEvidenceResult({
      candidateId: input.candidateId,
      chartTarget: input.chartTarget,
      authoritativeFailureKind: input.authoritativeFailureKind,
      recoveryAttempts: input.recoveryAttempts,
      status: "succeeded",
      reason: "local_fallback_completed",
      metrics,
      objectiveBreakdown,
      artifactValidation,
      decisionIfScreeningOnly,
      artifactBundle,
      syncArtifact,
      caveats: [
        "Local fallback evidence was collected after authoritative TradingView runtime failure.",
        "Do not treat local fallback evidence as verified improvement.",
      ],
      confidence: "very_low",
      compatibility: {
        symbol: input.chartTarget.symbol,
        timeframe: input.chartTarget.timeframe,
        strategyFamily: "AF",
        compatible: true,
        reasons: [],
      },
    });
  } catch (error) {
    return buildFallbackEvidenceResult({
      candidateId: input.candidateId,
      chartTarget: input.chartTarget,
      authoritativeFailureKind: input.authoritativeFailureKind,
      recoveryAttempts: input.recoveryAttempts,
      status: "failed",
      reason: error instanceof Error ? error.message : String(error),
      metrics,
      objectiveBreakdown,
      artifactValidation,
      decisionIfScreeningOnly,
      artifactBundle,
      syncArtifact,
      caveats: [
        "Local fallback execution failed before a stable evidence bundle could be collected.",
      ],
      confidence: "very_low",
      compatibility: {
        symbol: input.chartTarget.symbol,
        timeframe: input.chartTarget.timeframe,
        strategyFamily: "AF",
        compatible: true,
        reasons: [],
      },
    });
  } finally {
    await executor.close?.();
  }
}

function buildFallbackEvidenceResult(input: {
  candidateId: string;
  chartTarget: ChartTarget;
  authoritativeFailureKind: VerificationRuntimeFailureKind;
  recoveryAttempts: SurfaceRecoveryAttempt[];
  status: FallbackEvaluation["status"];
  reason: string | null;
  metrics: BacktestMetrics | null;
  objectiveBreakdown: ObjectiveBreakdown | null;
  artifactValidation: ArtifactValidationResult | null;
  decisionIfScreeningOnly: string | null;
  artifactBundle: ArtifactBundle | null;
  syncArtifact?: SyncArtifact | null;
  caveats: string[];
  confidence: FallbackEvaluation["confidence"];
  compatibility: FallbackEvaluation["compatibility"];
}): FallbackEvidenceCollectionResult {
  const basePayload: FallbackArtifactPayload = {
    kind: "fallbackEvaluation",
    role: "fallback_evidence",
    candidateId: input.candidateId,
    source: {
      authoritativeExecutorKind: "tradingview-live",
      authoritativeFailureReason: "verification_runtime_failure",
      runtimeFailureKind: input.authoritativeFailureKind,
      recoveryAttempts: input.recoveryAttempts,
    },
    fallback: {
      executorKind: "local-af-backtest",
      executorAuthoritative: false,
      promotionEligible: false,
      status: input.status,
      reason: input.reason,
      metrics: input.metrics,
      objectiveBreakdown: input.objectiveBreakdown,
      artifactValidation: input.artifactValidation,
      decisionIfScreeningOnly: input.decisionIfScreeningOnly,
    },
    usage: {
      canPromote: false,
      canUpdateActiveHead: false,
      canEnterVerifiedLeaderboard: false,
      canInformNextMutation: true,
    },
    parity: {
      status: "not_comparable",
      tradeCountDelta: null,
      netProfitPctDelta: null,
      maxDrawdownPctDelta: null,
      profitFactorDelta: null,
      winRateDelta: null,
    },
    generatedAt: new Date().toISOString(),
  };
  const artifactHash = sha256Json(basePayload);
  const artifactId = `fallback-evidence-${input.candidateId}`;
  const fallbackEvaluation: FallbackEvaluation = {
    role: "fallback_evidence",
    executorKind: "local-af-backtest",
    executorAuthoritative: false,
    promotionEligible: false,
    status: input.status,
    reason: input.reason,
    artifactId,
    artifactHash,
    metrics: input.metrics,
    objectiveBreakdown: input.objectiveBreakdown,
    artifactValidation: input.artifactValidation,
    decisionIfScreeningOnly: input.decisionIfScreeningOnly,
    compatibility: input.compatibility,
    evidenceUse: "mutation_context_only",
    confidence: input.confidence,
    caveats: input.caveats,
    parity: basePayload.parity,
  };

  return {
    fallbackEvaluation,
    artifactPayload: basePayload,
    syncArtifact: input.syncArtifact ?? null,
    artifactBundle: input.artifactBundle,
  };
}
