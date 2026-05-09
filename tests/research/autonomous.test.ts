import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { beforeEach, describe, expect, test, vi } from "vitest";

const { mockedEvaluateLocalSplit } = vi.hoisted(() => ({
  mockedEvaluateLocalSplit: vi.fn(),
}));

vi.mock("../../src/evaluation/autonomous-scoring.js", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../src/evaluation/autonomous-scoring.js")>();
  return {
    ...actual,
    evaluateLocalSplit: mockedEvaluateLocalSplit,
  };
});

import { loadObjectiveConfig } from "../../src/config/objective.js";
import { resolveTargetStateRoot } from "../../src/config/target-registry.js";
import {
  autonomousExperimentSchema,
  autonomousBranchRecordSchema,
  type ProblemEventRecord,
} from "../../src/contracts/autonomous.js";
import { type RuntimeEnvironment } from "../../src/cli/runtime-config.js";
import {
  type AutonomousIterationLearningRecord,
  type BacktestMetrics,
  type ExperimentRecord,
  type MutationBrief,
  type MutationBriefRecord,
  type MutationProvenance,
  type ObjectiveBreakdown,
} from "../../src/contracts/types.js";
import { evaluateObjective } from "../../src/evaluation/objective.js";
import { createStaticLlmClient } from "../../src/mutation/llm-client.js";
import { runAutoSelectionPhase } from "../../src/research/autonomous/auto-selection-phase.js";
import { runArchiveUpdatePhase } from "../../src/research/autonomous/archive-update-phase.js";
import { runAutonomousLoop } from "../../src/research/autonomous/autonomous-loop.js";
import { resolveStructureFamilyHash } from "../../src/research/autonomous/divergence-update-phase.js";
import { runLocalEvaluationPhase } from "../../src/research/autonomous/local-evaluation-phase.js";
import {
  buildRepairBriefForProblemEvent,
  prepareAutonomousMutationPlan,
} from "../../src/research/autonomous/mutation-planner.js";
import { runStage6ReadinessGate } from "../../src/research/autonomous/stage6-readiness.js";
import { initializeWorkspace } from "../../src/research/workspace.js";
import { rebuildIndexes } from "../../src/state/index-builder.js";
import { buildAutonomousViewPayloads } from "../../src/state/autonomous-index-builder.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";
import {
  appendExperimentRecord,
  appendHeadEventRecord,
  appendProblemEventRecord,
  appendRepairAttemptRecord,
  readArchiveEventRecords,
  readCalibrationEventRecords,
  readCandidateLedgerRecords,
  readExperimentRecords,
  readHeadEventRecords,
  readLocalConfidenceEventRecords,
  readProblemEventRecords,
  readRepairAttemptRecords,
} from "../../src/state/jsonl-store.js";
import { createMockPineEvaluationExecutor } from "../../src/automation/local-backtest/mock-driver.js";
import {
  AUTORESEARCH_CONTRACT_VERSION,
  STRATEGY_SPEC_MUTATION_AUTHORITY,
} from "../../src/policy/autoresearch-contract.js";
import { hashAfStrategySpec } from "../../src/strategy-spec/hash.js";

const testStateRoot = (workspaceRoot: string): string =>
  resolveTargetStateRoot({ workspaceRoot, targetId: "qqq-120m-af" });

vi.setConfig({ testTimeout: 30_000 });

const enqueueCalibrationCandidate = async (..._args: unknown[]): Promise<void> => {
  throw new Error("external calibration queue was removed in local-only mode");
};

const processTvCalibrationQueue = async (..._args: unknown[]): Promise<any> => {
  throw new Error("external calibration queue was removed in local-only mode");
};

function createRuntimeEnv(
  workspaceRoot: string,
  overrides?: Partial<RuntimeEnvironment>,
): RuntimeEnvironment {
  const stateRoot = testStateRoot(workspaceRoot);
  return {
    projectRoot: process.cwd(),
    workspaceRoot,
    stateRoot,
    researchTargetId: "qqq-120m-af",
    openAiAuthMode: "oauth_proxy" as const,
    openAiBaseUrl: "http://127.0.0.1:10531/v1",
    openAiModel: "gpt-5.4",
    openAiApiKey: undefined,
    openAiRequestTimeoutMs: 180_000,
    openAiMaxRetries: 3,
    openAiOauthProxyCommand: "npx openai-oauth",
    openAiOauthAuthFilePath: undefined,
    mutationStaticResponsePath: undefined,
    evaluationUseMock: false,
    evaluationExecutor: "local-backtest" as const,
    promotionVerificationExecutor: "none" as const,
    chartSymbol: "QQQ",
    chartTimeframe: "120",
    chartType: "candles",
    maxTrades: 50,
    researchRefreshEveryTasks: 3,
    alphaXivMcpUrl: "https://api.alphaxiv.org/mcp/v1",
    alphaXivMcpBearerToken: undefined,
    alphaXivAuthFilePath: undefined,
    alphaXivSessionFilePath: undefined,
    mutationSchemaMode: "strict" as const,
    autonomousBootstrapMode: "disabled" as const,
    autoProcessCalibration: false,
    calibrationBudget: 1,
    calibrationTimeoutMs: 30_000,
    strategyReviewMode: "selective" as const,
    strategyReviewDeepBudget: 0,
    strategyReviewMinConfidence: 0.7,
    strategyReviewQuarantineConfidence: 0.85,
    ...overrides,
    researchModeConfig: overrides?.researchModeConfig ?? {
      mode: "continuous_improvement",
      source: "default",
    },
  };
}

function createStrongMetrics(): BacktestMetrics {
  return {
    netProfitPercent: 30,
    postFeeNetProfitPercent: 25,
    profitFactor: 2.3,
    maxStrategyDrawdownPercent: 8,
    percentProfitable: 61,
    totalTrades: 84,
    avgTradePercent: 0.55,
  };
}

const testStrategySpec = {
  version: "af-spec/v1" as const,
  name: "AF Test Spec",
  event: {
    source: "event_floor" as const,
    L1: 8,
    L2: 12,
    L3: 15,
    confirmBars: 2,
    eventFloorBars: 5,
    eventWindowBars: 10,
  },
  regime: {
    trendMode: "Balanced" as const,
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

async function writeTestSpecArtifact(
  workspaceRoot: string,
  candidateId: string,
) {
  const specPath = path.join(
    workspaceRoot,
    "strategies",
    "specs",
    `${candidateId}.json`,
  );
  await mkdir(path.dirname(specPath), { recursive: true });
  await writeFile(specPath, `${JSON.stringify(testStrategySpec, null, 2)}\n`, "utf8");
  return {
    specPath,
    specHash: hashAfStrategySpec(testStrategySpec),
    strategySpec: testStrategySpec,
  };
}

function createSplitPass(
  metrics: BacktestMetrics,
  objectiveBreakdown: ObjectiveBreakdown,
) {
  return {
    splitMethod: "chronological_70_30" as const,
    fullSample: {
      metrics,
      objectiveBreakdown,
      trades: [],
      equity: null,
    },
    inSample: {
      metrics,
      objectiveBreakdown,
      trades: [],
      equity: null,
    },
    outOfSample: {
      metrics: {
        ...metrics,
        totalTrades: 26,
        postFeeNetProfitPercent: 11,
      },
      objectiveBreakdown: {
        ...objectiveBreakdown,
        score: Math.max(objectiveBreakdown.score - 0.05, 0),
      },
      trades: [],
      equity: null,
    },
    minimumOosTrades: 15,
    oosEligible: true,
    oosPassed: true,
    hardGatesPassed: true,
    gateReasons: [],
  };
}

function createSplitFailLowTrades(
  metrics: BacktestMetrics,
  objectiveBreakdown: ObjectiveBreakdown,
) {
  return {
    splitMethod: "chronological_70_30" as const,
    fullSample: {
      metrics,
      objectiveBreakdown,
      trades: [],
      equity: null,
    },
    inSample: {
      metrics,
      objectiveBreakdown,
      trades: [],
      equity: null,
    },
    outOfSample: {
      metrics: {
        ...metrics,
        totalTrades: 2,
        postFeeNetProfitPercent: -1,
      },
      objectiveBreakdown: {
        ...objectiveBreakdown,
        hardGatesPassed: false,
        score: Math.max(objectiveBreakdown.score - 0.3, 0),
      },
      trades: [],
      equity: null,
    },
    minimumOosTrades: 15,
    oosEligible: true,
    oosPassed: false,
    hardGatesPassed: false,
    gateReasons: [
      "minimum_oos_trades",
      "positive_oos_post_fee_profit",
      "oos_hard_gate_fail",
    ],
  };
}

function createBreakoutExperiment(input: {
  iteration: number;
  candidateId: string;
  routeSummary: string;
  totalTrades: number;
  oosTrades: number;
  eligible?: boolean;
  score?: number;
  recordedAt?: string;
}): ExperimentRecord {
  const rejectedReasons = input.oosTrades < 15
    ? [
        "objective_hard_gate_fail",
        "full_sample_hard_gate_fail",
        "minimum_oos_trades",
        "oos_hard_gate_fail",
      ]
    : [];
  const eligible = input.eligible ?? rejectedReasons.length === 0;
  return {
    runId: `run-${input.candidateId}`,
    iteration: input.iteration,
    candidateId: input.candidateId,
    parentCandidateId: null,
    branchId: "autonomous-main",
    acceptedHeadCandidateId: "cand-42ed2fa4",
    baselineCandidateId: null,
    decision: eligible ? "local_candidate_eligible" : "local_candidate_rejected",
    status: eligible ? "evaluated" : "rejected",
    candidateScore: input.score ?? (eligible ? 0.77 : 0.61),
    autoSelectionScore: input.score ?? (eligible ? 0.77 : 0.61),
    autoSelectionBreakdown: {
      baseObjectiveScore: 0.51,
      robustnessScore: eligible ? 0.07 : 0.1,
      noveltyScore: eligible ? 0.15 : 0.13,
      diversityScore: 0.05,
      localConfidenceBonus: 0,
      riskPenalty: 0,
      overfitPenalty: 0,
      duplicatePenalty: 0,
      divergencePenalty: 0,
      complexityPenalty: 0.03,
      totalScore: input.score ?? (eligible ? 0.77 : 0.61),
      eligible,
      rejectionReasons: rejectedReasons,
    },
    testerMetrics: {
      ...createStrongMetrics(),
      totalTrades: input.totalTrades,
    },
    splitEvaluation: {
      outOfSample: {
        metrics: {
          ...createStrongMetrics(),
          totalTrades: input.oosTrades,
        },
      },
    },
    mutationBriefSummary: `AF exploration-breakout ${input.routeSummary}`,
    recordedAt:
      input.recordedAt ??
      new Date(Date.UTC(2026, 0, 1, 0, input.iteration)).toISOString(),
  } as ExperimentRecord;
}

function createBreakoutMutationBriefRecord(input: {
  iteration: number;
  routeId:
    | "event_reclaim_reversal"
    | "momentum_continuation_pullback"
    | "mean_reversion_reentry"
    | "volatility_compression_release"
    | "time_boxed_event_rotation";
  recordedAt?: string;
}): MutationBriefRecord {
  return {
    runId: `brief-run-${input.iteration}-${input.routeId}`,
    iteration: input.iteration,
    acceptedHeadCandidateId: "cand-42ed2fa4",
    briefHash: `brief-${input.iteration}-${input.routeId}`,
    promptHash: `prompt-${input.iteration}-${input.routeId}`,
    responseHash: `response-${input.iteration}-${input.routeId}`,
    brief: {
      repairMode: "exploration_breakout",
      explorationDirective: {
        mode: "structure_breakout",
        routeId: input.routeId,
        routeSummary: `route ${input.routeId}`,
        reason: "test",
        ignoredCalibrationGuidance: true,
      },
    } as MutationBrief,
    recordedAt:
      input.recordedAt ??
      new Date(Date.UTC(2026, 0, 1, 0, input.iteration)).toISOString(),
  } as MutationBriefRecord;
}

function createValidMutationProvenance(): MutationProvenance {
  return {
    briefHash: "brief-hash",
    promptHash: "prompt-hash",
    responseHash: "response-hash",
    responseSchemaVersion: "parsed-mutation-response/v1",
    parseStatus: "valid",
    inventorySource: "llm",
    inferredFields: [],
    missingFields: [],
  };
}

function createStrictMutationResponse(candidateSummary: string): string {
  return JSON.stringify({
    candidateSummary,
    nextMutationHints: ["continue autonomous search"],
    pineScript:
      "//@version=5\nstrategy('Strict Autonomous Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n",
    inventory: [
      {
        conditionId: "entrySignal",
        role: "entry",
        summary: "Long when close is above open.",
        pineLineHints: ["entrySignal = close > open"],
      },
    ],
  });
}

async function writeCandidateFile(
  workspaceRoot: string,
  candidateId: string,
  source: string,
) {
  const candidatePath = path.join(
    workspaceRoot,
    "strategies",
    "candidates",
    `${candidateId}.pine`,
  );
  await writeFile(candidatePath, source, "utf8");
  return candidatePath;
}

function createLocalMockExecutor(metrics: BacktestMetrics) {
  return createMockPineEvaluationExecutor({
    capability: {
      kind: "local-af-backtest",
      authoritative: false,
      confidenceLevel: "screening",
      supportedStrategyFamilies: ["AF"],
      role: "primary_local_backtest",
      evidenceAuthority: "local_model",
    },
    metrics,
    trades: [
      {
        entryComment: "entry",
        entryPrice: 100,
        entryTime: "2026-04-20T00:00:00.000Z",
        exitComment: "exit",
        exitPrice: 101,
        exitTime: "2026-04-20T02:00:00.000Z",
        qty: 1,
        profitValue: 1,
        profitPercent: 1,
        runupPercent: 1.2,
        drawdownPercent: 0.4,
      },
    ],
    equity: {
      available: true,
      pointsAvailable: true,
      pointCount: 2,
      finalEquity: 10100,
      maxDrawdownPercent: metrics.maxStrategyDrawdownPercent,
      points: [
        { time: "2026-04-20T00:00:00.000Z", value: 10000 },
        { time: "2026-04-20T02:00:00.000Z", value: 10100 },
      ],
    },
  });
}

describe("autonomous tv-verified v4", () => {
  beforeEach(() => {
    mockedEvaluateLocalSplit.mockReset();
  });

  test("runAutonomousLoop appends local evaluation records without promoting local-only candidates", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-loop-"));
    const stateRoot = testStateRoot(workspaceRoot);
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitPass(metrics, objectiveBreakdown),
    );

    const llmClient = createStaticLlmClient(
      JSON.stringify({
        candidateSummary: "Autonomous loop candidate",
        nextMutationHints: ["increase novelty"],
        pineScript:
          "//@version=5\nstrategy('Auto Loop Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Long entry condition",
            pineLineHints: [3],
          },
        ],
      }),
    );

    const result = await runAutonomousLoop({
      workspaceRoot,
      env: createRuntimeEnv(workspaceRoot),
      llmClient,
      localExecutorFactory: () => createLocalMockExecutor(metrics),
    });

    const experiments = await readExperimentRecords(stateRoot);
    const headEvents = await readHeadEventRecords(stateRoot);
    const localLeaderboard = JSON.parse(
      await readFile(knowledgePaths.localLeaderboardPath, "utf8"),
    ) as {
      activeChampionCandidateId: string | null;
      entries: Array<{ candidateId: string; eligible: boolean }>;
    };

    expect(result.activeChampionChanged).toBe(false);
    expect(result.candidateId).toBeTruthy();
    expect(
      experiments.some(
        (record) =>
          (record as Record<string, unknown>).recordKind === "local_evaluation" &&
          record.candidateId === result.candidateId,
      ),
    ).toBe(true);
    expect(headEvents).toEqual([]);
    expect(localLeaderboard.activeChampionCandidateId).toBeNull();
    expect(localLeaderboard.entries[0]?.candidateId).toBe(result.candidateId);
    expect(localLeaderboard.entries[0]?.eligible).toBe(true);
  });

  test("runAutonomousLoop bootstraps the first fresh-root champion from the local-compatible seed", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-bootstrap-"));
    const stateRoot = testStateRoot(workspaceRoot);
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitPass(metrics, objectiveBreakdown),
    );

    const llmClient = createStaticLlmClient(
      JSON.stringify({
        candidateSummary: "unused bootstrap fallback",
        nextMutationHints: ["unused"],
        pineScript:
          "//@version=5\nstrategy('Unused Bootstrap Fallback', overlay=true)\nif close > open\n    strategy.entry('L', strategy.long)\n",
        inventory: [],
      }),
    );

    const result = await runAutonomousLoop({
      workspaceRoot,
      env: createRuntimeEnv(workspaceRoot, {
        autonomousBootstrapMode: "auto",
      }),
      llmClient,
      localExecutorFactory: () => createLocalMockExecutor(metrics),
    });

    const experiments = await readExperimentRecords(stateRoot);
    const headEvents = await readHeadEventRecords(stateRoot);
    const stateSummary = JSON.parse(
      await readFile(knowledgePaths.autonomousStateSummaryPath, "utf8"),
    ) as {
      activeChampionCandidateId: string | null;
      championOrigin: string | null;
      researchMaturity: string | null;
      bootstrapStatus: string;
      nextPlannedAction: string | null;
    };
    const championRecord = experiments.find(
      (record) => record.candidateId === result.candidateId,
    );

    expect(result.candidateId).toBeTruthy();
    expect(result.activeChampionChanged).toBe(true);
    expect(championRecord).toEqual(
      expect.objectContaining({
        decision: "local_candidate_eligible",
        selectionPhase: "bootstrap",
        bootstrapSource: "local_compatible_seed",
        bootstrapReason: "fresh_state_without_active_champion",
        eligibility: expect.objectContaining({
          bootstrapEligible: true,
        }),
      }),
    );
    expect(headEvents[0]).toEqual(
      expect.objectContaining({
        eventKind: "auto_selected_head",
        selectionPhase: "bootstrap",
        bootstrapSource: "local_compatible_seed",
        researchMaturity: "bootstrap",
      }),
    );
    expect(stateSummary).toEqual(
      expect.objectContaining({
        activeChampionCandidateId: result.candidateId,
        championOrigin: "local_compatible_seed",
        researchMaturity: "bootstrap",
        bootstrapStatus: "complete",
        nextPlannedAction: "mutate_beyond_bootstrap_seed",
      }),
    );
  });

  test("runAutonomousLoop records a repair attempt and promotes the repaired eligible candidate", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-repair-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit
      .mockResolvedValueOnce(createSplitFailLowTrades(metrics, objectiveBreakdown))
      .mockResolvedValueOnce(createSplitPass(metrics, objectiveBreakdown));

    const llmClient = createStaticLlmClient(
      JSON.stringify({
        candidateSummary: "Sparse initial candidate",
        nextMutationHints: ["increase trade frequency"],
        pineScript:
          "//@version=5\nstrategy('Sparse Initial Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Sparse long entry condition",
            pineLineHints: [3],
          },
        ],
      }),
      JSON.stringify({
        candidateSummary: "Recovered repair candidate",
        nextMutationHints: ["preserve the repaired entry frequency"],
        pineScript:
          "//@version=5\nstrategy('Recovered Repair Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Recovered long entry condition",
            pineLineHints: [3],
          },
        ],
      }),
    );

    const result = await runAutonomousLoop({
      workspaceRoot,
      env: createRuntimeEnv(workspaceRoot),
      llmClient,
      localExecutorFactory: () => createLocalMockExecutor(metrics),
    });

    const experiments = await readExperimentRecords(stateRoot);
    const problemEvents = await readProblemEventRecords(stateRoot);
    const repairAttempts = await readRepairAttemptRecords(stateRoot);
    const localEvaluations = experiments.filter(
      (record) => (record as Record<string, unknown>).recordKind === "local_evaluation",
    );

    expect(localEvaluations).toHaveLength(2);
    expect(problemEvents).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          problemKind: "local_backtest_fail",
          suggestedRepairKind: "entry_frequency_repair",
          failureSignatureHash: expect.any(String),
        }),
      ]),
    );
    expect(repairAttempts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          repairKind: "entry_frequency_repair",
          result: "success",
          repairedCandidateId: result.candidateId,
          failureSignatureHash: expect.any(String),
        }),
      ]),
    );
    expect(localEvaluations.map((record) => record.candidateId)).toContain(result.candidateId);
  });

  test("runAutonomousLoop does not persist late LLM output after mutation timeout", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-timeout-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const metrics = createStrongMetrics();
    const lateResponse = createStrictMutationResponse("Late timeout candidate");
    const llmClient = {
      async generateMutation() {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return lateResponse;
      },
      async generateConditionAblation() {
        throw new Error("condition ablation should not be called");
      },
      async repairMutation() {
        throw new Error("repair should not be called after mutation timeout");
      },
    };

    const result = await runAutonomousLoop({
      workspaceRoot,
      env: createRuntimeEnv(workspaceRoot),
      llmClient,
      localExecutorFactory: () => createLocalMockExecutor(metrics),
      phaseTimeouts: {
        mutationMs: 10,
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 80));

    expect(result.candidateId).toBeNull();
    expect(await readCandidateLedgerRecords(stateRoot)).toHaveLength(0);
    expect(
      (await readRepairAttemptRecords(stateRoot)).filter(
        (attempt) => attempt.result === "success",
      ),
    ).toHaveLength(0);
  });

  test("schema repair success links to the persisted repaired candidate", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-schema-repair-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitPass(metrics, objectiveBreakdown),
    );

    const llmClient = createStaticLlmClient(
      "not-json",
      createStrictMutationResponse("Schema repaired candidate"),
    );

    const result = await runAutonomousLoop({
      workspaceRoot,
      env: createRuntimeEnv(workspaceRoot),
      llmClient,
      localExecutorFactory: () => createLocalMockExecutor(metrics),
    });

    const candidateIds = (await readCandidateLedgerRecords(stateRoot)).map(
      (record) => record.candidateId,
    );
    const repairAttempts = await readRepairAttemptRecords(stateRoot);
    const schemaRepair = repairAttempts.find(
      (attempt) =>
        attempt.repairKind === "schema_repair" &&
        attempt.result === "success",
    );

    expect(result.candidateId).not.toBeNull();
    expect(candidateIds).toContain(result.candidateId);
    expect(schemaRepair?.repairedCandidateId).toBe(result.candidateId);
  });

  test("schema repair failure fails fast without a regenerate request", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-schema-fail-fast-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    let generateCalls = 0;

    const llmClient = {
      async generateMutation() {
        generateCalls += 1;
        return "not-json";
      },
      async generateConditionAblation() {
        throw new Error("condition ablation should not be called");
      },
      async repairMutation() {
        return "still-not-json";
      },
    };

    const result = await runAutonomousLoop({
      workspaceRoot,
      env: createRuntimeEnv(workspaceRoot),
      llmClient,
      localExecutorFactory: () => createLocalMockExecutor(createStrongMetrics()),
    });

    const repairAttempts = await readRepairAttemptRecords(stateRoot);

    expect(result.candidateId).toBeNull();
    expect(generateCalls).toBe(1);
    expect(
      repairAttempts.filter((attempt) => attempt.repairKind === "schema_repair"),
    ).toHaveLength(1);
    expect(
      repairAttempts.some((attempt) => attempt.repairKind === "schema_regenerate"),
    ).toBe(false);
  });

  test.skip("runAutonomousLoop keeps calibration candidates queued when external validation is unavailable", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-queue-"));
    const stateRoot = testStateRoot(workspaceRoot);
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitPass(metrics, objectiveBreakdown),
    );

    const llmClient = createStaticLlmClient(
      JSON.stringify({
        candidateSummary: "Deferred calibration candidate",
        nextMutationHints: ["defer external validation"],
        pineScript:
          "//@version=5\nstrategy('Deferred Calibration Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Long entry condition",
            pineLineHints: [3],
          },
        ],
      }),
    );

    const calibrationExecutorFactory = vi.fn(() => createMockPineEvaluationExecutor());
    const result = await runAutonomousLoop({
      workspaceRoot,
      env: createRuntimeEnv(workspaceRoot, {
        promotionVerificationExecutor: "none",
        autoProcessCalibration: false,
      }),
      llmClient,
      localExecutorFactory: () => createLocalMockExecutor(metrics),
      calibrationExecutorFactory,
    });

    const calibrationEvents = await readCalibrationEventRecords(stateRoot);
    const calibrationQueue = JSON.parse(
      await readFile(knowledgePaths.tvCalibrationQueuePath, "utf8"),
    ) as {
      entries: Array<{ candidateId: string; queueReason: string }>;
    };

    expect(result.candidateId).toBeTruthy();
    expect(calibrationEvents).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          eventKind: "calibration_candidate_added",
          candidateId: result.candidateId,
          queueReason: "tv_unavailable_deferred",
        }),
      ]),
    );
    expect(calibrationQueue.entries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          candidateId: result.candidateId,
          queueReason: "tv_unavailable_deferred",
        }),
      ]),
    );
    expect(calibrationExecutorFactory).not.toHaveBeenCalled();
  });

  test.skip("runAutonomousLoop auto-processes mock recovered calibration and applies non-zero confidence feedback to the next local evaluation", async () => {
    const workspaceRoot = await mkdtemp(
      path.join(tmpdir(), "af-autonomous-auto-calibration-"),
    );
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitPass(metrics, objectiveBreakdown),
    );

    const llmClient = createStaticLlmClient(
      JSON.stringify({
        candidateSummary: "Auto calibration seed candidate",
        nextMutationHints: ["seed calibration memory"],
        pineScript:
          "//@version=5\nstrategy('Auto Calibration Seed', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
      }),
    );

    const result = await runAutonomousLoop({
      workspaceRoot,
      env: createRuntimeEnv(workspaceRoot, {
        autoProcessCalibration: true,
        calibrationBudget: 1,
      }),
      llmClient,
      localExecutorFactory: () => createLocalMockExecutor(metrics),
    });

    const experiments = await readExperimentRecords(stateRoot);
    const calibrationEvents = await readCalibrationEventRecords(stateRoot);
    const confidenceEvents = await readLocalConfidenceEventRecords(stateRoot);
    const followupSource =
      "//@version=5\nstrategy('Auto Calibration Followup', overlay=true)\n// keep the same structure family but change the source hash\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n";
    const followupPath = await writeCandidateFile(
      workspaceRoot,
      "cand-auto-calibration-followup",
      followupSource,
    );
    const followupSpec = await writeTestSpecArtifact(
      workspaceRoot,
      "cand-auto-calibration-followup",
    );
    const followup = await runLocalEvaluationPhase({
      workspaceRoot,
      stateRoot,
      runId: "auto-calibration-followup-run",
      iteration: 2,
      executor: createLocalMockExecutor(metrics),
      objective,
      parsedMutation: {
        candidateSummary: "Auto calibration followup candidate",
        nextMutationHints: ["preserve low divergence family"],
        pineScript: followupSource,
        strategySpec: followupSpec.strategySpec,
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [4],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      candidateArtifact: {
        candidateId: "cand-auto-calibration-followup",
        parentId: result.candidateId,
        branchId: "autonomous-main",
        pinePath: followupPath,
        pineHash: "auto-calibration-followup-hash",
        specPath: followupSpec.specPath,
        specHash: followupSpec.specHash,
        studyTitle: "Auto Calibration Followup",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [4],
          },
        ],
        candidateSummary: "Auto calibration followup candidate",
        nextMutationHints: ["preserve low divergence family"],
      },
      mutationProvenance: createValidMutationProvenance(),
      previousExperiments: experiments,
      previousConfidenceEvents: confidenceEvents,
    });
    const plan = await prepareAutonomousMutationPlan({
      workspaceRoot,
      objective,
      experiments,
      headEvents: await readHeadEventRecords(stateRoot),
      archiveEvents: await readArchiveEventRecords(stateRoot),
      calibrationEvents,
      confidenceEvents,
      problemEvents: await readProblemEventRecords(stateRoot),
      repairAttempts: await readRepairAttemptRecords(stateRoot),
    });

    expect(result.candidateId).toBeTruthy();
    expect(
      calibrationEvents.some(
        (event) => event.eventKind === "local_tv_divergence_measured",
      ),
    ).toBe(true);
    expect(confidenceEvents.at(-1)).toEqual(
      expect.objectContaining({
        eventKind: "local_confidence_updated",
        localConfidenceBonus: 0.05,
        divergencePenalty: 0,
      }),
    );
    expect(followup.record.autoSelectionBreakdown?.localConfidenceBonus).toBe(0.05);
    expect(plan.parentCandidateId).toBe(result.candidateId);
    expect(plan.brief.candidateBehaviorChangeSummary).toEqual(
      expect.objectContaining({
        influencedBy: expect.arrayContaining(["calibration_divergence"]),
      }),
    );
    expect(
      plan.brief.candidateBehaviorChangeSummary?.addedConstraints ?? [],
    ).toEqual(
      expect.arrayContaining([
        expect.stringContaining("prefer_low_divergence_family"),
      ]),
    );
  });

  test(
    "runStage6ReadinessGate defaults to local-only readiness",
    async () => {
      const workspaceRoot = await mkdtemp(
        path.join(tmpdir(), "af-stage6-local-core-"),
      );
      const stateRoot = testStateRoot(workspaceRoot);
      const objective = await loadObjectiveConfig(process.cwd());
      const metrics = createStrongMetrics();
      const objectiveBreakdown = evaluateObjective(metrics, objective);
      mockedEvaluateLocalSplit.mockResolvedValue(
        createSplitPass(metrics, objectiveBreakdown),
      );
      const calibrationExecutorFactory = vi.fn(() => createMockPineEvaluationExecutor());

      const result = await runStage6ReadinessGate({
        env: createRuntimeEnv(workspaceRoot, {
          stateRoot,
          autonomousBootstrapMode: "auto",
        }),
        count: 5,
        mode: "deterministic",
        localExecutorFactory: () => createLocalMockExecutor(metrics),
        calibrationExecutorFactory,
      });

      expect(result.passed).toBe(true);
      expect(result.countFailed).toBe(0);
      expect(result.calibrationMode).toBe("local_only");
      expect(result.feedbackClosureRequired).toBe(false);
      expect(result.scoreFeedbackPassed).toBe(true);
      expect(result.calibrationQueuePassed).toBe(true);
      expect(result.feedbackClosureStatus).toEqual(
        expect.objectContaining({
          status: "passed",
          required: false,
          divergenceCount: 0,
          confidenceUpdateCount: 0,
        }),
      );
      expect(calibrationExecutorFactory).not.toHaveBeenCalled();
    },
    60_000,
  );

  test(
    "runStage6ReadinessGate passes deterministic fresh custom root readiness",
    async () => {
      const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-stage6-gate-current-"));
      const stateRoot = testStateRoot(workspaceRoot);
      const objective = await loadObjectiveConfig(process.cwd());
      const metrics = createStrongMetrics();
      const objectiveBreakdown = evaluateObjective(metrics, objective);
      mockedEvaluateLocalSplit.mockResolvedValue(
        createSplitPass(metrics, objectiveBreakdown),
      );

      const result = await runStage6ReadinessGate({
        env: createRuntimeEnv(workspaceRoot, {
          stateRoot,
          autonomousBootstrapMode: "auto",
        }),
        count: 5,
        mode: "deterministic",
        autoProcessCalibration: true,
        localExecutorFactory: () => createLocalMockExecutor(metrics),
        calibrationExecutorFactory: () => createMockPineEvaluationExecutor(),
      });
      const persisted = JSON.parse(
        await readFile(resolveKnowledgePaths(stateRoot).stage6ReadinessPath, "utf8"),
      ) as typeof result;

      expect(result.passed).toBe(true);
      expect(result.freshBootstrapPassed).toBe(true);
      expect(result.multiIterationPassed).toBe(true);
      expect(result.rootIsolationPassed).toBe(true);
      expect(result.repairTraceabilityPassed).toBe(true);
      expect(result.calibrationQueuePassed).toBe(true);
      expect(result.scoreFeedbackPassed).toBe(true);
      expect(result.countFailed).toBe(0);
      expect(persisted.passed).toBe(true);
    },
    60_000,
  );

  test("resolveStructureFamilyHash groups semantically similar AF structures into the same family", () => {
    const first = resolveStructureFamilyHash({
      noveltyFingerprint: {
        fingerprintFamily: "fingerprint-a",
        structureSignature: "structure-a",
        tokens: ["trendMode:WithTrend", "sameBarConflictMode:StrongWins"],
      },
      conditionInventory: [
        {
          conditionId: "entry_primary_trigger",
          role: "entry",
          summary:
            "Any resolved bullish exhaustion event B1/B2/B3/BCONF can open or scale a long slot.",
        },
        {
          conditionId: "entry_filters_bypassed",
          role: "entry",
          summary:
            "Risk-off gating is removed from the effective long path so bullish entries keep trade retention.",
        },
        {
          conditionId: "staged_bearish_exit",
          role: "exit",
          summary:
            "Seed-aligned staged bearish exit behavior closes weakest slots progressively on S1/S2/S3.",
        },
      ],
    });
    const second = resolveStructureFamilyHash({
      noveltyFingerprint: {
        fingerprintFamily: "fingerprint-b",
        structureSignature: "structure-b",
        tokens: ["trendMode:WithTrend", "sameBarConflictMode:StrongWins"],
      },
      conditionInventory: [
        {
          conditionId: "entry_primary_bull_event",
          role: "entry",
          summary:
            "Single primary long trigger remains any resolved new bullish exhaustion event from B1/B2/B3/BCONF.",
        },
        {
          conditionId: "entry_recovery_riskoff_removed",
          role: "entry",
          summary:
            "Risk-off no longer blocks bullish entries, preserving trade density for the same family.",
        },
        {
          conditionId: "staged_bear_exit",
          role: "exit",
          summary:
            "Staged bearish exits are preserved: weaker bears trim slots and stronger bears liquidate losers.",
        },
      ],
    });

    expect(first).toBeTruthy();
    expect(second).toBeTruthy();
    expect(second).toBe(first);
  });

  test("runLocalEvaluationPhase marks exact duplicates as ineligible and exposes them in duplicate-candidates view", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-dup-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitPass(metrics, objectiveBreakdown),
    );

    const pineSource =
      "//@version=5\nstrategy('Duplicate Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n";
    const candidatePathA = await writeCandidateFile(workspaceRoot, "cand-a", pineSource);
    const candidatePathB = await writeCandidateFile(workspaceRoot, "cand-b", pineSource);
    const specA = await writeTestSpecArtifact(workspaceRoot, "cand-a");
    const specB = await writeTestSpecArtifact(workspaceRoot, "cand-b");

    const first = await runLocalEvaluationPhase({
      workspaceRoot,
      stateRoot,
      runId: "dup-run-1",
      iteration: 1,
      executor: createLocalMockExecutor(metrics),
      objective,
      parsedMutation: {
        candidateSummary: "First candidate",
        nextMutationHints: [],
        pineScript: pineSource,
        strategySpec: specA.strategySpec,
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      candidateArtifact: {
        candidateId: "cand-a",
        parentId: null,
        branchId: "autonomous-main",
        pinePath: candidatePathA,
        pineHash: "same-hash",
        specPath: specA.specPath,
        specHash: specA.specHash,
        studyTitle: "Duplicate Candidate",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        candidateSummary: "First candidate",
        nextMutationHints: [],
      },
      mutationProvenance: createValidMutationProvenance(),
      previousExperiments: [],
    });

    const second = await runLocalEvaluationPhase({
      workspaceRoot,
      stateRoot,
      runId: "dup-run-2",
      iteration: 2,
      executor: createLocalMockExecutor(metrics),
      objective,
      parsedMutation: {
        candidateSummary: "Second candidate",
        nextMutationHints: [],
        pineScript: pineSource,
        strategySpec: specB.strategySpec,
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      candidateArtifact: {
        candidateId: "cand-b",
        parentId: null,
        branchId: "autonomous-main",
        pinePath: candidatePathB,
        pineHash: "same-hash",
        specPath: specB.specPath,
        specHash: specB.specHash,
        studyTitle: "Duplicate Candidate",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        candidateSummary: "Second candidate",
        nextMutationHints: [],
      },
      mutationProvenance: createValidMutationProvenance(),
      previousExperiments: await readExperimentRecords(stateRoot),
    });

    await rebuildIndexes(stateRoot);
    const duplicateView = JSON.parse(
      await readFile(resolveKnowledgePaths(stateRoot).duplicateCandidatesPath, "utf8"),
    ) as {
      entries: Array<{ candidateId: string; classification: string }>;
    };

    expect(first.record.autoSelectionBreakdown?.eligible).toBe(true);
    expect(second.record.duplicateStatus?.classification).toBe("exact_duplicate");
    expect(second.record.autoSelectionBreakdown?.eligible).toBe(false);
    expect(duplicateView.entries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          candidateId: "cand-b",
          classification: "exact_duplicate",
        }),
      ]),
    );
  });

  test("runLocalEvaluationPhase writes failure memory for rejection reasons that should steer the next mutation", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-failure-memory-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitFailLowTrades(metrics, objectiveBreakdown),
    );

    const pineSource =
      "//@version=5\nstrategy('Failure Memory Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n";
    const candidatePath = await writeCandidateFile(
      workspaceRoot,
      "cand-failure-memory",
      pineSource,
    );
    const spec = await writeTestSpecArtifact(workspaceRoot, "cand-failure-memory");

    const result = await runLocalEvaluationPhase({
      workspaceRoot,
      stateRoot,
      runId: "failure-memory-run",
      iteration: 1,
      executor: createLocalMockExecutor(metrics),
      objective,
      parsedMutation: {
        candidateSummary: "Failure memory candidate",
        nextMutationHints: [],
        pineScript: pineSource,
        strategySpec: spec.strategySpec,
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      candidateArtifact: {
        candidateId: "cand-failure-memory",
        parentId: null,
        branchId: "autonomous-main",
        pinePath: candidatePath,
        pineHash: "failure-memory-hash",
        specPath: spec.specPath,
        specHash: spec.specHash,
        studyTitle: "Failure Memory Candidate",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        candidateSummary: "Failure memory candidate",
        nextMutationHints: [],
      },
      mutationProvenance: createValidMutationProvenance(),
      previousExperiments: [],
    });

    const problemEvents = await readProblemEventRecords(stateRoot);

    expect(result.record.decision).toBe("local_candidate_rejected");
    expect(problemEvents).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          candidateId: "cand-failure-memory",
          problemKind: "local_backtest_fail",
          suggestedRepairKind: "entry_frequency_repair",
          failureSignatureHash: expect.any(String),
        }),
      ]),
    );
    expect(
      problemEvents.some((event) => event.diagnosis.includes("minimum_oos_trades")),
    ).toBe(true);
  });

  test("local compatibility summary normalizes historical unsupported reasons and repair success rates", async () => {
    const stateRoot = path.join(
      await mkdtemp(path.join(tmpdir(), "af-autonomous-compat-summary-")),
      "state",
      "pi-autoresearch",
    );
    const problemEvent = await appendProblemEventRecord(stateRoot, {
      problemEventId: "problem-unsupported-1",
      runId: "run-unsupported-1",
      iteration: 1,
      candidateId: "cand-unsupported-1",
      problemKind: "local_unsupported",
      diagnosis: "Missing inputs: trendMode, riskOffRsi",
      evidenceHash: "unsupported-evidence-1",
      suggestedRepairKind: "local_compatibility_repair",
      failureSignatureHash: "unsupported-signature-1",
      structureFamily: "family-unsupported-1",
    });
    await appendRepairAttemptRecord(stateRoot, {
      repairAttemptId: "repair-unsupported-1",
      problemEventId: problemEvent.problemEventId,
      runId: "run-unsupported-1",
      iteration: 1,
      candidateId: "cand-unsupported-1",
      repairedCandidateId: null,
      repairKind: "local_compatibility_repair",
      llmPromptHash: "prompt-unsupported-1",
      llmResponseHash: "response-unsupported-1",
      result: "success",
      failureReason: null,
      summary: "Recovered missing inputs for the AF contract.",
      failureSignatureHash: "unsupported-signature-1",
      structureFamily: "family-unsupported-1",
    });

    const views = buildAutonomousViewPayloads({
      experiments: [],
      headEvents: [],
      archiveEvents: [],
      calibrationEvents: [],
      confidenceEvents: [],
      problemEvents: [problemEvent],
      repairAttempts: await readRepairAttemptRecords(stateRoot),
    });

    expect(views.localCompatibilitySummary.unsupportedReasonCounts).toMatchObject({
      "Missing inputs: trendMode, riskOffRsi": 1,
    });
    expect(views.localCompatibilitySummary.missingInputsCounts).toMatchObject({
      trendMode: 1,
      riskOffRsi: 1,
    });
    expect(views.localCompatibilitySummary.recentUnsupportedExamples).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          candidateId: "cand-unsupported-1",
          diagnosis: "Missing inputs: trendMode, riskOffRsi",
          missingInputs: expect.arrayContaining(["trendMode", "riskOffRsi"]),
        }),
      ]),
    );
    expect(
      views.localCompatibilitySummary.repairAttemptSuccessRateByReason[
        "Missing inputs: trendMode, riskOffRsi"
      ],
    ).toEqual(
      expect.objectContaining({
        attempts: 1,
        successes: 1,
        successRate: 1,
      }),
    );
  });

  test("local compatibility summary derives unsupported details from candidate source when legacy fields are missing", async () => {
    const workspaceRoot = await mkdtemp(
      path.join(tmpdir(), "af-autonomous-compat-source-derived-"),
    );
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const candidatePath = await writeCandidateFile(
      workspaceRoot,
      "cand-source-derived-unsupported",
      [
        "//@version=5",
        "strategy('Source Derived Unsupported', overlay=true)",
        "indicator('forbidden helper')",
      ].join("\n"),
    );

    await appendExperimentRecord(stateRoot, {
      runId: "run-source-derived-unsupported",
      iteration: 1,
      candidateId: "cand-source-derived-unsupported",
      parentCandidateId: null,
      branchId: "autonomous-main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: null,
      candidatePath,
      candidateHash: "hash-source-derived-unsupported",
      studyTitle: "Source Derived Unsupported",
      candidateScore: null,
      decision: "local_unsupported",
      status: "unsupported",
      recordKind: "local_evaluation",
      executorRole: "primary_local_backtest",
      evidenceAuthority: "local_model",
      evaluationMode: "local_primary",
      mutationBriefSummary: "Unsupported candidate without persisted compatibility details.",
      conditionInventory: [],
      mutationProvenance: createValidMutationProvenance(),
      splitEvaluation: null,
      noveltyFingerprint: null,
      structureFamilyHash: null,
      fingerprintFamily: null,
      duplicateStatus: null,
      autoSelectionScore: null,
      autoSelectionBreakdown: null,
      objectivePolicyVersion: "objective.qqq-120m/v1",
      selectionPolicyVersion: "autonomous-local-first/v3-p0",
      localConfidence: 1,
      tvCalibrationStatus: "not_requested",
      localTvParity: null,
      localCompatibility: null,
      eligibility: null,
      artifactPaths: { candidate: candidatePath },
      recordMeta: {
        schemaVersion: "experiment/v3",
        recordHash: "record-hash-source-derived-unsupported",
        candidateHash: "hash-source-derived-unsupported",
        baselineHash: null,
        artifactBundleHash: null,
        pipelineVersion: "af-autonomous-local-first/v3",
      },
      recordedAt: new Date().toISOString(),
    });

    const experiments = await readExperimentRecords(stateRoot);
    const views = buildAutonomousViewPayloads({
      experiments,
      headEvents: [],
      archiveEvents: [],
      calibrationEvents: [],
      confidenceEvents: [],
      problemEvents: [],
      repairAttempts: [],
    });

    expect(views.localCompatibilitySummary.unsupportedReasonCounts).toMatchObject({
      "missing required AF inputs; missing required AF helper functions; uses unsupported AF patterns.": 1,
    });
    expect(views.localCompatibilitySummary.missingInputsCounts).toMatchObject({
      L1: 1,
      trendMode: 1,
    });
    expect(views.localCompatibilitySummary.missingFunctionsCounts).toMatchObject({
      f_find_weakest_idx: 1,
    });
    expect(views.localCompatibilitySummary.unsupportedPatternCounts).toMatchObject({
      "unsupported_pattern:indicator(": 1,
    });
  });

  test("runLocalEvaluationPhase escalates repeated failure signatures to archive gap redirect", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-failure-escalation-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitFailLowTrades(metrics, objectiveBreakdown),
    );

    const pineSource =
      "//@version=5\nstrategy('Failure Escalation Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n";

    const runFailure = async (candidateId: string) => {
      const candidatePath = await writeCandidateFile(workspaceRoot, candidateId, pineSource);
      const spec = await writeTestSpecArtifact(workspaceRoot, candidateId);
      const experiments = await readExperimentRecords(stateRoot);
      return runLocalEvaluationPhase({
        workspaceRoot,
        stateRoot,
        runId: `${candidateId}-run`,
        iteration: experiments.length + 1,
        executor: createLocalMockExecutor(metrics),
        objective,
        parsedMutation: {
          candidateSummary: "Failure escalation candidate",
          nextMutationHints: [],
          pineScript: pineSource,
          strategySpec: spec.strategySpec,
          inventory: [
            {
              conditionId: "entry-alpha",
              role: "entry",
              summary: "Entry condition",
              pineLineHints: [3],
            },
          ],
          inventorySource: "llm",
          missingFields: [],
          inferredFields: [],
        },
        candidateArtifact: {
          candidateId,
          parentId: null,
          branchId: "autonomous-main",
          pinePath: candidatePath,
          pineHash: `hash-${candidateId}`,
          specPath: spec.specPath,
          specHash: spec.specHash,
          studyTitle: "Failure Escalation Candidate",
          inventory: [
            {
              conditionId: "entry-alpha",
              role: "entry",
              summary: "Entry condition",
              pineLineHints: [3],
            },
          ],
          candidateSummary: "Failure escalation candidate",
          nextMutationHints: [],
        },
        mutationProvenance: createValidMutationProvenance(),
        previousExperiments: [],
        previousProblemEvents: await readProblemEventRecords(stateRoot),
        previousRepairAttempts: await readRepairAttemptRecords(stateRoot),
      });
    };

    const first = await runFailure("cand-failure-escalation-1");
    await appendRepairAttemptRecord(stateRoot, {
      repairAttemptId: "repair-failure-escalation-1",
      problemEventId: first.problemEvent!.problemEventId,
      runId: "repair-run-1",
      iteration: 1,
      candidateId: first.record.candidateId,
      repairedCandidateId: "cand-failure-escalation-repair-1",
      repairKind: "entry_frequency_repair",
      llmPromptHash: "prompt-hash-1",
      llmResponseHash: "response-hash-1",
      result: "success",
      failureReason: null,
      summary: "First repair attempt",
    });
    const second = await runFailure("cand-failure-escalation-2");
    const third = await runFailure("cand-failure-escalation-3");

    expect(first.problemEvent?.failureSignatureHash).toBeTruthy();
    expect(second.problemEvent?.failureSignatureHash).toBe(
      first.problemEvent?.failureSignatureHash,
    );
    expect(third.problemEvent?.failureSignatureHash).toBe(
      first.problemEvent?.failureSignatureHash,
    );
    expect(third.problemEvent?.suggestedRepairKind).toBe("archive_gap_redirect");
  });

  test("prepareAutonomousMutationPlan hardens repeated trade retention clusters", async () => {
    const workspaceRoot = await mkdtemp(
      path.join(tmpdir(), "af-autonomous-trade-retention-plan-"),
    );
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const recordedAt = new Date().toISOString();
    const problemEvents = ["family-a", "family-b", "family-c"].map((family, index) => ({
      problemEventId: `problem-trade-retention-${index + 1}`,
      runId: `run-trade-retention-${index + 1}`,
      iteration: index + 1,
      candidateId: `cand-trade-retention-${index + 1}`,
      problemKind: "local_backtest_fail" as const,
      diagnosis:
        "local_candidate_rejected | objective_hard_gate_fail | full_sample_hard_gate_fail | minimum_oos_trades | oos_hard_gate_fail | full_sample_trades=30 | oos_trades=8 | oos_post_fee_profit=2.036175",
      evidenceHash: `evidence-hash-${index + 1}`,
      suggestedRepairKind: "entry_frequency_repair" as const,
      failureSignatureHash: `failure-signature-${index + 1}`,
      structureFamily: family,
      recordedAt,
    }));

    const plan = await prepareAutonomousMutationPlan({
      workspaceRoot,
      objective,
      experiments: [],
      headEvents: [],
      archiveEvents: [],
      calibrationEvents: [],
      problemEvents,
      repairAttempts: [],
    });

    expect(plan.brief.repairPriorities).toEqual(
      expect.arrayContaining([
        "exploration_breakout",
        "rotate_structure_family",
        "stabilize_trade_retention_cluster",
        "lift_oos_trade_floor",
        "avoid_champion_family_repair",
      ]),
    );
    expect(plan.brief.stagnationSignals).toEqual(
      expect.arrayContaining([
        "exploration_breakout_active",
        "trade_count_collapse",
        "oos_failure_cluster",
        "repeated_trade_retention_cluster",
      ]),
    );
    expect(plan.brief.repairMode).toBe("exploration_breakout");
    expect(plan.parentCandidateId).toBeNull();
    expect(plan.brief.explorationDirective).toEqual(
      expect.objectContaining({
        mode: "structure_breakout",
      }),
    );
    expect(plan.brief.nextMutationDirection).toContain(
      "Do not recover by reverting to the current champion family",
    );
  });

  test("prepareAutonomousMutationPlan reads iteration records before forming the next hypothesis", async () => {
    const workspaceRoot = await mkdtemp(
      path.join(tmpdir(), "af-autonomous-iteration-record-memory-"),
    );
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const iterationRecords: AutonomousIterationLearningRecord[] = [
      {
        runId: "run-record-1",
        iteration: 41,
        researchMode: {
          mode: "continuous_improvement",
          source: "default",
        },
        activeCriterion: null,
        criterionBefore: null,
        criterionAfter: null,
        criterionDelta: null,
        criterionVerdict: null,
        acceptedHeadCandidateId: "cand-42ed2fa4",
        candidateId: "cand-record-1",
        briefHash: "brief-record-1",
        repairMode: "exploration_breakout",
        routeId: "time_boxed_event_rotation",
        variantId: null,
        hypothesis: "Try a narrow time-boxed route.",
        methodSummary: "Used a narrow event window.",
        resultSummary: "decision=local_candidate_rejected | trades=31 | oosTrades=7",
        lessonForNextHypothesis:
          "Do not repeat sparse event windows without broadening the primary entry.",
        decision: "local_candidate_rejected",
        score: 0.61,
        eligible: false,
        totalTrades: 31,
        oosTrades: 7,
        postFeeNetProfitPercent: 4.5,
        oosPostFeeNetProfitPercent: 1.5,
        blockingReasons: ["oos_trade_count_fail: observed 7 below 15"],
        championChanged: false,
        activeChampionCandidateId: "cand-42ed2fa4",
        recordedAt: "2026-05-01T00:00:00.000Z",
      },
    ];

    const plan = await prepareAutonomousMutationPlan({
      workspaceRoot,
      objective,
      experiments: [],
      headEvents: [],
      archiveEvents: [],
      calibrationEvents: [],
      problemEvents: [],
      repairAttempts: [],
      iterationRecords,
      ignoreCalibrationGuidance: true,
    });

    expect(plan.brief.iterationRecordMemory).toEqual(
      expect.objectContaining({
        recentRecordCount: 1,
        latestLessons: expect.arrayContaining([
          expect.stringContaining("Do not repeat sparse event windows"),
        ]),
      }),
    );
    expect(plan.brief.nextMutationDirection).toContain(
      "Iteration record memory is available",
    );
    expect(plan.brief.nextMutationDirection).toContain(
      "Do not repeat sparse event windows",
    );
  });

  test("prepareAutonomousMutationPlan carries promotion diagnostics and fixed exploration budget", async () => {
    const workspaceRoot = await mkdtemp(
      path.join(tmpdir(), "af-autonomous-promotion-diagnostics-"),
    );
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const experiments: ExperimentRecord[] = [
      {
        runId: "run-diagnostics",
        iteration: 1,
        candidateId: "diag-candidate",
        parentCandidateId: null,
        branchId: "autonomous-main",
        acceptedHeadCandidateId: null,
        baselineCandidateId: null,
        candidatePath: "C:\\tmp\\diag-candidate.pine",
        candidateHash: "hash-diagnostics",
        candidateScore: 0.5,
        decision: "tv_verified",
        status: "verified",
        testerMetrics: createStrongMetrics(),
        conditionContributions: [
          {
            conditionId: "risk-off-filter",
            scoreDelta: -0.08,
            ablatedScore: 0.58,
            ablatedDecision: "ablation_improved",
            oosFoldDelta: -1,
            failedFoldImpact: {
              baseFailedFoldCount: 2,
              ablatedFailedFoldCount: 1,
              changedFoldIds: ["wf-2022"],
              summary: "condition_removal_changed_folds:wf-2022",
            },
          },
        ],
        topLossZones: ["trend_down:bear_rebound_loss"],
        lossAnalysisSummary: {
          status: "available",
          summary: "Structured diagnostics test fixture.",
          topLossZones: ["trend_down:bear_rebound_loss"],
          lossZoneDetails: [
            {
              regime: "trend_down",
              volatilityBucket: "high",
              trendBucket: "trend_down",
              entryRoute: "bear_rebound",
              exitReason: "weak_exit",
              slotRank: 2,
              barsHeld: 6,
              lossCount: 4,
              averageLossPercent: -1.4,
            },
          ],
          tradeLifecycle: [
            {
              entryRoute: "bear_rebound",
              tradeCount: 9,
              averageBarsHeld: 5.5,
              mfeProxy: 0.7,
              maeProxy: 1.8,
              exitReasonDistribution: {
                weak_exit: 6,
                time_exit: 3,
              },
              profitDistribution: {
                winners: 3,
                losers: 6,
                breakeven: 0,
                averageProfitPercent: -0.42,
                medianProfitPercent: -0.6,
              },
            },
          ],
          repairPriorities: [
            "Reduce bear-rebound exposure during trend_down folds.",
          ],
        },
        walkForwardEvaluation: {
          policyVersion: "walk-forward-oos/v1",
          foldCount: 5,
          requiredPositiveOosFolds: 4,
          positiveOosFoldCount: 3,
          minimumTradesPerFold: 12,
          minimumTotalOosTrades: 60,
          totalOosTrades: 57,
          worstFoldDrawdownPercent: 19,
          medianOosProfitFactor: 1.05,
          medianOosPostFeeNetProfitPercent: 2,
          embargoBars: 5,
          passed: false,
          gateReasons: ["positive_oos_fold_count", "minimum_total_oos_trades"],
          failedFoldRegimeSummary: [
            {
              foldId: "wf-2022",
              dominantRegime: "trend_down",
              concentration: 0.72,
              gateReasons: ["positive_fold_post_fee_profit"],
            },
          ],
          folds: [
            {
              foldId: "wf-2022",
              index: 3,
              trainStartTime: null,
              trainEndTime: null,
              testStartTime: null,
              testEndTime: null,
              embargoBars: 5,
              metrics: null,
              objectiveBreakdown: null,
              passed: false,
              gateReasons: ["positive_fold_post_fee_profit"],
            },
          ],
        },
      } as ExperimentRecord,
    ];

    const plan = await prepareAutonomousMutationPlan({
      workspaceRoot,
      objective,
      experiments,
      headEvents: [],
      archiveEvents: [],
      calibrationEvents: [],
      selectedBranch: autonomousBranchRecordSchema.parse({
        branchId: "branch-test",
        branchKind: "exploration_breakout",
        budgetPct: 20,
        parentCandidateId: null,
        followUpRemaining: 0,
        createdAt: "2026-05-03T00:00:00.000Z",
        lastCandidateId: null,
        status: "active",
      }),
    });

    expect(plan.brief.explorationBudget).toEqual({
      championExploitPct: 50,
      frontierExploitPct: 20,
      breakoutPct: 20,
      nearMissRepairPct: 5,
      simplificationPct: 5,
    });
    expect(plan.brief.branchKind).toBe("exploration_breakout");
    expect(plan.brief.branchGoal).toContain("distinct AF-compatible");
    expect(plan.brief.followUpRemaining).toBe(0);
    expect(plan.brief.promotionDiagnostics?.conditionContribution[0]?.conditionId).toBe(
      "risk-off-filter",
    );
    expect(plan.brief.promotionDiagnostics?.foldFailureMap[0]?.summary).toContain(
      "walk_forward_failed:diag-candidate",
    );
    expect(plan.brief.promotionDiagnostics?.foldFailureMap[0]).toEqual(
      expect.objectContaining({
        dominantRegime: "trend_down",
        suspectedFailureReason: "insufficient_positive_oos_folds",
        suggestedMutationConstraint: expect.stringContaining("trend_down"),
      }),
    );
    expect(plan.brief.promotionDiagnostics?.lossZoneDetails[0]).toEqual(
      expect.objectContaining({
        regime: "trend_down",
        entryRoute: "bear_rebound",
        exitReason: "weak_exit",
      }),
    );
    expect(plan.brief.promotionDiagnostics?.tradeLifecycleDetails[0]).toEqual(
      expect.objectContaining({
        entryRoute: "bear_rebound",
        tradeCount: 9,
      }),
    );
    expect(plan.brief.analysisGuidance.lossZoneGuidance).toContain(
      "trend_down:bear_rebound_loss",
    );
    expect(plan.brief.nextMutationDirection).toContain(
      "Exploration budget is fixed",
    );
  });

  test("prepareAutonomousMutationPlan suppresses sparse breakout routes and prefers eligible time-boxed evidence", async () => {
    const workspaceRoot = await mkdtemp(
      path.join(tmpdir(), "af-autonomous-breakout-memory-"),
    );
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const sparseMomentum = Array.from({ length: 8 }, (_, index) =>
      createBreakoutExperiment({
        iteration: index + 1,
        candidateId: `cand-sparse-momentum-${index + 1}`,
        routeSummary: "momentum-continuation pullback candidate",
        totalTrades: 31,
        oosTrades: 7,
        score: 0.61,
      }),
    );
    const eligibleTimeBoxed = createBreakoutExperiment({
      iteration: 9,
      candidateId: "cand-time-boxed-eligible",
      routeSummary: "time-boxed event rotation candidate",
      totalTrades: 67,
      oosTrades: 20,
      eligible: true,
      score: 0.7748,
    });
    const experiments = [...sparseMomentum, eligibleTimeBoxed];
    const mutationBriefs = [
      ...sparseMomentum.map((record) =>
        createBreakoutMutationBriefRecord({
          iteration: record.iteration,
          routeId: "momentum_continuation_pullback",
        }),
      ),
      createBreakoutMutationBriefRecord({
        iteration: eligibleTimeBoxed.iteration,
        routeId: "time_boxed_event_rotation",
      }),
    ];

    const plan = await prepareAutonomousMutationPlan({
      workspaceRoot,
      objective,
      experiments,
      headEvents: [],
      archiveEvents: [],
      calibrationEvents: [],
      mutationBriefs,
      problemEvents: [],
      repairAttempts: [],
      ignoreCalibrationGuidance: true,
    });

    expect(plan.brief.repairMode).toBe("exploration_breakout");
    expect(plan.brief.breakoutOutcomeMemory).toEqual(
      expect.objectContaining({
        suppressedRoutes: expect.arrayContaining([
          "momentum_continuation_pullback",
        ]),
        preferredRoutes: expect.arrayContaining(["time_boxed_event_rotation"]),
        dominantSparsePatterns: expect.arrayContaining(["31/7"]),
        bestBreakoutCandidateId: "cand-time-boxed-eligible",
        bestBreakoutRoute: "time_boxed_event_rotation",
      }),
    );
    expect(plan.brief.explorationDirective?.routeId).toBe(
      "time_boxed_event_rotation",
    );
    expect(plan.brief.stagnationSignals).toContain("sparse_oos_trade_cluster");
    expect(plan.brief.forbiddenPatterns.join(" ")).toContain(
      "momentum_continuation_pullback",
    );
    expect(plan.brief.forbiddenPatterns.join(" ")).toContain("31/7");
  });

  test("prepareAutonomousMutationPlan escalates time-boxed variants after repeated 31/7 failures", async () => {
    const workspaceRoot = await mkdtemp(
      path.join(tmpdir(), "af-autonomous-timebox-variant-"),
    );
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const eligibleTimeBoxed = createBreakoutExperiment({
      iteration: 20,
      candidateId: "cand-time-boxed-eligible",
      routeSummary: "time boxed event rotation",
      totalTrades: 67,
      oosTrades: 20,
      eligible: true,
      score: 0.7748,
    });
    const sparseTimeBoxed = Array.from({ length: 8 }, (_, index) =>
      createBreakoutExperiment({
        iteration: index + 21,
        candidateId: `cand-time-boxed-sparse-${index}`,
        routeSummary: "time boxed event rotation",
        totalTrades: 31,
        oosTrades: 7,
        eligible: false,
        score: 0.6,
      }),
    );
    const experiments = [eligibleTimeBoxed, ...sparseTimeBoxed];
    const mutationBriefs = experiments.map((record) =>
      createBreakoutMutationBriefRecord({
        iteration: record.iteration,
        routeId: "time_boxed_event_rotation",
      }),
    );

    const plan = await prepareAutonomousMutationPlan({
      workspaceRoot,
      objective,
      experiments,
      headEvents: [],
      archiveEvents: [],
      calibrationEvents: [],
      mutationBriefs,
      problemEvents: [],
      repairAttempts: [],
      ignoreCalibrationGuidance: true,
    });

    expect(plan.brief.explorationDirective?.routeId).toBe(
      "time_boxed_event_rotation",
    );
    expect(plan.brief.breakoutVariantDirective?.routeId).toBe(
      "time_boxed_event_rotation",
    );
    expect(plan.brief.breakoutVariantDirective?.recentSparseCount).toBeGreaterThanOrEqual(
      8,
    );
    expect(plan.brief.breakoutVariantDirective?.forcedRules.join(" ")).toContain(
      "event",
    );
    expect(plan.brief.repairPriorities).toContain(
      "time_boxed_variant_escalation",
    );
    expect(plan.brief.stagnationSignals).toContain(
      "time_boxed_variant_escalation",
    );
    expect(plan.brief.nextMutationDirection).toContain(
      "Time-boxed variant escalation is active",
    );
    expect(plan.brief.forbiddenPatterns.join(" ")).toContain(
      "breakoutVariantDirective",
    );
  });

  test("buildRepairBriefForProblemEvent reroutes breakout trade-count repairs away from the failed route", async () => {
    const baseBrief = {
      repairMode: "exploration_breakout",
      explorationDirective: {
        mode: "structure_breakout",
        routeId: "momentum_continuation_pullback",
        routeSummary: "route momentum_continuation_pullback",
        reason: "test",
        ignoredCalibrationGuidance: true,
      },
      breakoutOutcomeMemory: {
        suppressedRoutes: ["momentum_continuation_pullback"],
        preferredRoutes: ["time_boxed_event_rotation"],
        dominantSparsePatterns: ["31/7"],
        bestBreakoutCandidateId: "cand-time-boxed-eligible",
        bestBreakoutRoute: "time_boxed_event_rotation",
      },
      stagnationSignals: [
        "exploration_breakout_active",
        "trade_count_collapse",
        "sparse_oos_trade_cluster",
      ],
      nextMutationDirection: "Use exploration breakout.",
      repairPriorities: ["exploration_breakout"],
      forbiddenPatterns: [],
      recentFailures: [],
    } as unknown as MutationBrief;
    const problemEvent: ProblemEventRecord = {
      problemEventId: "problem-reroute",
      runId: "run-reroute",
      iteration: 10,
      candidateId: "cand-failed-route",
      problemKind: "local_backtest_fail",
      diagnosis:
        "local_candidate_rejected | minimum_oos_trades | oos_hard_gate_fail | full_sample_trades=31 | oos_trades=7",
      evidenceHash: "evidence-reroute",
      suggestedRepairKind: "entry_frequency_repair",
      failureSignatureHash: "failure-reroute",
      structureFamily: "family-reroute",
      recordedAt: new Date().toISOString(),
    };

    const repairBrief = buildRepairBriefForProblemEvent({
      brief: baseBrief,
      problemEvent,
      compileErrors: ["minimumOosTrades failed with 31/7 sparse OOS profile"],
    });

    expect(repairBrief.repairMode).toBe("exploration_breakout");
    expect(repairBrief.explorationDirective?.routeId).toBe(
      "time_boxed_event_rotation",
    );
    expect(repairBrief.repairPriorities).toContain(
      "reroute_after_sparse_oos_failure",
    );
    expect(repairBrief.nextMutationDirection).toContain(
      "previous route momentum_continuation_pullback is forbidden",
    );
    expect(repairBrief.forbiddenPatterns.join(" ")).toContain("31/7");
  });

  test("buildRepairBriefForProblemEvent escapes preferred sparse route even when alternate routes were suppressed", async () => {
    const baseBrief = {
      repairMode: "exploration_breakout",
      explorationDirective: {
        mode: "structure_breakout",
        routeId: "time_boxed_event_rotation",
        routeSummary: "route time_boxed_event_rotation",
        reason: "test",
        ignoredCalibrationGuidance: true,
      },
      breakoutOutcomeMemory: {
        suppressedRoutes: [
          "momentum_continuation_pullback",
          "mean_reversion_reentry",
          "volatility_compression_release",
          "event_reclaim_reversal",
        ],
        preferredRoutes: ["time_boxed_event_rotation"],
        dominantSparsePatterns: ["31/7", "3/1", "7/1"],
        bestBreakoutCandidateId: "cand-time-boxed-eligible",
        bestBreakoutRoute: "time_boxed_event_rotation",
      },
      stagnationSignals: [
        "exploration_breakout_active",
        "trade_count_collapse",
        "sparse_oos_trade_cluster",
      ],
      nextMutationDirection: "Use exploration breakout.",
      repairPriorities: ["exploration_breakout"],
      forbiddenPatterns: [],
      recentFailures: [],
    } as unknown as MutationBrief;
    const problemEvent: ProblemEventRecord = {
      problemEventId: "problem-preferred-fallback",
      runId: "run-preferred-fallback",
      iteration: 10,
      candidateId: "cand-failed-time-boxed",
      problemKind: "local_backtest_fail",
      diagnosis:
        "local_candidate_rejected | minimum_oos_trades | oos_hard_gate_fail | full_sample_trades=31 | oos_trades=7",
      evidenceHash: "evidence-preferred-fallback",
      suggestedRepairKind: "entry_frequency_repair",
      failureSignatureHash: "failure-preferred-fallback",
      structureFamily: "family-preferred-fallback",
      recordedAt: new Date().toISOString(),
    };

    const repairBrief = buildRepairBriefForProblemEvent({
      brief: baseBrief,
      problemEvent,
      compileErrors: ["minimumOosTrades failed with 31/7 sparse OOS profile"],
    });

    expect(repairBrief.explorationDirective?.routeId).not.toBe(
      "time_boxed_event_rotation",
    );
    expect(repairBrief.repairPriorities).toContain(
      "escape_preferred_sparse_route",
    );
    expect(repairBrief.nextMutationDirection).toContain(
      "previous preferred route time_boxed_event_rotation is forbidden",
    );
    expect(repairBrief.forbiddenPatterns.join(" ")).toContain(
      "momentum_continuation_pullback",
    );
    expect(repairBrief.forbiddenPatterns.join(" ")).toContain(
      "time_boxed_event_rotation",
    );
  });

  test("runArchiveUpdatePhase writes failure archive events for rejected candidates", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-failure-archive-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitFailLowTrades(metrics, objectiveBreakdown),
    );

    const pineSource =
      "//@version=5\nstrategy('Failure Archive Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n";
    const candidatePath = await writeCandidateFile(
      workspaceRoot,
      "cand-failure-archive",
      pineSource,
    );
    const spec = await writeTestSpecArtifact(workspaceRoot, "cand-failure-archive");

    const local = await runLocalEvaluationPhase({
      workspaceRoot,
      stateRoot,
      runId: "failure-archive-run",
      iteration: 1,
      executor: createLocalMockExecutor(metrics),
      objective,
      parsedMutation: {
        candidateSummary: "Failure archive candidate",
        nextMutationHints: [],
        pineScript: pineSource,
        strategySpec: spec.strategySpec,
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      candidateArtifact: {
        candidateId: "cand-failure-archive",
        parentId: null,
        branchId: "autonomous-main",
        pinePath: candidatePath,
        pineHash: "failure-archive-hash",
        specPath: spec.specPath,
        specHash: spec.specHash,
        studyTitle: "Failure Archive Candidate",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        candidateSummary: "Failure archive candidate",
        nextMutationHints: [],
      },
      mutationProvenance: createValidMutationProvenance(),
      previousExperiments: [],
    });

    await runArchiveUpdatePhase({
      stateRoot,
      runId: "failure-archive-run",
      iteration: 1,
      evaluation: local.record,
      shouldArchive: local.shouldArchive,
    });

    const archiveEvents = await readArchiveEventRecords(stateRoot);
    expect(archiveEvents).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          eventKind: "failure_archive_added",
          candidateId: "cand-failure-archive",
        }),
      ]),
    );
  });

  test.skip("processTvCalibrationQueue records external validation failures without invalidating the local evaluation record", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-tvfail-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitPass(metrics, objectiveBreakdown),
    );

    const pineSource =
      "//@version=5\nstrategy('TV Failure Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n";
    const candidatePath = await writeCandidateFile(
      workspaceRoot,
      "cand-tv-failure",
      pineSource,
    );
    const spec = await writeTestSpecArtifact(workspaceRoot, "cand-tv-failure");

    const local = await runLocalEvaluationPhase({
      workspaceRoot,
      stateRoot,
      runId: "tv-local-run",
      iteration: 1,
      executor: createLocalMockExecutor(metrics),
      objective,
      parsedMutation: {
        candidateSummary: "Calibration candidate",
        nextMutationHints: [],
        pineScript: pineSource,
        strategySpec: spec.strategySpec,
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      candidateArtifact: {
        candidateId: "cand-tv-failure",
        parentId: null,
        branchId: "autonomous-main",
        pinePath: candidatePath,
        pineHash: "tv-failure-hash",
        specPath: spec.specPath,
        specHash: spec.specHash,
        studyTitle: "TV Failure Candidate",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        candidateSummary: "Calibration candidate",
        nextMutationHints: [],
      },
      mutationProvenance: createValidMutationProvenance(),
      previousExperiments: [],
    });

    await enqueueCalibrationCandidate({
      stateRoot,
      runId: "tv-queue-run",
      iteration: 2,
      localRecord: local.record,
      reason: "champion_or_eligible_candidate",
    });

    const processed = await processTvCalibrationQueue({
      workspaceRoot,
      stateRoot,
      runId: "tv-process-run",
      objective,
      env: createRuntimeEnv(workspaceRoot, {
        promotionVerificationExecutor: "local-backtest",
      }),
      experiments: await readExperimentRecords(stateRoot),
      calibrationEvents: await readCalibrationEventRecords(stateRoot),
      executorFactory: () =>
        createMockPineEvaluationExecutor({
          prepareChartError: "source panel timed out while opening local runtime",
        }),
    });

    await rebuildIndexes(stateRoot);
    const experiments = await readExperimentRecords(stateRoot);
    const tvSurfaceFailures = JSON.parse(
      await readFile(resolveKnowledgePaths(stateRoot).tvSurfaceFailuresPath, "utf8"),
    ) as {
      entries: Array<{ candidateId: string; decision: string }>;
    };

    const latestTvRecord = experiments
      .filter((record) => record.candidateId === local.record.candidateId)
      .map((record) => autonomousExperimentSchema.safeParse(record))
      .filter((result) => result.success)
      .map((result) => result.data)
      .find((record) => record.recordKind === "tv_verification");

    expect(processed.processedCandidateIds).toContain(local.record.candidateId);
    expect(
      experiments.some(
        (record) =>
          (record as Record<string, unknown>).recordKind === "local_evaluation" &&
          record.candidateId === local.record.candidateId,
      ),
    ).toBe(true);
    expect(latestTvRecord?.decision).toBe("tv_surface_failure");
    expect(tvSurfaceFailures.entries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          candidateId: local.record.candidateId,
          decision: "tv_surface_failure",
        }),
      ]),
    );
  });

  test.skip("processTvCalibrationQueue mock recovered mode writes tv verification and divergence evidence", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-tv-mock-recovered-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitPass(metrics, objectiveBreakdown),
    );

    const pineSource =
      "//@version=5\nstrategy('TV Mock Recovered Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n";
    const candidatePath = await writeCandidateFile(
      workspaceRoot,
      "cand-tv-mock-recovered",
      pineSource,
    );
    const spec = await writeTestSpecArtifact(workspaceRoot, "cand-tv-mock-recovered");

    const local = await runLocalEvaluationPhase({
      workspaceRoot,
      stateRoot,
      runId: "tv-mock-local-run",
      iteration: 1,
      executor: createLocalMockExecutor(metrics),
      objective,
      parsedMutation: {
        candidateSummary: "Calibration candidate",
        nextMutationHints: [],
        pineScript: pineSource,
        strategySpec: spec.strategySpec,
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      candidateArtifact: {
        candidateId: "cand-tv-mock-recovered",
        parentId: null,
        branchId: "autonomous-main",
        pinePath: candidatePath,
        pineHash: "tv-mock-recovered-hash",
        specPath: spec.specPath,
        specHash: spec.specHash,
        studyTitle: "TV Mock Recovered Candidate",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        candidateSummary: "Calibration candidate",
        nextMutationHints: [],
      },
      mutationProvenance: createValidMutationProvenance(),
      previousExperiments: [],
    });

    await enqueueCalibrationCandidate({
      stateRoot,
      runId: "tv-mock-queue-run",
      iteration: 2,
      localRecord: local.record,
      reason: "champion_or_eligible_candidate",
    });

    const processed = await processTvCalibrationQueue({
      workspaceRoot,
      stateRoot,
      runId: "tv-mock-process-run",
      objective,
      env: createRuntimeEnv(workspaceRoot, {
      }),
      experiments: await readExperimentRecords(stateRoot),
      calibrationEvents: await readCalibrationEventRecords(stateRoot),
      executorFactory: () => createMockPineEvaluationExecutor(),
    });

    const experiments = await readExperimentRecords(stateRoot);
    const calibrationEvents = await readCalibrationEventRecords(stateRoot);

    expect(processed.processedCandidateIds).toContain(local.record.candidateId);
    expect(
      experiments.some(
        (record) =>
          (record as Record<string, unknown>).recordKind === "tv_verification" &&
          record.candidateId === local.record.candidateId,
      ),
    ).toBe(true);
    expect(calibrationEvents).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          eventKind: "local_tv_divergence_measured",
          candidateId: local.record.candidateId,
        }),
      ]),
    );
  });

  test.skip("mock recovered calibration writes confidence updates and feeds the next brief and score breakdown", async () => {
    const workspaceRoot = await mkdtemp(
      path.join(tmpdir(), "af-autonomous-confidence-feedback-"),
    );
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);
    const objective = await loadObjectiveConfig(workspaceRoot);
    const metrics = createStrongMetrics();
    const objectiveBreakdown = evaluateObjective(metrics, objective);
    mockedEvaluateLocalSplit.mockResolvedValue(
      createSplitPass(metrics, objectiveBreakdown),
    );

    const pineSource =
      "//@version=5\nstrategy('Calibration Seed Candidate', overlay=true)\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n";
    const candidatePath = await writeCandidateFile(
      workspaceRoot,
      "cand-confidence-seed",
      pineSource,
    );
    const spec = await writeTestSpecArtifact(workspaceRoot, "cand-confidence-seed");

    const local = await runLocalEvaluationPhase({
      workspaceRoot,
      stateRoot,
      runId: "confidence-seed-run",
      iteration: 1,
      executor: createLocalMockExecutor(metrics),
      objective,
      parsedMutation: {
        candidateSummary: "Calibration seed candidate",
        nextMutationHints: [],
        pineScript: pineSource,
        strategySpec: spec.strategySpec,
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      candidateArtifact: {
        candidateId: "cand-confidence-seed",
        parentId: null,
        branchId: "autonomous-main",
        pinePath: candidatePath,
        pineHash: "confidence-seed-hash",
        specPath: spec.specPath,
        specHash: spec.specHash,
        studyTitle: "Calibration Seed Candidate",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [3],
          },
        ],
        candidateSummary: "Calibration seed candidate",
        nextMutationHints: [],
      },
      mutationProvenance: createValidMutationProvenance(),
      previousExperiments: [],
    });

    await enqueueCalibrationCandidate({
      stateRoot,
      runId: "confidence-queue-run",
      iteration: 2,
      localRecord: local.record,
      reason: "champion_or_eligible_candidate",
    });

    await processTvCalibrationQueue({
      workspaceRoot,
      stateRoot,
      runId: "confidence-process-run",
      objective,
      env: createRuntimeEnv(workspaceRoot, {
      }),
      experiments: await readExperimentRecords(stateRoot),
      calibrationEvents: await readCalibrationEventRecords(stateRoot),
      executorFactory: () => createMockPineEvaluationExecutor(),
    });

    const confidenceEvents = await readLocalConfidenceEventRecords(stateRoot);
    const calibrationEvents = await readCalibrationEventRecords(stateRoot);
    const confidenceEvent = confidenceEvents.at(-1);

    expect(confidenceEvent).toEqual(
      expect.objectContaining({
        eventKind: "local_confidence_updated",
        candidateId: local.record.candidateId,
        localConfidenceBonus: 0.05,
        divergencePenalty: 0,
        divergenceSeverity: "low",
      }),
    );

    const plan = await prepareAutonomousMutationPlan({
      workspaceRoot,
      objective,
      experiments: await readExperimentRecords(stateRoot),
      headEvents: await readHeadEventRecords(stateRoot),
      archiveEvents: await readArchiveEventRecords(stateRoot),
      calibrationEvents,
      confidenceEvents,
      problemEvents: await readProblemEventRecords(stateRoot),
      repairAttempts: await readRepairAttemptRecords(stateRoot),
    });

    expect(plan.brief.recentCalibrationSummary).not.toContain(
    "No external calibration history yet",
    );
    expect(plan.brief.lowDivergenceFamilies).toContain(
      confidenceEvent?.structureFamilyHash,
    );
    expect(plan.brief.calibrationAwareInstruction).toContain(
      "Prefer low-divergence families first",
    );

    const localOnlyPlan = await prepareAutonomousMutationPlan({
      workspaceRoot,
      objective,
      experiments: await readExperimentRecords(stateRoot),
      headEvents: await readHeadEventRecords(stateRoot),
      archiveEvents: await readArchiveEventRecords(stateRoot),
      calibrationEvents,
      confidenceEvents,
      problemEvents: await readProblemEventRecords(stateRoot),
      repairAttempts: await readRepairAttemptRecords(stateRoot),
      ignoreCalibrationGuidance: true,
    });

    expect(localOnlyPlan.parentCandidateId).toBeNull();
    expect(localOnlyPlan.brief.lowDivergenceFamilies).toEqual([]);
    expect(localOnlyPlan.brief.calibrationAwareInstruction).toContain(
      "Do not prefer or penalize structure families",
    );

    const nextSource =
      "//@version=5\nstrategy('Calibration Followup Candidate', overlay=true)\n// preserve same structure family while changing the source hash\nentrySignal = close > open\nif entrySignal\n    strategy.entry('L', strategy.long)\n";
    const nextCandidatePath = await writeCandidateFile(
      workspaceRoot,
      "cand-confidence-followup",
      nextSource,
    );
    const followupSpec = await writeTestSpecArtifact(
      workspaceRoot,
      "cand-confidence-followup",
    );

    const followup = await runLocalEvaluationPhase({
      workspaceRoot,
      stateRoot,
      runId: "confidence-followup-run",
      iteration: 3,
      executor: createLocalMockExecutor(metrics),
      objective,
      parsedMutation: {
        candidateSummary: "Calibration followup candidate",
        nextMutationHints: [],
        pineScript: nextSource,
        strategySpec: followupSpec.strategySpec,
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [4],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      candidateArtifact: {
        candidateId: "cand-confidence-followup",
        parentId: null,
        branchId: "autonomous-main",
        pinePath: nextCandidatePath,
        pineHash: "confidence-followup-hash",
        specPath: followupSpec.specPath,
        specHash: followupSpec.specHash,
        studyTitle: "Calibration Followup Candidate",
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [4],
          },
        ],
        candidateSummary: "Calibration followup candidate",
        nextMutationHints: [],
      },
      mutationProvenance: createValidMutationProvenance(),
      previousExperiments: await readExperimentRecords(stateRoot),
      previousConfidenceEvents: confidenceEvents,
    });

    expect(followup.record.autoSelectionBreakdown?.localConfidenceBonus).toBe(0.05);
    expect(followup.record.autoSelectionBreakdown?.divergencePenalty).toBe(0);
  });

  test("runAutoSelectionPhase does not replace the current champion unless a strictly better eligible score exists", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-autonomous-select-"));
    const stateRoot = testStateRoot(workspaceRoot);
    await initializeWorkspace(workspaceRoot);

    const currentChampion: Omit<ExperimentRecord, "recordedAt"> = {
      runId: "run-1",
      iteration: 1,
      candidateId: "champion-a",
      parentCandidateId: null,
      branchId: "autonomous-main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: null,
      candidatePath: "C:\\tmp\\champion-a.pine",
      candidateHash: "hash-a",
      contractVersion: AUTORESEARCH_CONTRACT_VERSION,
      mutationAuthority: STRATEGY_SPEC_MUTATION_AUTHORITY,
      specPath: "C:\\tmp\\champion-a.json",
      specHash: "spec-hash-a",
      studyTitle: "Champion A",
      candidateScore: 1.2,
      decision: "local_candidate_eligible",
      status: "evaluated",
      recordKind: "local_evaluation",
      executorRole: "primary_local_backtest",
      evidenceAuthority: "local_model",
      evaluationMode: "local_primary",
      mutationBriefSummary: "Champion A",
      conditionInventory: [],
      mutationProvenance: createValidMutationProvenance(),
      testerMetrics: createStrongMetrics(),
      splitEvaluation: null,
      noveltyFingerprint: null,
      duplicateStatus: {
        classification: "unique",
        exactDuplicateCandidateId: null,
        structuralDuplicateCandidateId: null,
        duplicateFingerprint: null,
      },
      autoSelectionScore: 1.2,
      autoSelectionBreakdown: {
        baseObjectiveScore: 0.8,
        robustnessScore: 0.2,
        noveltyScore: 0.3,
        riskPenalty: 0,
        duplicatePenalty: 0,
        complexityPenalty: 0.1,
        totalScore: 1.2,
        eligible: true,
        rejectionReasons: [],
      },
      objectivePolicyVersion: "objective.qqq-120m/v1",
      selectionPolicyVersion: "autonomous-tv-verified/v4",
      localConfidence: 1,
      tvCalibrationStatus: "not_requested",
      localTvParity: null,
      artifactPaths: {},
      recordMeta: {
        schemaVersion: "experiment/v3",
        recordHash: "record-a",
        candidateHash: "hash-a",
        baselineHash: null,
        artifactBundleHash: null,
        pipelineVersion: "af-autonomous-local-first/v3",
      },
      recordedAt: "2026-04-28T00:00:00.000Z",
    };

    const currentVerifiedChampion: Omit<ExperimentRecord, "recordedAt"> = {
      ...currentChampion,
      runId: "run-1-tv",
      recordKind: "tv_verification",
      executorRole: "primary_local_backtest",
      evidenceAuthority: "local_model",
      evaluationMode: "tv_calibration",
      decision: "tv_verified",
      status: "verified",
      tvCalibrationStatus: "verified_match",
      localTvParity: {
        status: "matched",
        tradeCountDelta: 0,
        netProfitPctDelta: 0,
        maxDrawdownPctDelta: 0,
        profitFactorDelta: 0,
        winRateDelta: 0,
        tradeParity: {
          status: "matched",
          entryTimeMatchRatio: 1,
          exitTimeMatchRatio: 1,
          profitSignMatchRatio: 1,
          orderCountDelta: 0,
        },
        eventParity: {
          status: "matched",
          eventMatchRatio: 1,
          entryPassMatchRatio: 1,
          exitReasonMatchRatio: 1,
        },
      },
      walkForwardEvaluation: {
        policyVersion: "walk-forward-oos/v1",
        foldCount: 5,
        requiredPositiveOosFolds: 4,
        positiveOosFoldCount: 5,
        minimumTradesPerFold: 12,
        minimumTotalOosTrades: 60,
        totalOosTrades: 80,
        worstFoldDrawdownPercent: 10,
        medianOosProfitFactor: 1.4,
        medianOosPostFeeNetProfitPercent: 8,
        embargoBars: 5,
        minimumCoverageDays: 730,
        coverageDays: 800,
        coverageStartTime: "2023-05-25T00:00:00.000Z",
        coverageEndTime: "2025-08-02T00:00:00.000Z",
        passed: true,
        gateReasons: [],
        failedFoldRegimeSummary: [],
        folds: [],
      },
      verifiedPromotionScore: 1.2,
      verifiedPromotion: {
        eligible: true,
        score: 1.2,
        scoreBreakdown: {
          tvPerformanceScore: 0.3,
          walkForwardRobustnessScore: 0.18,
          foldConsistencyScore: 0.15,
          tradeDensityScore: 0.1,
          parityScore: 0.1,
          simplicityScore: 0.04,
          trialBudgetPenalty: 0,
          regimeConcentrationPenalty: 0,
          complexityPenalty: 0,
          totalScore: 1.2,
          minimumRequiredScore: 0.62,
        },
        rejectionReasons: [],
        localCandidateHash: "hash-a",
        tvCandidateHash: "hash-a",
        localRecordKind: "local_evaluation",
        tvRecordKind: "tv_verification",
        policyVersion: "verified-promotion/v1",
      },
      recordMeta: {
        ...(currentChampion.recordMeta ?? {}),
        recordHash: "record-a-tv",
        candidateHash: "hash-a",
      },
    };

    const challenger: Omit<ExperimentRecord, "recordedAt"> = {
      ...currentChampion,
      runId: "run-2",
      iteration: 2,
      candidateId: "challenger-b",
      candidateHash: "hash-b",
      recordMeta: {
        ...(currentChampion.recordMeta ?? {}),
        recordHash: "record-b",
        candidateHash: "hash-b",
      },
      autoSelectionScore: 1.2,
    };

    await appendExperimentRecord(stateRoot, currentChampion);
    await appendExperimentRecord(stateRoot, currentVerifiedChampion);
    await appendExperimentRecord(stateRoot, challenger);
    await appendHeadEventRecord(stateRoot, {
      runId: "head-run",
      iteration: 1,
      eventKind: "auto_selected_head",
      candidateId: "champion-a",
      previousChampionId: null,
      selectedBy: "auto_policy",
      policyVersion: "autonomous-tv-verified/v4",
      headAuthority: "verified_promotion",
      selectionPhase: "steady_state",
      bootstrapSource: null,
      bootstrapReason: null,
      researchMaturity: "steady_state",
      objectiveScore: 0.8,
      noveltyScore: 0.3,
      robustnessScore: 0.2,
      diversityContribution: 0.3,
      riskPenalty: 0,
      overfitPenalty: 0,
      complexityPenalty: 0.1,
      selectionReason: "Initial champion",
      selectionEvidenceHash: "selection-a",
      humanOverride: false,
    });

    const selection = await runAutoSelectionPhase({
      stateRoot,
      runId: "run-3",
      iteration: 3,
      experiments: await readExperimentRecords(stateRoot),
      headEvents: await readHeadEventRecords(stateRoot),
    });

    expect(selection.activeChampionChanged).toBe(false);
    expect(selection.selectedCandidateId).toBe("champion-a");
  });

  test("runAutoSelectionPhase hands off the bootstrap champion to a viable steady-state candidate within the transition margin", async () => {
    const workspaceRoot = await mkdtemp(
      path.join(tmpdir(), "af-autonomous-bootstrap-transition-"),
    );
    const stateRoot = testStateRoot(workspaceRoot);
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    await initializeWorkspace(workspaceRoot);
    const steadySpecPath = "C:\\tmp\\steady-b.json";
    const steadySpecHash = hashAfStrategySpec(testStrategySpec);

    const bootstrapChampion: Omit<ExperimentRecord, "recordedAt"> = {
      runId: "run-bootstrap",
      iteration: 1,
      candidateId: "bootstrap-a",
      parentCandidateId: null,
      branchId: "autonomous-main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: null,
      candidatePath: "C:\\tmp\\bootstrap-a.pine",
      candidateHash: "hash-bootstrap-a",
      contractVersion: AUTORESEARCH_CONTRACT_VERSION,
      mutationAuthority: STRATEGY_SPEC_MUTATION_AUTHORITY,
      specPath: "C:\\tmp\\bootstrap-a.json",
      specHash: steadySpecHash,
      studyTitle: "Bootstrap A",
      candidateScore: 0.8615,
      decision: "local_candidate_eligible",
      status: "evaluated",
      recordKind: "local_evaluation",
      executorRole: "primary_local_backtest",
      evidenceAuthority: "local_model",
      evaluationMode: "local_primary",
      mutationBriefSummary: "Bootstrap baseline",
      conditionInventory: [],
      mutationProvenance: createValidMutationProvenance(),
      testerMetrics: createStrongMetrics(),
      splitEvaluation: null,
      noveltyFingerprint: null,
      duplicateStatus: {
        classification: "unique",
        exactDuplicateCandidateId: null,
        structuralDuplicateCandidateId: null,
        duplicateFingerprint: null,
      },
      autoSelectionScore: 0.8615,
      autoSelectionBreakdown: {
        performanceScore: 0.74,
        baseObjectiveScore: 0.74,
        robustnessScore: 0.08,
        noveltyScore: 0.08,
        diversityScore: 0.04,
        localConfidenceBonus: 0.05,
        riskPenalty: 0,
        overfitPenalty: 0,
        duplicatePenalty: 0,
        divergencePenalty: 0,
        complexityPenalty: 0.1285,
        autoSelectionScore: 0.8615,
        totalScore: 0.8615,
        eligible: true,
        rejectionReasons: [],
      },
      objectivePolicyVersion: "objective.qqq-120m/v1",
      selectionPolicyVersion: "autonomous-local-first/v3-p0",
      selectionPhase: "bootstrap",
      bootstrapSource: "local_compatible_seed",
      bootstrapReason: "fresh_state_without_active_champion",
      localConfidence: 1,
      tvCalibrationStatus: "not_requested",
      localTvParity: null,
      eligibility: {
        autoSelectionEligible: true,
        bootstrapEligible: true,
        archiveEligible: true,
        calibrationEligible: true,
        blockingReasons: [],
      },
      artifactPaths: {},
      recordMeta: {
        schemaVersion: "experiment/v3",
        recordHash: "record-bootstrap-a",
        candidateHash: "hash-bootstrap-a",
        baselineHash: null,
        artifactBundleHash: null,
        pipelineVersion: "af-autonomous-local-first/v3",
      },
      recordedAt: "2026-04-28T00:00:00.000Z",
    };

    const steadyStateChallenger: Omit<ExperimentRecord, "recordedAt"> = {
      ...bootstrapChampion,
      runId: "run-steady",
      iteration: 2,
      candidateId: "steady-b",
      candidateHash: "hash-steady-b",
      specPath: steadySpecPath,
      specHash: steadySpecHash,
      candidateScore: 0.7361,
      autoSelectionScore: 0.7361,
      autoSelectionBreakdown: {
        performanceScore: 0.67,
        baseObjectiveScore: 0.67,
        robustnessScore: 0.06,
        noveltyScore: 0.04,
        diversityScore: 0.02,
        localConfidenceBonus: 0.05,
        riskPenalty: 0,
        overfitPenalty: 0,
        duplicatePenalty: 0,
        divergencePenalty: 0,
        complexityPenalty: 0.1039,
        autoSelectionScore: 0.7361,
        totalScore: 0.7361,
        eligible: true,
        rejectionReasons: [],
      },
      selectionPhase: "steady_state",
      bootstrapSource: null,
      bootstrapReason: null,
      eligibility: {
        autoSelectionEligible: true,
        bootstrapEligible: false,
        archiveEligible: true,
        calibrationEligible: true,
        blockingReasons: [],
      },
      recordMeta: {
        ...(bootstrapChampion.recordMeta ?? {}),
        recordHash: "record-steady-b",
        candidateHash: "hash-steady-b",
      },
    };
    const verifiedSteadyStateChallenger: Omit<ExperimentRecord, "recordedAt"> = {
      ...steadyStateChallenger,
      runId: "run-steady-tv",
      recordKind: "tv_verification",
      executorRole: "primary_local_backtest",
      evidenceAuthority: "local_model",
      evaluationMode: "tv_calibration",
      decision: "tv_verified",
      status: "verified",
      localFrontierScore: 0.7361,
      autoSelectionScore: 0.7361,
      verifiedPromotionScore: 0.7361,
      verifiedPromotion: {
        eligible: true,
        score: 0.7361,
        scoreBreakdown: {
          tvPerformanceScore: 0.3,
          walkForwardRobustnessScore: 0.18,
          foldConsistencyScore: 0.15,
          tradeDensityScore: 0.1,
          parityScore: 0.1,
          simplicityScore: 0.0461,
          trialBudgetPenalty: 0,
          regimeConcentrationPenalty: 0,
          complexityPenalty: 0.14,
          totalScore: 0.7361,
          minimumRequiredScore: 0.62,
        },
        rejectionReasons: [],
        localCandidateHash: "hash-steady-b",
        tvCandidateHash: "hash-steady-b",
        localRecordKind: "local_evaluation",
        tvRecordKind: "tv_verification",
        policyVersion: "verified-promotion/v1",
      },
      walkForwardEvaluation: {
        policyVersion: "walk-forward-oos/v1",
        foldCount: 5,
        requiredPositiveOosFolds: 4,
        positiveOosFoldCount: 5,
        minimumTradesPerFold: 12,
        minimumTotalOosTrades: 60,
        totalOosTrades: 75,
        worstFoldDrawdownPercent: 11,
        medianOosProfitFactor: 1.4,
        medianOosPostFeeNetProfitPercent: 7,
        embargoBars: 5,
        passed: true,
        gateReasons: [],
        folds: [],
      },
      tvCalibrationStatus: "verified_match",
      localTvParity: {
        status: "matched",
        tradeCountDelta: 0,
        netProfitPctDelta: 0,
        maxDrawdownPctDelta: 0,
        profitFactorDelta: 0,
        winRateDelta: 0,
        tradeParity: {
          status: "matched",
          entryTimeMatchRatio: 1,
          exitTimeMatchRatio: 1,
          profitSignMatchRatio: 1,
          orderCountDelta: 0,
        },
        eventParity: {
          status: "matched",
          eventMatchRatio: 1,
          entryPassMatchRatio: 1,
          exitReasonMatchRatio: 1,
        },
      },
      recordMeta: {
        ...(steadyStateChallenger.recordMeta ?? {}),
        recordHash: "record-steady-b-tv",
        candidateHash: "hash-steady-b",
      },
    };

    await appendExperimentRecord(stateRoot, bootstrapChampion);
    await appendExperimentRecord(stateRoot, steadyStateChallenger);
    await appendExperimentRecord(stateRoot, verifiedSteadyStateChallenger);
    await appendHeadEventRecord(stateRoot, {
      runId: "head-bootstrap",
      iteration: 1,
      eventKind: "auto_selected_head",
      candidateId: "bootstrap-a",
      previousChampionId: null,
      selectedBy: "auto_policy",
      policyVersion: "autonomous-local-first/v3-p0",
      headAuthority: "bootstrap_seed",
      selectionPhase: "bootstrap",
      bootstrapSource: "local_compatible_seed",
      bootstrapReason: "fresh_state_without_active_champion",
      researchMaturity: "bootstrap",
      performanceScore: 0.74,
      objectiveScore: 0.74,
      noveltyScore: 0.08,
      robustnessScore: 0.08,
      autoSelectionScore: 0.8615,
      diversityScore: 0.04,
      diversityContribution: 0.04,
      localConfidenceBonus: 0.05,
      riskPenalty: 0,
      overfitPenalty: 0,
      duplicatePenalty: 0,
      divergencePenalty: 0,
      complexityPenalty: 0.1285,
      selectionReason: "Bootstrap baseline",
      selectionEvidenceHash: "selection-bootstrap-a",
      humanOverride: false,
    });

    const selection = await runAutoSelectionPhase({
      stateRoot,
      runId: "run-transition",
      iteration: 3,
      experiments: await readExperimentRecords(stateRoot),
      headEvents: await readHeadEventRecords(stateRoot),
    });

    await rebuildIndexes(stateRoot);
    const headEvents = await readHeadEventRecords(stateRoot);
    const stateSummary = JSON.parse(
      await readFile(knowledgePaths.autonomousStateSummaryPath, "utf8"),
    ) as {
      activeChampionCandidateId: string | null;
      championOrigin: string | null;
      researchMaturity: string | null;
      nextPlannedAction: string | null;
    };

    expect(selection.activeChampionChanged).toBe(true);
    expect(selection.selectedCandidateId).toBe("steady-b");
    expect(headEvents.at(-1)).toEqual(
      expect.objectContaining({
        candidateId: "steady-b",
        previousChampionId: "bootstrap-a",
        selectionPhase: "steady_state",
        bootstrapSource: null,
        researchMaturity: "steady_state",
      }),
    );
    expect(headEvents.at(-1)?.selectionReason).toContain(
      "bootstrap baseline champion",
    );
    expect(stateSummary).toEqual(
      expect.objectContaining({
        activeChampionCandidateId: "steady-b",
        championOrigin: "autonomous",
        researchMaturity: "steady_state",
        nextPlannedAction: "archive_gap_exploration",
      }),
    );
  });
});
