#!/usr/bin/env node

import os from "node:os";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { Command } from "commander";

import { loadObjectiveConfig } from "../config/objective.js";
import { loadAllResearchTargets } from "../config/target-registry.js";
import { evaluateObjective } from "../evaluation/objective.js";
import {
  assertPromotionEligible,
  classifyAuthoritativeDecision,
  classifyScreeningDecision,
  derivePromotionReadiness,
  derivePromotionStatus,
  deriveVerificationFailureReason,
  deriveVerificationStatus,
  normalizeDecisionCode,
  resolveRecordEra,
} from "../evaluation/decision.js";
import {
  isArtifactPromotionReady,
  isArtifactVerificationReady,
  validateArtifactBundle,
} from "../evaluation/artifact-validation.js";
import { collectPromotionEvidenceIssueDetails } from "../evaluation/record-eligibility.js";
import { extractStudyTitle } from "../automation/tradingview/pine-study.js";
import {
  type ArtifactValidationResult,
  type ArtifactBundle,
  type BacktestMetrics,
  type CompileResult,
  type DecisionCode,
  type EvaluationExecutorName,
  type ExperimentRecord,
  type ExecutorCapability,
  type FallbackEvaluation,
  type ObjectiveBreakdown,
  type ObjectiveConfig,
  type SurfaceRecoveryAttempt,
  type SyncArtifact,
  type ApplyResult,
  type MetricComparison,
  type LocalTvParitySummary,
  type VerificationStatus,
  type VerificationFailureReason,
  type VerificationRuntimeFailureKind,
} from "../contracts/types.js";
import { persistCandidateArtifact } from "../mutation/candidate-store.js";
import {
  parseMutationResponseStrict,
  parseMutationResponseWithRecovery,
  inferConditionInventoryFromPine,
} from "../mutation/parser.js";
import {
  formatPreflightIssuesForRepair,
  inspectGeneratedMutation,
} from "../mutation/preflight.js";
import { writeMutationRuntimeArtifact } from "../mutation/runtime-artifact.js";
import { buildObjectiveArtifact, writeIterationArtifacts } from "../research/artifact-writer.js";
import { ingestResearchKnowledge } from "../research/research-knowledge.js";
import { runSingleIteration } from "../research/iteration-runner.js";
import { runAutonomousIterations } from "../research/autonomous/autonomous-loop.js";
import { runStrategyReviewBatchForTarget } from "../research/autonomous/strategy-review-phase.js";
import { runAutoSelectionPhase } from "../research/autonomous/auto-selection-phase.js";
import { runLocalEvaluationPhase } from "../research/autonomous/local-evaluation-phase.js";
import {
  runStage6ReadinessGate,
  type Stage6CalibrationMode,
  type Stage6ReadinessMode,
} from "../research/autonomous/stage6-readiness.js";
import {
  processTvCalibrationQueue,
  selectPendingCalibrationCandidates,
} from "../research/autonomous/tv-calibration-phase.js";
import { buildCalibrationBackpressure } from "../research/autonomous/calibration-backpressure.js";
import { resolveTvHealthStatus } from "../research/autonomous/tv-health-phase.js";
import {
  prepareMutationContext,
  resolveMutationSourcePine,
} from "../research/mutation-context.js";
import {
  attemptTradingViewSurfaceRecovery,
  classifyTradingViewRuntimeFailure,
  collectLocalFallbackEvidence,
  summarizeLocalTvParity,
} from "../research/verification-fallback.js";
import { loadSeedStrategyReference } from "../research/seed-strategy.js";
import { runTaskBatch } from "../research/task-batch-runner.js";
import { generateIndicatorArtifact } from "../research/indicator-generator.js";
import { initializeWorkspace } from "../research/workspace.js";
import { rebuildIndexes } from "../state/index-builder.js";
import { findBestAcceptedRecord, findLegacyAcceptedRecord } from "../state/accepted-head.js";
import { buildAutonomousViewPayloads } from "../state/autonomous-index-builder.js";
import {
  findActiveChampionRecord,
  selectLocalEvaluationRecords,
  selectTvVerificationRecords,
} from "../state/autonomous-state.js";
import {
  appendCalibrationEventRecord,
  appendCandidateLedgerRecord,
  appendExperimentRecord,
  appendIncidentRecord,
  appendRunRecord,
  compactExperimentLedger,
  ensureStateRoot,
  readArchiveEventRecords,
  readCalibrationEventRecords,
  readCandidateLedgerRecords,
  readExperimentRecords,
  readHeadEventRecords,
  readIndicatorArtifactRecords,
  readLocalConfidenceEventRecords,
  readMutationBriefRecords,
  readProblemEventRecords,
  readRepairAttemptRecords,
  readStrategyReviewRecords,
  resolveStatePaths,
} from "../state/jsonl-store.js";
import {
  AUTORESEARCH_CONTRACT_VERSION,
  STRATEGY_SPEC_MUTATION_AUTHORITY,
} from "../policy/autoresearch-contract.js";
import {
  validateLedger,
  verifyDerivedViews,
  type LedgerValidationMode,
} from "../state/ledger-validator.js";
import {
  buildArtifactRetentionReport,
  buildSystemHealthReport,
  cleanupRuntime,
} from "../state/operational-reports.js";
import {
  auditKnowledgeTree,
  migrateLegacyKnowledgeLayout,
} from "../state/knowledge-catalog.js";
import { resolveKnowledgePaths } from "../state/knowledge-paths.js";
import { createCandidateId, fileExists, readJson, sha256, writeJson } from "../utils/fs.js";
import { createPineEvaluationExecutor } from "./executor-factory.js";
import { createMutationLlmClient } from "./llm-factory.js";
import { type MutationLlmClient } from "../mutation/llm-client.js";
import { isMonitorLoggedError, withCliMonitor } from "./monitor.js";
import { ensureAlphaXivAuthReady, loginAlphaXivWithBrowser } from "./alphaxiv-auth.js";
import {
  createAutomaticTaskBatchRecoveryHooks,
  inferAutomaticRecoverySurface,
} from "./run-tasks-autoheal.js";
import { ensureOpenAiAuthReady } from "./openai-oauth.js";
import {
  type RuntimeEnvironment,
  loadRuntimeEnvironment,
} from "./runtime-config.js";
import { reconcileAutonomousLoopRuntime } from "./runtime-heartbeat.js";
import { startDashboardServer } from "../dashboard/server.js";

const program = new Command();
program.name("af");
program
  .option("--project-root <path>", "Override the template/project root used for bootstrap")
  .option("--workspace-root <path>", "Override the workspace root used for runtime artifacts")
  .option("--state-root <path>", "Override the layered state root used for ledgers and views");
const DEFAULT_TASK_BATCH_COUNT = 3;

function loadRuntimeEnvironmentForTarget(targetId: string): RuntimeEnvironment {
  const previousTargetId = process.env.AF_RESEARCH_TARGET_ID;
  process.env.AF_RESEARCH_TARGET_ID = targetId;
  try {
    return loadRuntimeEnvironment();
  } finally {
    if (previousTargetId == null) {
      delete process.env.AF_RESEARCH_TARGET_ID;
    } else {
      process.env.AF_RESEARCH_TARGET_ID = previousTargetId;
    }
  }
}

function resolveTargetIds(baseEnv: RuntimeEnvironment, targetOption?: string): string[] {
  const requested = targetOption ?? baseEnv.researchTargetId;
  if (requested !== "all") {
    return [requested];
  }
  const targets = loadAllResearchTargets({
    projectRoot: baseEnv.projectRoot,
    workspaceRoot: baseEnv.workspaceRoot,
  });
  if (targets.length === 0) {
    throw new Error("No research targets were found under config/targets.");
  }
  return targets.map((target) => target.id);
}

async function writeNodeRuntimeTelemetry(input: {
  stateRoot: string;
  commandName: string;
  phase: string;
  extra?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  const memory = process.memoryUsage();
  const totalMemoryBytes = os.totalmem();
  const telemetry = {
    generatedAt: new Date().toISOString(),
    commandName: input.commandName,
    phase: input.phase,
    pid: process.pid,
    rssMB: roundMb(memory.rss),
    heapUsedMB: roundMb(memory.heapUsed),
    heapTotalMB: roundMb(memory.heapTotal),
    externalMB: roundMb(memory.external),
    arrayBuffersMB: roundMb(memory.arrayBuffers),
    systemTotalMemoryMB: roundMb(totalMemoryBytes),
    rssToSystemRatio: roundRatio(memory.rss / totalMemoryBytes),
    ...(input.extra ?? {}),
  };
  await writeJson(
    path.join(input.stateRoot, "runtime", "node-memory-telemetry.json"),
    telemetry,
  );
  return telemetry;
}

function roundMb(bytes: number): number {
  return Math.round((bytes / 1024 / 1024) * 100) / 100;
}

function roundRatio(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

function findLatestCompileFailRecord(
  records: Awaited<ReturnType<typeof readExperimentRecords>>,
  candidate?: string,
) {
  const reversed = [...records].reverse();
  if (!candidate) {
    return reversed.find((record) => record.decision === "compile_fail") ?? null;
  }

  const normalizedCandidate = candidate.toLowerCase();
  return (
    reversed.find((record) => {
      const candidateIdMatches =
        record.candidateId.toLowerCase() === normalizedCandidate;
      const candidatePathMatches =
        record.candidatePath?.toLowerCase() === normalizedCandidate;
      const fileNameMatches =
        path.basename(record.candidatePath ?? "", ".pine").toLowerCase() ===
        normalizedCandidate;
      return record.decision === "compile_fail" && (candidateIdMatches || candidatePathMatches || fileNameMatches);
    }) ?? null
  );
}

function resolveCandidatePath(workspaceRoot: string, candidate: string): string {
  return candidate.endsWith(".pine")
    ? path.resolve(candidate)
    : path.join(workspaceRoot, "strategies", "candidates", `${candidate}.pine`);
}

async function evaluateCandidateFile(input: {
  workspaceRoot: string;
  candidate: string;
  executor: ReturnType<typeof createPineEvaluationExecutor>;
  objective: ObjectiveConfig;
  acceptedHeadScore?: number | null;
  chartSymbol: string;
  chartTimeframe: string;
  chartType: string;
  maxTrades: number;
  monitor: {
    log: (
      event: string,
      message: string,
      details?: Record<string, unknown>,
    ) => Promise<void>;
    tracePath: string;
  };
}): Promise<{
  candidateId: string;
  candidatePath: string;
  candidateHash: string;
  pineScript: string;
  studyTitle: string | null;
  executorCapability: ExecutorCapability;
  decision: DecisionCode;
  verificationStatus: VerificationStatus;
  verificationFailureReason: VerificationFailureReason;
  promotionReady: boolean;
  compile: CompileResult | null;
  apply: ApplyResult | null;
  syncArtifact: SyncArtifact | null;
  artifactBundle: ArtifactBundle | null;
  testerMetrics: BacktestMetrics | null;
  artifactValidation: ArtifactValidationResult | null;
  objectiveBreakdown: ObjectiveBreakdown | null;
  verificationRuntimeFailureKind?: VerificationRuntimeFailureKind | null;
  recoveryAttempts?: SurfaceRecoveryAttempt[];
  fallbackEvaluation?: FallbackEvaluation | null;
  fallbackEvaluationArtifact?: Record<string, unknown> | null;
}> {
  const candidatePath = resolveCandidatePath(input.workspaceRoot, input.candidate);
  const pineScript = await readFile(candidatePath, "utf8");
  const studyTitle = extractStudyTitle(pineScript);
  const executorCapability = input.executor.getCapability();
  const chartTarget = {
    symbol: input.chartSymbol,
    timeframe: input.chartTimeframe,
    chartType: input.chartType,
  };

  await input.monitor.log("evaluate.start", "Starting candidate evaluation", {
    candidate: input.candidate,
    candidatePath,
  });

  const compatibility =
    (await input.executor.assessCompatibility?.({
      source: pineScript,
      chartTarget,
    })) ?? {
      supported: true,
      reasonCode: null,
      detail: null,
    };
  if (!compatibility.supported) {
    const decision = compatibility.reasonCode ?? "unsupported_strategy_family";
    const verificationStatus = deriveVerificationStatus({
      decision,
      executorCapability,
      usedVerificationExecutor: false,
    });
    await input.monitor.log("evaluate.compatibility", "Candidate is outside executor compatibility", {
      decision,
      detail: compatibility.detail,
      executorKind: executorCapability.kind,
    });
    return {
      candidateId: path.basename(candidatePath, ".pine"),
      candidatePath,
      candidateHash: sha256(pineScript),
      pineScript,
      studyTitle,
      executorCapability,
      decision,
      verificationStatus,
      verificationFailureReason: null,
      promotionReady: false,
      compile: null,
      apply: null,
      syncArtifact: null,
      artifactBundle: null,
      testerMetrics: null,
      artifactValidation: null,
      objectiveBreakdown: null,
    };
  }

  await input.executor.prepareChart(chartTarget);
  await input.monitor.log("executor.chart_ready", "Evaluation surface prepared", {
    symbol: input.chartSymbol,
    timeframe: input.chartTimeframe,
    chartType: input.chartType,
  });
  await input.executor.updateStrategySource(pineScript);
  await input.monitor.log("executor.source_updated", "Pine source pushed", {
    candidatePath,
    sourceLength: pineScript.length,
  });
  const compile = await input.executor.compileStrategy();
  await input.monitor.log("executor.compile", "Compile finished", {
    ok: compile.ok,
    errors: compile.errors,
  });
  if (!compile.ok) {
    const verificationStatus = deriveVerificationStatus({
      decision: "compile_fail",
      executorCapability,
      usedVerificationExecutor: false,
    });
    return {
      candidateId: path.basename(candidatePath, ".pine"),
      candidatePath,
      candidateHash: sha256(pineScript),
      pineScript,
      studyTitle,
      executorCapability,
      decision: "compile_fail",
      verificationStatus,
      verificationFailureReason: null,
      promotionReady: false,
      compile,
      apply: null,
      syncArtifact:
        (await input.executor.buildSyncArtifact?.({
          chartTarget,
          compile,
        })) ?? null,
      artifactBundle: null,
      testerMetrics: null,
      artifactValidation: null,
      objectiveBreakdown: null,
    };
  }

  const apply = await input.executor.applyStrategy({
    expectedStudyTitle: studyTitle,
  });
  await input.monitor.log("executor.apply", "Apply finished", {
    ok: apply.ok,
    message: apply.message,
  });
  if (!apply.ok) {
    const verificationStatus = deriveVerificationStatus({
      decision: "apply_fail",
      executorCapability,
      usedVerificationExecutor: false,
    });
    return {
      candidateId: path.basename(candidatePath, ".pine"),
      candidatePath,
      candidateHash: sha256(pineScript),
      pineScript,
      studyTitle,
      executorCapability,
      decision: "apply_fail",
      verificationStatus,
      verificationFailureReason: null,
      promotionReady: false,
      compile,
      apply,
      syncArtifact:
        (await input.executor.buildSyncArtifact?.({
          chartTarget,
          compile,
          apply,
        })) ?? null,
      artifactBundle: null,
      testerMetrics: null,
      artifactValidation: null,
      objectiveBreakdown: null,
    };
  }

  const artifactBundle = await input.executor.readArtifactBundle({
    expectedStudyTitle: studyTitle,
    maxTrades: input.maxTrades,
  });
  const testerMetrics = artifactBundle.strategy ?? null;
  const artifactValidation = validateArtifactBundle({
    artifactBundle,
    executorCapability,
  });
  await input.monitor.log("executor.metrics", "Backtest metrics captured", {
    totalTrades: testerMetrics?.totalTrades ?? 0,
    netProfitPercent: testerMetrics?.netProfitPercent ?? 0,
    tradesCollected: artifactBundle.trades.length,
    equityPoints: artifactBundle.equity.pointCount,
  });
  const syncArtifact =
    (await input.executor.buildSyncArtifact?.({
      chartTarget,
      compile,
      apply,
    })) ?? null;

  if (executorCapability.authoritative && !isArtifactVerificationReady(artifactValidation)) {
    const verificationStatus = deriveVerificationStatus({
      decision: "artifact_incomplete",
      executorCapability,
      usedVerificationExecutor: false,
    });
    return {
      candidateId: path.basename(candidatePath, ".pine"),
      candidatePath,
      candidateHash: sha256(pineScript),
      pineScript,
      studyTitle,
      executorCapability,
      decision: "artifact_incomplete",
      verificationStatus,
      verificationFailureReason: deriveVerificationFailureReason({
        decision: "artifact_incomplete",
        artifactValidation,
        hadRuntimeFailure: false,
        wasBacktestEmpty: false,
        usedVerificationExecutor: false,
      }),
      promotionReady: false,
      compile,
      apply,
      syncArtifact,
      artifactBundle,
      testerMetrics,
      artifactValidation,
      objectiveBreakdown: null,
    };
  }

  if (!testerMetrics || testerMetrics.totalTrades <= 0) {
    const verificationStatus = deriveVerificationStatus({
      decision: "backtest_empty",
      executorCapability,
      usedVerificationExecutor: false,
    });
    return {
      candidateId: path.basename(candidatePath, ".pine"),
      candidatePath,
      candidateHash: sha256(pineScript),
      pineScript,
      studyTitle,
      executorCapability,
      decision: "backtest_empty",
      verificationStatus,
      verificationFailureReason: deriveVerificationFailureReason({
        decision: "verification_fail",
        artifactValidation,
        hadRuntimeFailure: false,
        wasBacktestEmpty: true,
        usedVerificationExecutor: false,
      }),
      promotionReady: false,
      compile,
      apply,
      syncArtifact,
      artifactBundle,
      testerMetrics,
      artifactValidation,
      objectiveBreakdown: null,
    };
  }

  const objectiveBreakdown = evaluateObjective(testerMetrics, input.objective);
  const acceptedHeadScore = input.acceptedHeadScore ?? null;
  const decision = executorCapability.authoritative
    ? classifyAuthoritativeDecision({
        breakdown: objectiveBreakdown,
        acceptedHeadScore,
        artifactValidation,
      })
    : classifyScreeningDecision(objectiveBreakdown, acceptedHeadScore);
  const verificationStatus = deriveVerificationStatus({
    decision,
    executorCapability,
    usedVerificationExecutor: false,
  });
  await input.monitor.log("evaluation.objective", "Objective evaluated", {
    decision,
    score: objectiveBreakdown.score,
  });

  return {
    candidateId: path.basename(candidatePath, ".pine"),
    candidatePath,
    candidateHash: sha256(pineScript),
    pineScript,
    studyTitle,
    executorCapability,
    decision,
    verificationStatus,
    verificationFailureReason: deriveVerificationFailureReason({
      decision,
      artifactValidation,
      hadRuntimeFailure: false,
      wasBacktestEmpty: false,
      usedVerificationExecutor: false,
    }),
    promotionReady: derivePromotionReadiness({
      decision,
      artifactValidation,
      executorCapability,
      verificationStatus,
      fallbackEvaluation: null,
      mutationProvenance: null,
    }),
    compile,
    apply,
    syncArtifact,
    artifactBundle,
    testerMetrics,
    artifactValidation,
    objectiveBreakdown,
  };
}

function parsePositiveInteger(value: string, label: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`${label} must be a positive integer.`);
  }
  return parsed;
}

function parseNonNegativeInteger(value: string, label: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new Error(`${label} must be a non-negative integer.`);
  }
  return parsed;
}

function parseBoolean(value: string, label: string): boolean {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  throw new Error(`${label} must be true or false.`);
}

function parseStage6ReadinessMode(value: string): Stage6ReadinessMode {
  if (value === "deterministic" || value === "real-llm") {
    return value;
  }
  throw new Error('mode must be "deterministic" or "real-llm".');
}

function parseStage6CalibrationMode(value: string): Stage6CalibrationMode {
  if (value === "mock-recovered" || value === "live") {
    return value;
  }
  throw new Error('calibration mode must be "mock-recovered" or "live".');
}

function parseLedgerValidationMode(value: string | undefined): LedgerValidationMode {
  if (value == null || value === "") {
    return "fast";
  }
  if (value === "fast" || value === "deep") {
    return value;
  }
  throw new Error('ledger validation mode must be "fast" or "deep".');
}

async function assertPromotionEvidenceFilesExist(
  record: ExperimentRecord,
): Promise<void> {
  const fileIssueCodes = new Set([
    "candidate_path_missing",
    "candidate_file_missing",
    "backtest_artifact_path_missing",
    "artifact_file_missing",
  ]);
  const issues = collectPromotionEvidenceIssueDetails(record)
    .filter((issue) => fileIssueCodes.has(issue.code))
    .map((issue) => issue.message);

  if (issues.length > 0) {
    throw new Error(issues.join(" "));
  }
}

function parseBoundedTaskCount(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 10) {
    throw new Error("Task count must be between 1 and 10.");
  }
  return parsed;
}

function parseSurfaceRecoveryAttempts(value: string): 0 | 1 {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || (parsed !== 0 && parsed !== 1)) {
    throw new Error("Surface recovery attempts must be 0 or 1.");
  }
  return parsed;
}

function parseCommaSeparatedList(value?: string): string[] {
  if (!value) {
    return [];
  }

  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function matchesCandidateReference(
  reference: string,
  candidateId: string,
  candidatePath?: string | null,
): boolean {
  const normalizedReference = reference.toLowerCase();
  return (
    candidateId.toLowerCase() === normalizedReference ||
    candidatePath?.toLowerCase() === normalizedReference ||
    path.basename(candidatePath ?? "", ".pine").toLowerCase() ===
      normalizedReference
  );
}

function findLatestExperimentForCandidate(
  records: Awaited<ReturnType<typeof readExperimentRecords>>,
  candidate: string,
) {
  const reversed = [...records].reverse();
  return (
    reversed.find((record) =>
      matchesCandidateReference(candidate, record.candidateId, record.candidatePath),
    ) ?? null
  );
}

function findLatestVerifiedExperimentForCandidate(
  records: Awaited<ReturnType<typeof readExperimentRecords>>,
  candidate: string,
) {
  const reversed = [...records].reverse();
  return (
    reversed.find((record) => {
      if (!matchesCandidateReference(candidate, record.candidateId, record.candidatePath)) {
        return false;
      }
      const normalizedDecision = normalizeDecisionCode(record.decision);
      return (
        normalizedDecision === "verified_improvement" ||
        record.verificationStatus === "verified" ||
        record.promotionStatus === "verified_improvement" ||
        record.promotionStatus === "promoted_head"
      );
    }) ?? null
  );
}

function findLatestFallbackExperimentForCandidate(
  records: Awaited<ReturnType<typeof readExperimentRecords>>,
  candidate: string,
) {
  const reversed = [...records].reverse();
  return (
    reversed.find(
      (record) =>
        matchesCandidateReference(candidate, record.candidateId, record.candidatePath) &&
        record.fallbackEvaluation != null,
    ) ?? null
  );
}

function buildAutonomousReplayMutationProvenance(
  record: ExperimentRecord | null,
): NonNullable<ExperimentRecord["mutationProvenance"]> {
  if (record?.mutationProvenance) {
    return record.mutationProvenance;
  }

  return {
    briefHash: null,
    promptHash: null,
    responseHash: null,
    responseSchemaVersion: null,
    parseStatus: "invalid",
    inventorySource: null,
    inferredFields: ["inventory"],
    missingFields: ["briefHash", "promptHash", "responseHash"],
  };
}

function resolveLocalTvParityForVerification(input: {
  fallbackRecord: Awaited<ReturnType<typeof findLatestFallbackExperimentForCandidate>>;
  testerMetrics: BacktestMetrics | null;
  verificationStatus: VerificationStatus;
  fallbackEvaluation: FallbackEvaluation | null | undefined;
}): LocalTvParitySummary | null {
  if (
    input.verificationStatus !== "verified" ||
    input.testerMetrics == null ||
    input.fallbackEvaluation != null ||
    input.fallbackRecord?.fallbackEvaluation == null
  ) {
    return null;
  }

  return summarizeLocalTvParity({
    fallbackEvaluation: input.fallbackRecord.fallbackEvaluation,
    authoritativeMetrics: input.testerMetrics,
  });
}

async function buildAutonomousStateSummary(input: {
  stateRoot: string;
  env: RuntimeEnvironment;
}) {
  const knowledgePaths = resolveKnowledgePaths(input.stateRoot);
  const experiments = await readExperimentRecords(input.stateRoot);
  const headEvents = await readHeadEventRecords(input.stateRoot);
  const archiveEvents = await readArchiveEventRecords(input.stateRoot);
  const calibrationEvents = await readCalibrationEventRecords(input.stateRoot);
  const confidenceEvents = await readLocalConfidenceEventRecords(input.stateRoot);
  const problemEvents = await readProblemEventRecords(input.stateRoot);
  const repairAttempts = await readRepairAttemptRecords(input.stateRoot);
  const indicatorArtifacts = await readIndicatorArtifactRecords(input.stateRoot);
  const views = buildAutonomousViewPayloads({
    experiments,
    headEvents,
    archiveEvents,
    calibrationEvents,
    confidenceEvents,
    problemEvents,
    repairAttempts,
  });
  const persistedStage6Readiness = await readJson<Record<string, unknown>>(
    knowledgePaths.stage6ReadinessPath,
  ).catch(() => null);
  const stage6Readiness = (persistedStage6Readiness ??
    views.stage6Readiness) as Record<string, unknown>;
  const runtimeRoot = input.env.runtimeRoot ?? knowledgePaths.runtimeDir;
  const runtimeStatus = await reconcileAutonomousLoopRuntime({
    runtimeRoot,
    owner: "inspect-autonomous-state",
  });
  const calibrationBackpressure = buildCalibrationBackpressure({
    pendingCalibrationCandidateCount:
      views.autonomousStateSummary.pendingCalibrationCandidateCount ?? 0,
    parityStatusCounts: views.autonomousStateSummary.parityStatusCounts,
    repairTraceabilityStatus:
      stage6Readiness.repairTraceabilityStatus ??
      views.autonomousStateSummary.repairTraceabilityStatus,
  });
  const localEvaluations = selectLocalEvaluationRecords(experiments);
  const tvVerifications = selectTvVerificationRecords(experiments);
  const lastTvSurfaceFailure =
    [...tvVerifications]
      .filter(
        (record) =>
          record.decision === "tv_surface_failure" ||
          record.decision === "tv_executor_failure",
      )
      .sort((left, right) => {
        const leftRecordedAt = Date.parse(left.recordedAt ?? "");
        const rightRecordedAt = Date.parse(right.recordedAt ?? "");
        if (leftRecordedAt !== rightRecordedAt) {
          return rightRecordedAt - leftRecordedAt;
        }
        return right.iteration - left.iteration;
      })[0] ?? null;
  const nextPlannedAction = calibrationBackpressure.recommendedAction
    ? calibrationBackpressure.recommendedAction
    : !input.env.autoProcessCalibration &&
        views.autonomousStateSummary.nextPlannedAction === "process_tv_calibration_queue"
      ? "continue_local_first_research"
      : views.autonomousStateSummary.nextPlannedAction;
  const latestIndicatorArtifact =
    [...indicatorArtifacts].sort((left, right) => {
      const leftTime = Date.parse(left.createdAt ?? "");
      const rightTime = Date.parse(right.createdAt ?? "");
      return rightTime - leftTime;
    })[0] ?? null;
  const nextPlannedActionReason = calibrationBackpressure.active
    ? calibrationBackpressure.reasons.join(" | ")
    : input.env.researchModeConfig.mode === "criterion_focus"
      ? `criterion_focus:${input.env.researchModeConfig.criterion ?? "auto"}`
      : input.env.researchModeConfig.mode;

  return {
    ...views.autonomousStateSummary,
    researchMode: input.env.researchModeConfig,
    activeCriterion:
      input.env.researchModeConfig.mode === "criterion_focus"
        ? input.env.researchModeConfig.criterion ?? "auto"
        : null,
    latestIndicatorArtifact,
    calibrationBackpressure,
    stage6Readiness,
    runtimeStatus,
    lastStage6GatePassed:
      stage6Readiness.evaluated === true ? stage6Readiness.passed === true : null,
    rootIsolationStatus:
      stage6Readiness.rootIsolationStatus ??
      views.autonomousStateSummary.rootIsolationStatus,
    repairTraceabilityStatus:
      stage6Readiness.repairTraceabilityStatus ??
      views.autonomousStateSummary.repairTraceabilityStatus,
    feedbackClosureStatus:
      stage6Readiness.feedbackClosureStatus ??
      views.autonomousStateSummary.feedbackClosureStatus,
    projectRoot: input.env.projectRoot,
    workspaceRoot: input.env.workspaceRoot,
    stateRoot: input.env.stateRoot,
    traceRoot: input.env.traceRoot ?? knowledgePaths.tracesDir,
    artifactRoot: input.env.artifactRoot ?? knowledgePaths.artifactDir,
    evidenceRoot: input.env.evidenceRoot ?? knowledgePaths.evidenceDir,
    runtimeRoot,
    tvVerificationCount: tvVerifications.length,
    tvHealth: resolveTvHealthStatus(input.env),
    calibrationAutoProcess: input.env.autoProcessCalibration,
    calibrationMode: input.env.autoProcessCalibration ? "auto_process" : "queue_only",
    nextPlannedAction,
    nextPlannedActionReason,
    lastTvSurfaceFailure: lastTvSurfaceFailure
      ? {
          candidateId: lastTvSurfaceFailure.candidateId,
          decision: lastTvSurfaceFailure.decision,
          iteration: lastTvSurfaceFailure.iteration,
          tvCalibrationStatus: lastTvSurfaceFailure.tvCalibrationStatus,
          recordedAt: lastTvSurfaceFailure.recordedAt,
        }
      : null,
    selectedBy:
      headEvents
        .slice()
        .sort((left, right) => {
          const leftRecordedAt = Date.parse(left.recordedAt ?? "");
          const rightRecordedAt = Date.parse(right.recordedAt ?? "");
          if (leftRecordedAt !== rightRecordedAt) {
            return rightRecordedAt - leftRecordedAt;
          }
          return right.iteration - left.iteration;
        })[0]?.selectedBy ?? null,
    humanOverride: false,
    localEvaluationCount: localEvaluations.length,
  };
}

async function initializeWorkspaceForEnv(
  env: RuntimeEnvironment,
) {
  return initializeWorkspace({
    projectRoot: env.projectRoot,
    workspaceRoot: env.workspaceRoot,
    stateRoot: env.stateRoot,
    targetId: env.researchTargetId,
  });
}

function validateAutonomousResearchMode(env: RuntimeEnvironment): void {
  if (env.researchModeConfig.mode === "indicator_request") {
    throw new Error(
      "run-autonomous-loop does not support research mode indicator_request. Use generate-indicator.",
    );
  }
  if (
    env.researchModeConfig.criterion &&
    env.researchModeConfig.mode !== "criterion_focus"
  ) {
    throw new Error(
      "--criterion or AF_RESEARCH_CRITERION is only valid with research mode criterion_focus.",
    );
  }
}

function createPromotionVerificationExecutorFactory(
  env: ReturnType<typeof loadRuntimeEnvironment>,
): (() => ReturnType<typeof createPineEvaluationExecutor>) | undefined {
  if (!isTradingViewExecutorName(env.promotionVerificationExecutor)) {
    return undefined;
  }

  const executorName = env.promotionVerificationExecutor;
  return () => createPineEvaluationExecutor(env, executorName);
}

function isTradingViewExecutorName(
  value: RuntimeEnvironment["evaluationExecutor"] | RuntimeEnvironment["promotionVerificationExecutor"],
): value is Extract<
  EvaluationExecutorName,
  "tradingview-desktop-cdp" | "tradingview-web-playwright"
> {
  return (
    value === "tradingview-desktop-cdp" ||
    value === "tradingview-web-playwright"
  );
}

function resolveTradingViewExecutorName(
  env: ReturnType<typeof loadRuntimeEnvironment>,
): Extract<
  EvaluationExecutorName,
  "tradingview-desktop-cdp" | "tradingview-web-playwright"
> | null {
  if (isTradingViewExecutorName(env.promotionVerificationExecutor)) {
    return env.promotionVerificationExecutor;
  }
  if (isTradingViewExecutorName(env.evaluationExecutor)) {
    return env.evaluationExecutor;
  }
  return null;
}

function createLocalFallbackExecutorFactory(
  env: ReturnType<typeof loadRuntimeEnvironment>,
): () => ReturnType<typeof createPineEvaluationExecutor> {
  return () => createPineEvaluationExecutor(env, "local-backtest");
}

function createLazyMutationLlmClient(
  factory: () => Promise<MutationLlmClient>,
): MutationLlmClient {
  let clientPromise: Promise<MutationLlmClient> | null = null;
  const getClient = async () => {
    clientPromise ??= factory();
    return clientPromise;
  };

  return {
    async generateMutation(input) {
      return (await getClient()).generateMutation(input);
    },
    async generateIndicator(input) {
      const client = await getClient();
      if (!client.generateIndicator) {
        throw new Error("Configured LLM client does not support indicator generation.");
      }
      return client.generateIndicator(input);
    },
    async generateConditionAblation(input) {
      return (await getClient()).generateConditionAblation(input);
    },
    async repairMutation(input) {
      return (await getClient()).repairMutation(input);
    },
    async reviewStrategy(input) {
      const client = await getClient();
      if (!client.reviewStrategy) {
        throw new Error("Configured LLM client does not support strategy review.");
      }
      return client.reviewStrategy(input);
    },
  };
}

function resolveAuthoritativeExecutorName(
  env: ReturnType<typeof loadRuntimeEnvironment>,
): EvaluationExecutorName | null {
  return resolveTradingViewExecutorName(env);
}

function mapDecisionToExperimentStatus(decision: DecisionCode): string {
  switch (decision) {
    case "compile_fail":
      return "compile_failed";
    case "apply_fail":
      return "apply_failed";
    case "mutation_generation_fail":
      return "generation_failed";
    case "mutation_schema_fail":
      return "schema_failed";
    case "preflight_fail":
      return "preflight_failed";
    case "verification_fail":
      return "verification_failed";
    case "promoted_head":
      return "promoted_head";
    default:
      return "evaluated";
  }
}

program
  .command("login-alphaxiv")
  .description("Open alphaXiv sign-in in a browser, capture the session, and verify MCP access.")
  .option("--timeout-ms <value>", "Override login timeout in milliseconds.")
  .action(async (options: { timeoutMs?: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "login-alphaxiv",
      },
      async (monitor) => {
        const timeoutMs = options.timeoutMs
          ? parsePositiveInteger(options.timeoutMs, "timeoutMs")
          : undefined;

        await monitor.log("alphaxiv.login.start", "Opening alphaXiv sign-in", {
          timeoutMs: timeoutMs ?? 300000,
        });

        console.log(
          "alphaXiv sign-in will open in your browser. If it does not open automatically, paste the printed URL into a browser; AF will capture the callback automatically.",
        );

        let authorizationUrl: string | null = null;
        const result = await loginAlphaXivWithBrowser(env, {
          timeoutMs,
          authFilePath: env.alphaXivAuthFilePath,
          onAuthorizationUrl(url) {
            authorizationUrl = url;
            console.log(`alphaXiv login URL:\n${url}`);
          },
        });

        await monitor.log("alphaxiv.login.done", "alphaXiv login completed", {
          authFilePath: result.authFilePath,
          toolCount: result.toolNames.length,
          authorizationUrl,
        });

        console.log(
          JSON.stringify(
            {
              loggedIn: true,
              authFilePath: result.authFilePath,
              tools: result.toolNames,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("bootstrap")
  .description("Initialize workspace structure and optionally validate Pine evaluation access.")
  .option("--smoke", "Run a live Pine evaluation executor smoke check.")
  .action(async (options: { smoke?: boolean }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "bootstrap",
      },
      async (monitor) => {
        await monitor.log("bootstrap.start", "Initializing workspace", {
          workspaceRoot: env.workspaceRoot,
        });
        await initializeWorkspace(env.workspaceRoot);
        const openAiInspection = await ensureOpenAiAuthReady(env).catch((error) => ({
          authMode: env.openAiAuthMode,
          authConfigured: false,
          reachable: false,
          status: null,
          proxyStarted: false,
          proxyRestarted: false,
          authFilePath: null,
          error: error instanceof Error ? error.message : String(error),
        }));
        const alphaXivInspection = await ensureAlphaXivAuthReady(env).catch((error) => ({
          authConfigured: false,
          reachable: false,
          status: null,
          authMethod: "none" as const,
          authFilePath: null,
          sessionFilePath: null,
          error: error instanceof Error ? error.message : String(error),
        }));
        const report: Record<string, unknown> = {
          workspaceRoot: env.workspaceRoot,
          nodeVersion: process.version,
          objectiveConfig: await fileExists(
            path.join(env.workspaceRoot, "config", "objective.qqq-120m.json"),
          ),
          baseline: await fileExists(
            path.join(env.workspaceRoot, "strategies", "source", "baseline.pine"),
          ),
          runtimeTarget: await fileExists(
            path.join(env.workspaceRoot, "strategies", "source", "runtime_target.pine"),
          ),
          mockPolicy: "forbidden",
          evaluationExecutor: env.evaluationExecutor,
          promotionVerificationExecutor: env.promotionVerificationExecutor,
          executionSurface: env.evaluationExecutor,
          openAiAuthMode: env.openAiAuthMode,
          openAiConfigured: Boolean(env.openAiBaseUrl && env.openAiModel),
          openAiAuthConfigured: openAiInspection.authConfigured,
          openAiReachable: openAiInspection.reachable,
          openAiStatus: openAiInspection.status,
          openAiProxyStarted: "proxyStarted" in openAiInspection ? openAiInspection.proxyStarted : false,
          openAiProxyRestarted:
            "proxyRestarted" in openAiInspection ? openAiInspection.proxyRestarted : false,
          openAiAuthFilePath:
            "authFilePath" in openAiInspection ? openAiInspection.authFilePath : null,
          openAiError: "error" in openAiInspection ? openAiInspection.error : null,
          executionSurfaceConfigured: Boolean(
            env.evaluationExecutor === "local-backtest"
              ? true
              : env.tradingViewDesktopPath || env.tradingViewCdpUrl,
          ),
          researchRefreshEveryTasks: env.researchRefreshEveryTasks,
          alphaXivMcpConfigured: Boolean(env.alphaXivMcpUrl),
          alphaXivMcpUrl: env.alphaXivMcpUrl,
          alphaXivApiKeyRequired: false,
          alphaXivAuthType: "oauth2_bearer",
          alphaXivAuthConfigured: alphaXivInspection.authConfigured,
          alphaXivAuthMethod: alphaXivInspection.authMethod,
          alphaXivStatus: alphaXivInspection.status,
          alphaXivReachable: alphaXivInspection.reachable,
          alphaXivAuthFilePath: alphaXivInspection.authFilePath,
          alphaXivSessionFilePath: alphaXivInspection.sessionFilePath,
          alphaXivError: alphaXivInspection.error,
          tracePath: monitor.tracePath,
        };

        if (options.smoke) {
          const executor = createPineEvaluationExecutor(env);
          try {
            await monitor.log("bootstrap.smoke", "Running Pine evaluation smoke check", {
              symbol: env.chartSymbol,
              timeframe: env.chartTimeframe,
            });
            await executor.prepareChart({
              symbol: env.chartSymbol,
              timeframe: env.chartTimeframe,
              chartType: env.chartType,
            });
            report.smoke = "ok";
            await monitor.log("bootstrap.smoke", "Pine evaluation smoke check succeeded", {
              symbol: env.chartSymbol,
              timeframe: env.chartTimeframe,
              chartType: env.chartType,
            });
          } finally {
            await executor.close?.();
          }
        }

        await monitor.log("bootstrap.done", "Bootstrap command completed", report);
        console.log(JSON.stringify(report, null, 2));
      },
    );
  });

program
  .command("mutate")
  .description("Generate one Pine candidate and persist it under strategies/candidates.")
  .action(async () => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "mutate",
      },
      async (monitor) => {
        await monitor.log("mutate.start", "Preparing mutation request", {
          workspaceRoot: env.workspaceRoot,
        });
        await initializeWorkspace(env.workspaceRoot);
        const stateRoot = env.stateRoot;
        const objective = await loadObjectiveConfig(env.workspaceRoot);
        const previousRecords = await readExperimentRecords(stateRoot);
        const mutationContext = await prepareMutationContext({
          workspaceRoot: env.workspaceRoot,
          stateRoot: env.stateRoot,
          objective,
          previousRecords,
        });
        const {
          activeHeadRecord,
          acceptedHeadCandidateId,
          recentFailures,
          recentCompileFailureClasses,
          brief,
        } = mutationContext;
        await monitor.log("hypothesis.ready", "Mutation hypothesis prepared", {
          objective: brief.objective,
          recentFailures,
          acceptedHead: acceptedHeadCandidateId,
        });
        const baselinePine = await resolveMutationSourcePine(
          env.workspaceRoot,
          activeHeadRecord,
        );
        const llmClient = await createMutationLlmClient(env);
        await monitor.log("mutation.request", "Sending mutation request", {
          baselineLength: baselinePine.length,
        });
        let response: string;
        try {
          response = await llmClient.generateMutation({
            brief,
            baselinePine,
          });
        } catch (error) {
          const detail = error instanceof Error ? error.message : String(error);
          const artifactPath = await writeMutationRuntimeArtifact({
            workspaceRoot: env.workspaceRoot,
            stateRoot: env.stateRoot,
            iteration: previousRecords.length + 1,
            stage: "mutate-request-failed",
            payload: {
              detail,
              brief,
            },
          });
          await appendIncidentRecord(stateRoot, {
            runId: "mutate-cli",
            iteration: previousRecords.length + 1,
            candidateId: createCandidateId("mutate"),
            incidentType: "mutation_request_failed",
            detail: `${detail} | artifact=${artifactPath}`,
          });
          await monitor.log("mutation.generation_failed", "Mutation generation failure recorded", {
            incidentType: "mutation_request_failed",
            artifactPath,
          });
          throw error;
        }
        await monitor.log("mutation.response", "Received mutation response", {
          responseLength: response.length,
        });
        let parsed: ReturnType<typeof parseMutationResponseStrict>;
        try {
          parsed = parseMutationResponseStrict(response);
        } catch (error) {
          const detail = error instanceof Error ? error.message : String(error);
          const artifactPath = await writeMutationRuntimeArtifact({
            workspaceRoot: env.workspaceRoot,
            stateRoot: env.stateRoot,
            iteration: previousRecords.length + 1,
            stage: "mutate-parse-failed",
            payload: {
              detail,
              response,
              brief,
            },
          });
          await appendIncidentRecord(stateRoot, {
            runId: "mutate-cli",
            iteration: previousRecords.length + 1,
            candidateId: createCandidateId("mutate"),
            incidentType: "mutation_parse_failed",
            detail: `${detail} | artifact=${artifactPath}`,
          });
          await monitor.log("mutation.generation_failed", "Mutation generation failure recorded", {
            incidentType: "mutation_parse_failed",
            artifactPath,
          });
          throw error;
        }
        let preflight = inspectGeneratedMutation(parsed, {
          breakoutVariantDirective: brief.breakoutVariantDirective,
          recentCompileErrors: mutationContext.recentCompileErrors,
          recentCompileFailureClasses,
        });
        await monitor.log("mutation.preflight", "Mutation preflight completed", {
          issueCount: preflight.issues.length,
          blockingIssueCount: preflight.blockingIssues.length,
          warningIssueCount: preflight.warningIssues.length,
          issueCodes: preflight.issues.map((issue) => issue.code),
        });
        if (preflight.blockingIssues.length > 0) {
          const preflightArtifactPath = await writeMutationRuntimeArtifact({
            workspaceRoot: env.workspaceRoot,
            stateRoot: env.stateRoot,
            iteration: previousRecords.length + 1,
            stage: "mutate-preflight-blocked",
            payload: {
              issues: preflight.blockingIssues,
              candidateSummary: parsed.candidateSummary,
              pineScript: parsed.pineScript,
            },
          });
          await appendIncidentRecord(stateRoot, {
            runId: "mutate-cli",
            iteration: previousRecords.length + 1,
            candidateId: createCandidateId("mutate"),
            incidentType: "mutation_preflight_blocked",
            detail: `Blocking Pine generation issues detected | artifact=${preflightArtifactPath}`,
          });
          await monitor.log("mutation.preflight_blocked", "Blocking mutation preflight issues detected", {
            issueCodes: preflight.blockingIssues.map((issue) => issue.code),
            artifactPath: preflightArtifactPath,
          });
          const repairedResponse = await llmClient.repairMutation({
            brief,
            candidatePine: parsed.pineScript,
            compileErrors: formatPreflightIssuesForRepair(preflight.blockingIssues),
            candidateSummary: parsed.candidateSummary,
            inventory: parsed.inventory,
          });
          await monitor.log("mutation.preflight_repair", "Attempting preflight repair", {
            blockingIssueCount: preflight.blockingIssues.length,
            responseLength: repairedResponse.length,
          });
          parsed = parseMutationResponseStrict(repairedResponse);
          preflight = inspectGeneratedMutation(parsed, {
            breakoutVariantDirective: brief.breakoutVariantDirective,
            recentCompileErrors: mutationContext.recentCompileErrors,
            recentCompileFailureClasses,
          });
          await monitor.log("mutation.preflight", "Mutation preflight completed", {
            issueCount: preflight.issues.length,
            blockingIssueCount: preflight.blockingIssues.length,
            warningIssueCount: preflight.warningIssues.length,
            issueCodes: preflight.issues.map((issue) => issue.code),
            repaired: true,
          });
          if (preflight.blockingIssues.length > 0) {
            const artifactPath = await writeMutationRuntimeArtifact({
              workspaceRoot: env.workspaceRoot,
              stateRoot: env.stateRoot,
              iteration: previousRecords.length + 1,
              stage: "mutate-preflight-failed",
              payload: {
                issues: preflight.blockingIssues,
                candidateSummary: parsed.candidateSummary,
                pineScript: parsed.pineScript,
              },
            });
            await appendIncidentRecord(stateRoot, {
              runId: "mutate-cli",
              iteration: previousRecords.length + 1,
              candidateId: createCandidateId("mutate"),
              incidentType: "mutation_preflight_failed",
              detail: `Blocking Pine generation issues remained after repair | artifact=${artifactPath}`,
            });
            await monitor.log("mutation.generation_failed", "Mutation generation failure recorded", {
              incidentType: "mutation_preflight_failed",
              artifactPath,
            });
            throw new Error("Blocking Pine generation issues remained after preflight repair.");
          }
        }
        await monitor.log("mutation.parsed", "Parsed mutation payload", {
          candidateSummary: parsed.candidateSummary,
          conditionCount: parsed.inventory.length,
        });
        const artifact = await persistCandidateArtifact({
          workspaceRoot: env.workspaceRoot,
          parsedMutation: parsed,
          parentCandidateId: acceptedHeadCandidateId,
          branchId: "main",
        });
        await monitor.log("mutate.done", "Candidate artifact persisted", {
          candidateId: artifact.candidateId,
          candidatePath: artifact.pinePath,
        });

        console.log(
          JSON.stringify(
            {
              ...artifact,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("generate-indicator")
  .description("Generate a user-requested TradingView Pine indicator artifact without entering the strategy promotion pipeline.")
  .requiredOption("--indicator-goal <text>", "User goal for the indicator, for example short-term top detection.")
  .option("--output <path>", "Optional output path under strategies/indicators.")
  .option(
    "--research-mode <mode>",
    "Research mode. This command accepts indicator_request only when provided.",
  )
  .action(async (options: {
    indicatorGoal: string;
    output?: string;
    researchMode?: string;
  }) => {
    const env = loadRuntimeEnvironment();
    if (options.researchMode && options.researchMode !== "indicator_request") {
      throw new Error("generate-indicator requires research mode indicator_request.");
    }
    if (
      env.researchModeConfig.mode !== "continuous_improvement" &&
      env.researchModeConfig.mode !== "indicator_request"
    ) {
      throw new Error(
        `generate-indicator cannot run while AF_RESEARCH_MODE=${env.researchModeConfig.mode}.`,
      );
    }
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "generate-indicator",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const [experiments, mutationBriefs] = await Promise.all([
          readExperimentRecords(env.stateRoot),
          readMutationBriefRecords(env.stateRoot),
        ]);
        const latestExperiment = [...experiments].sort(
          (left, right) => right.iteration - left.iteration,
        )[0] ?? null;
        const latestBrief = mutationBriefs.at(-1) ?? null;
        const llmClient = createLazyMutationLlmClient(() =>
          createMutationLlmClient(env),
        );
        const result = await generateIndicatorArtifact({
          workspaceRoot: env.workspaceRoot,
          stateRoot: env.stateRoot,
          llmClient,
          goal: options.indicatorGoal,
          outputPath: options.output,
          sourceContext: {
            researchMode: {
              mode: "indicator_request",
              indicatorRequest: options.indicatorGoal,
              source: options.researchMode ? "cli" : env.researchModeConfig.source,
            },
            latestExperiment: latestExperiment
              ? {
                  candidateId: latestExperiment.candidateId,
                  decision: latestExperiment.decision,
                  score:
                    latestExperiment.autoSelectionScore ??
                    latestExperiment.candidateScore ??
                    null,
                  metrics:
                    latestExperiment.testerMetrics ??
                    latestExperiment.artifactSummary?.strategy ??
                    null,
                }
              : null,
            latestMutationBrief: latestBrief
              ? {
                  repairMode: latestBrief.brief.repairMode,
                  nextMutationDirection: latestBrief.brief.nextMutationDirection,
                  activeCriterion: latestBrief.brief.criterionDirective?.criterion ?? null,
                }
              : null,
          },
        });
        await monitor.log("indicator.generated", "Indicator artifact generated", {
          indicatorId: result.record.indicatorId,
          pinePath: result.record.pinePath,
          goal: result.record.goal,
        });
        console.log(
          JSON.stringify(
            {
              ...result.record,
              indicatorSummary: result.indicatorSummary,
              nextSteps: result.nextSteps,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("run-autonomous-loop")
  .description("Run one or more v3 autonomous local-first iterations; TradingView calibration stays queued unless explicitly enabled.")
  .option("--count <number>", "Iteration count", "1")
  .option("--target <id|all>", "Research target id, or all to run target configs sequentially.")
  .option(
    "--research-mode <mode>",
    "Research mode: continuous_improvement or criterion_focus. indicator_request uses generate-indicator.",
  )
  .option("--criterion <criterion>", "Criterion key used by criterion_focus mode.")
  .option(
    "--auto-process-calibration <boolean>",
    "Opt in to processing the optional TradingView calibration queue after each iteration.",
  )
  .option(
    "--calibration-budget <number>",
    "Maximum queued calibration candidates to process per iteration.",
  )
  .action(async (options: {
    count: string;
    target?: string;
    researchMode?: string;
    criterion?: string;
    autoProcessCalibration?: string;
    calibrationBudget?: string;
  }) => {
    const baseEnv = loadRuntimeEnvironment();
    const targetIds = resolveTargetIds(baseEnv, options.target);
    if (options.criterion && baseEnv.researchModeConfig.mode !== "criterion_focus") {
      throw new Error("--criterion is only valid when --research-mode criterion_focus is active.");
    }
    await withCliMonitor(
      {
        workspaceRoot: baseEnv.workspaceRoot,
        commandName: "run-autonomous-loop",
      },
      async (monitor) => {
        const count = parsePositiveInteger(options.count, "count");
        const targetRuns = [];
        for (const targetId of targetIds) {
          const env =
            targetId === baseEnv.researchTargetId
              ? baseEnv
              : loadRuntimeEnvironmentForTarget(targetId);
          validateAutonomousResearchMode(env);
          const autoProcessCalibration =
            options.autoProcessCalibration == null
              ? env.autoProcessCalibration
              : parseBoolean(
                  options.autoProcessCalibration,
                  "auto-process-calibration",
                );
          const calibrationBudget =
            options.calibrationBudget == null
              ? env.calibrationBudget
              : parsePositiveInteger(
                  options.calibrationBudget,
                  "calibration-budget",
                );
          const llmClient = createLazyMutationLlmClient(() =>
            createMutationLlmClient(env),
          );
          const loopEnv = {
            ...env,
            autoProcessCalibration,
            calibrationBudget,
          };
          const calibrationExecutorName =
            resolveTradingViewExecutorName(loopEnv) ?? "tradingview-desktop-cdp";
          await monitor.log("autonomous.loop.start", "Starting autonomous local-first loop", {
            count,
            targetId,
            workspaceRoot: env.workspaceRoot,
            stateRoot: env.stateRoot,
            projectRoot: env.projectRoot,
            tvHealth: resolveTvHealthStatus(env),
            autoProcessCalibration,
            calibrationBudget,
            researchMode: loopEnv.researchModeConfig,
          });
          const iterationRun = await runAutonomousIterations({
            workspaceRoot: env.workspaceRoot,
            env: loopEnv,
            llmClient,
            localExecutorFactory: () =>
              createPineEvaluationExecutor(env, "local-backtest"),
            calibrationExecutorFactory: autoProcessCalibration
              ? () => createPineEvaluationExecutor(loopEnv, calibrationExecutorName)
              : undefined,
            count,
            monitor,
          });
          const autonomousState = await buildAutonomousStateSummary({
            stateRoot: env.stateRoot,
            env: loopEnv,
          });
          targetRuns.push({
            targetId,
            ...iterationRun,
            autonomousState,
          });
        }
        monitor.clearTask();
        const memoryTelemetry = await writeNodeRuntimeTelemetry({
          stateRoot: baseEnv.stateRoot,
          commandName: "run-autonomous-loop",
          phase: "completed",
          extra: {
            count,
            targetCount: targetRuns.length,
            countCompleted: targetRuns.reduce(
              (total, run) => total + run.countCompleted,
              0,
            ),
            countFailed: targetRuns.reduce((total, run) => total + run.countFailed, 0),
          },
        });

        console.log(
          JSON.stringify(
            targetRuns.length === 1
              ? {
                  ...targetRuns[0],
                  memoryTelemetry,
                  tracePath: monitor.tracePath,
                }
              : {
                  targetRuns,
                  memoryTelemetry,
                  tracePath: monitor.tracePath,
                },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("review-strategies")
  .description("Run deterministic triage and selective deep strategy reviews for autonomous candidates.")
  .option("--target <id|all>", "Research target id, or all target configs.", "all")
  .option("--deep-budget <number>", "Maximum deep LLM reviews per target.")
  .action(async (options: { target: string; deepBudget?: string }) => {
    const baseEnv = loadRuntimeEnvironment();
    const targetIds = resolveTargetIds(baseEnv, options.target);
    await withCliMonitor(
      {
        workspaceRoot: baseEnv.workspaceRoot,
        commandName: "review-strategies",
      },
      async (monitor) => {
        const results = [];
        for (const targetId of targetIds) {
          const env =
            targetId === baseEnv.researchTargetId
              ? baseEnv
              : loadRuntimeEnvironmentForTarget(targetId);
          const objective = await loadObjectiveConfig(env.workspaceRoot, targetId);
          const deepBudget =
            options.deepBudget == null
              ? env.strategyReviewDeepBudget
              : parseNonNegativeInteger(options.deepBudget, "deep-budget");
          const llmClient =
            deepBudget > 0 && env.strategyReviewMode !== "off"
              ? createLazyMutationLlmClient(() => createMutationLlmClient(env))
              : undefined;
          const reviews = await runStrategyReviewBatchForTarget({
            stateRoot: env.stateRoot,
            targetId,
            objective,
            llmClient,
            mode: env.strategyReviewMode,
            deepBudget,
            monitor,
          });
          results.push({
            targetId,
            reviewCount: reviews.length,
            deepReviewCount: reviews.filter((review) => review.reviewMode === "deep_llm")
              .length,
            latestDecision: reviews[0]?.reviewDecision ?? null,
          });
        }
        await rebuildIndexes(baseEnv.stateRoot, { mode: "incremental" });
        monitor.clearTask();
        console.log(
          JSON.stringify(
            {
              results,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("inspect-strategy-reviews")
  .description("Inspect strategy review ledger entries for a target and optional candidate.")
  .requiredOption("--target <id>", "Research target id.")
  .option("--candidate <candidateId>", "Candidate id filter.")
  .action(async (options: { target: string; candidate?: string }) => {
    const env = loadRuntimeEnvironmentForTarget(options.target);
    const reviews = (await readStrategyReviewRecords(env.stateRoot))
      .filter((review) => review.targetId === options.target)
      .filter((review) =>
        options.candidate ? review.candidateId === options.candidate : true,
      )
      .sort(
        (left, right) =>
          Date.parse(right.recordedAt) - Date.parse(left.recordedAt) ||
          right.iteration - left.iteration,
      );
    console.log(
      JSON.stringify(
        {
          targetId: options.target,
          candidateId: options.candidate ?? null,
          count: reviews.length,
          reviews: reviews.slice(0, 50),
        },
        null,
        2,
      ),
    );
  });

program
  .command("verify-stage6-readiness")
  .description("Run the Stage 6 autonomous readiness gate in an isolated fresh/custom root.")
  .option("--count <number>", "Iteration count", "5")
  .option(
    "--mode <mode>",
    "Readiness mode: deterministic or real-llm.",
    "deterministic",
  )
  .option(
    "--auto-process-calibration <boolean>",
    "Process calibration feedback during the gate. Defaults to false for local-core readiness.",
    "false",
  )
  .option(
    "--keep-temp-root <boolean>",
    "Keep the temporary workspace and state root for inspection.",
    "false",
  )
  .action(async (options: {
    count: string;
    mode: string;
    autoProcessCalibration: string;
    keepTempRoot: string;
  }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "verify-stage6-readiness",
      },
      async (monitor) => {
        const count = parsePositiveInteger(options.count, "count");
        const mode = parseStage6ReadinessMode(options.mode);
        const autoProcessCalibration = parseBoolean(
          options.autoProcessCalibration,
          "auto-process-calibration",
        );
        const keepTempRoot = parseBoolean(options.keepTempRoot, "keep-temp-root");
        const result = await runStage6ReadinessGate({
          env,
          count,
          mode,
          autoProcessCalibration,
          keepTempRoot,
          llmClientFactory: (gateEnv) => createMutationLlmClient(gateEnv),
          localExecutorFactory: (gateEnv) =>
            createPineEvaluationExecutor(gateEnv, "local-backtest"),
          calibrationExecutorFactory: (gateEnv) =>
            createPineEvaluationExecutor(gateEnv, "tradingview-desktop-cdp"),
          monitor,
        });
        monitor.clearTask();
        console.log(
          JSON.stringify(
            {
              ...result,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
        if (!result.passed) {
          process.exitCode = 1;
        }
      },
    );
  });

program
  .command("verify-calibration-readiness")
  .description("Run an explicit calibration feedback readiness gate outside the default local-core Stage 6 gate.")
  .option("--count <number>", "Iteration count", "5")
  .option(
    "--mode <mode>",
    "Calibration mode: mock-recovered or live.",
    "mock-recovered",
  )
  .option(
    "--llm-mode <mode>",
    "LLM mode: deterministic or real-llm.",
    "deterministic",
  )
  .option(
    "--keep-temp-root <boolean>",
    "Keep the temporary workspace and state root for inspection.",
    "false",
  )
  .action(async (options: {
    count: string;
    mode: string;
    llmMode: string;
    keepTempRoot: string;
  }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "verify-calibration-readiness",
      },
      async (monitor) => {
        const count = parsePositiveInteger(options.count, "count");
        const calibrationMode = parseStage6CalibrationMode(options.mode);
        const mode = parseStage6ReadinessMode(options.llmMode);
        const keepTempRoot = parseBoolean(options.keepTempRoot, "keep-temp-root");
        const result = await runStage6ReadinessGate({
          env,
          count,
          mode,
          calibrationMode,
          autoProcessCalibration: true,
          keepTempRoot,
          persistToState: false,
          llmClientFactory: (gateEnv) => createMutationLlmClient(gateEnv),
          localExecutorFactory: (gateEnv) =>
            createPineEvaluationExecutor(gateEnv, "local-backtest"),
          calibrationExecutorFactory: (gateEnv) =>
            createPineEvaluationExecutor(gateEnv, "tradingview-desktop-cdp"),
          monitor,
        });
        const calibrationReadinessPath = path.join(
          resolveKnowledgePaths(env.stateRoot).viewsDir,
          "autonomous",
          "calibration-readiness.json",
        );
        await writeJson(calibrationReadinessPath, result);
        monitor.clearTask();
        console.log(
          JSON.stringify(
            {
              ...result,
              calibrationReadinessPath,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
        if (!result.passed) {
          process.exitCode = 1;
        }
      },
    );
  });

program
  .command("evaluate-local")
  .description("Evaluate a candidate through the v3 local-first autonomous path.")
  .requiredOption("--candidate <id>", "Candidate id or explicit .pine path")
  .action(async (options: { candidate: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "evaluate-local",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const stateRoot = env.stateRoot;
        const objective = await loadObjectiveConfig(env.workspaceRoot);
        const experiments = await readExperimentRecords(stateRoot);
        const candidates = await readCandidateLedgerRecords(stateRoot);
        const candidatePath = resolveCandidatePath(env.workspaceRoot, options.candidate);
        const pineScript = await readFile(candidatePath, "utf8");
        const candidateId = path.basename(candidatePath, ".pine");
        const latestCandidate = [...candidates]
          .reverse()
          .find((record) =>
            matchesCandidateReference(
              options.candidate,
              record.candidateId,
              record.candidatePath,
            ),
          );
        const latestExperiment = findLatestExperimentForCandidate(
          experiments,
          options.candidate,
        );
        const inventory = inferConditionInventoryFromPine(pineScript);
        const candidateSummary =
          latestCandidate?.candidateSummary ??
          latestExperiment?.mutationBriefSummary ??
          `Autonomous local evaluation replay for ${candidateId}.`;
        const nextMutationHints = latestCandidate?.nextMutationHints ?? [];
        const runId = `local-eval-${Date.now()}`;
        const iteration = experiments.length + 1;

        await appendRunRecord(stateRoot, {
          runId,
          startedAt: new Date().toISOString(),
          executor: "local-backtest",
          symbol: env.chartSymbol,
          timeframe: env.chartTimeframe,
          chartType: env.chartType,
          model: env.openAiModel,
        });

        const executor = createPineEvaluationExecutor(env, "local-backtest");
        try {
          const result = await runLocalEvaluationPhase({
            workspaceRoot: env.workspaceRoot,
            stateRoot,
            runId,
            iteration,
            executor,
            objective,
            parsedMutation: {
              candidateSummary,
              nextMutationHints,
              pineScript,
              inventory,
              inventorySource: "inferred",
              missingFields: [],
              inferredFields: ["inventory"],
            },
            candidateArtifact: {
              candidateId,
              parentId:
                latestCandidate?.parentCandidateId ??
                latestExperiment?.parentCandidateId ??
                null,
              branchId:
                latestCandidate?.branchId ??
                latestExperiment?.branchId ??
                "autonomous-main",
              pinePath: candidatePath,
              pineHash: sha256(pineScript),
              studyTitle:
                latestCandidate?.studyTitle ??
                latestExperiment?.studyTitle ??
                extractStudyTitle(pineScript),
              inventory,
              candidateSummary,
              nextMutationHints,
            },
            mutationProvenance:
              buildAutonomousReplayMutationProvenance(latestExperiment),
            previousExperiments: experiments,
            monitor,
          });
          await rebuildIndexes(stateRoot);

          console.log(
            JSON.stringify(
              {
                candidateId: result.record.candidateId,
                decision: result.record.decision,
                autoSelectionScore: result.record.autoSelectionScore,
                autoSelectionEligible:
                  result.record.autoSelectionBreakdown?.eligible ?? false,
                duplicateStatus: result.record.duplicateStatus,
                splitEvaluation: result.record.splitEvaluation,
                shouldArchive: result.shouldArchive,
                shouldQueueCalibration: result.shouldQueueCalibration,
                tracePath: monitor.tracePath,
              },
              null,
              2,
            ),
          );
        } finally {
          await executor.close?.();
        }
      },
    );
  });

program
  .command("auto-select-head")
  .description("Apply the v3 automatic champion selection policy over local evaluation records.")
  .action(async () => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "auto-select-head",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const stateRoot = env.stateRoot;
        const experiments = await readExperimentRecords(stateRoot);
        const headEvents = await readHeadEventRecords(stateRoot);
        const result = await runAutoSelectionPhase({
          stateRoot,
          runId: `auto-select-${Date.now()}`,
          iteration: experiments.length + 1,
          experiments,
          headEvents,
        });
        await rebuildIndexes(stateRoot);

        console.log(
          JSON.stringify(
            {
              ...result,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("inspect-autonomous-state")
  .description("Inspect the current v3 autonomous local-first operating state.")
  .action(async () => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "inspect-autonomous-state",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const stateRoot = env.stateRoot;
        const summary = await buildAutonomousStateSummary({
          stateRoot,
          env,
        });
        await monitor.log("autonomous.state.inspect", "Autonomous state inspected", summary);
        console.log(
          JSON.stringify(
            {
              ...summary,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("dashboard")
  .description("Serve a local-only autonomous loop dashboard over HTTP.")
  .option("--port <number>", "Preferred local dashboard port", "4177")
  .option("--host <host>", "Bind host. Defaults to 127.0.0.1 for local-only use.", "127.0.0.1")
  .option("--open <boolean>", "Open the dashboard in the default browser.", "false")
  .action(async (options: { port: string; host: string; open: string }) => {
    const env = loadRuntimeEnvironment();
    const port = parsePositiveInteger(options.port, "port");
    const open = parseBoolean(options.open, "open");
    const server = await startDashboardServer({
      workspaceRoot: env.workspaceRoot,
      stateRoot: env.stateRoot,
      autoProcessCalibration: env.autoProcessCalibration,
      promotionVerificationExecutor: env.promotionVerificationExecutor,
      researchModeConfig: env.researchModeConfig,
      host: options.host,
      port,
      open,
    });

    console.log(
      JSON.stringify(
        {
          url: server.url,
          host: server.host,
          port: server.port,
          localOnly: server.host === "127.0.0.1" || server.host === "::1",
          workspaceRoot: env.workspaceRoot,
          stateRoot: env.stateRoot,
        },
        null,
        2,
      ),
    );

    const shutdown = () => {
      server.server.close();
    };
    process.once("SIGINT", shutdown);
    process.once("SIGTERM", shutdown);
    await new Promise<void>((resolve) => {
      server.server.once("close", resolve);
    });
  });

program
  .command("inspect-failure-memory")
  .description("Inspect autonomous problem events and repair attempts.")
  .action(async () => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "inspect-failure-memory",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const problemEvents = await readProblemEventRecords(env.stateRoot);
        const repairAttempts = await readRepairAttemptRecords(env.stateRoot);
        const repairByProblemEventId = new Map(
          repairAttempts.map((attempt) => [attempt.problemEventId, attempt] as const),
        );
        console.log(
          JSON.stringify(
            {
              stateRoot: env.stateRoot,
              problemEventCount: problemEvents.length,
              repairAttemptCount: repairAttempts.length,
              recentProblemEvents: problemEvents.slice(-20).map((event) => ({
                ...event,
                repairAttempt:
                  repairByProblemEventId.get(event.problemEventId) == null
                    ? null
                    : repairByProblemEventId.get(event.problemEventId),
              })),
              recentRepairAttempts: repairAttempts.slice(-20),
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("inspect-calibration-queue")
  .description("Inspect the queued TradingView calibration candidates.")
  .action(async () => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "inspect-calibration-queue",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const experiments = await readExperimentRecords(env.stateRoot);
        const calibrationEvents = await readCalibrationEventRecords(env.stateRoot);
        const confidenceEvents = await readLocalConfidenceEventRecords(env.stateRoot);
        const archiveEvents = await readArchiveEventRecords(env.stateRoot);
        const headEvents = await readHeadEventRecords(env.stateRoot);
        const problemEvents = await readProblemEventRecords(env.stateRoot);
        const repairAttempts = await readRepairAttemptRecords(env.stateRoot);
        const views = buildAutonomousViewPayloads({
          experiments,
          headEvents,
          archiveEvents,
          calibrationEvents,
          confidenceEvents,
          problemEvents,
          repairAttempts,
        });
        const pendingQueueEntries = views.tvCalibrationQueue.entries.filter(
          (entry) => entry.derivedStatus === "pending" || entry.derivedStatus === "deferred",
        );
        console.log(
          JSON.stringify(
            {
              stateRoot: env.stateRoot,
              tvHealth: resolveTvHealthStatus(env),
              pendingCalibrationCandidateIds: pendingQueueEntries.map(
                (entry) => entry.candidateId,
              ),
              pendingCalibrationCandidateCount: pendingQueueEntries.length,
              calibrationEvents: calibrationEvents.slice(-50),
              queueEntries: views.tvCalibrationQueue.entries,
              localConfidenceSummary: views.localConfidenceSummary,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("inspect-local-compatibility")
  .description("Inspect local compatibility failure patterns and success rate.")
  .action(async () => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "inspect-local-compatibility",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const experiments = await readExperimentRecords(env.stateRoot);
        const archiveEvents = await readArchiveEventRecords(env.stateRoot);
        const headEvents = await readHeadEventRecords(env.stateRoot);
        const problemEvents = await readProblemEventRecords(env.stateRoot);
        const calibrationEvents = await readCalibrationEventRecords(env.stateRoot);
        const confidenceEvents = await readLocalConfidenceEventRecords(env.stateRoot);
        const repairAttempts = await readRepairAttemptRecords(env.stateRoot);
        const views = buildAutonomousViewPayloads({
          experiments,
          headEvents,
          archiveEvents,
          calibrationEvents,
          confidenceEvents,
          problemEvents,
          repairAttempts,
        });
        console.log(
          JSON.stringify(
            {
              stateRoot: env.stateRoot,
              ...views.localCompatibilitySummary,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("process-tv-calibration-queue")
  .description("Manually process the optional v3 TradingView calibration queue for diagnostic or recovery use.")
  .option("--max-candidates <number>", "Maximum queued candidates to process")
  .action(async (options: { maxCandidates?: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "process-tv-calibration-queue",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const stateRoot = env.stateRoot;
        const experiments = await readExperimentRecords(stateRoot);
        const calibrationEvents = await readCalibrationEventRecords(stateRoot);
        const pendingCalibrationCandidateIds = selectPendingCalibrationCandidates({
          events: calibrationEvents,
          experiments,
        });
        const tvHealth = resolveTvHealthStatus(env);
        if (tvHealth === "unavailable") {
          console.log(
            JSON.stringify(
              {
                processedCandidateIds: [],
                pendingCalibrationCandidateIds,
                pendingCalibrationCandidateCount: pendingCalibrationCandidateIds.length,
                tvHealth,
                skipped: true,
                tracePath: monitor.tracePath,
              },
              null,
              2,
            ),
          );
          return;
        }

        const objective = await loadObjectiveConfig(env.workspaceRoot);
        const runId = `tv-calibration-${Date.now()}`;
        const confidenceEvents = await readLocalConfidenceEventRecords(stateRoot);
        const calibrationExecutorName =
          resolveTradingViewExecutorName(env) ?? "tradingview-desktop-cdp";

        await appendRunRecord(stateRoot, {
          runId,
          startedAt: new Date().toISOString(),
          executor: calibrationExecutorName,
          symbol: env.chartSymbol,
          timeframe: env.chartTimeframe,
          chartType: env.chartType,
          model: env.openAiModel,
        });

        const result = await processTvCalibrationQueue({
          workspaceRoot: env.workspaceRoot,
          stateRoot,
          runId,
          objective,
          env,
          experiments,
          calibrationEvents,
          confidenceEvents,
          executorFactory: () =>
            createPineEvaluationExecutor(env, calibrationExecutorName),
          maxCandidates: options.maxCandidates
            ? parsePositiveInteger(options.maxCandidates, "maxCandidates")
            : undefined,
          monitor,
        });
        await rebuildIndexes(stateRoot);
        const autonomousState = await buildAutonomousStateSummary({
          stateRoot,
          env,
        });

        console.log(
          JSON.stringify(
            {
              ...result,
              pendingCalibrationCandidateCount: pendingCalibrationCandidateIds.length,
              autonomousState,
              tvHealth,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("evaluate")
  .description("[legacy] Evaluate an existing candidate file through the configured Pine evaluation executor.")
  .requiredOption("--candidate <id>", "Candidate id or explicit .pine path")
  .action(async (options: { candidate: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "evaluate",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const objective = await loadObjectiveConfig(env.workspaceRoot);
        const previousRecords = await readExperimentRecords(env.stateRoot);
        const acceptedHeadScore = findBestAcceptedRecord(previousRecords)?.candidateScore ?? null;
        const executor = createPineEvaluationExecutor(env);
        try {
          const result = await evaluateCandidateFile({
            workspaceRoot: env.workspaceRoot,
            candidate: options.candidate,
            executor,
            objective,
            acceptedHeadScore,
            chartSymbol: env.chartSymbol,
            chartTimeframe: env.chartTimeframe,
            chartType: env.chartType,
            maxTrades: env.maxTrades,
            monitor,
          });
          console.log(
            JSON.stringify(
              {
                decision: result.decision,
                compile: result.compile,
                apply: result.apply,
                syncArtifact: result.syncArtifact,
                artifactBundle: result.artifactBundle,
                testerMetrics: result.testerMetrics,
                artifactValidation: result.artifactValidation,
                objectiveBreakdown: result.objectiveBreakdown,
                objectiveArtifact:
                  result.objectiveBreakdown && result.testerMetrics
                    ? buildObjectiveArtifact({
                        candidateId: result.candidateId,
                        decision: result.decision,
                        objectiveBreakdown: result.objectiveBreakdown,
                        strategyMetrics: result.testerMetrics,
                        attachDiagnostics:
                          result.artifactBundle?.attachDiagnostics,
                        artifactValidation:
                          result.artifactValidation ?? undefined,
                      })
                    : null,
                executorCapability: result.executorCapability,
                studyTitle: result.studyTitle,
                tracePath: monitor.tracePath,
              },
              null,
              2,
            ),
          );
        } finally {
          await executor.close?.();
        }
      },
    );
  });

program
  .command("verify")
  .description("[legacy] Re-evaluate a candidate with the authoritative executor and append a verification record.")
  .requiredOption("--candidate <id>", "Candidate id or explicit .pine path")
  .option(
    "--fallback-local-on-runtime-failure",
    "Collect local fallback evidence after TradingView runtime failure",
  )
  .option(
    "--no-fallback-local",
    "Disable local fallback evidence after TradingView runtime failure",
  )
  .option(
    "--surface-recovery-attempts <number>",
    "TradingView surface recovery attempts (0 or 1)",
    "1",
  )
  .action(
    async (options: {
      candidate: string;
      fallbackLocalOnRuntimeFailure?: boolean;
      noFallbackLocal?: boolean;
      surfaceRecoveryAttempts: string;
    }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "verify",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const authoritativeExecutorName = resolveAuthoritativeExecutorName(env);
        if (!authoritativeExecutorName) {
          throw new Error(
            "No authoritative executor is configured. Set AF_PROMOTION_VERIFICATION_EXECUTOR=tradingview-web-playwright or tradingview-desktop-cdp, or use TradingView as the primary executor.",
          );
        }

        const stateRoot = env.stateRoot;
        const objective = await loadObjectiveConfig(env.workspaceRoot);
        const previousRecords = await readExperimentRecords(stateRoot);
        const acceptedRecord = findBestAcceptedRecord(previousRecords);
        const latestCandidateRecord = findLatestExperimentForCandidate(
          previousRecords,
          options.candidate,
        );
        const fallbackCandidateRecord = findLatestFallbackExperimentForCandidate(
          previousRecords,
          options.candidate,
        );
        const seedStrategy = await loadSeedStrategyReference(env.workspaceRoot);
        const iteration = previousRecords.length + 1;
        const runId = `run-${Date.now()}`;
        const fallbackLocalOnRuntimeFailure = options.noFallbackLocal ? false : true;
        const surfaceRecoveryAttempts = parseSurfaceRecoveryAttempts(
          options.surfaceRecoveryAttempts,
        );
        const chartTarget = {
          symbol: env.chartSymbol,
          timeframe: env.chartTimeframe,
          chartType: env.chartType,
        };
        const candidatePath = resolveCandidatePath(env.workspaceRoot, options.candidate);
        const pineScript = await readFile(candidatePath, "utf8");
        const studyTitle = extractStudyTitle(pineScript);
        const candidateId = path.basename(candidatePath, ".pine");
        let executor = createPineEvaluationExecutor(env, authoritativeExecutorName);
        const authoritativeExecutorCapability = executor.getCapability();

        await appendRunRecord(stateRoot, {
          runId,
          startedAt: new Date().toISOString(),
          executor: authoritativeExecutorName,
          symbol: env.chartSymbol,
          timeframe: env.chartTimeframe,
          chartType: env.chartType,
          model: env.openAiModel,
        });

        try {
          const evaluateCurrentExecutor = () =>
            evaluateCandidateFile({
              workspaceRoot: env.workspaceRoot,
              candidate: options.candidate,
              executor,
              objective,
              acceptedHeadScore: acceptedRecord?.candidateScore ?? null,
              chartSymbol: env.chartSymbol,
              chartTimeframe: env.chartTimeframe,
              chartType: env.chartType,
              maxTrades: env.maxTrades,
              monitor,
            });

          let result: Awaited<ReturnType<typeof evaluateCandidateFile>>;
          let recoveryAttempts: SurfaceRecoveryAttempt[] = [];
          try {
            result = await evaluateCurrentExecutor();
          } catch (error) {
            const failureKind = classifyTradingViewRuntimeFailure(error);
            if (!failureKind) {
              throw error;
            }
            await monitor.log(
              "verification.runtime_failure",
              "Authoritative verification runtime failure detected",
              {
                candidate: options.candidate,
                executor: authoritativeExecutorName,
                detail: error instanceof Error ? error.message : String(error),
                failureKind,
              },
            );
            let resolvedResult: Awaited<ReturnType<typeof evaluateCandidateFile>> | undefined;
            let finalRuntimeFailureKind: VerificationRuntimeFailureKind =
              failureKind;
            if (surfaceRecoveryAttempts > 0) {
              const recovery = await attemptTradingViewSurfaceRecovery({
                executorFactory: () =>
                  createPineEvaluationExecutor(env, authoritativeExecutorName),
                chartTarget,
                failureKind,
                attempt: 1,
                monitor,
              });
              recoveryAttempts = [recovery.recoveryAttempt];
              if (recovery.recovered && recovery.executor) {
                await executor.close?.();
                executor = recovery.executor;
                try {
                  resolvedResult = await evaluateCurrentExecutor();
                } catch (retryError) {
                  const retryFailureKind = classifyTradingViewRuntimeFailure(retryError);
                  if (!retryFailureKind) {
                    throw retryError;
                  }
                  finalRuntimeFailureKind = retryFailureKind;
                }
              }
            }
            if (!resolvedResult) {
              let fallbackEvaluation: FallbackEvaluation | null = null;
              let fallbackEvaluationArtifact: Record<string, unknown> | null = null;
              if (fallbackLocalOnRuntimeFailure) {
                const fallbackResult = await collectLocalFallbackEvidence({
                  candidateId,
                  pineSource: pineScript,
                  chartTarget,
                  objective,
                  acceptedHeadScore: acceptedRecord?.candidateScore ?? null,
                  maxTrades: env.maxTrades,
                  authoritativeFailureKind: finalRuntimeFailureKind,
                  recoveryAttempts,
                  executorFactory: createLocalFallbackExecutorFactory(env),
                  monitor,
                });
                fallbackEvaluation = fallbackResult.fallbackEvaluation;
                fallbackEvaluationArtifact = fallbackResult.artifactPayload;
              }

              resolvedResult = {
                candidateId,
                candidatePath,
                candidateHash: sha256(pineScript),
                pineScript,
                studyTitle,
                executorCapability: authoritativeExecutorCapability,
                decision: "verification_fail",
                verificationStatus: "verification_failed",
                verificationFailureReason: "verification_runtime_failure",
                verificationRuntimeFailureKind: finalRuntimeFailureKind,
                recoveryAttempts,
                fallbackEvaluation,
                fallbackEvaluationArtifact,
                promotionReady: false,
                compile: null,
                apply: null,
                syncArtifact: null,
                artifactBundle: null,
                testerMetrics: null,
                artifactValidation: null,
                objectiveBreakdown: null,
              };
            } else if (recoveryAttempts.length > 0) {
              resolvedResult = {
                ...resolvedResult,
                recoveryAttempts,
              };
            }
            result = resolvedResult;
          }

          const verificationStatus =
            result.verificationStatus ??
            deriveVerificationStatus({
              decision: result.decision,
              executorCapability: result.executorCapability,
              usedVerificationExecutor: true,
            });
          const promotionStatus = derivePromotionStatus({
            decision: result.decision,
            executorCapability: result.executorCapability,
          });
          const promotionReady = derivePromotionReadiness({
            decision: result.decision,
            artifactValidation: result.artifactValidation,
            executorCapability: result.executorCapability,
            verificationStatus,
            fallbackEvaluation: result.fallbackEvaluation ?? null,
            mutationProvenance: latestCandidateRecord?.mutationProvenance ?? null,
          });
          const localTvParity = resolveLocalTvParityForVerification({
            fallbackRecord: fallbackCandidateRecord,
            testerMetrics: result.testerMetrics,
            verificationStatus,
            fallbackEvaluation: result.fallbackEvaluation ?? null,
          });

          const objectiveArtifact =
            result.objectiveBreakdown && result.testerMetrics
              ? buildObjectiveArtifact({
                  candidateId: result.candidateId,
                  decision: result.decision,
                objectiveBreakdown: result.objectiveBreakdown,
                strategyMetrics: result.testerMetrics,
                  attachDiagnostics: result.artifactBundle?.attachDiagnostics,
                  artifactValidation: result.artifactValidation ?? undefined,
                  verificationRuntimeFailureKind:
                    result.verificationRuntimeFailureKind ?? null,
                  recoveryAttempts: result.recoveryAttempts ?? [],
                  fallbackEvaluation: result.fallbackEvaluation ?? null,
                  verificationStatus,
                  promotionStatus,
                  verificationFailureReason:
                    result.verificationFailureReason ?? null,
                  promotionReady,
                  screeningVsVerificationDiff: null,
                  recordEra: "v2",
                })
              : undefined;

          const artifactPaths =
            result.syncArtifact !== null
              ? await writeIterationArtifacts({
                  workspaceRoot: env.workspaceRoot,
                  stateRoot,
                  candidateId: result.candidateId,
                  iteration,
                  syncArtifact: result.syncArtifact ?? undefined,
                  artifactBundle: result.artifactBundle ?? undefined,
                  objectiveArtifact,
                  fallbackEvaluationArtifact:
                    result.fallbackEvaluationArtifact ?? undefined,
                })
              : result.fallbackEvaluationArtifact
                ? await writeIterationArtifacts({
                    workspaceRoot: env.workspaceRoot,
                    stateRoot,
                    candidateId: result.candidateId,
                    iteration,
                    fallbackEvaluationArtifact: result.fallbackEvaluationArtifact,
                  })
                : {};

          const experiment = await appendExperimentRecord(stateRoot, {
            runId,
            iteration,
            candidateId: result.candidateId,
            parentCandidateId: latestCandidateRecord?.parentCandidateId ?? null,
            branchId: latestCandidateRecord?.branchId ?? "main",
            acceptedHeadCandidateId: acceptedRecord?.candidateId ?? null,
            baselineCandidateId: seedStrategy.candidateId,
            seedStrategyId: seedStrategy.candidateId,
            improvementSource: acceptedRecord ? "accepted_head" : "seed",
            candidatePath: result.candidatePath,
            candidateHash: result.candidateHash,
            studyTitle: result.studyTitle,
            candidateScore: result.objectiveBreakdown?.score ?? null,
            decision: result.decision,
            status: mapDecisionToExperimentStatus(result.decision),
            compile: result.compile ?? undefined,
            apply: result.apply ?? undefined,
            syncArtifact: result.syncArtifact ?? undefined,
            testerMetrics: result.testerMetrics ?? undefined,
            artifactBundle: result.artifactBundle ?? undefined,
            objectiveBreakdown: result.objectiveBreakdown ?? undefined,
            conditionInventory: latestCandidateRecord?.conditionInventory,
            mutationBriefSummary: "Manual authoritative verification of an existing candidate.",
            nextMutationHints: latestCandidateRecord?.nextMutationHints ?? [],
            mutationParseStatus: latestCandidateRecord?.mutationParseStatus ?? "valid",
            mutationProvenance: latestCandidateRecord?.mutationProvenance ?? null,
            executorCapability: result.executorCapability,
            artifactValidation: result.artifactValidation ?? undefined,
            verificationStatus,
            verificationFailureReason: result.verificationFailureReason ?? null,
            verificationRuntimeFailureKind:
              result.verificationRuntimeFailureKind ?? null,
            recoveryAttempts: result.recoveryAttempts ?? [],
            fallbackEvaluation: result.fallbackEvaluation ?? undefined,
            promotionStatus,
            promotionReady,
            localTvParity,
            screeningVsVerificationDiff: null,
            recordEra: "v2",
            artifactPaths: {
              candidate: result.candidatePath,
              ...artifactPaths,
            },
            recordMeta: {
              schemaVersion: "experiment/v2",
              recordHash: "",
              candidateHash: result.candidateHash,
              baselineHash: seedStrategy.candidateHash,
              artifactBundleHash: result.artifactBundle
                ? sha256(JSON.stringify(result.artifactBundle))
                : null,
              pipelineVersion: "af-research-pipeline/v2",
            },
          });
          await rebuildIndexes(stateRoot);
          await monitor.log("verification.done", "Candidate verification recorded", {
            candidateId: result.candidateId,
            decision: result.decision,
            executor: authoritativeExecutorName,
          });
          console.log(
            JSON.stringify(
              {
                verified: result.decision === "verified_improvement",
                decision: result.decision,
                verificationStatus,
                promotionReady,
                localTvParity,
                experiment,
                tracePath: monitor.tracePath,
              },
              null,
              2,
            ),
          );
        } finally {
          await executor.close?.();
        }
      },
    );
    },
  );

program
  .command("promote")
  .alias("promote-head")
  .description("[legacy] Promote a previously verified candidate to the active head. This does not re-run evaluation.")
  .requiredOption("--candidate <id>", "Candidate id or explicit .pine path")
  .action(async (options: { candidate: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "promote",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const stateRoot = env.stateRoot;
        const previousRecords = await readExperimentRecords(stateRoot);
        const acceptedRecord = findBestAcceptedRecord(previousRecords);
        const verifiedRecord = findLatestVerifiedExperimentForCandidate(
          previousRecords,
          options.candidate,
        );
        if (!verifiedRecord) {
          throw new Error(
            "Candidate has not been verified. Run `af verify --candidate <id>` first.",
          );
        }
        if (resolveRecordEra(verifiedRecord) === "legacy") {
          throw new Error(
            "Legacy accepted records cannot be promoted under the v2 workflow. Re-run `af verify --candidate <id>` first.",
          );
        }
        if (
          verifiedRecord.decision === "promoted_head" ||
          verifiedRecord.promotionStatus === "promoted_head"
        ) {
          console.log(
            JSON.stringify(
              {
                promoted: false,
                alreadyActiveHead: true,
                candidateId: verifiedRecord.candidateId,
                tracePath: monitor.tracePath,
              },
              null,
              2,
            ),
          );
          return;
        }
        assertPromotionEligible(verifiedRecord);
        await assertPromotionEvidenceFilesExist(verifiedRecord);

        const runId = `run-${Date.now()}`;
        const iteration = previousRecords.length + 1;
        await appendRunRecord(stateRoot, {
          runId,
          startedAt: new Date().toISOString(),
          executor: env.evaluationExecutor,
          symbol: env.chartSymbol,
          timeframe: env.chartTimeframe,
          chartType: env.chartType,
          model: env.openAiModel,
        });

        const promotedRecord = await appendExperimentRecord(stateRoot, {
          ...verifiedRecord,
          runId,
          iteration,
          acceptedHeadCandidateId: acceptedRecord?.candidateId ?? null,
          decision: "promoted_head",
          status: mapDecisionToExperimentStatus("promoted_head"),
          verificationStatus: "verified",
          verificationFailureReason: null,
          promotionStatus: "promoted_head",
          promotionReady: true,
          recordEra: "v2",
          mutationBriefSummary:
            verifiedRecord.mutationBriefSummary ??
            "Manual promotion of a previously verified candidate.",
          recordMeta: {
            schemaVersion: "experiment/v2",
            recordHash: "",
            candidateHash: verifiedRecord.candidateHash ?? null,
            baselineHash:
              verifiedRecord.recordMeta?.baselineHash ??
              verifiedRecord.baselineCandidateId ??
              null,
            artifactBundleHash:
              verifiedRecord.recordMeta?.artifactBundleHash ??
              verifiedRecord.artifactBundleHash ??
              (verifiedRecord.artifactBundle
                ? sha256(JSON.stringify(verifiedRecord.artifactBundle))
                : null),
            promotedFromRunId: verifiedRecord.runId,
            promotedFromIteration: verifiedRecord.iteration,
            promotedFromRecordHash:
              verifiedRecord.recordMeta?.recordHash ?? null,
            pipelineVersion: "af-research-pipeline/v2",
          },
          recordedAt: undefined,
        });
        await rebuildIndexes(stateRoot);
        await monitor.log("promotion.done", "Verified candidate promoted", {
          previousHeadCandidateId: acceptedRecord?.candidateId ?? null,
          promotedCandidateId: promotedRecord.candidateId,
          promotedScore: promotedRecord.candidateScore ?? null,
        });
        console.log(
          JSON.stringify(
            {
              promoted: true,
              candidateId: promotedRecord.candidateId,
              previousHeadCandidateId: acceptedRecord?.candidateId ?? null,
              activeHeadCandidateId: promotedRecord.candidateId,
              score: promotedRecord.candidateScore ?? null,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("repair")
  .description("Repair a compile-failed candidate, then compile/apply/backtest it again.")
  .option("--candidate <id>", "Candidate id or explicit .pine path. Defaults to latest compile_fail candidate.")
  .option("--max-attempts <number>", "Maximum compile repair attempts", "2")
  .action(async (options: { candidate?: string; maxAttempts: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "repair",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const stateRoot = env.stateRoot;
        const objective = await loadObjectiveConfig(env.workspaceRoot);
        const previousRecords = await readExperimentRecords(stateRoot);
        const compileFailRecord = findLatestCompileFailRecord(previousRecords, options.candidate);
        const fallbackCandidatePath = options.candidate
          ? resolveCandidatePath(env.workspaceRoot, options.candidate)
          : null;

        if (!compileFailRecord && !fallbackCandidatePath) {
          throw new Error("No compile_fail candidate was found to repair.");
        }

        const iteration = previousRecords.length + 1;
        const runId = `run-${Date.now()}`;
        const maxAttempts = parsePositiveInteger(options.maxAttempts, "max-attempts");
        const mutationContext = await prepareMutationContext({
          workspaceRoot: env.workspaceRoot,
          stateRoot,
          objective,
          previousRecords,
        });
        const {
          seedStrategy,
          acceptedRecord,
          brief,
        } = mutationContext;

        const candidatePath = compileFailRecord?.candidatePath
          ? compileFailRecord.candidatePath
          : fallbackCandidatePath!;
        let currentSource = await readFile(candidatePath, "utf8");
        let currentSummary =
          compileFailRecord?.mutationBriefSummary ??
          extractStudyTitle(currentSource) ??
          path.basename(candidatePath, ".pine");
        let currentInventory = compileFailRecord?.conditionInventory ?? [];
        let currentCandidateId =
          compileFailRecord?.candidateId ?? path.basename(candidatePath, ".pine");
        let currentParentCandidateId = currentCandidateId;
        let currentCandidatePath = candidatePath;
        let currentStudyTitle =
          compileFailRecord?.studyTitle ?? extractStudyTitle(currentSource);
        let currentCandidateHash = compileFailRecord?.candidateHash;
        let currentHintList = compileFailRecord?.nextMutationHints ?? [];
        let currentCompileErrors = compileFailRecord?.compile?.errors ?? [];
        let currentFailureRecorded = Boolean(compileFailRecord);
        let latestCompileFailureRecord = compileFailRecord;
        const runtimeTargetPath = path.join(
          env.workspaceRoot,
          "strategies",
          "source",
          "runtime_target.pine",
        );
        const llmClient = await createMutationLlmClient(env);
        const executor = createPineEvaluationExecutor(env);
        const executorCapability = executor.getCapability();

        await appendRunRecord(stateRoot, {
          runId,
          startedAt: new Date().toISOString(),
          executor: env.evaluationExecutor,
          symbol: env.chartSymbol,
          timeframe: env.chartTimeframe,
          chartType: env.chartType,
          model: env.openAiModel,
        });

        try {
          await monitor.log("repair.start", "Preparing compile repair", {
            sourceCandidateId: compileFailRecord?.candidateId ?? currentCandidateId,
            candidatePath,
            maxAttempts,
          });
          await executor.prepareChart({
            symbol: env.chartSymbol,
            timeframe: env.chartTimeframe,
            chartType: env.chartType,
          });
          await monitor.log("executor.chart_ready", "Evaluation surface prepared", {
            symbol: env.chartSymbol,
            timeframe: env.chartTimeframe,
            chartType: env.chartType,
          });

          let compile = compileFailRecord?.compile ?? { ok: false, errors: currentCompileErrors };
          let syncArtifact = null as Awaited<ReturnType<NonNullable<typeof executor.buildSyncArtifact>>> | null;

          for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
            await writeFile(runtimeTargetPath, currentSource, "utf8");
            await executor.updateStrategySource(currentSource);
            await monitor.log("executor.source_updated", "Pine source pushed", {
              candidateId: currentCandidateId,
              studyTitle: currentStudyTitle,
              attempt,
            });
            compile = await executor.compileStrategy();
            syncArtifact =
              (await executor.buildSyncArtifact?.({
                chartTarget: {
                  symbol: env.chartSymbol,
                  timeframe: env.chartTimeframe,
                  chartType: env.chartType,
                },
                compile,
              })) ?? null;
            await monitor.log("executor.compile", "Compile finished", {
              ok: compile.ok,
              errors: compile.errors,
              attempt,
              candidateId: currentCandidateId,
            });

            if (compile.ok) {
              break;
            }

            currentCompileErrors = compile.errors;
            if (!currentFailureRecorded) {
              const artifactPaths = syncArtifact
                ? await writeIterationArtifacts({
                    workspaceRoot: env.workspaceRoot,
                    stateRoot,
                    candidateId: currentCandidateId,
                    iteration,
                    syncArtifact,
                  })
                : {};
              latestCompileFailureRecord = await appendExperimentRecord(stateRoot, {
                runId,
                iteration,
                candidateId: currentCandidateId,
                parentCandidateId: currentParentCandidateId,
                branchId: "main",
                acceptedHeadCandidateId: acceptedRecord?.candidateId ?? null,
                baselineCandidateId: seedStrategy.candidateId,
                seedStrategyId: seedStrategy.candidateId,
                improvementSource: acceptedRecord ? "accepted_head" : "seed",
                candidatePath: currentCandidatePath,
                candidateHash: currentCandidateHash,
                studyTitle: currentStudyTitle,
                candidateScore: null,
                decision: "compile_fail",
                status: "compile_failed",
                compile,
                syncArtifact: syncArtifact ?? undefined,
                conditionInventory: currentInventory,
                mutationBriefSummary: currentSummary,
                nextMutationHints: currentHintList,
                mutationParseStatus: "recovered",
                mutationProvenance: compileFailRecord?.mutationProvenance ?? null,
                executorCapability,
                verificationStatus: "not_requested",
                verificationFailureReason: null,
                promotionStatus: "not_promoted",
                promotionReady: false,
                localTvParity: null,
                screeningVsVerificationDiff: null,
                recordEra: "v2",
                artifactPaths: {
                  candidate: currentCandidatePath,
                  runtimeTarget: runtimeTargetPath,
                  ...artifactPaths,
                },
                recordMeta: {
                  schemaVersion: "experiment/v2",
                  recordHash: "",
                  candidateHash: currentCandidateHash ?? null,
                  baselineHash: seedStrategy.candidateHash,
                  artifactBundleHash: null,
                  pipelineVersion: "af-research-pipeline/v2",
                },
              });
              currentFailureRecorded = true;
            }

            if (attempt === maxAttempts) {
              await monitor.log("repair.done", "Compile repair attempts exhausted", {
                candidateId: currentCandidateId,
                errors: currentCompileErrors,
              });
              console.log(
                JSON.stringify(
                  {
                    decision: "compile_fail",
                    candidateId: currentCandidateId,
                    compile,
                    tracePath: monitor.tracePath,
                  },
                  null,
                  2,
                ),
              );
              return;
            }

            await monitor.log("repair.compile.start", "Starting compile repair", {
              attempt,
              candidateId: currentCandidateId,
              errors: currentCompileErrors,
            });
            const repairResponse = await llmClient.repairMutation({
              brief,
              candidatePine: currentSource,
              compileErrors: currentCompileErrors,
              candidateSummary: currentSummary,
              inventory: currentInventory,
            });
            await monitor.log("repair.compile.response", "Received compile repair response", {
              attempt,
              responseLength: repairResponse.length,
            });
            const parsedRepair = parseMutationResponseWithRecovery(repairResponse);
            await monitor.log("repair.compile.parsed", "Parsed compile repair response", {
              attempt,
              candidateSummary: parsedRepair.candidateSummary,
              conditionCount: parsedRepair.inventory.length,
            });
            const repairArtifact = await persistCandidateArtifact({
              workspaceRoot: env.workspaceRoot,
              parsedMutation: parsedRepair,
              parentCandidateId: currentCandidateId,
              branchId: "main",
            });
            await appendCandidateLedgerRecord(stateRoot, {
              runId,
              iteration,
              candidateId: repairArtifact.candidateId,
              parentCandidateId: repairArtifact.parentId,
              branchId: repairArtifact.branchId,
              studyTitle: repairArtifact.studyTitle,
              candidatePath: repairArtifact.pinePath,
              candidateHash: repairArtifact.pineHash,
              contractVersion: AUTORESEARCH_CONTRACT_VERSION,
              mutationAuthority: repairArtifact.specHash
                ? STRATEGY_SPEC_MUTATION_AUTHORITY
                : null,
              specPath: repairArtifact.specPath ?? null,
              specHash: repairArtifact.specHash ?? null,
              candidateSummary: repairArtifact.candidateSummary,
              nextMutationHints: repairArtifact.nextMutationHints,
            });
            currentSource = await readFile(repairArtifact.pinePath, "utf8");
            await writeFile(runtimeTargetPath, currentSource, "utf8");
            currentSummary = repairArtifact.candidateSummary;
            currentInventory = repairArtifact.inventory;
            currentCandidateId = repairArtifact.candidateId;
            currentParentCandidateId = repairArtifact.parentId ?? currentParentCandidateId;
            currentCandidatePath = repairArtifact.pinePath;
            currentStudyTitle = repairArtifact.studyTitle;
            currentCandidateHash = repairArtifact.pineHash;
            currentHintList = repairArtifact.nextMutationHints;
            currentFailureRecorded = false;
            await monitor.log("repair.persisted", "Repair candidate artifact persisted", {
              attempt,
              candidateId: repairArtifact.candidateId,
              candidatePath: repairArtifact.pinePath,
              parentCandidateId: repairArtifact.parentId,
            });
          }

          const apply = await executor.applyStrategy({
            expectedStudyTitle: currentStudyTitle,
          });
          await monitor.log("executor.apply", "Apply finished", {
            ok: apply.ok,
            message: apply.message,
            expectedStudyTitle: currentStudyTitle,
            detectedStudyTitle: apply.attachDiagnostics?.detectedStudyTitle ?? null,
          });
          if (!apply.ok) {
            console.log(
              JSON.stringify(
                {
                  decision: "apply_fail",
                  candidateId: currentCandidateId,
                  compile,
                  apply,
                  tracePath: monitor.tracePath,
                },
                null,
                2,
              ),
            );
            return;
          }

          const appliedSyncArtifact =
            (await executor.buildSyncArtifact?.({
              chartTarget: {
                symbol: env.chartSymbol,
                timeframe: env.chartTimeframe,
                chartType: env.chartType,
              },
              compile,
              apply,
            })) ?? {
              chartTarget: {
                symbol: env.chartSymbol,
                timeframe: env.chartTimeframe,
                chartType: env.chartType,
              },
              compile,
              apply,
              attachDiagnostics: apply.attachDiagnostics,
              stateAfter: {},
            };
          const artifactBundle = await executor.readArtifactBundle({
            expectedStudyTitle: currentStudyTitle,
            maxTrades: env.maxTrades,
          });
          const testerMetrics = artifactBundle.strategy;
          const artifactValidation = validateArtifactBundle({
            artifactBundle,
            executorCapability,
          });
          await monitor.log("executor.metrics", "Backtest metrics captured", {
            totalTrades: testerMetrics?.totalTrades ?? 0,
            netProfitPercent: testerMetrics?.netProfitPercent ?? 0,
            postFeeNetProfitPercent: testerMetrics?.postFeeNetProfitPercent ?? 0,
            tradesCollected: artifactBundle.trades.length,
            equityPoints: artifactBundle.equity.pointCount,
          });

          if (!testerMetrics) {
            console.log(
              JSON.stringify(
                {
                  decision: "backtest_empty",
                  candidateId: currentCandidateId,
                  compile,
                  apply,
                  artifactBundle,
                  tracePath: monitor.tracePath,
                },
                null,
                2,
              ),
            );
            return;
          }

          const objectiveBreakdown = evaluateObjective(testerMetrics, objective);
          const decision = executorCapability.authoritative
            ? classifyAuthoritativeDecision({
                breakdown: objectiveBreakdown,
                acceptedHeadScore: acceptedRecord?.candidateScore ?? null,
                artifactValidation,
              })
            : classifyScreeningDecision(
                objectiveBreakdown,
                acceptedRecord?.candidateScore ?? null,
              );
          const verificationStatus = deriveVerificationStatus({
            decision,
            executorCapability,
            usedVerificationExecutor: false,
          });
          const promotionStatus = derivePromotionStatus({
            decision,
            executorCapability,
          });
          const promotionReady = derivePromotionReadiness({
            decision,
            artifactValidation,
            executorCapability,
            verificationStatus,
            fallbackEvaluation: null,
            mutationProvenance: compileFailRecord?.mutationProvenance ?? null,
          });
          const objectiveArtifact = buildObjectiveArtifact({
            candidateId: currentCandidateId,
            decision,
            objectiveBreakdown,
            strategyMetrics: testerMetrics,
            attachDiagnostics: artifactBundle.attachDiagnostics,
            artifactValidation,
            verificationStatus,
            verificationFailureReason:
              decision === "verified_improvement"
                ? null
                : deriveVerificationFailureReason({
                    decision,
                    artifactValidation,
                    hadRuntimeFailure: false,
                    wasBacktestEmpty: false,
                    usedVerificationExecutor: false,
                  }),
            promotionStatus,
            promotionReady,
            screeningVsVerificationDiff: null,
            recordEra: "v2",
          });
          const artifactPaths = await writeIterationArtifacts({
            workspaceRoot: env.workspaceRoot,
            stateRoot,
            candidateId: currentCandidateId,
            iteration,
            syncArtifact: appliedSyncArtifact,
            artifactBundle,
            objectiveArtifact,
          });
          const experiment = await appendExperimentRecord(stateRoot, {
            runId,
            iteration,
            candidateId: currentCandidateId,
            parentCandidateId: currentParentCandidateId,
            branchId: "main",
            acceptedHeadCandidateId: acceptedRecord?.candidateId ?? null,
            baselineCandidateId: seedStrategy.candidateId,
            seedStrategyId: seedStrategy.candidateId,
            improvementSource: acceptedRecord ? "accepted_head" : "seed",
            candidatePath: currentCandidatePath,
            candidateHash: currentCandidateHash,
            studyTitle: currentStudyTitle,
            candidateScore: objectiveBreakdown.score,
            decision,
            status: "evaluated",
            compile,
            apply,
            syncArtifact: appliedSyncArtifact,
            artifactBundle,
            testerMetrics,
            objectiveBreakdown,
            conditionInventory: currentInventory,
            mutationBriefSummary: currentSummary,
            nextMutationHints: currentHintList,
            mutationParseStatus: "recovered",
            mutationProvenance: compileFailRecord?.mutationProvenance ?? null,
            executorCapability,
            artifactValidation,
            verificationStatus,
            verificationFailureReason:
              decision === "verified_improvement"
                ? null
                : deriveVerificationFailureReason({
                    decision,
                    artifactValidation,
                    hadRuntimeFailure: false,
                    wasBacktestEmpty: false,
                    usedVerificationExecutor: false,
                  }),
            promotionStatus,
            promotionReady,
            localTvParity: null,
            screeningVsVerificationDiff: null,
            recordEra: "v2",
            artifactPaths: {
              candidate: currentCandidatePath,
              runtimeTarget: runtimeTargetPath,
              ...artifactPaths,
            },
            recordMeta: {
              schemaVersion: "experiment/v2",
              recordHash: "",
              candidateHash: currentCandidateHash ?? null,
              baselineHash: seedStrategy.candidateHash,
              artifactBundleHash: sha256(JSON.stringify(artifactBundle)),
              pipelineVersion: "af-research-pipeline/v2",
            },
          });
          await rebuildIndexes(stateRoot);
          await monitor.log("repair.done", "Compile repair completed", {
            sourceCandidateId: compileFailRecord?.candidateId ?? currentCandidateId,
            repairedCandidateId: currentCandidateId,
            decision,
            score: objectiveBreakdown.score,
          });
          console.log(
            JSON.stringify(
                {
                  sourceCompileFailCandidateId:
                    compileFailRecord?.candidateId ?? currentCandidateId,
                  repairedCandidateId: currentCandidateId,
                  decision,
                compile,
                apply,
                testerMetrics,
                objectiveBreakdown,
                experiment,
                latestCompileFailureRecord,
                tracePath: monitor.tracePath,
              },
            null,
              2,
            ),
          );
        } finally {
          await executor.close?.();
        }
      },
    );
  });

program
  .command("iterate")
  .description("[legacy] Run one or more mutation/evaluation iterations.")
  .option("--count <number>", "Iteration count", "1")
  .action(async (options: { count: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "iterate",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const llmClient = await createMutationLlmClient(env);
          const iterations = Number.parseInt(options.count, 10);
          const results = [];
          const executor = createPineEvaluationExecutor(env);
          const promotionVerificationExecutorFactory =
            createPromotionVerificationExecutorFactory(env);
          const runId = `run-${Date.now()}`;
        await monitor.log("iterate.start", "Starting iterate command", {
          count: iterations,
          workspaceRoot: env.workspaceRoot,
          runId,
        });
        await appendRunRecord(env.stateRoot, {
          runId,
          startedAt: new Date().toISOString(),
          executor: env.evaluationExecutor,
          symbol: env.chartSymbol,
          timeframe: env.chartTimeframe,
          chartType: env.chartType,
          model: env.openAiModel,
        });

        try {
          for (let index = 0; index < iterations; index += 1) {
            await monitor.setTask(index + 1);
            await monitor.log("iterate.loop", "Running iteration", {
              currentIteration: index + 1,
              totalIterations: iterations,
            });
            results.push(
                await runSingleIteration({
                  workspaceRoot: env.workspaceRoot,
                  stateRoot: env.stateRoot,
                  llmClient,
                  executor,
                  executorName: env.evaluationExecutor,
                  promotionVerificationExecutorFactory,
                  promotionVerificationExecutorName:
                    env.promotionVerificationExecutor,
                  runId,
                  chartType: env.chartType,
                  maxTrades: env.maxTrades,
                  monitor,
                  fallbackLocalOnRuntimeFailure: true,
                  localFallbackExecutorFactory:
                    createLocalFallbackExecutorFactory(env),
                }),
            );
          }
        } finally {
          await executor.close?.();
        }

        monitor.clearTask();
        await monitor.log("iterate.done", "Iterate command completed", {
          count: iterations,
          results: results.map((result) => ({
            candidateId: result.experiment.candidateId,
            decision: result.decision,
            score: result.experiment.candidateScore ?? null,
          })),
        });
        console.log(
          JSON.stringify(
            {
              results,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("run-tasks")
  .description("[legacy] Run a bounded task batch with hypothesis, execution, and analysis records.")
  .option(
    "--count <number>",
    `Task count (1-10, default ${DEFAULT_TASK_BATCH_COUNT} for faster feedback)`,
    String(DEFAULT_TASK_BATCH_COUNT),
  )
  .option("--max-runtime-failures <number>", "Stop after this many runtime failures", "3")
  .option(
    "--fallback-local-on-tv-runtime-failure",
    "Collect local fallback evidence after TradingView runtime failures",
  )
  .option(
    "--no-fallback-local-on-tv-runtime-failure",
    "Disable local fallback evidence after TradingView runtime failures",
  )
  .option(
    "--max-fallbacks-per-batch <number>",
    "Maximum local fallback evidence collections per batch",
    "5",
  )
  .action(async (options: {
    count: string;
    maxRuntimeFailures: string;
    fallbackLocalOnTvRuntimeFailure?: boolean;
    noFallbackLocalOnTvRuntimeFailure?: boolean;
    maxFallbacksPerBatch: string;
  }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "run-tasks",
      },
      async (monitor) => {
        const taskCount = parseBoundedTaskCount(options.count);
        const maxRuntimeFailures = parseBoundedTaskCount(options.maxRuntimeFailures);
        const maxFallbacksPerBatch = parsePositiveInteger(
          options.maxFallbacksPerBatch,
          "max-fallbacks-per-batch",
        );
        const fallbackLocalOnTvRuntimeFailure =
          options.noFallbackLocalOnTvRuntimeFailure ? false : true;
        const llmClient = await createMutationLlmClient(env);
          const executorFactory = () => createPineEvaluationExecutor(env);
          const executor = executorFactory();
          const promotionVerificationExecutorFactory =
            createPromotionVerificationExecutorFactory(env);
          const runId = `run-${Date.now()}`;
        const recoveryHooks = createAutomaticTaskBatchRecoveryHooks({
          env,
          monitor,
          executorFactory,
        });

        await appendRunRecord(env.stateRoot, {
          runId,
          startedAt: new Date().toISOString(),
          executor: env.evaluationExecutor,
          symbol: env.chartSymbol,
          timeframe: env.chartTimeframe,
          chartType: env.chartType,
          model: env.openAiModel,
        });

        try {
          const batch = await runTaskBatch({
            workspaceRoot: env.workspaceRoot,
            stateRoot: env.stateRoot,
            llmClient,
            executor,
            executorName: env.evaluationExecutor,
            promotionVerificationExecutorFactory,
            promotionVerificationExecutorName:
              env.promotionVerificationExecutor,
            taskCount,
            maxRuntimeFailures,
            runId,
            chartType: env.chartType,
            maxTrades: env.maxTrades,
            monitor,
            env,
            researchRefreshEveryTasks: env.researchRefreshEveryTasks,
            maxAutoRecoveryAttemptsPerTask: 1,
            recoveryHooks,
            fallbackLocalOnTvRuntimeFailure,
            maxFallbacksPerBatch,
            localFallbackExecutorFactory: createLocalFallbackExecutorFactory(env),
          });

          console.log(
            JSON.stringify(
              {
                batch,
                tracePath: monitor.tracePath,
              },
              null,
              2,
            ),
          );
        } finally {
          await executor.close?.();
        }
      },
    );
  });

program
  .command("ingest-knowledge")
  .description("Ingest external research knowledge from a PDF, text file, markdown, JSON, or inline text.")
  .option("--file <path>", "Path to a PDF, text, markdown, or JSON file")
  .option("--text <content>", "Inline text or JSON content to ingest")
  .option("--title <title>", "Knowledge title override")
  .option("--source-url <url>", "Original source URL when applicable")
  .option(
    "--source-type <type>",
    "Source type override (alphaxiv_mcp, manual_pdf, manual_text, manual_markdown, manual_json)",
  )
  .option("--problem-tags <tags>", "Comma-separated problem tags")
  .option("--strategy-tags <tags>", "Comma-separated strategy tags")
  .action(
    async (options: {
      file?: string;
      text?: string;
      title?: string;
      sourceUrl?: string;
      sourceType?: "alphaxiv_mcp" | "manual_pdf" | "manual_text" | "manual_markdown" | "manual_json";
      problemTags?: string;
      strategyTags?: string;
    }) => {
      const env = loadRuntimeEnvironment();
      await withCliMonitor(
        {
          workspaceRoot: env.workspaceRoot,
          commandName: "ingest-knowledge",
        },
      async (monitor) => {
          if (!options.file && !options.text) {
            throw new Error("Provide --file or --text to ingest research knowledge.");
          }

          await initializeWorkspace(env.workspaceRoot);
          await monitor.log("knowledge.ingest.start", "Starting research knowledge ingestion", {
            file: options.file ?? null,
            title: options.title ?? null,
            sourceType: options.sourceType ?? null,
          });
          const records = await ingestResearchKnowledge({
            workspaceRoot: env.workspaceRoot,
            env,
            filePath: options.file,
            rawText: options.text,
            title: options.title,
            sourceType: options.sourceType,
            sourceUrl: options.sourceUrl ?? null,
            problemTags: parseCommaSeparatedList(options.problemTags),
            strategyTags: parseCommaSeparatedList(options.strategyTags),
          });
          await rebuildIndexes(env.stateRoot);
          await monitor.log("knowledge.ingest.done", "Research knowledge ingestion completed", {
            ingestedCount: records.length,
            knowledgeIds: records.map((record) => record.knowledgeId),
          });
          console.log(
            JSON.stringify(
              {
                records,
                tracePath: monitor.tracePath,
              },
              null,
              2,
            ),
          );
        },
      );
    },
  );

program
  .command("rebuild-indexes")
  .description("Rebuild layered derived views from the experiment and incident ledgers.")
  .option("--verify", "Verify derived views against the ledger after rebuilding.")
  .option(
    "--validation-mode <mode>",
    "Ledger validation mode used by --verify: fast or deep.",
    "fast",
  )
  .action(async (options: { verify?: boolean; validationMode?: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "rebuild-indexes",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        await monitor.log("indexes.start", "Rebuilding derived indexes", {
          stateRoot: env.stateRoot,
        });
        await rebuildIndexes(env.stateRoot);
        const validationMode = parseLedgerValidationMode(options.validationMode);
        const autonomousState = await buildAutonomousStateSummary({
          stateRoot: env.stateRoot,
          env,
        });
        const verification = options.verify
          ? await verifyDerivedViews(env.stateRoot, { validationMode })
          : null;
        await monitor.log("indexes.done", "Derived indexes rebuilt", {
          stateRoot: env.stateRoot,
          validationMode: options.verify ? validationMode : null,
          verificationOk: verification?.ok ?? null,
        });
        if (options.verify && verification && !verification.ok) {
          throw new Error(
            `Derived view verification failed with ${verification.issues.length} issue(s).`,
          );
        }
        console.log(
          JSON.stringify(
            {
              rebuilt: true,
              stateRoot: env.stateRoot,
              autonomousState,
              verification,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("validate-ledger")
  .description("Validate JSONL ledgers. Defaults to fast metadata checks; use --deep for artifact hash verification.")
  .option("--mode <mode>", "Validation mode: fast or deep.", "fast")
  .option("--deep", "Run deep artifact hash validation.")
  .action(async (options: { mode?: string; deep?: boolean }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "validate-ledger",
      },
      async (monitor) => {
        const stateRoot = env.stateRoot;
        await ensureStateRoot(stateRoot);
        const mode = options.deep ? "deep" : parseLedgerValidationMode(options.mode);
        const validation = await validateLedger(stateRoot, { mode });
        await monitor.log("ledger.validation", "Ledger validation completed", {
          stateRoot,
          mode,
          ok: validation.ok,
          errorCount: validation.errorCount,
          warningCount: validation.warningCount,
        });
        console.log(
          JSON.stringify(
            {
              ...validation,
              mode,
              stateRoot,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("artifact-retention-report")
  .description("Classify referenced artifacts for retention review without deleting files.")
  .option("--json", "Emit JSON output.", true)
  .option("--output <path>", "Optional path to write the JSON report.")
  .action(async (options: { json?: boolean; output?: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "artifact-retention-report",
      },
      async (monitor) => {
        await ensureStateRoot(env.stateRoot);
        const outputPath = options.output
          ? path.resolve(options.output)
          : undefined;
        const report = await buildArtifactRetentionReport({
          stateRoot: env.stateRoot,
          outputPath,
        });
        await monitor.log("artifact_retention.report", "Artifact retention report generated", {
          stateRoot: env.stateRoot,
          outputPath: outputPath ?? null,
          totalArtifacts: report.summary.totalArtifacts,
          totalSizeBytes: report.summary.totalSizeBytes,
        });
        console.log(
          JSON.stringify(
            {
              ...report,
              outputPath: outputPath ?? null,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("cleanup-runtime")
  .description("Inspect or clean safe runtime cache files without touching TradingView login/session data.")
  .option("--dry-run", "Only report cleanup candidates; this is the default.")
  .option("--confirm", "Delete allowlisted cache candidates.")
  .option("--target <target>", "Cleanup target. Currently only tradingview-cache.", "tradingview-cache")
  .action(
    async (options: {
      dryRun?: boolean;
      confirm?: boolean;
      target?: string;
    }) => {
      const env = loadRuntimeEnvironment();
      await withCliMonitor(
        {
          workspaceRoot: env.workspaceRoot,
          commandName: "cleanup-runtime",
        },
        async (monitor) => {
          const target = options.target ?? "tradingview-cache";
          if (target !== "tradingview-cache") {
            throw new Error("cleanup-runtime target must be tradingview-cache.");
          }
          await ensureStateRoot(env.stateRoot);
          const report = await cleanupRuntime({
            stateRoot: env.stateRoot,
            target,
            dryRun: options.dryRun ?? options.confirm !== true,
            confirm: options.confirm === true,
          });
          await monitor.log("runtime_cleanup.report", "Runtime cleanup report completed", {
            stateRoot: env.stateRoot,
            target,
            dryRun: report.dryRun,
            deletedCount: report.deletedCount,
            deletedBytes: report.deletedBytes,
            candidateCount: report.candidates.length,
          });
          console.log(
            JSON.stringify(
              {
                ...report,
                tracePath: monitor.tracePath,
              },
              null,
              2,
            ),
          );
        },
      );
    },
  );

program
  .command("system-health-report")
  .description("Summarize loop bottlenecks, storage pressure, heartbeat state, and index freshness.")
  .option("--json", "Emit JSON output.", true)
  .action(async () => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "system-health-report",
      },
      async (monitor) => {
        await ensureStateRoot(env.stateRoot);
        const report = await buildSystemHealthReport({ stateRoot: env.stateRoot });
        await monitor.log("system_health.report", "System health report generated", {
          stateRoot: env.stateRoot,
          artifactBytes: report.sizes.artifactBytes,
          runtimeBytes: report.sizes.runtimeBytes,
          heartbeatStatus: report.heartbeat.status,
          longestPhase: report.latestTrace.longestPhase?.phase ?? null,
        });
        console.log(
          JSON.stringify(
            {
              ...report,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("inspect-candidate")
  .description("Inspect candidate ledger entries and linked experiments for a candidate.")
  .requiredOption("--candidate <id>", "Candidate id or explicit .pine path")
  .action(async (options: { candidate: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "inspect-candidate",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const stateRoot = env.stateRoot;
        const candidates = await readCandidateLedgerRecords(stateRoot);
        const experiments = await readExperimentRecords(stateRoot);
        const matchingCandidates = candidates.filter((record) =>
          matchesCandidateReference(
            options.candidate,
            record.candidateId,
            record.candidatePath,
          ),
        );
        const matchingExperiments = experiments.filter((record) =>
          matchesCandidateReference(
            options.candidate,
            record.candidateId,
            record.candidatePath,
          ),
        );
        await monitor.log("candidate.inspect", "Candidate inspection completed", {
          candidate: options.candidate,
          candidateRecords: matchingCandidates.length,
          experimentRecords: matchingExperiments.length,
        });
        console.log(
          JSON.stringify(
            {
              candidate: options.candidate,
              candidateRecords: matchingCandidates,
              experiments: matchingExperiments.map((record) => ({
                ...record,
                recordEra: resolveRecordEra(record),
              })),
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("inspect-experiment")
  .description("Inspect the latest experiment for a candidate, or a specific iteration when provided.")
  .requiredOption("--candidate <id>", "Candidate id or explicit .pine path")
  .option("--iteration <number>", "Specific iteration to inspect")
  .action(async (options: { candidate: string; iteration?: string }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "inspect-experiment",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const stateRoot = env.stateRoot;
        const experiments = await readExperimentRecords(stateRoot);
        const targetIteration = options.iteration
          ? parsePositiveInteger(options.iteration, "iteration")
          : null;
        const selected = options.iteration
          ? experiments.find(
              (record) =>
                matchesCandidateReference(
                  options.candidate,
                  record.candidateId,
                  record.candidatePath,
                ) &&
                record.iteration === targetIteration,
            ) ?? null
          : findLatestExperimentForCandidate(experiments, options.candidate);
        await monitor.log("experiment.inspect", "Experiment inspection completed", {
          candidate: options.candidate,
          iteration: selected?.iteration ?? null,
          found: selected !== null,
        });
        console.log(
          JSON.stringify(
            {
              candidate: options.candidate,
              experiment: selected
                ? {
                    ...selected,
                    recordEra: resolveRecordEra(selected),
                  }
                : null,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

program
  .command("check-knowledge-tree")
  .description("Audit the layered knowledge tree for coverage, reachability, and legacy drift.")
  .action(async () => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "check-knowledge-tree",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        const audit = await auditKnowledgeTree(env.workspaceRoot);
        await monitor.log("knowledge.audit", "Knowledge tree audited", {
          auditOk: audit.ok,
          totalEntries: audit.summary.totalEntries,
          missingEntries: audit.summary.missingEntries,
          legacyRootArtifacts: audit.summary.legacyRootArtifacts,
        });
        console.log(
          JSON.stringify(
            {
              ...audit,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
        if (!audit.ok) {
          process.exitCode = 1;
        }
      },
    );
  });

program
  .command("migrate-state")
  .description("Copy legacy flat state/artifact files into the layered knowledge tree.")
  .option(
    "--compact-experiments",
    "Rewrite experiments.jsonl into compact artifact-ref records.",
  )
  .option("--backup", "Create a ledger backup before compacting experiments.")
  .option("--dry-run", "Report compaction impact without rewriting experiments.jsonl.")
  .action(async (options: {
    compactExperiments?: boolean;
    backup?: boolean;
    dryRun?: boolean;
  }) => {
    const env = loadRuntimeEnvironment();
    await withCliMonitor(
      {
        workspaceRoot: env.workspaceRoot,
        commandName: "migrate-state",
      },
      async (monitor) => {
        await initializeWorkspace(env.workspaceRoot);
        if (options.compactExperiments) {
          const compaction = await compactExperimentLedger(env.stateRoot, {
            backup: options.backup ?? false,
            dryRun: options.dryRun ?? false,
          });
          await monitor.log("knowledge.compact_experiments", "Experiment ledger compacted", {
            dryRun: compaction.dryRun,
            recordsWritten: compaction.recordsWritten,
            artifactBundlesStripped: compaction.artifactBundlesStripped,
            originalBytes: compaction.originalBytes,
            compactedBytes: compaction.compactedBytes,
          });
          console.log(
            JSON.stringify(
              {
                compactExperiments: compaction,
                tracePath: monitor.tracePath,
              },
              null,
              2,
            ),
          );
          return;
        }
        const migration = await migrateLegacyKnowledgeLayout(env.workspaceRoot);
        await monitor.log("knowledge.migrate", "Legacy knowledge migrated", {
          copiedCount: migration.copied.length,
        });
        console.log(
          JSON.stringify(
            {
              ...migration,
              tracePath: monitor.tracePath,
            },
            null,
            2,
          ),
        );
      },
    );
  });

try {
  await program.parseAsync(process.argv);
} catch (error) {
  if (!isMonitorLoggedError(error)) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${message}\n`);
  }
  process.exitCode = 1;
}
