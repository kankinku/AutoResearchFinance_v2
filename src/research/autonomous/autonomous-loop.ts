import { type RuntimeEnvironment } from "../../cli/runtime-config.js";
import { type LocalCompatibilityIssue } from "../../contracts/types.js";
import { type MutationLlmClient } from "../../mutation/llm-client.js";
import {
  appendAutonomousIterationRecord,
  appendAutonomousBranchRecord,
  appendIncidentRecord,
  appendProblemEventRecord,
  appendRunRecord,
  ensureStateRoot,
  readArchiveEventRecords,
  readAutonomousBranchRecords,
  readCalibrationEventRecords,
  readExperimentRecords,
  readHeadEventRecords,
  readLocalConfidenceEventRecords,
  readMutationBriefRecords,
  readProblemEventRecords,
  readRecentAutonomousIterationRecords,
  readRepairAttemptRecords,
  readResearchKnowledgeRecords,
  readStrategyReviewRecords,
} from "../../state/jsonl-store.js";
import { rebuildIndexes } from "../../state/index-builder.js";
import { loadObjectiveConfig } from "../../config/objective.js";
import {
  prepareAutonomousMutationPlan,
  generateAutonomousCandidate,
  repairAutonomousCandidateForCompatibility,
  repairAutonomousCandidateForProblemEvent,
  type AutonomousMutationPlan,
} from "./mutation-planner.js";
import { runLocalEvaluationPhase } from "./local-evaluation-phase.js";
import { runArchiveUpdatePhase } from "./archive-update-phase.js";
import {
  prepareBootstrapCandidate,
  shouldRunBootstrapSeed,
} from "./bootstrap-phase.js";
import {
  enqueueCalibrationCandidate,
  processTvCalibrationQueue,
  selectPendingCalibrationCandidates,
} from "./tv-calibration-phase.js";
import { resolveTvHealthStatus } from "./tv-health-phase.js";
import { runAutoSelectionPhase } from "./auto-selection-phase.js";
import {
  buildAutonomousBranchRecord,
  selectNextAutonomousBranch,
} from "./branch-scheduler.js";
import { ensureMarketContext } from "../market-context.js";
import {
  initializeWorkspace,
  type WorkspaceBootstrapDiagnostics,
  WorkspaceBootstrapError,
} from "../workspace.js";
import { type PineEvaluationExecutor } from "../../automation/common/executor.js";
import { type ProblemEventRecord, type RepairKind } from "../../contracts/autonomous.js";
import { createCandidateId, sha256 } from "../../utils/fs.js";
import {
  type AutonomousIterationLearningRecord,
  type CriterionDirective,
  type MutationBrief,
} from "../../contracts/types.js";
import {
  buildCriterionDirective,
  buildCriterionOutcome,
} from "./criterion-analysis-phase.js";
import {
  collectSuppressedFamiliesFromReviews,
  filterStrategyReviewRecordsForTarget,
  runStrategyReviewPhase,
  selectLatestStrategyReviewDirective,
} from "./strategy-review-phase.js";

interface MonitorLike {
  log: (
    event: string,
    message: string,
    details?: Record<string, unknown>,
  ) => Promise<void>;
}

export interface AutonomousLoopResult {
  runId: string;
  iteration: number;
  candidateId: string | null;
  localDecision: string | null;
  activeChampionChanged: boolean;
  activeChampionCandidateId: string | null;
}

export interface AutonomousLoopPhaseTimeouts {
  bootstrapMs: number;
  mutationMs: number;
  localEvaluationMs: number;
  repairMs: number;
  archiveUpdateMs: number;
  calibrationEnqueueMs: number;
  calibrationProcessMs: number;
  strategyReviewMs: number;
  autoSelectionMs: number;
  rebuildIndexesMs: number;
}

export interface AutonomousIterationFailure {
  iteration: number;
  phase: string;
  message: string;
}

export async function runAutonomousLoop(input: {
  workspaceRoot: string;
  env: RuntimeEnvironment;
  llmClient: MutationLlmClient;
  localExecutorFactory: () => PineEvaluationExecutor;
  calibrationExecutorFactory?: () => PineEvaluationExecutor;
  phaseTimeouts?: Partial<AutonomousLoopPhaseTimeouts>;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}): Promise<AutonomousLoopResult> {
  const stateRoot = input.env.stateRoot;
  const runId = `autonomous-${Date.now()}`;
  if (input.env.researchModeConfig.mode === "indicator_request") {
    throw new Error(
      "research mode indicator_request does not run autonomous strategy improvement. Use generate-indicator instead.",
    );
  }
  const phaseTimeouts = resolvePhaseTimeouts(
    input.env.openAiRequestTimeoutMs,
    input.env.calibrationTimeoutMs,
    input.phaseTimeouts,
  );
  await ensureStateRoot(stateRoot);

  try {
    await runPhase({
      monitor: input.monitor,
      phase: "bootstrap",
      message: "Initializing autonomous workspace",
      timeoutMs: phaseTimeouts.bootstrapMs,
      signal: input.signal,
      run: (signal) =>
        initializeWorkspace({
          projectRoot: input.env.projectRoot,
          workspaceRoot: input.workspaceRoot,
          stateRoot,
          targetId: input.env.researchTargetId,
        }),
    });
  } catch (error) {
    if (error instanceof WorkspaceBootstrapError) {
      await recordBootstrapFailure({
        stateRoot,
        runId,
        diagnostics: error.diagnostics,
      });
      await rebuildIndexes(stateRoot);
      return {
        runId,
        iteration: 0,
        candidateId: null,
        localDecision: null,
        activeChampionChanged: false,
        activeChampionCandidateId: null,
      };
    }
    throw error;
  }

  const objective = await loadObjectiveConfig(
    input.workspaceRoot,
    input.env.researchTargetId,
  );
  const previousExperiments = await readExperimentRecords(stateRoot);
  const headEvents = await readHeadEventRecords(stateRoot);
  const archiveEvents = await readArchiveEventRecords(stateRoot);
  const calibrationEvents = await readCalibrationEventRecords(stateRoot);
  const confidenceEvents = await readLocalConfidenceEventRecords(stateRoot);
  const problemEvents = await readProblemEventRecords(stateRoot);
  const repairAttempts = await readRepairAttemptRecords(stateRoot);
  const mutationBriefs = await readMutationBriefRecords(stateRoot);
  const strategyReviewRecords = await readStrategyReviewRecords(stateRoot);
  const iterationRecords = await readRecentAutonomousIterationRecords(stateRoot);
  const branchRecords = await readAutonomousBranchRecords(stateRoot);
  const targetExperiments = filterStrategyReviewRecordsForTarget(
    previousExperiments,
    input.env.researchTargetId,
    objective,
  );
  const targetCandidateIds = buildCandidateIdSet(targetExperiments);
  const targetHeadEvents = filterHeadEventsForTarget(headEvents, targetCandidateIds);
  const targetArchiveEvents = filterByCandidateId(archiveEvents, targetCandidateIds);
  const targetCalibrationEvents = filterByCandidateId(
    calibrationEvents,
    targetCandidateIds,
  );
  const targetConfidenceEvents = filterByCandidateId(
    confidenceEvents,
    targetCandidateIds,
  );
  const targetProblemEvents = filterByCandidateId(problemEvents, targetCandidateIds);
  const targetRepairAttempts = filterRepairAttemptsForTarget(
    repairAttempts,
    targetCandidateIds,
  );
  const targetMutationBriefs = filterMutationBriefsForTarget(
    mutationBriefs,
    targetCandidateIds,
  );
  const targetBranchRecords = filterBranchRecordsForTarget(
    branchRecords,
    targetCandidateIds,
  );
  const iteration = previousExperiments.length + 1;
  const criterionDirective =
    input.env.researchModeConfig.mode === "criterion_focus"
      ? buildCriterionDirective({
          criterion: input.env.researchModeConfig.criterion,
          experiments: targetExperiments,
          calibrationEvents: targetCalibrationEvents,
          problemEvents: targetProblemEvents,
          objective,
        })
      : null;
  const strategyReviewDirective = selectLatestStrategyReviewDirective({
    records: strategyReviewRecords,
    targetId: input.env.researchTargetId,
    minConfidence: input.env.strategyReviewMinConfidence,
    quarantineConfidence: input.env.strategyReviewQuarantineConfidence,
  });
  const reviewSuppressedFamilies = collectSuppressedFamiliesFromReviews({
    records: strategyReviewRecords,
    targetId: input.env.researchTargetId,
    quarantineConfidence: input.env.strategyReviewQuarantineConfidence,
  });

  await appendRunRecord(stateRoot, {
    runId,
    startedAt: new Date().toISOString(),
    executor: "local-backtest",
    symbol: input.env.chartSymbol,
    timeframe: input.env.chartTimeframe,
    chartType: input.env.chartType,
    model: input.env.openAiModel,
  });

  if (
    input.env.autonomousBootstrapMode === "auto" &&
    shouldRunBootstrapSeed({
      experiments: targetExperiments,
      headEvents: targetHeadEvents,
    })
  ) {
    const bootstrapSeed = await runPhase({
      monitor: input.monitor,
      phase: "bootstrap_seed_candidate",
      message: "Preparing bootstrap local-compatible seed candidate",
      timeoutMs: phaseTimeouts.bootstrapMs,
      signal: input.signal,
      run: (signal) =>
        prepareBootstrapCandidate({
          projectRoot: input.env.projectRoot,
          workspaceRoot: input.workspaceRoot,
          stateRoot,
          runId,
          iteration,
          signal,
        }),
    });
    const localExecutor = input.localExecutorFactory();
    try {
      const bootstrapEvaluation = await runPhase({
        monitor: input.monitor,
        phase: "bootstrap_local_evaluation",
        message: "Evaluating bootstrap seed candidate locally",
        timeoutMs: phaseTimeouts.localEvaluationMs,
        signal: input.signal,
        run: async (signal) => {
          const localCapability = localExecutor.getCapability();
          if (localCapability.kind === "local-af-backtest") {
            const ensuredContext = await ensureMarketContext(
              input.workspaceRoot,
              {
                symbol: input.env.chartSymbol,
                timeframe: input.env.chartTimeframe,
              },
              { stateRoot },
            );
            await input.monitor?.log(
              "autonomous.market_context_ready",
              "Local-first market context is ready",
              {
                cachePath: ensuredContext.cachePath,
                fromCache: ensuredContext.fromCache,
                barCount: ensuredContext.bars.length,
              },
            );
          }

          return runLocalEvaluationPhase({
            workspaceRoot: input.workspaceRoot,
            stateRoot,
            runId,
            iteration,
            executor: localExecutor,
            objective,
            targetId: input.env.researchTargetId,
            parsedMutation: bootstrapSeed.parsedMutation,
            candidateArtifact: bootstrapSeed.candidateArtifact,
            mutationProvenance: bootstrapSeed.mutationProvenance,
            previousExperiments: targetExperiments,
            previousConfidenceEvents: targetConfidenceEvents,
            previousProblemEvents: targetProblemEvents,
            previousRepairAttempts: targetRepairAttempts,
            bootstrapMetadata: {
              source: "local_compatible_seed",
              reason: "fresh_state_without_active_champion",
            },
            signal,
            monitor: input.monitor,
          });
        },
      });

      if (
        bootstrapEvaluation.record.eligibility?.autoSelectionEligible === true ||
        bootstrapEvaluation.record.eligibility?.bootstrapEligible === true
      ) {
        const selection = await finalizeAutonomousLocalEvaluation({
          workspaceRoot: input.workspaceRoot,
          stateRoot,
          runId,
          iteration,
          objective,
          env: input.env,
          calibrationExecutorFactory: input.calibrationExecutorFactory,
          llmClient: input.llmClient,
          localEvaluation: bootstrapEvaluation,
          monitor: input.monitor,
          phaseTimeouts,
          signal: input.signal,
        });
        return {
          runId,
          iteration,
          candidateId: bootstrapEvaluation.record.candidateId,
          localDecision: bootstrapEvaluation.record.decision,
          activeChampionChanged: selection.activeChampionChanged,
          activeChampionCandidateId: selection.selectedCandidateId,
        };
      }
    } finally {
      await localExecutor.close?.();
    }
  }

  try {
    const selectedBranch = selectNextAutonomousBranch({
      branches: targetBranchRecords,
      experiments: targetExperiments,
      branchKindBias:
        criterionDirective?.branchBias ?? strategyReviewDirective?.branchKindBias ?? null,
      suppressedFamilies: reviewSuppressedFamilies,
    });
    const selectedBranchRecord = buildAutonomousBranchRecord({
      selection: selectedBranch,
      parentCandidateId: null,
      lastCandidateId: null,
    });
    const plan = await prepareAutonomousMutationPlan({
      workspaceRoot: input.workspaceRoot,
      objective,
      experiments: targetExperiments,
      headEvents: targetHeadEvents,
      archiveEvents: targetArchiveEvents,
      calibrationEvents: targetCalibrationEvents,
      confidenceEvents: targetConfidenceEvents,
      problemEvents: targetProblemEvents,
      repairAttempts: targetRepairAttempts,
      mutationBriefs: targetMutationBriefs,
      iterationRecords,
      selectedBranch: selectedBranchRecord,
      researchModeConfig: input.env.researchModeConfig,
      criterionDirective,
      strategyReviewDirective,
      ignoreCalibrationGuidance:
        input.env.tvCalibrationMode !== "mock-recovered" &&
        (!input.env.autoProcessCalibration ||
          resolveTvHealthStatus(input.env) !== "healthy"),
    });
    let mutation;
    try {
      mutation = await runPhase({
        monitor: input.monitor,
        phase: "mutation_generation",
        message: "Generating autonomous mutation candidate",
        timeoutMs: phaseTimeouts.mutationMs,
        signal: input.signal,
        run: (signal) =>
          generateAutonomousCandidate({
            workspaceRoot: input.workspaceRoot,
            stateRoot,
            runId,
            iteration,
            llmClient: input.llmClient,
            plan,
            parentCandidateId: plan.parentCandidateId,
            branchId: selectedBranch.branchId,
            mutationSchemaMode: input.env.mutationSchemaMode,
            signal,
            monitor: input.monitor,
          }),
      });
    } catch (error) {
      const failureDiagnostic = summarizeMutationGenerationFailure(error);
      await appendProblemEventRecord(stateRoot, {
        problemEventId: createCandidateId("problem"),
        runId,
        iteration,
        candidateId: plan.activeChampion?.candidateId ?? null,
        problemKind: "mutation_generation_fail",
        diagnosis: [
          failureDiagnostic.diagnosis,
          `Next prompt adjustment: ${failureDiagnostic.nextPromptAdjustment}`,
        ].join(" | "),
        evidenceHash: sha256(
          JSON.stringify({
            diagnosis: failureDiagnostic.diagnosis,
            nextPromptAdjustment: failureDiagnostic.nextPromptAdjustment,
            activeChampionCandidateId: plan.activeChampion?.candidateId ?? null,
          }),
        ),
        suggestedRepairKind: failureDiagnostic.suggestedRepairKind,
        failureSignatureHash: sha256(
          JSON.stringify({
            problemKind: "mutation_generation_fail",
            diagnosis: failureDiagnostic.diagnosis,
            suggestedRepairKind: failureDiagnostic.suggestedRepairKind,
          }),
        ),
        structureFamily:
          plan.activeChampion?.noveltyFingerprint?.fingerprintFamily ?? null,
      });
      throw error;
    }

    const localExecutor = input.localExecutorFactory();
    let localEvaluation: Awaited<ReturnType<typeof runLocalEvaluationPhase>>;
    try {
      localEvaluation = await runPhase({
        monitor: input.monitor,
        phase: "local_evaluation",
        message: "Evaluating autonomous candidate locally",
        timeoutMs: phaseTimeouts.localEvaluationMs,
        signal: input.signal,
        run: async (signal) => {
          const localCapability = localExecutor.getCapability();
          if (localCapability.kind === "local-af-backtest") {
            const ensuredContext = await ensureMarketContext(
              input.workspaceRoot,
              {
                symbol: input.env.chartSymbol,
                timeframe: input.env.chartTimeframe,
              },
              { stateRoot },
            );
            await input.monitor?.log(
              "autonomous.market_context_ready",
              "Local-first market context is ready",
              {
                cachePath: ensuredContext.cachePath,
                fromCache: ensuredContext.fromCache,
                barCount: ensuredContext.bars.length,
              },
            );
          }

          return runLocalEvaluationPhase({
            workspaceRoot: input.workspaceRoot,
            stateRoot,
            runId,
            iteration,
            executor: localExecutor,
            objective,
            targetId: input.env.researchTargetId,
            parsedMutation: mutation.parsedMutation,
            candidateArtifact: mutation.candidateArtifact,
            mutationProvenance: mutation.mutationProvenance,
            previousExperiments: targetExperiments,
            previousConfidenceEvents: targetConfidenceEvents,
            previousProblemEvents: targetProblemEvents,
            previousRepairAttempts: targetRepairAttempts,
            signal,
            monitor: input.monitor,
          });
        },
      });

      if (shouldAttemptAutonomousRepair(localEvaluation.problemEvent)) {
        const repairedMutation = await runPhase({
          monitor: input.monitor,
          phase: "repair_candidate_generation",
          message: "Repairing autonomous candidate after local failure",
          timeoutMs: phaseTimeouts.repairMs,
          signal: input.signal,
          run: async (signal) => {
            if (localEvaluation.problemEvent?.problemKind === "local_unsupported") {
              const compatibilityIssues = await resolveCompatibilityIssues({
                executor: localExecutor,
                env: input.env,
                pineScript: mutation.parsedMutation.pineScript,
              });
              if (compatibilityIssues.length === 0) {
                return null;
              }
              return repairAutonomousCandidateForCompatibility({
                workspaceRoot: input.workspaceRoot,
                stateRoot,
                runId,
                iteration,
                llmClient: input.llmClient,
                plan,
                candidateId: mutation.candidateArtifact.candidateId,
                parsedMutation: mutation.parsedMutation,
                compatibilityIssues,
                problemEvent: localEvaluation.problemEvent,
                branchId: selectedBranch.branchId,
                mutationSchemaMode: input.env.mutationSchemaMode,
                signal,
                monitor: input.monitor,
              });
            }

            if (!localEvaluation.problemEvent) {
              return null;
            }

            return repairAutonomousCandidateForProblemEvent({
              workspaceRoot: input.workspaceRoot,
              stateRoot,
              runId,
              iteration,
              llmClient: input.llmClient,
              plan,
              candidateId: localEvaluation.record.candidateId,
              parsedMutation: mutation.parsedMutation,
              problemEvent: localEvaluation.problemEvent,
              repairKind: localEvaluation.problemEvent
                .suggestedRepairKind as Exclude<RepairKind, "schema_repair">,
              compileErrors: buildProblemRepairInstructions({
                problemEvent: localEvaluation.problemEvent,
                evaluation: localEvaluation.record,
              }),
              summary: `Requested ${localEvaluation.problemEvent.suggestedRepairKind} after ${localEvaluation.problemEvent.problemKind}.`,
              branchId: selectedBranch.branchId,
              mutationSchemaMode: input.env.mutationSchemaMode,
              signal,
              monitor: input.monitor,
            });
          },
        });

        if (repairedMutation) {
          const experimentsAfterRepair = await readExperimentRecords(stateRoot);
          const confidenceEventsAfterRepair =
            await readLocalConfidenceEventRecords(stateRoot);
          const problemEventsAfterRepair = await readProblemEventRecords(stateRoot);
          const repairAttemptsAfterRepair = await readRepairAttemptRecords(stateRoot);
          const targetExperimentsAfterRepair = filterStrategyReviewRecordsForTarget(
            experimentsAfterRepair,
            input.env.researchTargetId,
            objective,
          );
          const targetCandidateIdsAfterRepair = buildCandidateIdSet(
            targetExperimentsAfterRepair,
          );
          localEvaluation = await runPhase({
            monitor: input.monitor,
            phase: "repair_local_evaluation",
            message: "Evaluating repaired autonomous candidate locally",
            timeoutMs: phaseTimeouts.localEvaluationMs,
            signal: input.signal,
            run: async (signal) => {
              const localCapability = localExecutor.getCapability();
              if (localCapability.kind === "local-af-backtest") {
                const ensuredContext = await ensureMarketContext(
                  input.workspaceRoot,
                  {
                    symbol: input.env.chartSymbol,
                    timeframe: input.env.chartTimeframe,
                  },
                  { stateRoot },
                );
                await input.monitor?.log(
                  "autonomous.market_context_ready",
                  "Local-first market context is ready",
                  {
                    cachePath: ensuredContext.cachePath,
                    fromCache: ensuredContext.fromCache,
                    barCount: ensuredContext.bars.length,
                  },
                );
              }
              return runLocalEvaluationPhase({
                workspaceRoot: input.workspaceRoot,
                stateRoot,
                runId,
                iteration,
                executor: localExecutor,
                objective,
                targetId: input.env.researchTargetId,
                parsedMutation: repairedMutation.parsedMutation,
                candidateArtifact: repairedMutation.candidateArtifact,
                mutationProvenance: repairedMutation.mutationProvenance,
                previousExperiments: targetExperimentsAfterRepair,
                previousConfidenceEvents: filterByCandidateId(
                  confidenceEventsAfterRepair,
                  targetCandidateIdsAfterRepair,
                ),
                previousProblemEvents: filterByCandidateId(
                  problemEventsAfterRepair,
                  targetCandidateIdsAfterRepair,
                ),
                previousRepairAttempts: filterRepairAttemptsForTarget(
                  repairAttemptsAfterRepair,
                  targetCandidateIdsAfterRepair,
                ),
                signal,
                monitor: input.monitor,
              });
            },
          });
        }
      }
    } finally {
      await localExecutor.close?.();
    }

    const selection = await finalizeAutonomousLocalEvaluation({
      workspaceRoot: input.workspaceRoot,
      stateRoot,
      runId,
      iteration,
      objective,
      env: input.env,
      calibrationExecutorFactory: input.calibrationExecutorFactory,
      llmClient: input.llmClient,
      localEvaluation,
      monitor: input.monitor,
      phaseTimeouts,
      signal: input.signal,
    });
    await appendAutonomousBranchRecord(
      stateRoot,
      buildAutonomousBranchRecord({
        selection: selectedBranch,
        parentCandidateId: plan.parentCandidateId,
        lastCandidateId: localEvaluation.record.candidateId,
      }),
    );
    await recordAutonomousIterationLearning({
      stateRoot,
      runId,
      iteration,
      plan,
      criterionDirective,
      localEvaluation,
      selection,
      monitor: input.monitor,
    });
    return {
      runId,
      iteration,
      candidateId: localEvaluation.record.candidateId,
      localDecision: localEvaluation.record.decision,
      activeChampionChanged: selection.activeChampionChanged,
      activeChampionCandidateId: selection.selectedCandidateId,
    };
  } catch (error) {
    await appendIncidentRecord(stateRoot, {
      runId,
      iteration,
      candidateId: `autonomous-${iteration}`,
      incidentType: "autonomous_loop_failed",
      detail: error instanceof Error ? error.message : String(error),
    });
    await rebuildIndexes(stateRoot);
    return {
      runId,
      iteration,
      candidateId: null,
      localDecision: null,
      activeChampionChanged: false,
      activeChampionCandidateId: null,
    };
  }
}

export async function runAutonomousIterations(input: {
  workspaceRoot: string;
  env: RuntimeEnvironment;
  llmClient: MutationLlmClient;
  localExecutorFactory: () => PineEvaluationExecutor;
  calibrationExecutorFactory?: () => PineEvaluationExecutor;
  count: number;
  phaseTimeouts?: Partial<AutonomousLoopPhaseTimeouts>;
  iterationDeadlineMs?: number;
  monitor?: MonitorLike;
}): Promise<{
  countRequested: number;
  countCompleted: number;
  countFailed: number;
  results: AutonomousLoopResult[];
  deadlineBreaches: AutonomousIterationFailure[];
}> {
  const phaseTimeouts = {
    ...resolvePhaseTimeouts(
      input.env.openAiRequestTimeoutMs,
      input.env.calibrationTimeoutMs,
      input.phaseTimeouts,
    ),
  };
  const iterationDeadlineMs =
    input.iterationDeadlineMs ??
    phaseTimeouts.bootstrapMs +
      phaseTimeouts.mutationMs +
      phaseTimeouts.localEvaluationMs +
      phaseTimeouts.repairMs +
      phaseTimeouts.archiveUpdateMs +
      phaseTimeouts.calibrationEnqueueMs +
      phaseTimeouts.calibrationProcessMs +
      phaseTimeouts.strategyReviewMs +
      phaseTimeouts.autoSelectionMs +
      phaseTimeouts.rebuildIndexesMs;

  const results: AutonomousLoopResult[] = [];
  const deadlineBreaches: AutonomousIterationFailure[] = [];
  let countFailed = 0;

  for (let index = 0; index < input.count; index += 1) {
    const iterationNumber = index + 1;
    await input.monitor?.log("iteration.started", "Starting autonomous iteration", {
      task: iterationNumber,
      iterationDeadlineMs,
      phaseTimeouts,
    });
    const startedAt = Date.now();
    try {
      const result = await withTimeout(
        (signal) =>
          runAutonomousLoop({
            workspaceRoot: input.workspaceRoot,
            env: input.env,
            llmClient: input.llmClient,
            localExecutorFactory: input.localExecutorFactory,
            calibrationExecutorFactory: input.calibrationExecutorFactory,
            phaseTimeouts,
            signal,
            monitor: input.monitor,
          }),
        iterationDeadlineMs,
        `autonomous iteration ${iterationNumber} exceeded deadline`,
      );
      results.push(result);
      const failed = result.candidateId == null || result.localDecision == null;
      if (failed) {
        countFailed += 1;
        await input.monitor?.log("iteration.failed", "Autonomous iteration ended in failure", {
          task: iterationNumber,
          durationMs: Date.now() - startedAt,
          result,
        });
      } else {
        await input.monitor?.log("iteration.completed", "Autonomous iteration completed", {
          task: iterationNumber,
          durationMs: Date.now() - startedAt,
          result,
        });
      }
    } catch (error) {
      countFailed += 1;
      deadlineBreaches.push({
        iteration: iterationNumber,
        phase: "iteration",
        message: error instanceof Error ? error.message : String(error),
      });
      await appendIncidentRecord(input.env.stateRoot, {
        runId: `autonomous-iter-${Date.now()}`,
        iteration: iterationNumber,
        candidateId: `autonomous-${iterationNumber}`,
        incidentType: "autonomous_iteration_deadline_exceeded",
        detail: error instanceof Error ? error.message : String(error),
      });
      await input.monitor?.log("iteration.failed", "Autonomous iteration deadline exceeded", {
        task: iterationNumber,
        durationMs: Date.now() - startedAt,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return {
    countRequested: input.count,
    countCompleted: results.length,
    countFailed,
    results,
    deadlineBreaches,
  };
}

async function recordBootstrapFailure(input: {
  stateRoot: string;
  runId: string;
  diagnostics: WorkspaceBootstrapDiagnostics;
}): Promise<void> {
  await appendIncidentRecord(input.stateRoot, {
    runId: input.runId,
    iteration: 0,
    candidateId: "bootstrap",
    incidentType: "bootstrap_failed",
    detail: JSON.stringify(input.diagnostics),
  });
  await appendProblemEventRecord(input.stateRoot, {
    problemEventId: createCandidateId("problem"),
    runId: input.runId,
    iteration: 0,
    candidateId: null,
    problemKind: "bootstrap_failed",
    diagnosis: `Workspace bootstrap failed: ${input.diagnostics.missingTemplateFiles.join(", ")}`,
    evidenceHash: sha256(JSON.stringify(input.diagnostics)),
    suggestedRepairKind: "mutation_prompt_adjustment",
  });
}

async function resolveCompatibilityIssues(input: {
  executor: PineEvaluationExecutor;
  env: RuntimeEnvironment;
  pineScript: string;
}): Promise<LocalCompatibilityIssue[]> {
  const compatibility =
    (await input.executor.assessCompatibility?.({
      source: input.pineScript,
      chartTarget: {
        symbol: input.env.chartSymbol,
        timeframe: input.env.chartTimeframe,
        chartType: input.env.chartType,
      },
    })) ?? {
      supported: true,
      issues: [],
    };
  return compatibility.issues ?? [];
}

function summarizeMutationGenerationFailure(
  error: unknown,
): {
  diagnosis: string;
  nextPromptAdjustment: string;
  suggestedRepairKind: RepairKind;
} {
  const diagnosis = error instanceof Error ? error.message : String(error);
  const lower = diagnosis.toLowerCase();
  const schemaRelated =
    lower.includes("schema") ||
    lower.includes("json") ||
    lower.includes("candidatesummary") ||
    lower.includes("nextmutationhints") ||
    lower.includes("inventory");
  return {
    diagnosis,
    nextPromptAdjustment: schemaRelated
      ? "Reinforce strict JSON structure, required fields, and response completeness before exploring a new mutation."
      : "Tighten the next mutation brief with clearer structural constraints and preserve only ledger-backed guidance.",
    suggestedRepairKind: schemaRelated
      ? "schema_repair"
      : "mutation_prompt_adjustment",
  };
}

function shouldAttemptAutonomousRepair(
  problemEvent: ProblemEventRecord | null | undefined,
): problemEvent is ProblemEventRecord {
  if (!problemEvent) {
    return false;
  }

  return (
    problemEvent.problemKind === "local_unsupported" ||
    problemEvent.problemKind === "local_backtest_fail"
  );
}

function buildProblemRepairInstructions(input: {
  problemEvent: ProblemEventRecord;
  evaluation: Awaited<ReturnType<typeof runLocalEvaluationPhase>>["record"];
}): string[] {
  const instructions = [
    `Previous candidate failed during ${input.problemEvent.problemKind}.`,
    `Diagnosis: ${input.problemEvent.diagnosis}`,
  ];
  const blockingReasons = input.evaluation.eligibility?.blockingReasons ?? [];
  let observedTotalTrades: number | null = null;
  let minimumTotalTrades: number | null = null;
  let observedOosTrades: number | null = null;
  let minimumOosTrades: number | null = null;
  let observedOosPostFeeProfit: number | null = null;
  for (const reason of blockingReasons) {
    instructions.push(`Blocking reason: ${reason.kind} | ${reason.message}`);
    if (reason.evidence) {
      instructions.push(`Evidence: ${JSON.stringify(reason.evidence)}`);
    }
    if (reason.kind === "low_trade_count") {
      minimumTotalTrades = readNumericEvidence(reason.evidence, "minimumTotalTrades");
      observedTotalTrades =
        readNumericEvidence(reason.evidence, "observedTotalTrades") ??
        readNumericEvidence(reason.evidence, "totalTrades");
      if (minimumTotalTrades != null && observedTotalTrades != null) {
        instructions.push(
          `Raise full-sample trades from ${observedTotalTrades} to at least ${minimumTotalTrades}.`,
        );
      }
    }
    if (reason.kind === "oos_trade_count_fail") {
      minimumOosTrades = readNumericEvidence(reason.evidence, "minimumOosTrades");
      observedOosTrades = readNumericEvidence(reason.evidence, "observedOosTrades");
      if (minimumOosTrades != null && observedOosTrades != null) {
        instructions.push(
          `Raise out-of-sample trades from ${observedOosTrades} to at least ${minimumOosTrades}.`,
        );
      }
    }
    if (reason.kind === "robustness_fail") {
      observedOosPostFeeProfit = readNumericEvidence(
        reason.evidence,
        "oosPostFeeNetProfitPercent",
      );
      if (observedOosPostFeeProfit != null) {
        instructions.push(
          `Keep out-of-sample post-fee net profit positive; current value is ${observedOosPostFeeProfit}.`,
        );
      }
    }
  }

  const hasTradeCountFailure = blockingReasons.some(
    (reason) =>
      reason.kind === "low_trade_count" || reason.kind === "oos_trade_count_fail",
  );
  const hasRobustnessFailure = blockingReasons.some(
    (reason) => reason.kind === "robustness_fail",
  );

  if (hasTradeCountFailure) {
    instructions.push(
      "Treat this as a trade-retention repair, not a cosmetic optimization pass.",
      "Remove secondary confirmations, cooldown-heavy logic, and narrow regime gates before adding any new subsystem.",
      "Prefer one primary entry trigger and at most one lightweight regime filter until the candidate clears the trade floors.",
    );
  }

  if (hasTradeCountFailure && hasRobustnessFailure) {
    const profileSummary =
      observedTotalTrades != null &&
      minimumTotalTrades != null &&
      observedOosTrades != null &&
      minimumOosTrades != null
        ? `Recent profile stalled at ${observedTotalTrades}/${minimumTotalTrades} full-sample trades and ${observedOosTrades}/${minimumOosTrades} OOS trades.`
        : "Recent profile still failed both the total-trade and OOS-trade requirements.";
    instructions.push(
      profileSummary,
      "Do not preserve the current sparse trade profile.",
      "Increase OOS trade retention first, but keep OOS post-fee profit positive while doing so.",
    );
    if (observedOosPostFeeProfit != null) {
      instructions.push(
        `Current OOS post-fee profit is ${observedOosPostFeeProfit}; keep it positive while lifting OOS trades.`,
      );
    }
  }

  if (input.problemEvent.suggestedRepairKind === "mutation_prompt_adjustment") {
    instructions.push(
      "Adjust the entry frequency, confirmation pressure, or trade retention so the local backtest clears the trade-count and OOS gates.",
    );
  }
  if (input.problemEvent.suggestedRepairKind === "archive_gap_redirect") {
    instructions.push(
      "Generate a structurally different AF candidate to avoid recent duplicate fingerprint families.",
    );
  }
  if (input.problemEvent.suggestedRepairKind === "pine_source_repair") {
    instructions.push(
      "Repair the Pine source directly without changing the overall research objective.",
    );
  }

  instructions.push(
    "Return a strict JSON mutation response and keep the candidate compatible with the AF local-first executor.",
  );
  return instructions;
}

function readNumericEvidence(
  evidence: Record<string, unknown> | undefined,
  key: string,
): number | null {
  const value = evidence?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function withTimeout<T>(
  run: (signal: AbortSignal) => Promise<T>,
  timeoutMs: number,
  message: string,
  parentSignal?: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const controller = new AbortController();
    let settled = false;

    const cleanup = () => {
      clearTimeout(timeout);
      parentSignal?.removeEventListener("abort", onParentAbort);
      controller.signal.removeEventListener("abort", onAbort);
    };
    const rejectOnce = (error: unknown) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      reject(error);
    };
    const onAbort = () => {
      rejectOnce(
        controller.signal.reason instanceof Error
          ? controller.signal.reason
          : new Error(message),
      );
    };
    const onParentAbort = () => {
      controller.abort(
        parentSignal?.reason instanceof Error
          ? parentSignal.reason
          : new Error(message),
      );
    };
    const timeout = setTimeout(() => {
      controller.abort(new Error(message));
    }, timeoutMs);

    controller.signal.addEventListener("abort", onAbort, { once: true });
    if (parentSignal?.aborted) {
      onParentAbort();
    } else {
      parentSignal?.addEventListener("abort", onParentAbort, { once: true });
    }

    if (controller.signal.aborted) {
      return;
    }

    run(controller.signal)
      .then((value) => {
        if (controller.signal.aborted) {
          return;
        }
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        resolve(value);
      })
      .catch((error) => {
        rejectOnce(error);
      });
  });
}

function resolvePhaseTimeouts(
  openAiRequestTimeoutMs: number,
  calibrationTimeoutMs: number,
  overrides?: Partial<AutonomousLoopPhaseTimeouts>,
): AutonomousLoopPhaseTimeouts {
  return {
    bootstrapMs: 30_000,
    mutationMs: Math.min(
      Math.max(openAiRequestTimeoutMs + 10_000, 135_000),
      150_000,
    ),
    localEvaluationMs: 60_000,
    repairMs: Math.min(
      Math.max(openAiRequestTimeoutMs + 10_000, 90_000),
      150_000,
    ),
    archiveUpdateMs: 15_000,
    calibrationEnqueueMs: 15_000,
    calibrationProcessMs: calibrationTimeoutMs,
    strategyReviewMs: openAiRequestTimeoutMs,
    autoSelectionMs: 15_000,
    rebuildIndexesMs: 20_000,
    ...overrides,
  };
}

function buildCandidateIdSet(records: Array<{ candidateId: string }>): Set<string> {
  return new Set(records.map((record) => record.candidateId));
}

function filterByCandidateId<T extends { candidateId?: string | null }>(
  records: T[],
  candidateIds: Set<string>,
): T[] {
  if (candidateIds.size === 0) {
    return [];
  }
  return records.filter((record) =>
    record.candidateId != null && candidateIds.has(record.candidateId),
  );
}

function filterHeadEventsForTarget<T extends {
  candidateId: string;
  previousChampionId?: string | null;
}>(
  records: T[],
  candidateIds: Set<string>,
): T[] {
  if (candidateIds.size === 0) {
    return [];
  }
  return records.filter(
    (record) =>
      candidateIds.has(record.candidateId) ||
      (record.previousChampionId != null && candidateIds.has(record.previousChampionId)),
  );
}

function filterRepairAttemptsForTarget<T extends {
  candidateId?: string | null;
  repairedCandidateId?: string | null;
}>(
  records: T[],
  candidateIds: Set<string>,
): T[] {
  if (candidateIds.size === 0) {
    return [];
  }
  return records.filter(
    (record) =>
      (record.candidateId != null && candidateIds.has(record.candidateId)) ||
      (record.repairedCandidateId != null && candidateIds.has(record.repairedCandidateId)),
  );
}

function filterMutationBriefsForTarget<T extends {
  acceptedHeadCandidateId?: string | null;
}>(
  records: T[],
  candidateIds: Set<string>,
): T[] {
  if (candidateIds.size === 0) {
    return [];
  }
  return records.filter(
    (record) =>
      record.acceptedHeadCandidateId != null &&
      candidateIds.has(record.acceptedHeadCandidateId),
  );
}

function filterBranchRecordsForTarget<T extends {
  parentCandidateId?: string | null;
  lastCandidateId?: string | null;
}>(
  records: T[],
  candidateIds: Set<string>,
): T[] {
  if (candidateIds.size === 0) {
    return [];
  }
  return records.filter(
    (record) =>
      (record.parentCandidateId != null && candidateIds.has(record.parentCandidateId)) ||
      (record.lastCandidateId != null && candidateIds.has(record.lastCandidateId)),
  );
}

async function maybeAutoProcessCalibration(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  objective: Awaited<ReturnType<typeof loadObjectiveConfig>>;
  env: RuntimeEnvironment;
  calibrationExecutorFactory?: () => PineEvaluationExecutor;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}): Promise<void> {
  const experiments = await readExperimentRecords(input.stateRoot);
  const calibrationEvents = await readCalibrationEventRecords(input.stateRoot);
  const confidenceEvents = await readLocalConfidenceEventRecords(input.stateRoot);
  const pendingCandidateIds = selectPendingCalibrationCandidates({
    events: calibrationEvents,
    experiments,
  });
  if (pendingCandidateIds.length === 0 || input.env.calibrationBudget <= 0) {
    await input.monitor?.log(
      "autonomous.calibration.skipped",
      "No queued calibration candidates were auto-processed",
      {
        pendingCalibrationCandidateCount: pendingCandidateIds.length,
        calibrationBudget: input.env.calibrationBudget,
      },
    );
    return;
  }

  const configTvHealth = resolveTvHealthStatus(input.env);
  if (input.env.tvCalibrationMode !== "mock-recovered") {
    if (configTvHealth !== "healthy") {
      await input.monitor?.log(
        "autonomous.calibration.skipped",
        "Skipped auto calibration because TradingView is not healthy",
        {
          tvHealth: configTvHealth,
          pendingCalibrationCandidateCount: pendingCandidateIds.length,
        },
      );
      return;
    }
    if (!input.calibrationExecutorFactory) {
      await input.monitor?.log(
        "autonomous.calibration.skipped",
        "Skipped auto calibration because no calibration executor factory was provided",
        {
          pendingCalibrationCandidateCount: pendingCandidateIds.length,
        },
      );
      return;
    }
    const calibrationExecutor = input.calibrationExecutorFactory();
    try {
      const health = await calibrationExecutor.healthCheck();
      if (!health.healthy || health.status !== "ready") {
        await input.monitor?.log(
          "autonomous.calibration.skipped",
          "Skipped auto calibration because the calibration executor health check is not ready",
          {
            pendingCalibrationCandidateCount: pendingCandidateIds.length,
            executorHealth: health,
          },
        );
        return;
      }
    } finally {
      await calibrationExecutor.close?.();
    }
  }

  const result = await processTvCalibrationQueue({
    workspaceRoot: input.workspaceRoot,
    stateRoot: input.stateRoot,
    runId: input.runId,
    objective: input.objective,
    env: input.env,
    experiments,
    calibrationEvents,
    confidenceEvents,
    executorFactory: input.calibrationExecutorFactory,
    maxCandidates: input.env.calibrationBudget,
    signal: input.signal,
    monitor: input.monitor,
  });
  await input.monitor?.log(
    "autonomous.calibration.processed",
    "Auto calibration processed queued candidates",
    {
      processedCandidateIds: result.processedCandidateIds,
      calibrationBudget: input.env.calibrationBudget,
      tvCalibrationMode: input.env.tvCalibrationMode,
    },
  );
}

async function finalizeAutonomousLocalEvaluation(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  objective: Awaited<ReturnType<typeof loadObjectiveConfig>>;
  env: RuntimeEnvironment;
  calibrationExecutorFactory?: () => PineEvaluationExecutor;
  llmClient: MutationLlmClient;
  localEvaluation: Awaited<ReturnType<typeof runLocalEvaluationPhase>>;
  phaseTimeouts: AutonomousLoopPhaseTimeouts;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}): Promise<{
  activeChampionChanged: boolean;
  selectedCandidateId: string | null;
}> {
  await runPhase({
    monitor: input.monitor,
    phase: "archive_update",
    message: "Updating autonomous archive views",
    timeoutMs: input.phaseTimeouts.archiveUpdateMs,
    signal: input.signal,
    run: () =>
      runArchiveUpdatePhase({
        stateRoot: input.stateRoot,
        runId: input.runId,
        iteration: input.iteration,
        evaluation: input.localEvaluation.record,
        shouldArchive: input.localEvaluation.shouldArchive,
      }),
  });

  await runPhase({
    monitor: input.monitor,
    phase: "strategy_review",
    message: "Reviewing strategy candidate for next mutation guidance",
    timeoutMs: input.phaseTimeouts.strategyReviewMs,
    signal: input.signal,
    run: async (signal) => {
      const [
        experiments,
        headEvents,
        calibrationEvents,
        problemEvents,
        repairAttempts,
        mutationBriefs,
        researchKnowledge,
      ] = await Promise.all([
        readExperimentRecords(input.stateRoot),
        readHeadEventRecords(input.stateRoot),
        readCalibrationEventRecords(input.stateRoot),
        readProblemEventRecords(input.stateRoot),
        readRepairAttemptRecords(input.stateRoot),
        readMutationBriefRecords(input.stateRoot),
        readResearchKnowledgeRecords(input.stateRoot),
      ]);
      await runStrategyReviewPhase({
        stateRoot: input.stateRoot,
        runId: input.runId,
        iteration: input.iteration,
        targetId: input.env.researchTargetId,
        objective: input.objective,
        record: input.localEvaluation.record,
        experiments,
        headEvents,
        calibrationEvents,
        problemEvents,
        repairAttempts,
        mutationBriefs,
        researchKnowledge,
        llmClient: input.llmClient,
        mode: input.env.strategyReviewMode,
        deepBudget: input.env.strategyReviewDeepBudget,
        signal,
        monitor: input.monitor,
      });
    },
  });

  if (
    input.localEvaluation.shouldQueueCalibration ||
    input.localEvaluation.record.eligibility?.bootstrapEligible === true
  ) {
    await runPhase({
      monitor: input.monitor,
      phase: "calibration_enqueue",
      message: "Queueing candidate for TradingView calibration",
      timeoutMs: input.phaseTimeouts.calibrationEnqueueMs,
      signal: input.signal,
      run: async () => {
        const tvHealth = resolveTvHealthStatus(input.env);
        await enqueueCalibrationCandidate({
          stateRoot: input.stateRoot,
          runId: input.runId,
          iteration: input.iteration,
          localRecord: input.localEvaluation.record,
          tvHealthAtQueueTime: tvHealth,
          reason:
            tvHealth === "unavailable"
              ? "tv_unavailable_deferred"
              : input.localEvaluation.record.selectionPhase === "bootstrap"
                ? "bootstrap_seed_candidate"
                : (input.localEvaluation.record.autoSelectionBreakdown?.noveltyScore ?? 0) >=
                      0.15
                  ? "novelty_frontier_candidate"
                  : "champion_or_eligible_candidate",
        });
      },
    });
  }

  if (input.env.autoProcessCalibration) {
    await runPhase({
      monitor: input.monitor,
      phase: "calibration_process",
      message: "Processing autonomous calibration queue",
      timeoutMs: input.phaseTimeouts.calibrationProcessMs,
      signal: input.signal,
      run: async (signal) => {
        await maybeAutoProcessCalibration({
          workspaceRoot: input.workspaceRoot,
          stateRoot: input.stateRoot,
          runId: input.runId,
          objective: input.objective,
          env: input.env,
          calibrationExecutorFactory: input.calibrationExecutorFactory,
          signal,
          monitor: input.monitor,
        });
      },
    });
  }

  const experimentsAfterLocal = await readExperimentRecords(input.stateRoot);
  const headEventsAfterLocal = await readHeadEventRecords(input.stateRoot);
  const targetExperimentsAfterLocal = filterStrategyReviewRecordsForTarget(
    experimentsAfterLocal,
    input.env.researchTargetId,
    input.objective,
  );
  const targetCandidateIdsAfterLocal = buildCandidateIdSet(targetExperimentsAfterLocal);
  const targetHeadEventsAfterLocal = filterHeadEventsForTarget(
    headEventsAfterLocal,
    targetCandidateIdsAfterLocal,
  );
  const selection = await runPhase({
    monitor: input.monitor,
    phase: "auto_selection",
    message: "Selecting active autonomous champion",
    timeoutMs: input.phaseTimeouts.autoSelectionMs,
    signal: input.signal,
    run: async () =>
      runAutoSelectionPhase({
        stateRoot: input.stateRoot,
        runId: input.runId,
        iteration: input.iteration,
        experiments: targetExperimentsAfterLocal,
        headEvents: targetHeadEventsAfterLocal,
        targetId: input.env.researchTargetId,
        strategyReviewRecords: await readStrategyReviewRecords(input.stateRoot),
        strategyReviewQuarantineConfidence:
          input.env.strategyReviewQuarantineConfidence,
      }),
  });

  await runPhase({
    monitor: input.monitor,
    phase: "rebuild_indexes",
    message: "Rebuilding derived autonomous views",
    timeoutMs: input.phaseTimeouts.rebuildIndexesMs,
    signal: input.signal,
    run: () => rebuildIndexes(input.stateRoot, { mode: "incremental" }),
  });

  return selection;
}

async function recordAutonomousIterationLearning(input: {
  stateRoot: string;
  runId: string;
  iteration: number;
  plan: AutonomousMutationPlan;
  criterionDirective?: CriterionDirective | null;
  localEvaluation: Awaited<ReturnType<typeof runLocalEvaluationPhase>>;
  selection: {
    activeChampionChanged: boolean;
    selectedCandidateId: string | null;
  };
  monitor?: MonitorLike;
}): Promise<void> {
  try {
    const record = buildAutonomousIterationLearningRecord(input);
    await appendAutonomousIterationRecord(input.stateRoot, record);
    await input.monitor?.log(
      "autonomous.iteration_recorded",
      "Recorded autonomous iteration learning summary",
      {
        iteration: record.iteration,
        candidateId: record.candidateId,
        decision: record.decision,
        score: record.score,
        routeId: record.routeId,
      },
    );
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    await input.monitor?.log(
      "autonomous.iteration_record_failed",
      "Failed to record autonomous iteration learning summary",
      { iteration: input.iteration, detail },
    );
    try {
      await appendIncidentRecord(input.stateRoot, {
        runId: input.runId,
        iteration: input.iteration,
        candidateId: input.localEvaluation.record.candidateId,
        incidentType: "autonomous_iteration_record_failed",
        detail,
      });
    } catch {
      // Best-effort observability must not fail an otherwise completed iteration.
    }
  }
}

function buildAutonomousIterationLearningRecord(input: {
  runId: string;
  iteration: number;
  plan: AutonomousMutationPlan;
  criterionDirective?: CriterionDirective | null;
  localEvaluation: Awaited<ReturnType<typeof runLocalEvaluationPhase>>;
  selection: {
    activeChampionChanged: boolean;
    selectedCandidateId: string | null;
  };
}): Omit<AutonomousIterationLearningRecord, "recordedAt"> {
  const brief = input.plan.brief;
  const record = input.localEvaluation.record;
  const metrics = record.testerMetrics;
  const oosMetrics = record.splitEvaluation?.outOfSample.metrics ?? null;
  const blockingReasons =
    record.eligibility?.blockingReasons.map((reason) =>
      truncateSummary(`${reason.kind}: ${reason.message}`, 220),
    ) ?? [];
  const score = record.autoSelectionScore ?? record.candidateScore ?? null;
  const eligible = record.eligibility?.autoSelectionEligible ?? null;
  const criterionOutcome = buildCriterionOutcome({
    directive: input.criterionDirective,
    record,
  });

  return {
    runId: input.runId,
    iteration: input.iteration,
    researchMode: brief.researchMode ?? {
      mode: "continuous_improvement",
      source: "default",
    },
    activeCriterion: input.criterionDirective?.criterion ?? null,
    ...criterionOutcome,
    acceptedHeadCandidateId: brief.acceptedHead?.candidateId ?? null,
    candidateId: record.candidateId,
    briefHash: input.plan.briefHash,
    repairMode: brief.repairMode,
    routeId: brief.explorationDirective?.routeId ?? null,
    variantId: brief.breakoutVariantDirective?.variantId ?? null,
    hypothesis: truncateSummary(brief.analysisGuidance.hypothesis, 600),
    methodSummary: buildIterationMethodSummary(brief),
    resultSummary: buildIterationResultSummary({
      record,
      score,
      eligible,
      championChanged: input.selection.activeChampionChanged,
      selectedCandidateId: input.selection.selectedCandidateId,
    }),
    lessonForNextHypothesis: buildLessonForNextHypothesis({
      brief,
      record,
      blockingReasons,
      championChanged: input.selection.activeChampionChanged,
      score,
    }),
    decision: record.decision,
    score,
    eligible,
    totalTrades: metrics?.totalTrades ?? null,
    oosTrades: oosMetrics?.totalTrades ?? null,
    postFeeNetProfitPercent: metrics?.postFeeNetProfitPercent ?? null,
    oosPostFeeNetProfitPercent: oosMetrics?.postFeeNetProfitPercent ?? null,
    blockingReasons,
    championChanged: input.selection.activeChampionChanged,
    activeChampionCandidateId: input.selection.selectedCandidateId,
  };
}

function buildIterationMethodSummary(brief: MutationBrief): string {
  const parts = [
    `repairMode=${brief.repairMode}`,
    brief.explorationDirective?.routeId
      ? `route=${brief.explorationDirective.routeId}`
      : null,
    brief.breakoutVariantDirective?.variantId
      ? `variant=${brief.breakoutVariantDirective.variantId}`
      : null,
    brief.candidateBehaviorChangeSummary?.changedEntryLogic ?? null,
    brief.nextMutationDirection,
  ].filter((value): value is string => Boolean(value));
  return truncateSummary(parts.join(" | "), 900);
}

function buildIterationResultSummary(input: {
  record: Awaited<ReturnType<typeof runLocalEvaluationPhase>>["record"];
  score: number | null;
  eligible: boolean | null;
  championChanged: boolean;
  selectedCandidateId: string | null;
}): string {
  const metrics = input.record.testerMetrics;
  const oosMetrics = input.record.splitEvaluation?.outOfSample.metrics ?? null;
  const parts = [
    `decision=${input.record.decision}`,
    `eligible=${input.eligible ?? "unknown"}`,
    `score=${formatNullableNumber(input.score)}`,
    `trades=${metrics?.totalTrades ?? "n/a"}`,
    `oosTrades=${oosMetrics?.totalTrades ?? "n/a"}`,
    `postFeeNet=${formatNullableNumber(metrics?.postFeeNetProfitPercent ?? null)}`,
    `oosPostFeeNet=${formatNullableNumber(oosMetrics?.postFeeNetProfitPercent ?? null)}`,
    `championChanged=${input.championChanged}`,
    `activeChampion=${input.selectedCandidateId ?? "none"}`,
  ];
  return truncateSummary(parts.join(" | "), 700);
}

function buildLessonForNextHypothesis(input: {
  brief: MutationBrief;
  record: Awaited<ReturnType<typeof runLocalEvaluationPhase>>["record"];
  blockingReasons: string[];
  championChanged: boolean;
  score: number | null;
}): string {
  if (input.championChanged) {
    return "Promote this hypothesis family as positive evidence; keep the core method while testing small robustness and OOS improvements.";
  }

  const joinedReasons = input.blockingReasons.join(" | ").toLowerCase();
  if (joinedReasons.includes("missing_required_input") || joinedReasons.includes("local_unsupported")) {
    return "Treat the result as AF contract evidence: keep every required input/helper explicit before attempting structural changes.";
  }
  if (joinedReasons.includes("low_trade_count") || joinedReasons.includes("oos_trade_count_fail")) {
    return "Treat the result as sparse-trade negative evidence: broaden the primary entry window and remove secondary filters before optimizing profit.";
  }
  if (
    joinedReasons.includes("robustness_fail") ||
    joinedReasons.includes("positive_oos_post_fee_profit") ||
    (input.record.splitEvaluation?.outOfSample.metrics?.postFeeNetProfitPercent ?? 0) < 0
  ) {
    return "Treat the result as OOS robustness negative evidence: preserve trade count but simplify fragile exit/risk logic and avoid adding new filters.";
  }
  if (input.record.eligibility?.autoSelectionEligible === true) {
    return "Eligible but not promoted: preserve the viable trade-retention method and search for higher score/OOS robustness without changing the route too aggressively.";
  }
  if (input.brief.explorationDirective?.routeId) {
    return `Do not over-trust route ${input.brief.explorationDirective.routeId}; use this outcome as route evidence before repeating the same structure.`;
  }
  return "Treat this outcome as neutral-to-negative evidence and require the next hypothesis to state a measurable change from this method.";
}

function formatNullableNumber(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(4)
    : "n/a";
}

function truncateSummary(value: string, maxLength: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`;
}

async function runPhase<T>(input: {
  monitor?: MonitorLike;
  phase: string;
  message: string;
  timeoutMs: number;
  signal?: AbortSignal;
  run: (signal: AbortSignal) => Promise<T>;
}): Promise<T> {
  const startedAt = Date.now();
  await input.monitor?.log("phase.started", input.message, {
    phase: input.phase,
    timeoutMs: input.timeoutMs,
  });
  try {
    const result = await withTimeout(
      input.run,
      input.timeoutMs,
      `${input.phase} exceeded ${input.timeoutMs}ms`,
      input.signal,
    );
    await input.monitor?.log("phase.completed", input.message, {
      phase: input.phase,
      durationMs: Date.now() - startedAt,
    });
    return result;
  } catch (error) {
    await input.monitor?.log("phase.failed", input.message, {
      phase: input.phase,
      durationMs: Date.now() - startedAt,
      detail: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}
