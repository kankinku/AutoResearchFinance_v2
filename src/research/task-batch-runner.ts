import path from "node:path";

import { type RuntimeEnvironment } from "../cli/runtime-config.js";
import {
  DEFAULT_RESEARCH_TARGET_ID,
  resolveTargetStateRoot,
} from "../config/target-registry.js";
import {
  type ArtifactValidationResult,
  type ConditionContribution,
  type DecisionCode,
  type EvaluationExecutorName,
  type ExecutorCapability,
  type ExperimentRecord,
  type FallbackEvaluation,
  type FinalAnalysisSummary,
  type MetricComparison,
  type MutationParseStatus,
  type PineAnalysisSummary,
  type PromotionStatus,
  type RecordEra,
  type SurfaceRecoveryAttempt,
  type TaskAnalysisSummary,
  type TaskBatchRecord,
  type TaskExecutionSummary,
  type TaskHypothesis,
  type TaskRecord,
  type VerificationFailureReason,
  type VerificationRuntimeFailureKind,
  type VerificationStatus,
} from "../contracts/types.js";
import { type PineEvaluationExecutor } from "../automation/common/executor.js";
import { type MutationLlmClient } from "../mutation/llm-client.js";
import { rebuildIndexes } from "../state/index-builder.js";
import {
  appendIncidentRecord,
  appendTaskBatchRecord,
  appendTaskRecord,
  readTaskBatchRecords,
} from "../state/jsonl-store.js";
import { createCandidateId } from "../utils/fs.js";
import { type CliMonitor } from "../cli/monitor.js";
import { runBatchResearchRefresh } from "./batch-research-refresh.js";
import { runSingleIteration } from "./iteration-runner.js";
import { initializeWorkspace } from "./workspace.js";

interface RunTaskBatchInput {
  workspaceRoot: string;
  stateRoot?: string;
  llmClient: MutationLlmClient;
  executor: PineEvaluationExecutor;
  executorName?: EvaluationExecutorName;
  promotionVerificationExecutorFactory?: () => PineEvaluationExecutor;
  promotionVerificationExecutorName?: EvaluationExecutorName | "none";
  taskCount: number;
  maxRuntimeFailures: number;
  runId: string;
  chartType?: string;
  maxTrades?: number;
  monitor?: CliMonitor;
  env?: RuntimeEnvironment;
  researchRefreshEveryTasks?: number;
  researchRefreshRunner?: typeof runBatchResearchRefresh;
  maxAutoRecoveryAttemptsPerTask?: number;
  fallbackLocalOnTvRuntimeFailure?: boolean;
  maxFallbacksPerBatch?: number;
  localFallbackExecutorFactory?: () => PineEvaluationExecutor;
  taskRunner?: typeof runSingleIteration;
  recoveryHooks?: TaskBatchRecoveryHooks;
}

interface TaskBatchRunResult {
  batchId: string;
  runId: string;
  targetTaskCount: number;
  completedTaskCount: number;
  runtimeFailureCount: number;
  status: "completed" | "stopped";
  stopReason: string | null;
  tasks: TaskRecord[];
}

export interface TaskBatchRecoveryOutcome {
  recovered: boolean;
  recoveryActions: string[];
  executor?: PineEvaluationExecutor;
}

export interface TaskBatchRecoveryContext {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  batchId: string;
  taskId: string;
  taskNumber: number;
  attempt: number;
  currentExecutor: PineEvaluationExecutor;
  error?: Error;
  decision?: DecisionCode;
  experiment?: ExperimentRecord;
  failureDetail?: string | null;
}

export interface TaskBatchRecoveryHooks {
  beforeBatch?(input: {
    workspaceRoot: string;
    stateRoot: string;
    runId: string;
    batchId: string;
    taskCount: number;
    currentExecutor: PineEvaluationExecutor;
  }): Promise<TaskBatchRecoveryOutcome | void>;
  onFailure?(input: TaskBatchRecoveryContext): Promise<TaskBatchRecoveryOutcome | void>;
}

const STALE_TASK_BATCH_MS = 5 * 60_000;

export async function reconcileStaleTaskBatches(
  stateRoot: string,
  staleAfterMs = STALE_TASK_BATCH_MS,
): Promise<number> {
  const records = await readTaskBatchRecords(stateRoot);
  const latestByBatchId = new Map<string, TaskBatchRecord>();
  for (const record of records) {
    const current = latestByBatchId.get(record.batchId);
    if (!current) {
      latestByBatchId.set(record.batchId, record);
      continue;
    }

    const currentRecordedAt = Date.parse(current.recordedAt ?? "");
    const nextRecordedAt = Date.parse(record.recordedAt ?? "");
    if (nextRecordedAt >= currentRecordedAt) {
      latestByBatchId.set(record.batchId, record);
    }
  }

  let reconciled = 0;
  const now = Date.now();
  for (const record of latestByBatchId.values()) {
    if (record.status !== "running") {
      continue;
    }

    const recordedAt = Date.parse(record.recordedAt ?? "");
    if (!Number.isFinite(recordedAt) || now - recordedAt < staleAfterMs) {
      continue;
    }

    await appendTaskBatchRecord(stateRoot, {
      runId: record.runId,
      batchId: record.batchId,
      targetTaskCount: record.targetTaskCount,
      completedTaskCount: record.completedTaskCount,
      runtimeFailureCount: record.runtimeFailureCount,
      maxRuntimeFailures: record.maxRuntimeFailures,
      status: "stopped",
      stopReason: "interrupted_or_stale",
    });
    reconciled += 1;
  }

  if (reconciled > 0) {
    await rebuildIndexes(stateRoot);
  }

  return reconciled;
}

export async function runTaskBatch(
  input: RunTaskBatchInput,
): Promise<TaskBatchRunResult> {
  const stateRoot =
    input.stateRoot ??
    resolveTargetStateRoot({
      workspaceRoot: input.workspaceRoot,
      targetId: process.env.AF_RESEARCH_TARGET_ID ?? DEFAULT_RESEARCH_TARGET_ID,
    });
  await initializeWorkspace({
    workspaceRoot: input.workspaceRoot,
    stateRoot,
  });

  await reconcileStaleTaskBatches(stateRoot);
  const batchId = createCandidateId("batch");
  const tasks: TaskRecord[] = [];
  let runtimeFailureCount = 0;
  let stopReason: string | null = null;
  let finalized = false;
  const researchRefreshEveryTasks = input.researchRefreshEveryTasks ?? 3;
  const researchRefreshRunner = input.researchRefreshRunner ?? runBatchResearchRefresh;
  const maxAutoRecoveryAttemptsPerTask = input.maxAutoRecoveryAttemptsPerTask ?? 1;
  let remainingFallbacks = input.maxFallbacksPerBatch ?? 5;
  const taskRunner = input.taskRunner ?? runSingleIteration;
  let activeExecutor = input.executor;

  const persistBatchState = async (
    status: "running" | "completed" | "stopped",
    nextStopReason: string | null,
  ): Promise<void> => {
    await appendTaskBatchRecord(stateRoot, {
      runId: input.runId,
      batchId,
      targetTaskCount: input.taskCount,
      completedTaskCount: tasks.filter((task) => task.status === "completed").length,
      runtimeFailureCount,
      maxRuntimeFailures: input.maxRuntimeFailures,
      status,
      stopReason: nextStopReason,
    });
  };

  const finalizeBatch = async (
    status: "completed" | "stopped",
    nextStopReason: string | null,
  ): Promise<void> => {
    if (finalized) {
      return;
    }

    finalized = true;
    input.monitor?.clearTask();
    await persistBatchState(status, nextStopReason);
    await rebuildIndexes(stateRoot);
    if (activeExecutor !== input.executor) {
      await activeExecutor.close?.();
    }
  };

  const applyReplacementExecutor = async (
    nextExecutor: PineEvaluationExecutor | undefined,
  ): Promise<void> => {
    if (!nextExecutor || nextExecutor === activeExecutor) {
      return;
    }

    const previousExecutor = activeExecutor;
    activeExecutor = nextExecutor;
    await previousExecutor.close?.();
  };

  const logAutoRecoveryApplied = async (inputDetail: {
    taskNumber: number;
    taskId: string;
    recoveryActions: string[];
    decision?: DecisionCode;
    detail: string;
  }): Promise<void> => {
    await appendIncidentRecord(stateRoot, {
      runId: input.runId,
      iteration: inputDetail.taskNumber,
      candidateId: inputDetail.taskId,
      incidentType: "task_auto_recovery_applied",
      detail: `${inputDetail.detail} | actions=${inputDetail.recoveryActions.join(",")}`,
    });
    await input.monitor?.log(
      "task.auto_recovery",
      "Automatic task recovery applied",
      {
        taskId: inputDetail.taskId,
        taskNumber: inputDetail.taskNumber,
        decision: inputDetail.decision ?? "runtime_error",
        recoveryActions: inputDetail.recoveryActions,
      },
    );
  };

  const logAutoRecoveryFailed = async (inputDetail: {
    taskNumber: number;
    taskId: string;
    decision?: DecisionCode;
    detail: string;
  }): Promise<void> => {
    await appendIncidentRecord(stateRoot, {
      runId: input.runId,
      iteration: inputDetail.taskNumber,
      candidateId: inputDetail.taskId,
      incidentType: "task_auto_recovery_failed",
      detail: inputDetail.detail,
    });
    await input.monitor?.log(
      "task.auto_recovery_failed",
      "Automatic task recovery failed",
      {
        taskId: inputDetail.taskId,
        taskNumber: inputDetail.taskNumber,
        decision: inputDetail.decision ?? "runtime_error",
        detail: inputDetail.detail,
      },
    );
  };

  const attemptTaskRecovery = async (
    context: TaskBatchRecoveryContext,
  ): Promise<boolean> => {
    if (!input.recoveryHooks?.onFailure) {
      return false;
    }

    try {
      const outcome = await input.recoveryHooks.onFailure(context);
      if (!outcome?.recovered) {
        return false;
      }

      await applyReplacementExecutor(outcome.executor);
      await logAutoRecoveryApplied({
        taskNumber: context.taskNumber,
        taskId: context.taskId,
        decision: context.decision,
        recoveryActions: outcome.recoveryActions,
        detail:
          context.failureDetail ??
          context.error?.message ??
          context.experiment?.mutationBriefSummary ??
          "automatic_recovery",
      });
      return true;
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      await logAutoRecoveryFailed({
        taskNumber: context.taskNumber,
        taskId: context.taskId,
        decision: context.decision,
        detail,
      });
      return false;
    }
  };

  const maybeRunResearchRefresh = async (): Promise<void> => {
    if (tasks.length === 0 || tasks.length % researchRefreshEveryTasks !== 0) {
      return;
    }

    try {
      const result = await researchRefreshRunner({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        env: input.env,
        batchId,
        tasks: tasks.slice(-researchRefreshEveryTasks),
        refreshEveryTasks: researchRefreshEveryTasks,
        monitor: input.monitor,
      });
      await input.monitor?.log(
        "research.refresh.result",
        "Research refresh completed without affecting task runtime status",
        {
          batchId,
          status: result.status,
          reason: result.reason,
          knowledgeIds: result.knowledgeIds,
          searchQueries: result.searchQueries,
        },
      );
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      await appendIncidentRecord(stateRoot, {
        runId: input.runId,
        iteration: tasks.at(-1)?.iteration ?? tasks.length,
        candidateId: batchId,
        incidentType: "research_refresh_runner_failed",
        detail,
      });
      await input.monitor?.log(
        "research.refresh.failed",
        "Research refresh failed softly without incrementing task runtime failures",
        {
          batchId,
          detail,
        },
      );
    } finally {
      await rebuildIndexes(stateRoot);
    }
  };

  const interruptHandler = (signal: NodeJS.Signals) => {
    stopReason = `interrupted_by_${signal.toLowerCase()}`;
    void finalizeBatch("stopped", stopReason);
  };

  process.once("SIGINT", interruptHandler);
  process.once("SIGTERM", interruptHandler);

  await input.monitor?.log("task.batch_start", "Starting task batch", {
    batchId,
    taskCount: input.taskCount,
    maxRuntimeFailures: input.maxRuntimeFailures,
  });
  await persistBatchState("running", null);
  await rebuildIndexes(stateRoot);

  if (input.recoveryHooks?.beforeBatch) {
    try {
      const outcome = await input.recoveryHooks.beforeBatch({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        runId: input.runId,
        batchId,
        taskCount: input.taskCount,
        currentExecutor: activeExecutor,
      });
      if (outcome?.recovered) {
        await applyReplacementExecutor(outcome.executor);
        await appendIncidentRecord(stateRoot, {
          runId: input.runId,
          iteration: 0,
          candidateId: batchId,
          incidentType: "task_batch_preflight_recovery_applied",
          detail: `actions=${outcome.recoveryActions.join(",")}`,
        });
        await input.monitor?.log(
          "task.system_ready",
          "Task batch system preflight succeeded",
          {
            batchId,
            recoveryActions: outcome.recoveryActions,
          },
        );
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      await appendIncidentRecord(stateRoot, {
        runId: input.runId,
        iteration: 0,
        candidateId: batchId,
        incidentType: "task_batch_preflight_recovery_failed",
        detail,
      });
      await input.monitor?.log(
        "task.system_ready_failed",
        "Task batch system preflight failed",
        {
          batchId,
          detail,
        },
      );
    }
  }

  try {
    for (let index = 0; index < input.taskCount; index += 1) {
      const taskNumber = index + 1;
      const taskId = `${batchId}-task-${String(taskNumber).padStart(2, "0")}`;
      await input.monitor?.setTask(taskNumber);
      let taskResolved = false;
      let autoRecoveryAttempts = 0;
      while (!taskResolved) {
        try {
          const result = await taskRunner({
            workspaceRoot: input.workspaceRoot,
            stateRoot,
            llmClient: input.llmClient,
            executor: activeExecutor,
            executorName: input.executorName,
            promotionVerificationExecutorFactory:
              input.promotionVerificationExecutorFactory,
            promotionVerificationExecutorName:
              input.promotionVerificationExecutorName,
            runId: input.runId,
            chartType: input.chartType,
            maxTrades: input.maxTrades,
            monitor: input.monitor,
            fallbackLocalOnRuntimeFailure:
              input.fallbackLocalOnTvRuntimeFailure ?? true,
            localFallbackExecutorFactory: input.localFallbackExecutorFactory,
            consumeFallbackSlot: () => {
              if (remainingFallbacks <= 0) {
                return false;
              }
              remainingFallbacks -= 1;
              return true;
            },
          });
          const generationFailed = isGenerationStageFailure(result.decision);
          const failureDetail = extractDecisionFailureDetail(result.decision, result.experiment);
          const shouldAttemptRecovery =
            autoRecoveryAttempts < maxAutoRecoveryAttemptsPerTask &&
            isAutoRecoverableDecision(result.decision);
          if (shouldAttemptRecovery) {
            const recovered = await attemptTaskRecovery({
              workspaceRoot: input.workspaceRoot,
              stateRoot,
              runId: input.runId,
              batchId,
              taskId,
              taskNumber,
              attempt: autoRecoveryAttempts + 1,
              currentExecutor: activeExecutor,
              decision: result.decision,
              experiment: result.experiment,
              failureDetail,
            });
            if (recovered) {
              autoRecoveryAttempts += 1;
              continue;
            }
          }

          if (generationFailed) {
            runtimeFailureCount += 1;
          }

          const taskRecord = await appendTaskRecord(stateRoot, {
            runId: input.runId,
            batchId,
            taskId,
            taskNumber,
            iteration: result.experiment.iteration,
            status: generationFailed ? "generation_failed" : "completed",
            hypothesis: result.hypothesis,
            execution: buildTaskExecutionSummary(result.decision, result.experiment),
            analysis: buildTaskAnalysisSummary(
              result.decision,
              result.experiment.candidateScore ?? null,
              result.experiment.objectiveBreakdown?.hardGatesPassed ?? null,
              result.experiment.objectiveBreakdown?.softGuardrailBreached ?? null,
              result.experiment.mutationParseStatus ?? null,
              result.experiment.verificationStatus ?? null,
              result.experiment.verificationFailureReason ?? null,
              result.experiment.verificationRuntimeFailureKind ?? null,
              result.experiment.recoveryAttempts ?? [],
              result.experiment.fallbackEvaluation ?? null,
              result.experiment.promotionStatus ?? null,
              result.experiment.promotionReady ?? null,
              result.experiment.screeningVsVerificationDiff ?? null,
              result.experiment.recordEra ?? null,
              result.experiment.pineAnalysisSummary ?? null,
              result.experiment.finalAnalysisSummary ?? null,
              result.conditionContributions,
              result.experiment.nextMutationHints ?? [],
            ),
            mutationParseStatus: result.experiment.mutationParseStatus ?? null,
            mutationProvenance: result.experiment.mutationProvenance ?? null,
            executorCapability: result.experiment.executorCapability ?? null,
            artifactValidation: result.experiment.artifactValidation ?? null,
            verificationStatus: result.experiment.verificationStatus ?? null,
            verificationFailureReason:
              result.experiment.verificationFailureReason ?? null,
            verificationRuntimeFailureKind:
              result.experiment.verificationRuntimeFailureKind ?? null,
            recoveryAttempts: result.experiment.recoveryAttempts ?? [],
            fallbackEvaluation: result.experiment.fallbackEvaluation ?? null,
            promotionStatus: result.experiment.promotionStatus ?? null,
            promotionReady: result.experiment.promotionReady ?? null,
            localTvParity: result.experiment.localTvParity ?? null,
            screeningVsVerificationDiff:
              result.experiment.screeningVsVerificationDiff ?? null,
            recordEra: result.experiment.recordEra ?? "v2",
          });
          tasks.push(taskRecord);

          await persistBatchState("running", null);
          await input.monitor?.log("task.batch_update", "Task batch progress updated", {
            batchId,
            completedTaskCount: taskNumber,
            runtimeFailureCount,
            lastDecision: result.decision,
          });
          await rebuildIndexes(stateRoot);
          await maybeRunResearchRefresh();

          if (generationFailed && runtimeFailureCount >= input.maxRuntimeFailures) {
            stopReason = `generation failures reached ${runtimeFailureCount}`;
          }
          taskResolved = true;
        } catch (error) {
          const runtimeError =
            error instanceof Error ? error : new Error(String(error));
          const recovered =
            autoRecoveryAttempts < maxAutoRecoveryAttemptsPerTask
              ? await attemptTaskRecovery({
                  workspaceRoot: input.workspaceRoot,
                  stateRoot,
                  runId: input.runId,
                  batchId,
                  taskId,
                  taskNumber,
                  attempt: autoRecoveryAttempts + 1,
                  currentExecutor: activeExecutor,
                  error: runtimeError,
                  failureDetail: runtimeError.message,
                })
              : false;
          if (recovered) {
            autoRecoveryAttempts += 1;
            continue;
          }

          runtimeFailureCount += 1;
          const detail = runtimeError.message;

          const taskRecord = await appendTaskRecord(stateRoot, {
            runId: input.runId,
            batchId,
            taskId,
            taskNumber,
            iteration: taskNumber,
            status: "runtime_failed",
            hypothesis: buildRuntimeFailureHypothesis(),
            execution: {
              candidateId: null,
              studyTitle: null,
              status: "runtime_failed",
              decision: "runtime_failed",
              compileOk: null,
              applyOk: null,
              artifactPaths: {},
              executorCapability: null,
              artifactValidation: null,
            },
            analysis: {
              decision: "runtime_failed",
              score: null,
              hardGatesPassed: null,
              softGuardrailBreached: null,
              mutationParseStatus: null,
              verificationStatus: null,
              verificationFailureReason: null,
              verificationRuntimeFailureKind: null,
              recoveryAttempts: [],
              fallbackEvaluation: null,
              promotionStatus: null,
              promotionReady: null,
              screeningVsVerificationDiff: null,
              recordEra: null,
              pineAnalysisSummary: null,
              finalAnalysisSummary: null,
              topConditionContributions: [],
              nextMutationHints: [],
            },
            mutationParseStatus: null,
            executorCapability: null,
            artifactValidation: null,
            verificationStatus: null,
            verificationFailureReason: null,
            verificationRuntimeFailureKind: null,
            recoveryAttempts: [],
            fallbackEvaluation: null,
            promotionStatus: null,
            promotionReady: null,
            screeningVsVerificationDiff: null,
            recordEra: null,
          });
          tasks.push(taskRecord);
          await appendIncidentRecord(stateRoot, {
            runId: input.runId,
            iteration: taskNumber,
            candidateId: taskId,
            incidentType: "task_runtime_failure",
            detail,
          });
          await input.monitor?.log("task.runtime_failure", "Task runtime failure recorded", {
            batchId,
            taskId,
            taskNumber,
            runtimeFailureCount,
            detail,
          });

          await persistBatchState("running", null);
          await rebuildIndexes(stateRoot);
          await maybeRunResearchRefresh();

          if (runtimeFailureCount >= input.maxRuntimeFailures) {
            stopReason = `runtime failures reached ${runtimeFailureCount}`;
          }
          taskResolved = true;
        }
      }

      if (stopReason !== null) {
        break;
      }
    }
  } finally {
    process.removeListener("SIGINT", interruptHandler);
    process.removeListener("SIGTERM", interruptHandler);
  }

  const completedTaskCount = tasks.filter((task) => task.status === "completed").length;
  const status = stopReason === null ? "completed" : "stopped";
  await finalizeBatch(status, stopReason);
  await input.monitor?.log("task.batch_done", "Task batch completed", {
    batchId,
    status,
    completedTaskCount,
    runtimeFailureCount,
    stopReason,
  });

  return {
    batchId,
    runId: input.runId,
    targetTaskCount: input.taskCount,
    completedTaskCount,
    runtimeFailureCount,
    status,
    stopReason,
    tasks,
  };
}

function isAutoRecoverableDecision(decision: DecisionCode): boolean {
  return decision === "mutation_generation_fail" || decision === "apply_fail";
}

function isGenerationStageFailure(decision: DecisionCode): boolean {
  return (
    decision === "mutation_generation_fail" ||
    decision === "mutation_schema_fail" ||
    decision === "preflight_fail"
  );
}

function extractDecisionFailureDetail(
  decision: DecisionCode,
  experiment: ExperimentRecord,
): string | null {
  if (decision === "mutation_generation_fail") {
    return experiment.mutationBriefSummary ?? null;
  }

  if (decision === "mutation_schema_fail" || decision === "preflight_fail") {
    return experiment.mutationBriefSummary ?? null;
  }

  if (decision === "apply_fail") {
    return experiment.apply?.message ?? null;
  }

  return null;
}

function buildTaskExecutionSummary(
  decision: DecisionCode,
  experiment: {
    candidateId: string;
    studyTitle?: string | null;
    status: string;
    compile?: { ok: boolean };
    apply?: { ok: boolean };
    artifactPaths?: Record<string, string>;
    executorCapability?: ExecutorCapability;
    artifactValidation?: ArtifactValidationResult;
  },
): TaskExecutionSummary {
  return {
    candidateId: experiment.candidateId,
    studyTitle: experiment.studyTitle ?? null,
    status: mapDecisionToExecutionStatus(decision, experiment.status),
    decision,
    compileOk: experiment.compile?.ok ?? null,
    applyOk: experiment.apply?.ok ?? null,
    artifactPaths: experiment.artifactPaths ?? {},
    executorCapability: experiment.executorCapability ?? null,
    artifactValidation: experiment.artifactValidation ?? null,
  };
}

function buildTaskAnalysisSummary(
  decision: string,
  score: number | null,
  hardGatesPassed: boolean | null,
  softGuardrailBreached: boolean | null,
  mutationParseStatus: MutationParseStatus | null,
  verificationStatus: VerificationStatus | null,
  verificationFailureReason: VerificationFailureReason,
  verificationRuntimeFailureKind: VerificationRuntimeFailureKind,
  recoveryAttempts: SurfaceRecoveryAttempt[],
  fallbackEvaluation: FallbackEvaluation | null,
  promotionStatus: PromotionStatus | null,
  promotionReady: boolean | null,
  screeningVsVerificationDiff: MetricComparison[] | null,
  recordEra: RecordEra | null,
  pineAnalysisSummary: PineAnalysisSummary | null,
  finalAnalysisSummary: FinalAnalysisSummary | null,
  conditionContributions: ConditionContribution[],
  nextMutationHints: string[],
): TaskAnalysisSummary {
  return {
    decision,
    score,
    hardGatesPassed,
    softGuardrailBreached,
    mutationParseStatus,
    verificationStatus,
    verificationFailureReason,
    verificationRuntimeFailureKind,
    recoveryAttempts,
    fallbackEvaluation,
    promotionStatus,
    promotionReady,
    screeningVsVerificationDiff,
    recordEra,
    pineAnalysisSummary,
    finalAnalysisSummary,
    topConditionContributions: [...conditionContributions]
      .sort((left, right) => Math.abs(right.scoreDelta) - Math.abs(left.scoreDelta))
      .slice(0, 3),
    nextMutationHints,
  };
}

function buildRuntimeFailureHypothesis(): TaskHypothesis {
  return {
    objective: "runtime_failure_before_hypothesis",
    nextMutationDirection: "Resolve runtime failure before generating the next hypothesis.",
    recentFailures: ["task_runtime_failure"],
    acceptedHeadCandidateId: null,
  };
}

function mapDecisionToExecutionStatus(
  decision: DecisionCode,
  fallbackStatus: string,
): TaskExecutionSummary["status"] {
  if (
    decision === "mutation_generation_fail" ||
    decision === "mutation_schema_fail" ||
    decision === "preflight_fail" ||
    decision === "unsupported_strategy_family" ||
    decision === "unsupported_chart_target"
  ) {
    return "generation_failed";
  }

  if (decision === "compile_fail") {
    return "compile_failed";
  }

  if (decision === "apply_fail") {
    return "apply_failed";
  }

  if (decision === "backtest_empty") {
    return "backtest_empty";
  }

  if (decision === "artifact_incomplete" || decision === "verification_fail") {
    return "evaluated";
  }

  if (fallbackStatus === "evaluated") {
    return "evaluated";
  }

  return "evaluated";
}
