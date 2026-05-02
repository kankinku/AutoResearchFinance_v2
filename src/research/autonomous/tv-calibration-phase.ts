import { readFile } from "node:fs/promises";

import { type RuntimeEnvironment } from "../../cli/runtime-config.js";
import {
  type CalibrationEventRecord,
  type AutonomousExperimentRecord,
  type LocalConfidenceEventRecord,
  type VerifiedPromotionEvidence,
  type WalkForwardEvaluation,
} from "../../contracts/autonomous.js";
import {
  type ObjectiveConfig,
  type ExperimentRecord,
  type BacktestMetrics,
} from "../../contracts/types.js";
import { parseAfStrategyConfig } from "../../automation/local-backtest/af-config.js";
import { afStrategySpecFromPine } from "../../strategy-spec/to-af-config.js";
import { type PineEvaluationExecutor } from "../../automation/common/executor.js";
import { validateArtifactBundle } from "../../evaluation/artifact-validation.js";
import {
  buildVerifiedPromotionScore,
  buildTvCalibrationStatus,
  buildTvFailureDecision,
  getAutonomousSelectionPolicyVersion,
  getObjectivePolicyVersion,
} from "../../evaluation/autonomous-scoring.js";
import {
  buildWalkForwardEvaluationFromFoldMetrics,
  evaluateWalkForward,
} from "../../evaluation/walkforward.js";
import {
  appendCalibrationEventRecord,
  appendExperimentRecord,
} from "../../state/jsonl-store.js";
import { selectLocalEvaluationRecords } from "../../state/autonomous-state.js";
import { classifyTradingViewRuntimeFailure } from "../verification-fallback.js";
import {
  appendDivergenceEvent,
  appendLocalConfidenceUpdate,
  buildLocalTvParity,
  resolveStructureFamilyHash,
} from "./divergence-update-phase.js";
import { autonomousExperimentSchema } from "../../contracts/autonomous.js";
import { createCandidateId, sha256Json } from "../../utils/fs.js";
import { selectPendingCalibrationCandidateIds } from "./tv-calibration-queue-phase.js";

interface MonitorLike {
  log: (
    event: string,
    message: string,
    details?: Record<string, unknown>,
  ) => Promise<void>;
}

export async function enqueueCalibrationCandidate(input: {
  stateRoot: string;
  runId: string;
  iteration: number;
  localRecord: AutonomousExperimentRecord;
  reason: string;
  tvHealthAtQueueTime?: "healthy" | "unavailable" | "degraded";
}): Promise<void> {
  await appendCalibrationEventRecord(input.stateRoot, {
    calibrationEventId: createCandidateId("calibration"),
    runId: input.runId,
    iteration: input.iteration,
    eventKind: "calibration_candidate_added",
    candidateId: input.localRecord.candidateId,
    structureFamilyHash: resolveStructureFamilyHash({
      noveltyFingerprint: input.localRecord.noveltyFingerprint,
      candidateId: input.localRecord.candidateId,
      conditionInventory: input.localRecord.conditionInventory,
    }),
    fingerprintFamily: input.localRecord.noveltyFingerprint?.fingerprintFamily ?? null,
    queueState: "queued",
    queueReason: input.reason,
    tvHealthAtQueueTime: input.tvHealthAtQueueTime ?? "healthy",
    localConfidenceBefore: input.localRecord.localConfidence,
    localConfidenceAfter: input.localRecord.localConfidence,
    parity: null,
    tvDecision: null,
  });
}

export function selectPendingCalibrationCandidates(input: {
  events: CalibrationEventRecord[];
  experiments: ExperimentRecord[];
}): string[] {
  return selectPendingCalibrationCandidateIds(input);
}

export async function processTvCalibrationQueue(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  objective: ObjectiveConfig;
  env: RuntimeEnvironment;
  experiments: ExperimentRecord[];
  calibrationEvents: CalibrationEventRecord[];
  confidenceEvents?: LocalConfidenceEventRecord[];
  executorFactory?: () => PineEvaluationExecutor;
  maxCandidates?: number;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}): Promise<{
  processedCandidateIds: string[];
}> {
  const pendingCandidates = selectPendingCalibrationCandidates({
    events: input.calibrationEvents,
    experiments: input.experiments,
  }).slice(0, input.maxCandidates ?? 5);
  const localRecords = selectLocalEvaluationRecords(input.experiments);
  const confidenceEvents = [...(input.confidenceEvents ?? [])];
  const processedCandidateIds: string[] = [];

  for (const candidateId of pendingCandidates) {
    const localRecord = [...localRecords]
      .filter((record) => record.candidateId === candidateId)
      .sort((left, right) => right.iteration - left.iteration)[0];
    if (!localRecord) {
      throwIfAborted(input.signal);
      await appendCalibrationQueueStatusEvent(input.stateRoot, {
        runId: input.runId,
        iteration: 1,
        candidateId,
        localRecord: null,
        queueState: "skipped",
        queueReason: "candidate_not_calibration_eligible",
        tvHealthAtQueueTime: "healthy",
      });
      processedCandidateIds.push(candidateId);
      continue;
    }

    if (!localRecord.candidatePath) {
      throwIfAborted(input.signal);
      await appendCalibrationQueueStatusEvent(input.stateRoot, {
        runId: input.runId,
        iteration: localRecord.iteration,
        candidateId,
        localRecord,
        queueState: "skipped",
        queueReason: "candidate_source_missing",
        tvHealthAtQueueTime: "healthy",
      });
      processedCandidateIds.push(candidateId);
      continue;
    }

    let candidateSource: string;
    try {
      candidateSource = await readFile(localRecord.candidatePath, "utf8");
    } catch {
      throwIfAborted(input.signal);
      await appendCalibrationQueueStatusEvent(input.stateRoot, {
        runId: input.runId,
        iteration: localRecord.iteration,
        candidateId,
        localRecord,
        queueState: "skipped",
        queueReason: "candidate_source_missing",
        tvHealthAtQueueTime: "healthy",
      });
      processedCandidateIds.push(candidateId);
      continue;
    }

    if (input.env.tvCalibrationMode === "mock-recovered") {
      const mockTvMetrics = buildMockRecoveredMetrics(localRecord.testerMetrics);
      const parity = buildLocalTvParity({
        localMetrics: localRecord.testerMetrics,
        tvMetrics: mockTvMetrics,
        localTrades: localRecord.artifactBundle?.trades ?? [],
        tvTrades: localRecord.artifactBundle?.trades ?? [],
        localEventTrace: readEventTrace(localRecord.artifactBundle?.state),
        tvEventTrace: readEventTrace(localRecord.artifactBundle?.state),
      });
      const localConfidenceAfter =
        parity.status === "matched"
          ? 1
          : parity.status === "minor_drift"
            ? 0.8
            : 0.6;
      const tvCalibrationStatus = buildTvCalibrationStatus({
        decision: "tv_verified",
        parityMatched: parity.status === "matched",
      });
      const promotionEvidence = await buildTvPromotionEvidence({
        workspaceRoot: input.workspaceRoot,
        stateRoot: input.stateRoot,
        objective: input.objective,
        candidateSource,
        localRecord,
        tvMetrics: mockTvMetrics,
        tvCalibrationStatus,
        localTvParity: parity,
        referenceExperiments: input.experiments,
      });
      throwIfAborted(input.signal);
      const tvRecord = await appendTvRecord(input.stateRoot, {
        localRecord,
        runId: input.runId,
        iteration: localRecord.iteration,
        decision: "tv_verified",
        status: "verified",
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "mock-recovered calibration" },
        artifactValidation: {
          hasMetrics: true,
          hasNetProfit: true,
          hasTotalTrades: true,
          hasMaxDrawdown: true,
          hasProfitFactor: true,
          hasWinRate: true,
          hasTrades: true,
          hasEquitySummary: true,
          hasRawReport: true,
          verificationReady: true,
          promotionReady: true,
          completenessScore: 1,
          missingFields: [],
          missingForVerification: [],
          missingForPromotion: [],
          parseWarnings: [],
          parserVersion: "mock-recovered/v1",
        },
        testerMetrics: mockTvMetrics,
        artifactBundle: {
          strategy: mockTvMetrics,
          trades: localRecord.artifactBundle?.trades ?? [],
          equity: {
            available: true,
            unavailableReason: null,
            pointsAvailable: false,
            pointCount: 0,
            finalEquity: null,
            maxDrawdownPercent: mockTvMetrics?.maxStrategyDrawdownPercent ?? null,
            points: [],
          },
          rawReportHash: "mock-recovered-report",
          state: {
            engine: "mock-recovered",
          },
        },
        localTvParity: parity,
        localConfidence: localConfidenceAfter,
        tvCalibrationStatus,
        walkForwardEvaluation: promotionEvidence.walkForwardEvaluation,
        verifiedPromotion: promotionEvidence.verifiedPromotion,
      });
      throwIfAborted(input.signal);
      const divergenceEvent = await appendDivergenceEvent({
        stateRoot: input.stateRoot,
        runId: input.runId,
        iteration: localRecord.iteration,
        localRecord,
        tvRecord,
        localConfidenceAfter,
      });
      throwIfAborted(input.signal);
      const confidenceEvent = await appendLocalConfidenceUpdate({
        stateRoot: input.stateRoot,
        runId: input.runId,
        iteration: localRecord.iteration,
        candidateId,
        structureFamilyHash:
          divergenceEvent.structureFamilyHash ??
          resolveStructureFamilyHash({
            noveltyFingerprint: localRecord.noveltyFingerprint,
            candidateId: localRecord.candidateId,
            conditionInventory: localRecord.conditionInventory,
          }),
        sourceCalibrationEventId: divergenceEvent.calibrationEventId ?? null,
        parityStatus: parity.status,
        previousConfidenceEvents: confidenceEvents,
      });
      if (confidenceEvent) {
        confidenceEvents.push(confidenceEvent);
      }
      processedCandidateIds.push(candidateId);
      continue;
    }

    if (!input.executorFactory) {
      throwIfAborted(input.signal);
      await appendCalibrationQueueStatusEvent(input.stateRoot, {
        runId: input.runId,
        iteration: localRecord.iteration,
        candidateId,
        localRecord,
        queueState: "failed",
        queueReason: "executor_unavailable",
        tvHealthAtQueueTime: "degraded",
      });
      processedCandidateIds.push(candidateId);
      continue;
    }

    const executor = input.executorFactory();
    try {
      const chartTarget = {
        symbol: input.env.chartSymbol,
        timeframe: input.env.chartTimeframe,
        chartType: input.env.chartType,
      };
      await executor.prepareChart(chartTarget);
      await executor.updateStrategySource(candidateSource);
      const compile = await executor.compileStrategy();
      throwIfAborted(input.signal);
      if (!compile.ok) {
        await appendTvRecord(input.stateRoot, {
          localRecord,
          runId: input.runId,
          iteration: localRecord.iteration,
          decision: "tv_portability_failure",
          status: "compile_failed",
          compile,
          apply: null,
          artifactValidation: null,
          testerMetrics: null,
          artifactBundle: null,
          localTvParity: null,
          localConfidence: 0.5,
          tvCalibrationStatus: buildTvCalibrationStatus({
            decision: "tv_portability_failure",
          }),
        });
        await appendCalibrationQueueStatusEvent(input.stateRoot, {
          runId: input.runId,
          iteration: localRecord.iteration,
          candidateId,
          localRecord,
          queueState: "skipped",
          queueReason: "unsupported_target",
          tvHealthAtQueueTime: "healthy",
        });
        processedCandidateIds.push(candidateId);
        continue;
      }

      const apply = await executor.applyStrategy({
        expectedStudyTitle: localRecord.studyTitle,
      });
      throwIfAborted(input.signal);
      if (!apply.ok) {
        await appendTvRecord(input.stateRoot, {
          localRecord,
          runId: input.runId,
          iteration: localRecord.iteration,
          decision: "tv_portability_failure",
          status: "apply_failed",
          compile,
          apply,
          artifactValidation: null,
          testerMetrics: null,
          artifactBundle: null,
          localTvParity: null,
          localConfidence: 0.5,
          tvCalibrationStatus: buildTvCalibrationStatus({
            decision: "tv_portability_failure",
          }),
        });
        await appendCalibrationQueueStatusEvent(input.stateRoot, {
          runId: input.runId,
          iteration: localRecord.iteration,
          candidateId,
          localRecord,
          queueState: "skipped",
          queueReason: "unsupported_target",
          tvHealthAtQueueTime: "healthy",
        });
        processedCandidateIds.push(candidateId);
        continue;
      }

      const artifactBundle = await executor.readArtifactBundle({
        expectedStudyTitle: localRecord.studyTitle,
        maxTrades: input.env.maxTrades,
      });
      throwIfAborted(input.signal);
      const artifactValidation = validateArtifactBundle({
        artifactBundle,
        executorCapability: executor.getCapability(),
      });
      if (!artifactValidation.verificationReady) {
        throwIfAborted(input.signal);
        await appendTvRecord(input.stateRoot, {
          localRecord,
          runId: input.runId,
          iteration: localRecord.iteration,
          decision: "tv_artifact_failure",
          status: "artifact_failed",
          compile,
          apply,
          artifactValidation,
          testerMetrics: artifactBundle.strategy ?? null,
          artifactBundle,
          localTvParity: null,
          localConfidence: 0.6,
          tvCalibrationStatus: buildTvCalibrationStatus({
            decision: "tv_artifact_failure",
          }),
        });
        await appendCalibrationQueueStatusEvent(input.stateRoot, {
          runId: input.runId,
          iteration: localRecord.iteration,
          candidateId,
          localRecord,
          queueState: "skipped",
          queueReason: "candidate_not_calibration_eligible",
          tvHealthAtQueueTime: "healthy",
        });
        processedCandidateIds.push(candidateId);
        continue;
      }

      const parity = buildLocalTvParity({
        localMetrics: localRecord.testerMetrics,
        tvMetrics: artifactBundle.strategy,
        localTrades: localRecord.artifactBundle?.trades ?? [],
        tvTrades: artifactBundle.trades,
        localEventTrace: readEventTrace(localRecord.artifactBundle?.state),
        tvEventTrace: readEventTrace(artifactBundle.state),
      });
      const localConfidenceAfter =
        parity.status === "matched"
          ? 1
          : parity.status === "minor_drift"
            ? 0.8
            : 0.6;
      const tvCalibrationStatus = buildTvCalibrationStatus({
        decision: "tv_verified",
        parityMatched: parity.status === "matched",
      });
      const promotionEvidence = await buildTvPromotionEvidence({
        workspaceRoot: input.workspaceRoot,
        stateRoot: input.stateRoot,
        objective: input.objective,
        candidateSource,
        localRecord,
        tvMetrics: artifactBundle.strategy ?? null,
        tvCalibrationStatus,
        localTvParity: parity,
        referenceExperiments: input.experiments,
      });
      throwIfAborted(input.signal);
      const tvRecord = await appendTvRecord(input.stateRoot, {
        localRecord,
        runId: input.runId,
        iteration: localRecord.iteration,
        decision: "tv_verified",
        status: "verified",
        compile,
        apply,
        artifactValidation,
        testerMetrics: artifactBundle.strategy ?? null,
        artifactBundle,
        localTvParity: parity,
        localConfidence: localConfidenceAfter,
        tvCalibrationStatus,
        walkForwardEvaluation: promotionEvidence.walkForwardEvaluation,
        verifiedPromotion: promotionEvidence.verifiedPromotion,
      });
      throwIfAborted(input.signal);
      const divergenceEvent = await appendDivergenceEvent({
        stateRoot: input.stateRoot,
        runId: input.runId,
        iteration: localRecord.iteration,
        localRecord,
        tvRecord,
        localConfidenceAfter,
      });
      throwIfAborted(input.signal);
      const confidenceEvent = await appendLocalConfidenceUpdate({
        stateRoot: input.stateRoot,
        runId: input.runId,
        iteration: localRecord.iteration,
        candidateId,
        structureFamilyHash:
          divergenceEvent.structureFamilyHash ??
          resolveStructureFamilyHash({
            noveltyFingerprint: localRecord.noveltyFingerprint,
            candidateId: localRecord.candidateId,
            conditionInventory: localRecord.conditionInventory,
          }),
        sourceCalibrationEventId: divergenceEvent.calibrationEventId ?? null,
        parityStatus: parity.status,
        previousConfidenceEvents: confidenceEvents,
      });
      if (confidenceEvent) {
        confidenceEvents.push(confidenceEvent);
      }
      processedCandidateIds.push(candidateId);
    } catch (error) {
      throwIfAborted(input.signal);
      const failureKind = classifyTradingViewRuntimeFailure(error);
      const decision = buildTvFailureDecision({
        failureKind,
      });
      await appendTvRecord(input.stateRoot, {
        localRecord,
        runId: input.runId,
        iteration: localRecord.iteration,
        decision,
        status: "runtime_failed",
        compile: null,
        apply: null,
        artifactValidation: null,
        testerMetrics: null,
        artifactBundle: null,
        localTvParity: null,
        localConfidence: localRecord.localConfidence ?? 1,
        tvCalibrationStatus: buildTvCalibrationStatus({
          decision,
        }),
      });
      await appendCalibrationQueueStatusEvent(input.stateRoot, {
        runId: input.runId,
        iteration: localRecord.iteration,
        candidateId,
        localRecord,
        queueState: "failed",
        queueReason: "executor_unavailable",
        tvHealthAtQueueTime: "degraded",
      });
      await input.monitor?.log(
        "autonomous.tv_calibration_failure",
        "TradingView calibration failed",
        {
          candidateId,
          decision,
          detail: error instanceof Error ? error.message : String(error),
        },
      );
      processedCandidateIds.push(candidateId);
    } finally {
      await executor.close?.();
    }
  }

  return {
    processedCandidateIds,
  };
}

async function appendCalibrationQueueStatusEvent(
  stateRoot: string,
  input: {
    runId: string;
    iteration: number;
    candidateId: string;
    localRecord: AutonomousExperimentRecord | null;
    queueState: "processed" | "skipped" | "failed";
    queueReason:
      | "candidate_source_missing"
      | "local_artifact_missing"
      | "candidate_not_calibration_eligible"
      | "executor_unavailable"
      | "unsupported_target";
    tvHealthAtQueueTime: "healthy" | "unavailable" | "degraded";
  },
) {
  return appendCalibrationEventRecord(stateRoot, {
    calibrationEventId: createCandidateId("calibration"),
    runId: input.runId,
    iteration: input.iteration,
    eventKind: "calibration_queue_status_updated",
    candidateId: input.candidateId,
    structureFamilyHash: resolveStructureFamilyHash({
      noveltyFingerprint: input.localRecord?.noveltyFingerprint,
      candidateId: input.localRecord?.candidateId ?? input.candidateId,
      conditionInventory: input.localRecord?.conditionInventory,
    }),
    fingerprintFamily: input.localRecord?.noveltyFingerprint?.fingerprintFamily ?? null,
    queueState: input.queueState,
    queueReason: input.queueReason,
    tvHealthAtQueueTime: input.tvHealthAtQueueTime,
    localConfidenceBefore: input.localRecord?.localConfidence ?? null,
    localConfidenceAfter: input.localRecord?.localConfidence ?? null,
    parity: null,
    tvDecision: null,
  });
}


function buildMockRecoveredMetrics(
  localMetrics: BacktestMetrics | null | undefined,
): BacktestMetrics | null {
  if (!localMetrics) {
    return null;
  }

  return {
    ...localMetrics,
    totalTrades: Math.max(0, localMetrics.totalTrades - 1),
    postFeeNetProfitPercent: localMetrics.postFeeNetProfitPercent - 0.8,
    maxStrategyDrawdownPercent: localMetrics.maxStrategyDrawdownPercent + 0.7,
    profitFactor: Math.max(0, localMetrics.profitFactor - 0.05),
  };
}

function readEventTrace(state: Record<string, unknown> | null | undefined) {
  const trace = state?.eventTrace;
  return Array.isArray(trace)
    ? trace.filter(
        (entry): entry is Record<string, unknown> =>
          typeof entry === "object" && entry !== null && !Array.isArray(entry),
      )
    : [];
}

async function buildTvPromotionEvidence(input: {
  workspaceRoot: string;
  stateRoot: string;
  objective: ObjectiveConfig;
  candidateSource: string;
  localRecord: AutonomousExperimentRecord;
  tvMetrics: BacktestMetrics | null | undefined;
  tvCalibrationStatus: AutonomousExperimentRecord["tvCalibrationStatus"];
  localTvParity: AutonomousExperimentRecord["localTvParity"];
  referenceExperiments: ExperimentRecord[];
}): Promise<{
  walkForwardEvaluation: WalkForwardEvaluation;
  verifiedPromotion: VerifiedPromotionEvidence;
}> {
  const parsedConfig = parseAfStrategyConfig(input.candidateSource);
  const config = parsedConfig.issues.length === 0 ? parsedConfig.config : null;
  const strategySpec = afStrategySpecFromPine(input.candidateSource).spec;
  const walkForwardEvaluation = await evaluateWalkForward({
    workspaceRoot: input.workspaceRoot,
    stateRoot: input.stateRoot,
    pineScript: input.candidateSource,
    strategySpec,
    objective: input.objective,
  }).catch(() =>
    buildWalkForwardEvaluationFromFoldMetrics({
      foldMetrics: [],
      foldCount: 5,
      embargoBars: 5,
    }),
  );
  const verifiedPromotion = buildVerifiedPromotionScore({
    localMetrics: input.localRecord.testerMetrics,
    tvMetrics: input.tvMetrics,
    localCandidateHash: input.localRecord.candidateHash,
    tvCandidateHash: input.localRecord.candidateHash,
    tvCalibrationStatus: input.tvCalibrationStatus,
    localTvParity: input.localTvParity,
    walkForwardEvaluation,
    config,
    referenceExperiments: input.referenceExperiments,
  });

  return {
    walkForwardEvaluation,
    verifiedPromotion,
  };
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (!signal?.aborted) {
    return;
  }
  const reason = signal.reason;
  throw reason instanceof Error ? reason : new Error("Autonomous phase was aborted.");
}

async function appendTvRecord(
  stateRoot: string,
  input: {
  runId: string;
  iteration: number;
  localRecord: AutonomousExperimentRecord;
  decision: string;
  status: string;
  compile: Record<string, unknown> | null;
  apply: Record<string, unknown> | null;
  artifactValidation: Record<string, unknown> | null;
  testerMetrics: Record<string, unknown> | null;
  artifactBundle: Record<string, unknown> | null;
  localTvParity: Record<string, unknown> | null;
  localConfidence: number;
  tvCalibrationStatus: AutonomousExperimentRecord["tvCalibrationStatus"];
  walkForwardEvaluation?: WalkForwardEvaluation | null;
  verifiedPromotion?: VerifiedPromotionEvidence | null;
},
) {
  const normalized = await appendExperimentRecord(
    stateRoot,
    {
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.localRecord.candidateId,
      parentCandidateId: input.localRecord.parentCandidateId,
      branchId: input.localRecord.branchId,
      acceptedHeadCandidateId: null,
      baselineCandidateId: null,
      candidatePath: input.localRecord.candidatePath,
      candidateHash: input.localRecord.candidateHash,
      studyTitle: input.localRecord.studyTitle,
      candidateScore:
        input.verifiedPromotion?.score ??
        input.localRecord.localFrontierScore ??
        input.localRecord.autoSelectionScore,
      decision: input.decision,
      status: input.status,
      compile: input.compile ?? undefined,
      apply: input.apply ?? undefined,
      testerMetrics: input.testerMetrics ?? undefined,
      artifactBundle: input.artifactBundle ?? undefined,
      conditionInventory: input.localRecord.conditionInventory,
      mutationBriefSummary: input.localRecord.mutationBriefSummary,
      mutationProvenance: input.localRecord.mutationProvenance,
      artifactValidation: input.artifactValidation ?? undefined,
      localTvParity: input.localTvParity ?? undefined,
      recordKind: "tv_verification",
      executorRole: "external_calibration",
      evidenceAuthority: "external_tv",
      evaluationMode: "tv_calibration",
      splitEvaluation: input.localRecord.splitEvaluation,
      noveltyFingerprint: input.localRecord.noveltyFingerprint,
      structureFamilyHash: input.localRecord.structureFamilyHash ?? null,
      fingerprintFamily: input.localRecord.fingerprintFamily ?? null,
      duplicateStatus: input.localRecord.duplicateStatus,
      localFrontierScore:
        input.localRecord.localFrontierScore ??
        input.localRecord.autoSelectionScore,
      autoSelectionScore:
        input.verifiedPromotion?.score ??
        input.localRecord.autoSelectionScore,
      autoSelectionBreakdown: input.localRecord.autoSelectionBreakdown,
      walkForwardEvaluation: input.walkForwardEvaluation ?? undefined,
      verifiedPromotionScore: input.verifiedPromotion?.score ?? null,
      verifiedPromotion: input.verifiedPromotion ?? undefined,
      objectivePolicyVersion: getObjectivePolicyVersion(),
      selectionPolicyVersion: getAutonomousSelectionPolicyVersion(),
      localConfidence: input.localConfidence,
      tvCalibrationStatus: input.tvCalibrationStatus,
      artifactPaths: input.localRecord.artifactPaths,
      recordMeta: {
        schemaVersion: "experiment/v3",
        recordHash: "",
        candidateHash: input.localRecord.candidateHash,
        baselineHash: input.localRecord.recordMeta?.baselineHash ?? null,
        artifactBundleHash: input.artifactBundle
          ? sha256Json(input.artifactBundle)
          : null,
        pipelineVersion: "af-autonomous-local-first/v3",
      },
    } as Parameters<typeof appendExperimentRecord>[1],
  );
  return autonomousExperimentSchema.parse(normalized);
}
