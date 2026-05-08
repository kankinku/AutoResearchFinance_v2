import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { createMockPineEvaluationExecutor } from "../../src/automation/tradingview/mock-driver.js";
import { createCliMonitor } from "../../src/cli/monitor.js";
import { createStaticLlmClient, type MutationLlmClient } from "../../src/mutation/llm-client.js";
import {
  reconcileStaleTaskBatches,
  runTaskBatch,
} from "../../src/research/task-batch-runner.js";
import { appendTaskBatchRecord } from "../../src/state/jsonl-store.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";

const baseMutationResponse = JSON.stringify({
  candidateSummary: "Task batch candidate",
  nextMutationHints: ["keep-risk-bounded"],
  pineScript: "//@version=5\nstrategy('Task Batch', overlay=true)\n",
  inventory: [
    {
      conditionId: "entry-alpha",
      role: "entry",
      summary: "Entry condition",
      pineLineHints: [10],
    },
  ],
});

describe("runTaskBatch", () => {
  test("completes a bounded task batch and writes task ledgers", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-task-batch-"));
    const monitorLines: string[] = [];
    const monitor = await createCliMonitor({
      workspaceRoot: workspace,
      commandName: "run-tasks",
      sink: (line) => monitorLines.push(line),
    });

    const result = await runTaskBatch({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor(),
      taskCount: 3,
      maxRuntimeFailures: 2,
      runId: "run-batch-1",
      chartType: "candles",
      maxTrades: 50,
      monitor,
    });
    await monitor.close();

    const knowledgePaths = resolveKnowledgePaths(path.join(workspace, "state", "pi-autoresearch"));
    const taskBatches = (await readFile(knowledgePaths.taskBatchesPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    const tasks = (await readFile(knowledgePaths.tasksPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    const taskBoard = JSON.parse(await readFile(knowledgePaths.taskBoardPath, "utf8"));

    expect(result.status).toBe("completed");
    expect(result.completedTaskCount).toBe(3);
    expect(taskBatches.at(-1)?.status).toBe("completed");
    expect(tasks).toHaveLength(3);
    expect(tasks[0]?.hypothesis?.objective).toContain("QQQ 120m");
    expect(tasks[0]?.analysis?.decision).toBeTruthy();
    expect(tasks[0]?.analysis?.pineAnalysisSummary).toMatchObject({
      status: "available",
    });
    expect(tasks[0]?.analysis?.finalAnalysisSummary).toMatchObject({
      status: "available",
    });
    expect(taskBoard.batches[0]?.completedTaskCount).toBe(3);
    expect(monitorLines[0]).toContain("batch:");
    expect(monitorLines).toContain("-------task 01----------");
  }, 10000);

  test("runs research refresh after every configured three tasks", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-task-batch-refresh-"));
    const refreshCalls: Array<{ batchId: string; taskNumbers: number[] }> = [];

    const result = await runTaskBatch({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor(),
      taskCount: 3,
      maxRuntimeFailures: 2,
      runId: "run-batch-refresh-1",
      chartType: "candles",
      maxTrades: 50,
      env: {
        projectRoot: process.cwd(),
        workspaceRoot: workspace,
        stateRoot: path.join(workspace, "state", "pi-autoresearch"),
        researchTargetId: "qqq-120m-af",
        openAiAuthMode: "oauth_proxy",
        openAiBaseUrl: "http://127.0.0.1:10531/v1",
        openAiModel: "gpt-5.4",
        openAiApiKey: undefined,
        openAiRequestTimeoutMs: 180_000,
        openAiMaxRetries: 3,
        openAiOauthProxyCommand: "npx openai-oauth",
        openAiOauthAuthFilePath: undefined,
        mutationStaticResponsePath: undefined,
        evaluationUseMock: false,
        evaluationExecutor: "tradingview-desktop-cdp",
        promotionVerificationExecutor: "none",
        tradingViewDesktopPath: undefined,
        tradingViewCdpUrl: "http://127.0.0.1:9222",
        pineEditorTimeoutMs: 15_000,
        tradingViewCdpCommandTimeoutMs: 8_000,
        chartSymbol: "QQQ",
        chartTimeframe: "120",
        chartType: "candles",
        maxTrades: 50,
        researchRefreshEveryTasks: 3,
        alphaXivMcpUrl: "https://api.alphaxiv.org/mcp/v1",
        alphaXivMcpBearerToken: "token",
        alphaXivAuthFilePath: undefined,
        alphaXivSessionFilePath: undefined,
        tvCalibrationMode: "live",
        mutationSchemaMode: "strict",
        autonomousBootstrapMode: "disabled",
        autoProcessCalibration: false,
        calibrationBudget: 1,
        calibrationTimeoutMs: 30_000,
        strategyReviewMode: "selective",
        strategyReviewDeepBudget: 3,
        strategyReviewMinConfidence: 0.7,
        strategyReviewQuarantineConfidence: 0.85,
        researchModeConfig: {
          mode: "continuous_improvement",
          source: "default",
        },
      },
      researchRefreshEveryTasks: 3,
      researchRefreshRunner: async (input) => {
        refreshCalls.push({
          batchId: input.batchId,
          taskNumbers: input.tasks.map((task) => task.taskNumber),
        });
        return {
          status: "ingested",
          reason: "test-refresh",
          artifactPath: null,
          knowledgeIds: ["rsk-test"],
          searchQueries: ["query"],
        };
      },
    });

    expect(result.status).toBe("completed");
    expect(refreshCalls).toHaveLength(1);
    expect(refreshCalls[0]).toEqual({
      batchId: result.batchId,
      taskNumbers: [1, 2, 3],
    });
  }, 10000);

  test("does not count research refresh failures as task runtime failures", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-task-batch-refresh-soft-"));

    const result = await runTaskBatch({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor(),
      taskCount: 3,
      maxRuntimeFailures: 1,
      runId: "run-batch-refresh-soft-1",
      chartType: "candles",
      maxTrades: 50,
      researchRefreshEveryTasks: 3,
      researchRefreshRunner: async () => {
        throw new Error("refresh planner exploded");
      },
    });

    const knowledgePaths = resolveKnowledgePaths(path.join(workspace, "state", "pi-autoresearch"));
    const incidents = (await readFile(knowledgePaths.incidentsPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(result.status).toBe("completed");
    expect(result.runtimeFailureCount).toBe(0);
    expect(
      incidents.some((incident) => incident.incidentType === "research_refresh_runner_failed"),
    ).toBe(true);
    expect(
      incidents.some((incident) => incident.incidentType === "task_runtime_failure"),
    ).toBe(false);
  }, 10000);

  test("stops task batch after runtime failures hit the limit", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-task-batch-stop-"));
    const failingLlmClient: MutationLlmClient = {
      async generateMutation() {
        throw new Error("LLM offline");
      },
      async generateConditionAblation() {
        throw new Error("LLM offline");
      },
      async repairMutation() {
        throw new Error("LLM offline");
      },
    };

    const result = await runTaskBatch({
      workspaceRoot: workspace,
      llmClient: failingLlmClient,
      executor: createMockPineEvaluationExecutor(),
      taskCount: 5,
      maxRuntimeFailures: 2,
      runId: "run-batch-2",
      chartType: "candles",
      maxTrades: 50,
    });

    const knowledgePaths = resolveKnowledgePaths(path.join(workspace, "state", "pi-autoresearch"));
    const taskBatches = (await readFile(knowledgePaths.taskBatchesPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    const tasks = (await readFile(knowledgePaths.tasksPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(result.status).toBe("stopped");
    expect(result.runtimeFailureCount).toBe(2);
    expect(tasks).toHaveLength(2);
    expect(tasks.every((task) => task.status === "generation_failed")).toBe(true);
    expect(tasks.every((task) => task.analysis.decision === "mutation_generation_fail")).toBe(true);
    expect(taskBatches.at(-1)?.stopReason).toContain("generation failures reached 2");
  }, 10000);

  test("reconciles stale running task batches as stopped", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-task-batch-stale-"));
    const stateRoot = path.join(workspace, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendTaskBatchRecord(stateRoot, {
      runId: "run-stale-1",
      batchId: "batch-stale-1",
      targetTaskCount: 10,
      completedTaskCount: 7,
      runtimeFailureCount: 0,
      maxRuntimeFailures: 3,
      status: "running",
      stopReason: null,
      recordedAt: "2026-04-23T00:00:00.000Z",
    });

    const reconciled = await reconcileStaleTaskBatches(stateRoot, 1);
    const taskBatches = (await readFile(knowledgePaths.taskBatchesPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(reconciled).toBe(1);
    expect(taskBatches.at(-1)?.status).toBe("stopped");
    expect(taskBatches.at(-1)?.stopReason).toBe("interrupted_or_stale");
  });

  test("retries the same task after automatic recovery of a generation failure", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-task-batch-autoheal-decision-"));
    let taskRunnerCalls = 0;
    let recoveryCalls = 0;

    const result = await runTaskBatch({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor(),
      taskCount: 1,
      maxRuntimeFailures: 1,
      maxAutoRecoveryAttemptsPerTask: 1,
      runId: "run-batch-autoheal-1",
      chartType: "candles",
      maxTrades: 50,
      taskRunner: async () => {
        taskRunnerCalls += 1;
        if (taskRunnerCalls === 1) {
          return {
            decision: "mutation_generation_fail",
            experiment: {
              runId: "run-batch-autoheal-1",
              iteration: 1,
              candidateId: "genfail-1",
              parentCandidateId: null,
              branchId: "main",
              acceptedHeadCandidateId: null,
              baselineCandidateId: "seed_primary",
              mutationBriefSummary: "LLM offline",
              decision: "mutation_generation_fail",
              status: "mutation_failed",
            },
            conditionContributions: [],
            hypothesis: {
              objective: "recover-openai",
              nextMutationDirection: "retry after auth recovery",
              recentFailures: ["mutation_request_failed"],
              acceptedHeadCandidateId: null,
            },
          };
        }

        return {
          decision: "accepted_no_improvement",
          experiment: {
            runId: "run-batch-autoheal-1",
            iteration: 1,
            candidateId: "cand-1",
            parentCandidateId: null,
            branchId: "main",
            acceptedHeadCandidateId: null,
            baselineCandidateId: "seed_primary",
            candidateScore: 0.42,
            decision: "accepted_no_improvement",
            status: "evaluated",
            objectiveBreakdown: {
              score: 0.42,
              hardGatesPassed: true,
              softGuardrailBreached: false,
              hardGateReasons: [],
              components: {
                netProfitPercent: { rawValue: 12, normalizedValue: 0.3, weight: 0.2, contribution: 0.06 },
                profitFactor: { rawValue: 1.8, normalizedValue: 0.3, weight: 0.2, contribution: 0.06 },
                inverseMaxDrawdown: { rawValue: 8, normalizedValue: 0.8, weight: 0.2, contribution: 0.16 },
                percentProfitable: { rawValue: 58, normalizedValue: 0.58, weight: 0.15, contribution: 0.087 },
                totalTrades: { rawValue: 60, normalizedValue: 0.6, weight: 0.15, contribution: 0.09 },
                avgTradePercent: { rawValue: 0.3, normalizedValue: 0.3, weight: 0.1, contribution: 0.03 },
              },
            },
            nextMutationHints: ["continue"],
            pineAnalysisSummary: {
              status: "available",
              summary: "Targeted entry change.",
              changeScope: "targeted",
              noOpRisk: "medium",
              hypothesisAlignment: "aligned",
              materialChangeDetected: true,
              conditionCount: 1,
              changedLineCount: 3,
              changedRoles: ["entry"],
              blockingIssueCodes: [],
              warningIssueCodes: [],
            },
            finalAnalysisSummary: {
              status: "available",
              verdict: "neutral",
              summary: "Recovered batch task completed.",
              signals: ["recovered"],
              recommendedAction: "continue",
            },
          },
          conditionContributions: [],
          hypothesis: {
            objective: "recover-openai",
            nextMutationDirection: "continue",
            recentFailures: [],
            acceptedHeadCandidateId: null,
          },
        };
      },
      recoveryHooks: {
        async onFailure() {
          recoveryCalls += 1;
          return {
            recovered: true,
            recoveryActions: ["recovered_openai_auth"],
          };
        },
      },
    });

    const knowledgePaths = resolveKnowledgePaths(path.join(workspace, "state", "pi-autoresearch"));
    const incidents = (await readFile(knowledgePaths.incidentsPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(result.status).toBe("completed");
    expect(result.runtimeFailureCount).toBe(0);
    expect(result.completedTaskCount).toBe(1);
    expect(taskRunnerCalls).toBe(2);
    expect(recoveryCalls).toBe(1);
    expect(
      incidents.some((incident) => incident.incidentType === "task_auto_recovery_applied"),
    ).toBe(true);
  });

  test("retries the same task after automatic recovery of a runtime error", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-task-batch-autoheal-runtime-"));
    let taskRunnerCalls = 0;

    const result = await runTaskBatch({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor(),
      taskCount: 1,
      maxRuntimeFailures: 1,
      maxAutoRecoveryAttemptsPerTask: 1,
      runId: "run-batch-autoheal-2",
      chartType: "candles",
      maxTrades: 50,
      taskRunner: async () => {
        taskRunnerCalls += 1;
        if (taskRunnerCalls === 1) {
          throw new Error("Pine editor open timed out after 30000ms.");
        }

        return {
          decision: "accepted_improvement",
          experiment: {
            runId: "run-batch-autoheal-2",
            iteration: 1,
            candidateId: "cand-runtime-1",
            parentCandidateId: null,
            branchId: "main",
            acceptedHeadCandidateId: null,
            baselineCandidateId: "seed_primary",
            candidateScore: 0.75,
            decision: "accepted_improvement",
            status: "evaluated",
            objectiveBreakdown: {
              score: 0.75,
              hardGatesPassed: true,
              softGuardrailBreached: false,
              hardGateReasons: [],
              components: {
                netProfitPercent: { rawValue: 25, normalizedValue: 0.5, weight: 0.2, contribution: 0.1 },
                profitFactor: { rawValue: 2.4, normalizedValue: 0.4, weight: 0.2, contribution: 0.08 },
                inverseMaxDrawdown: { rawValue: 9, normalizedValue: 0.7, weight: 0.2, contribution: 0.14 },
                percentProfitable: { rawValue: 63, normalizedValue: 0.63, weight: 0.15, contribution: 0.0945 },
                totalTrades: { rawValue: 87, normalizedValue: 0.87, weight: 0.15, contribution: 0.1305 },
                avgTradePercent: { rawValue: 0.55, normalizedValue: 0.55, weight: 0.1, contribution: 0.055 },
              },
            },
            nextMutationHints: ["hold gains"],
            pineAnalysisSummary: {
              status: "available",
              summary: "Balanced mutation.",
              changeScope: "balanced",
              noOpRisk: "low",
              hypothesisAlignment: "aligned",
              materialChangeDetected: true,
              conditionCount: 2,
              changedLineCount: 12,
              changedRoles: ["entry", "risk"],
              blockingIssueCodes: [],
              warningIssueCodes: [],
            },
            finalAnalysisSummary: {
              status: "available",
              verdict: "promising",
              summary: "Recovered TradingView surface and finished task.",
              signals: ["tradingview"],
              recommendedAction: "continue",
            },
          },
          conditionContributions: [],
          hypothesis: {
            objective: "recover-tradingview",
            nextMutationDirection: "continue",
            recentFailures: [],
            acceptedHeadCandidateId: null,
          },
        };
      },
      recoveryHooks: {
        async onFailure() {
          return {
            recovered: true,
            recoveryActions: ["restarted_tradingview_surface"],
            executor: createMockPineEvaluationExecutor(),
          };
        },
      },
    });

    expect(result.status).toBe("completed");
    expect(result.runtimeFailureCount).toBe(0);
    expect(taskRunnerCalls).toBe(2);
  });

  test("records batch-level preflight recovery incidents without aborting the batch", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-task-batch-preflight-recovery-"));

    const result = await runTaskBatch({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor(),
      taskCount: 1,
      maxRuntimeFailures: 1,
      runId: "run-batch-preflight-1",
      chartType: "candles",
      maxTrades: 50,
      recoveryHooks: {
        async beforeBatch() {
          return {
            recovered: true,
            recoveryActions: ["started_openai_oauth_proxy"],
          };
        },
      },
    });

    const knowledgePaths = resolveKnowledgePaths(path.join(workspace, "state", "pi-autoresearch"));
    const incidents = (await readFile(knowledgePaths.incidentsPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(result.status).toBe("completed");
    expect(
      incidents.some(
        (incident) =>
          incident.incidentType === "task_batch_preflight_recovery_applied" &&
          incident.iteration === 0 &&
          incident.candidateId === result.batchId,
      ),
    ).toBe(true);
  });

  test("passes fallback policy and batch fallback budget into task runners", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-task-batch-fallback-budget-"));
    const fallbackBudgetObservations: boolean[] = [];
    const factoryCalls: boolean[] = [];

    const result = await runTaskBatch({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor(),
      taskCount: 2,
      maxRuntimeFailures: 1,
      maxFallbacksPerBatch: 1,
      fallbackLocalOnTvRuntimeFailure: false,
      localFallbackExecutorFactory: () => {
        factoryCalls.push(true);
        return createMockPineEvaluationExecutor({
          capability: {
            kind: "local-af-screening",
            authoritative: false,
            confidenceLevel: "screening",
          },
        });
      },
      runId: "run-batch-fallback-budget-1",
      chartType: "candles",
      maxTrades: 50,
      taskRunner: async (input) => {
        fallbackBudgetObservations.push(input.consumeFallbackSlot?.() ?? false);
        return {
          decision: "valid_no_promotion",
          experiment: {
            runId: "run-batch-fallback-budget-1",
            iteration: fallbackBudgetObservations.length,
            candidateId: `cand-fallback-${fallbackBudgetObservations.length}`,
            parentCandidateId: null,
            branchId: "main",
            acceptedHeadCandidateId: null,
            baselineCandidateId: "seed_primary",
            candidateScore: 0.42,
            decision: "valid_no_promotion",
            status: "evaluated",
            nextMutationHints: ["continue"],
            verificationStatus: "not_requested",
            promotionStatus: "not_promoted",
            promotionReady: false,
          },
          conditionContributions: [],
          hypothesis: {
            objective: input.fallbackLocalOnRuntimeFailure
              ? "unexpected"
              : "fallback-disabled",
            nextMutationDirection:
              typeof input.localFallbackExecutorFactory === "function"
                ? "factory-available"
                : "factory-missing",
            recentFailures: [],
            acceptedHeadCandidateId: null,
          },
        };
      },
    });

    expect(result.status).toBe("completed");
    expect(fallbackBudgetObservations).toEqual([true, false]);
    expect(factoryCalls).toHaveLength(0);
  });
});
