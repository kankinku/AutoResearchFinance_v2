import { mkdtemp, readdir, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { type PineEvaluationExecutor } from "../../automation/common/executor.js";
import { type RuntimeEnvironment } from "../../cli/runtime-config.js";
import { type MutationLlmClient } from "../../mutation/llm-client.js";
import { readJsonl, writeJson } from "../../utils/fs.js";
import { validateLedger, verifyDerivedViews } from "../../state/ledger-validator.js";
import {
  readArchiveEventRecords,
  readCalibrationEventRecords,
  readExperimentRecords,
  readHeadEventRecords,
  readLocalConfidenceEventRecords,
  readProblemEventRecords,
  readRepairAttemptRecords,
} from "../../state/jsonl-store.js";
import { buildAutonomousViewPayloads } from "../../state/autonomous-index-builder.js";
import { selectLocalEvaluationRecords } from "../../state/autonomous-state.js";
import { rebuildIndexes } from "../../state/index-builder.js";
import { resolveKnowledgePaths } from "../../state/knowledge-paths.js";
import { initializeWorkspace } from "../workspace.js";
import { runAutonomousIterations } from "./autonomous-loop.js";
import { type MutationBriefRecord } from "../../contracts/types.js";
import { renderAfStrategySpecToPine } from "../../strategy-spec/codegen-pine.js";
import { afStrategySpecFromPine } from "../../strategy-spec/to-af-config.js";
import { type AfStrategySpec } from "../../strategy-spec/schema.js";

export type Stage6ReadinessMode = "deterministic" | "real-llm";
export type Stage6CalibrationMode = "mock-recovered" | "live";

interface MonitorLike {
  log: (
    event: string,
    message: string,
    data?: Record<string, unknown>,
  ) => Promise<void>;
}

export interface Stage6ReadinessResult {
  generatedAt: string;
  evaluated: true;
  passed: boolean;
  mode: Stage6ReadinessMode;
  countRequested: number;
  countCompleted: number;
  countFailed: number;
  activeChampionCandidateId: string | null;
  freshBootstrapPassed: boolean;
  multiIterationPassed: boolean;
  rootIsolationPassed: boolean;
  repairTraceabilityPassed: boolean;
  calibrationQueuePassed: boolean;
  scoreFeedbackPassed: boolean;
  feedbackClosureRequired: boolean;
  calibrationMode: "queue_only" | Stage6CalibrationMode;
  ledgerValidationPassed: boolean;
  indexVerificationPassed: boolean;
  rootIsolationStatus: {
    status: "passed" | "failed";
    customStateRoot: string;
    defaultWorkspaceStateRoot: string;
    customContextExists: boolean;
    defaultWorkspaceStateHasArtifacts: boolean;
  };
  repairTraceabilityStatus: {
    status: "passed" | "failed";
    successfulRepairCount: number;
    successfulRepairsWithoutCandidateCount: number;
  };
  feedbackClosureStatus: {
    status: "passed" | "failed";
    required?: boolean;
    promptFeedbackObserved: boolean;
    scoreBreakdownFeedbackObserved: boolean;
    divergenceCount: number;
    confidenceUpdateCount: number;
  };
  evidence: {
    tempWorkspaceRoot: string | null;
    tempStateRoot: string | null;
    localEvaluationCount: number;
    headEventCount: number;
    archiveEventCount: number;
    calibrationEventCount: number;
    mutationBriefCount: number;
    problemEventCount: number;
    repairAttemptCount: number;
    deadlineBreachCount: number;
  };
  warnings: string[];
}

export async function runStage6ReadinessGate(input: {
  env: RuntimeEnvironment;
  count?: number;
  mode?: Stage6ReadinessMode;
  calibrationMode?: Stage6CalibrationMode;
  autoProcessCalibration?: boolean;
  keepTempRoot?: boolean;
  persistToState?: boolean;
  llmClientFactory?: (env: RuntimeEnvironment) => Promise<MutationLlmClient>;
  localExecutorFactory: (env: RuntimeEnvironment) => PineEvaluationExecutor;
  calibrationExecutorFactory?: (env: RuntimeEnvironment) => PineEvaluationExecutor;
  monitor?: MonitorLike;
}): Promise<Stage6ReadinessResult> {
  const count = input.count ?? 5;
  const mode = input.mode ?? "deterministic";
  const autoProcessCalibration = input.autoProcessCalibration ?? false;
  const calibrationMode = input.calibrationMode ?? "mock-recovered";
  const keepTempRoot = input.keepTempRoot ?? false;
  const persistToState = input.persistToState ?? true;
  const tempWorkspaceRoot = await mkdtemp(path.join(tmpdir(), "af-stage6-workspace-"));
  const tempStateRoot = await mkdtemp(path.join(tmpdir(), "af-stage6-state-"));
  const defaultWorkspaceStateRoot = path.join(
    tempWorkspaceRoot,
    "state",
    "pi-autoresearch",
  );

  await input.monitor?.log("stage6.gate.start", "Starting Stage 6 readiness gate", {
    mode,
    count,
    tempWorkspaceRoot,
    tempStateRoot,
    autoProcessCalibration,
    calibrationMode: autoProcessCalibration ? calibrationMode : "queue_only",
  });

  let result: Stage6ReadinessResult | null = null;
  try {
    const gateEnv: RuntimeEnvironment = {
      ...input.env,
      workspaceRoot: tempWorkspaceRoot,
      stateRoot: tempStateRoot,
      tvCalibrationMode: calibrationMode,
      autonomousBootstrapMode: "auto",
      autoProcessCalibration,
      calibrationBudget: autoProcessCalibration ? Math.max(input.env.calibrationBudget, 1) : 0,
      promotionVerificationExecutor: "none",
    };
    await initializeWorkspace({
      projectRoot: gateEnv.projectRoot,
      workspaceRoot: gateEnv.workspaceRoot,
      stateRoot: gateEnv.stateRoot,
    });
    const seedPine = await readFile(
      path.join(tempWorkspaceRoot, "strategies", "source", "seed_primary.pine"),
      "utf8",
    );
    const llmClient =
      mode === "deterministic"
        ? createDeterministicStage6LlmClient(seedPine)
        : await resolveRealLlmClient(input.llmClientFactory, gateEnv);

    const calibrationExecutorFactory = input.calibrationExecutorFactory;
    const iterationRun = await runAutonomousIterations({
      workspaceRoot: tempWorkspaceRoot,
      env: gateEnv,
      llmClient,
      localExecutorFactory: () => input.localExecutorFactory(gateEnv),
      calibrationExecutorFactory: autoProcessCalibration && calibrationExecutorFactory
        ? () => calibrationExecutorFactory(gateEnv)
        : undefined,
      count,
      monitor: input.monitor,
    });
    await rebuildIndexes(tempStateRoot);
    const validation = await validateLedger(tempStateRoot);
    const indexVerification = await verifyDerivedViews(tempStateRoot);
    const ledgers = await readStage6Ledgers(tempStateRoot);
    const views = buildAutonomousViewPayloads(ledgers);
    const localRecords = selectLocalEvaluationRecords(ledgers.experiments);
    const mutationBriefs = await readMutationBriefRecords(tempStateRoot);
    const activeChampionCandidateId =
      views.autonomousStateSummary.activeChampionCandidateId ?? null;
    const rootIsolationStatus = await inspectRootIsolation({
      customStateRoot: tempStateRoot,
      defaultWorkspaceStateRoot,
    });
    const repairTraceabilityStatus = inspectRepairTraceability(
      ledgers.repairAttempts,
      mode,
    );
    const feedbackClosureStatus = inspectFeedbackClosure({
      localRecords,
      mutationBriefs,
      calibrationEvents: ledgers.calibrationEvents,
      confidenceEvents: ledgers.confidenceEvents,
      required: autoProcessCalibration,
    });
    const freshBootstrapPassed = localRecords.some(
      (record) =>
        record.selectionPhase === "bootstrap" &&
        record.bootstrapSource === "local_compatible_seed" &&
        (record.eligibility?.bootstrapEligible === true ||
          record.eligibility?.autoSelectionEligible === true),
    );
    const multiIterationPassed =
      iterationRun.countCompleted === count &&
      iterationRun.countFailed === 0 &&
      iterationRun.deadlineBreaches.length === 0 &&
      localRecords.length >= count &&
      activeChampionCandidateId != null;
    const calibrationQueuePassed = autoProcessCalibration
      ? ledgers.calibrationEvents.some(
          (event) => event.eventKind === "calibration_candidate_added",
        ) &&
        ledgers.calibrationEvents.some(
          (event) => event.eventKind === "local_tv_divergence_measured",
        ) &&
        ledgers.confidenceEvents.length > 0
      : ledgers.calibrationEvents.some(
          (event) =>
            event.eventKind === "calibration_candidate_added" &&
            event.queueState === "queued",
        );
    const scoreFeedbackPassed =
      autoProcessCalibration ? feedbackClosureStatus.status === "passed" : true;
    const warnings = [
      ...validation.issues
        .filter((issue) => issue.severity === "warning")
        .map((issue) => `${issue.scope}: ${issue.message}`),
      ...indexVerification.issues
        .filter((issue) => issue.severity === "warning")
        .map((issue) => `${issue.scope}: ${issue.message}`),
    ];
    if (!validation.ok) {
      warnings.push(`Ledger validation failed with ${validation.errorCount} errors.`);
    }
    if (!indexVerification.ok) {
      warnings.push(
        `Index verification failed with ${indexVerification.issues.length} issues.`,
      );
    }

    result = {
      generatedAt: new Date().toISOString(),
      evaluated: true,
      passed:
        freshBootstrapPassed &&
        multiIterationPassed &&
        rootIsolationStatus.status === "passed" &&
        repairTraceabilityStatus.status === "passed" &&
        calibrationQueuePassed &&
        scoreFeedbackPassed &&
        validation.ok &&
        indexVerification.ok,
      mode,
      countRequested: count,
      countCompleted: iterationRun.countCompleted,
      countFailed: iterationRun.countFailed,
      activeChampionCandidateId,
      freshBootstrapPassed,
      multiIterationPassed,
      rootIsolationPassed: rootIsolationStatus.status === "passed",
      repairTraceabilityPassed: repairTraceabilityStatus.status === "passed",
      calibrationQueuePassed,
      scoreFeedbackPassed,
      feedbackClosureRequired: autoProcessCalibration,
      calibrationMode: autoProcessCalibration ? calibrationMode : "queue_only",
      ledgerValidationPassed: validation.ok,
      indexVerificationPassed: indexVerification.ok,
      rootIsolationStatus,
      repairTraceabilityStatus,
      feedbackClosureStatus,
      evidence: {
        tempWorkspaceRoot: keepTempRoot ? tempWorkspaceRoot : null,
        tempStateRoot: keepTempRoot ? tempStateRoot : null,
        localEvaluationCount: localRecords.length,
        headEventCount: ledgers.headEvents.length,
        archiveEventCount: ledgers.archiveEvents.length,
        calibrationEventCount: ledgers.calibrationEvents.length,
        mutationBriefCount: mutationBriefs.length,
        problemEventCount: ledgers.problemEvents.length,
        repairAttemptCount: ledgers.repairAttempts.length,
        deadlineBreachCount: iterationRun.deadlineBreaches.length,
      },
      warnings,
    };
    if (persistToState) {
      await writeStage6ReadinessView(input.env.stateRoot, result);
    }
    await input.monitor?.log("stage6.gate.done", "Stage 6 readiness gate completed", {
      passed: result.passed,
      activeChampionCandidateId: result.activeChampionCandidateId,
    });
    return result;
  } finally {
    if (!keepTempRoot) {
      await rm(tempWorkspaceRoot, { recursive: true, force: true });
      await rm(tempStateRoot, { recursive: true, force: true });
    } else if (result) {
      await writeStage6ReadinessView(tempStateRoot, result);
    }
  }
}

export async function writeStage6ReadinessView(
  stateRoot: string,
  result: Stage6ReadinessResult,
): Promise<void> {
  await writeJson(resolveKnowledgePaths(stateRoot).stage6ReadinessPath, result);
}

function createDeterministicStage6LlmClient(seedPine: string): MutationLlmClient {
  let mutationCount = 0;
  let repairCount = 0;
  return {
    async generateMutation(input) {
      assertNotAborted(input.signal);
      mutationCount += 1;
      if (mutationCount === 1) {
        return buildRecoverableDeterministicMutationResponse(
          input.baselinePine,
          mutationCount,
        );
      }
      return buildDeterministicMutationResponse(input.baselinePine, mutationCount);
    },
    async generateConditionAblation(input) {
      assertNotAborted(input.signal);
      return buildDeterministicMutationResponse(input.candidatePine, mutationCount + 10);
    },
    async repairMutation(input) {
      assertNotAborted(input.signal);
      repairCount += 1;
      const source =
        looksLikePineSource(input.candidatePine) &&
        input.candidatePine.includes("useSupertrendFilter")
          ? input.candidatePine
          : seedPine;
      return buildDeterministicMutationResponse(source, repairCount + 100);
    },
  };
}

function buildDeterministicMutationResponse(seedPine: string, index: number): string {
  const parsedSpec = afStrategySpecFromPine(seedPine);
  const strategySpec = {
    ...(parsedSpec.spec ?? buildStage6FallbackSpec(index)),
    name: `AF Stage6 Deterministic ${index}`,
  };
  return JSON.stringify({
    candidateSummary: `Stage 6 deterministic AF mutation ${index}`,
    nextMutationHints: [
      "preserve local AF compatibility",
      "continue beyond bootstrap while retaining calibration feedback",
    ],
    pineScript: renderAfStrategySpecToPine(strategySpec),
    strategySpec,
    specPatch: {
      version: "af-spec-patch/v1",
      summary: `Derive deterministic Stage 6 spec mutation ${index}.`,
      operations: [
        {
          path: "/entry",
          after: strategySpec.entry,
          reason: "Keep deterministic readiness mutations under the editable AF entry spec.",
        },
      ],
    },
    inventory: [
      {
        conditionId: "af-exhaustion-entry",
        role: "entry",
        summary: "AF exhaustion entry ladder retained from the seed scaffold",
        pineLineHints: [1],
      },
      {
        conditionId: "af-risk-exit",
        role: "exit",
        summary: "AF bearish risk-off exit retained for deterministic verification",
        pineLineHints: [1],
      },
    ],
  });
}

function buildRecoverableDeterministicMutationResponse(
  seedPine: string,
  index: number,
): string {
  const pineScript = seedPine.replace(
    /strategy\((['"])(.*?)\1/,
    `strategy("AF Stage6 Recoverable ${index}"`,
  );
  return JSON.stringify({
    summary: `Stage 6 recoverable schema mutation ${index}`,
    hints: ["exercise local schema recovery before local evaluation"],
    pine: pineScript,
    conditions: [
      {
        conditionId: "af-exhaustion-entry",
        role: "entry",
        summary: "AF exhaustion entry ladder retained from the current baseline",
        pineLineHints: [1],
      },
    ],
  });
}

function looksLikePineSource(value: string): boolean {
  const trimmed = value.trimStart();
  return trimmed.startsWith("//@version=") || trimmed.startsWith("strategy(");
}

function buildStage6FallbackSpec(index: number): AfStrategySpec {
  return {
    version: "af-spec/v1",
    name: `AF Stage6 Deterministic ${index}`,
    event: {
      source: "event_floor",
      L1: 8,
      L2: 12,
      L3: 15,
      confirmBars: 2,
      eventFloorBars: 5,
      eventWindowBars: 10,
    },
    regime: {
      trendMode: "Balanced",
      useSupertrendFilter: true,
      riskOffRsi: 44,
      maxExtPct: 5.5,
    },
    entry: {
      primaryTrigger: "bull_event",
      cooldownBars: 1,
      allowBearRebound: true,
      applyFilterToB1: false,
    },
    slot: {
      slotPct: 12,
      maxSlots: 14,
      useReplacement: true,
      replaceMinRank: 3,
      replaceIfPnlBelow: -4,
    },
    exit: {
      weakRangeExit: true,
      maxHoldBars: 18,
      closeAllOnBearConfRiskOff: true,
      resetOnL3: false,
    },
  };
}

async function resolveRealLlmClient(
  factory: ((env: RuntimeEnvironment) => Promise<MutationLlmClient>) | undefined,
  env: RuntimeEnvironment,
): Promise<MutationLlmClient> {
  if (!factory) {
    throw new Error("real-llm Stage 6 readiness mode requires an LLM client factory.");
  }
  return factory(env);
}

async function readStage6Ledgers(stateRoot: string) {
  return {
    experiments: await readExperimentRecords(stateRoot),
    headEvents: await readHeadEventRecords(stateRoot),
    archiveEvents: await readArchiveEventRecords(stateRoot),
    calibrationEvents: await readCalibrationEventRecords(stateRoot),
    confidenceEvents: await readLocalConfidenceEventRecords(stateRoot),
    problemEvents: await readProblemEventRecords(stateRoot),
    repairAttempts: await readRepairAttemptRecords(stateRoot),
  };
}

async function readMutationBriefRecords(stateRoot: string): Promise<MutationBriefRecord[]> {
  return readJsonl<MutationBriefRecord>(resolveKnowledgePaths(stateRoot).mutationBriefsPath);
}

async function inspectRootIsolation(input: {
  customStateRoot: string;
  defaultWorkspaceStateRoot: string;
}): Promise<Stage6ReadinessResult["rootIsolationStatus"]> {
  const customContextExists = await pathExists(
    resolveKnowledgePaths(input.customStateRoot).qqqTwoHourContextPath,
  );
  const defaultWorkspaceStateHasArtifacts = await hasStateArtifacts(
    input.defaultWorkspaceStateRoot,
  );
  return {
    status:
      customContextExists && !defaultWorkspaceStateHasArtifacts ? "passed" : "failed",
    customStateRoot: input.customStateRoot,
    defaultWorkspaceStateRoot: input.defaultWorkspaceStateRoot,
    customContextExists,
    defaultWorkspaceStateHasArtifacts,
  };
}

function inspectRepairTraceability(
  repairAttempts: Awaited<ReturnType<typeof readRepairAttemptRecords>>,
  mode: Stage6ReadinessMode,
): Stage6ReadinessResult["repairTraceabilityStatus"] {
  const successfulRepairs = repairAttempts.filter(
    (attempt) => attempt.result === "success",
  );
  const successfulRepairsWithoutCandidate = successfulRepairs.filter(
    (attempt) => !attempt.repairedCandidateId,
  );
  const deterministicProofSatisfied =
    mode !== "deterministic" || successfulRepairs.length > 0;
  return {
    status:
      deterministicProofSatisfied && successfulRepairsWithoutCandidate.length === 0
        ? "passed"
        : "failed",
    successfulRepairCount: successfulRepairs.length,
    successfulRepairsWithoutCandidateCount:
      successfulRepairsWithoutCandidate.length,
  };
}

function inspectFeedbackClosure(input: {
  localRecords: ReturnType<typeof selectLocalEvaluationRecords>;
  mutationBriefs: MutationBriefRecord[];
  calibrationEvents: Awaited<ReturnType<typeof readCalibrationEventRecords>>;
  confidenceEvents: Awaited<ReturnType<typeof readLocalConfidenceEventRecords>>;
  required: boolean;
}): Stage6ReadinessResult["feedbackClosureStatus"] {
  const scoreBreakdownFeedbackObserved = input.localRecords.some((record) => {
    const breakdown = record.autoSelectionBreakdown;
    return (
      (breakdown?.localConfidenceBonus ?? 0) !== 0 ||
      (breakdown?.divergencePenalty ?? 0) !== 0
    );
  });
  const promptFeedbackObserved = input.mutationBriefs.some((record) => {
    const summary = record.brief.candidateBehaviorChangeSummary;
    return (
      summary?.influencedBy?.includes("calibration_divergence") ||
      Boolean(record.brief.recentCalibrationSummary?.trim()) ||
      Boolean(record.brief.confidenceAdjustmentSummary?.trim())
    );
  });
  const divergenceCount = input.calibrationEvents.filter(
    (event) => event.eventKind === "local_tv_divergence_measured",
  ).length;
  if (!input.required) {
    return {
      status: "passed",
      required: false,
      promptFeedbackObserved,
      scoreBreakdownFeedbackObserved,
      divergenceCount,
      confidenceUpdateCount: input.confidenceEvents.length,
    };
  }
  return {
    status:
      divergenceCount > 0 &&
      input.confidenceEvents.length > 0 &&
      promptFeedbackObserved &&
      scoreBreakdownFeedbackObserved
        ? "passed"
        : "failed",
    required: true,
    promptFeedbackObserved,
    scoreBreakdownFeedbackObserved,
    divergenceCount,
    confidenceUpdateCount: input.confidenceEvents.length,
  };
}

async function hasStateArtifacts(stateRoot: string): Promise<boolean> {
  const paths = resolveKnowledgePaths(stateRoot);
  return (
    (await pathExists(paths.qqqTwoHourContextPath)) ||
    (await directoryContainsFile(paths.ledgerDir)) ||
    (await directoryContainsFile(paths.viewsDir))
  );
}

async function directoryContainsFile(dirPath: string): Promise<boolean> {
  try {
    const entries = await readdir(dirPath, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = path.join(dirPath, entry.name);
      if (entry.isFile()) {
        return true;
      }
      if (entry.isDirectory() && (await directoryContainsFile(entryPath))) {
        return true;
      }
    }
    return false;
  } catch {
    return false;
  }
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await readFile(filePath);
    return true;
  } catch {
    return false;
  }
}

function assertNotAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw new Error("Stage 6 deterministic LLM request was aborted.");
  }
}
