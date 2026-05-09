import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { type ArtifactBundle, type ExecutorCapability } from "../../src/contracts/types.js";
import { validateArtifactBundle } from "../../src/evaluation/artifact-validation.js";
import {
  appendAutonomousBranchRecord,
  appendExperimentRecord,
  appendHeadEventRecord,
  appendIncidentRecord,
  appendResearchKnowledgeRecord,
  appendTaskBatchRecord,
  appendTaskRecord,
  readExperimentRecords,
} from "../../src/state/jsonl-store.js";
import { rebuildIndexes } from "../../src/state/index-builder.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";
import { sha256Json } from "../../src/utils/fs.js";
import {
  AUTORESEARCH_CONTRACT_VERSION,
  STRATEGY_SPEC_MUTATION_AUTHORITY,
} from "../../src/policy/autoresearch-contract.js";

const tradingViewCapability: ExecutorCapability = {
  kind: "local-af-backtest",
  authoritative: true,
  supportedSymbols: ["QQQ"],
  supportedTimeframes: ["120"],
  supportedStrategyFamilies: ["Pine"],
  confidenceLevel: "verification",
};

function createPromotableArtifactBundle(): ArtifactBundle {
  return {
    strategy: {
      netProfitPercent: 25,
      postFeeNetProfitPercent: 21,
      profitFactor: 2.1,
      maxStrategyDrawdownPercent: 8,
      percentProfitable: 58,
      totalTrades: 73,
      avgTradePercent: 0.4,
    },
    trades: [
      {
        entryComment: null,
        entryPrice: null,
        entryTime: null,
        exitComment: null,
        exitPrice: null,
        exitTime: null,
        qty: null,
        profitValue: null,
        profitPercent: null,
        runupPercent: null,
        drawdownPercent: null,
      },
    ],
    equity: {
      available: true,
      unavailableReason: null,
      pointsAvailable: true,
      pointCount: 2,
      finalEquity: 10200,
      maxDrawdownPercent: 8,
      points: [
        { time: "2026-04-20T00:00:00.000Z", value: 10000 },
        { time: "2026-04-20T02:00:00.000Z", value: 10200 },
      ],
    },
    rawReportHash: "raw-report-hash",
    state: {
      reportDiagnostics: {
        hasNetProfit: true,
        hasTotalTrades: true,
        hasMaxDrawdown: true,
        hasProfitFactor: true,
        hasWinRate: true,
        hasTrades: true,
        hasEquitySummary: true,
        hasRawReport: true,
        missingFields: [],
        parseWarnings: [],
        parserVersion: "local-backtest-report/v1",
      },
    },
  };
}

async function writePromotionArtifacts(root: string, candidateId: string) {
  const candidatePath = path.join(root, `${candidateId}.pine`);
  const backtestArtifact = path.join(root, `${candidateId}.backtest.json`);
  await writeFile(candidatePath, "//@version=5\nstrategy('Index Test')\n", "utf8");
  await writeFile(backtestArtifact, JSON.stringify({ candidateId }), "utf8");
  return { candidatePath, backtestArtifact };
}

describe("rebuildIndexes", () => {
  test("uses index cache for append-only incremental updates after an initial full build", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-index-incremental-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    const manifestPath = path.join(
      knowledgePaths.runtimeDir,
      "autonomous-index-manifest.json",
    );

    await appendExperimentRecord(stateRoot, {
      runId: "run-incremental",
      iteration: 1,
      candidateId: "cand-first",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.35,
      decision: "accepted_no_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });
    await rebuildIndexes(stateRoot, { mode: "incremental" });
    const firstManifest = JSON.parse(await readFile(manifestPath, "utf8"));
    expect(firstManifest.mode).toBe("full");

    await appendExperimentRecord(stateRoot, {
      runId: "run-incremental",
      iteration: 2,
      candidateId: "cand-second",
      parentCandidateId: "cand-first",
      branchId: "main",
      acceptedHeadCandidateId: "cand-first",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.47,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });
    await rebuildIndexes(stateRoot, { mode: "incremental" });

    const secondManifest = JSON.parse(await readFile(manifestPath, "utf8"));
    const leaderboard = JSON.parse(
      await readFile(knowledgePaths.leaderboardPath, "utf8"),
    );

    expect(secondManifest.mode).toBe("incremental");
    expect(secondManifest.fallbackReason).toBeNull();
    expect(leaderboard.entries[0].candidateId).toBe("cand-second");
  });

  test("rebuilds leaderboard, lineage, and frontier deterministically from experiments.jsonl", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-indexes-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendExperimentRecord(stateRoot, {
      runId: "run-1",
      iteration: 1,
      candidateId: "baseline",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: "baseline",
      baselineCandidateId: "baseline",
      candidateScore: 0.44,
      decision: "accepted_no_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-1",
      iteration: 2,
      candidateId: "cand-2",
      parentCandidateId: "baseline",
      branchId: "main",
      acceptedHeadCandidateId: "baseline",
      baselineCandidateId: "baseline",
      candidateScore: 0.59,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-1",
      iteration: 3,
      candidateId: "cand-3",
      parentCandidateId: "cand-2",
      branchId: "main",
      acceptedHeadCandidateId: "cand-2",
      baselineCandidateId: "baseline",
      candidateScore: 0.31,
      decision: "hard_gate_fail",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-1",
      iteration: 4,
      candidateId: "cand-4",
      parentCandidateId: "cand-2",
      branchId: "main",
      acceptedHeadCandidateId: "cand-2",
      baselineCandidateId: "baseline",
      candidateScore: 0.39,
      decision: "accepted_no_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });
    await appendIncidentRecord(stateRoot, {
      runId: "run-1",
      iteration: 4,
      candidateId: "cand-4",
      incidentType: "accepted_no_improvement",
      detail: "legacy incident entry",
    });

    await rebuildIndexes(stateRoot);

    const leaderboard = JSON.parse(
      await readFile(knowledgePaths.leaderboardPath, "utf8"),
    );
    const lineage = JSON.parse(await readFile(knowledgePaths.lineagePath, "utf8"));
    const frontier = JSON.parse(await readFile(knowledgePaths.frontierPath, "utf8"));
    const failureSummary = JSON.parse(
      await readFile(knowledgePaths.failureSummaryPath, "utf8"),
    );
    const taskBoard = JSON.parse(await readFile(knowledgePaths.taskBoardPath, "utf8"));
    const lossPatternSummary = JSON.parse(
      await readFile(knowledgePaths.lossPatternSummaryPath, "utf8"),
    );
    const researchSummary = JSON.parse(
      await readFile(knowledgePaths.researchSummaryPath, "utf8"),
    );

    expect(leaderboard.entries.map((entry: { candidateId: string }) => entry.candidateId)).toEqual([
      "cand-2",
      "baseline",
      "cand-4",
    ]);
    expect(lineage.acceptedHeadCandidateId).toBe("cand-2");
    expect(lineage.activeHeadCandidateId).toBeNull();
    expect(leaderboard.verifiedHeadCandidateId).toBeNull();
    expect(leaderboard.legacyHeadCandidateId).toBe("cand-2");
    expect(leaderboard.topRankedCandidateId).toBe("cand-2");
    expect(leaderboard.headMatchesTopRanked).toBe(false);
    expect(lineage.nodes).toHaveLength(4);
    expect(frontier.entries.map((entry: { candidateId: string }) => entry.candidateId)).toEqual(
      [],
    );
    expect(failureSummary.decisionCounts.hard_gate_fail).toBe(1);
    expect(failureSummary.systemIncidentCounts).toEqual({});
    expect(failureSummary.evaluationIncidentCounts.accepted_no_improvement).toBe(1);
    expect(failureSummary.evaluationOutcomeCounts.hard_gate_fail).toBe(1);
    expect(failureSummary.verificationFailureReasonCounts).toEqual({});
    expect(failureSummary.compileFailureClassCounts.undeclared_identifier).toBe(0);
    expect(failureSummary.hardGateFailReasonCounts).toEqual({});
    expect(taskBoard.batches).toEqual([]);
    expect(lossPatternSummary.topLossZones).toEqual([]);
    expect(researchSummary.totalKnowledgeRecords).toBe(0);
  });

  test("prefers the best accepted improvement as the active head instead of the latest one", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-best-head-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendExperimentRecord(stateRoot, {
      runId: "run-best-head",
      iteration: 1,
      candidateId: "cand-strong",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.62,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-best-head",
      iteration: 2,
      candidateId: "cand-weaker",
      parentCandidateId: "cand-strong",
      branchId: "main",
      acceptedHeadCandidateId: "cand-strong",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.41,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });

    await rebuildIndexes(stateRoot);

    const leaderboard = JSON.parse(
      await readFile(knowledgePaths.leaderboardPath, "utf8"),
    );
    const lineage = JSON.parse(await readFile(knowledgePaths.lineagePath, "utf8"));

    expect(leaderboard.acceptedHeadCandidateId).toBe("cand-strong");
    expect(leaderboard.verifiedHeadCandidateId).toBeNull();
    expect(leaderboard.legacyHeadCandidateId).toBe("cand-strong");
    expect(leaderboard.activeHeadCandidateId).toBeNull();
    expect(leaderboard.topRankedCandidateId).toBe("cand-strong");
    expect(leaderboard.headMatchesTopRanked).toBe(false);
    expect(lineage.acceptedHeadCandidateId).toBe("cand-strong");
    expect(lineage.activeHeadCandidateId).toBeNull();
  });

  test("promotes a head-equivalent descendant into active-head views without changing accepted head", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-active-head-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    const artifactBundle = createPromotableArtifactBundle();
    const { candidatePath, backtestArtifact } = await writePromotionArtifacts(
      root,
      "cand-ae2377f7",
    );

    await appendExperimentRecord(stateRoot, {
      runId: "run-active-head",
      iteration: 1,
      candidateId: "cand-head",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.75,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
      testerMetrics: {
        netProfitPercent: 31.1,
        postFeeNetProfitPercent: 31.1,
        profitFactor: 7.52,
        maxStrategyDrawdownPercent: 4.8,
        percentProfitable: 79.75,
        totalTrades: 79,
        avgTradePercent: 3.41,
      },
      objectiveBreakdown: {
        score: 0.75,
        hardGatesPassed: true,
        softGuardrailBreached: false,
        hardGateReasons: [],
        components: {
          netProfitPercent: { rawValue: 31.1, normalizedValue: 1, weight: 0.45, contribution: 0.45 },
          profitFactor: { rawValue: 7.52, normalizedValue: 1, weight: 0.15, contribution: 0.15 },
          inverseMaxDrawdown: { rawValue: 4.8, normalizedValue: 0.84, weight: 0.15, contribution: 0.126 },
          percentProfitable: { rawValue: 79.75, normalizedValue: 0.7975, weight: 0.1, contribution: 0.07975 },
          totalTrades: { rawValue: 79, normalizedValue: 0.79, weight: 0.05, contribution: 0.0395 },
          avgTradePercent: { rawValue: 3.41, normalizedValue: 1, weight: 0.1, contribution: 0.1 },
        },
      },
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-verified-head",
      iteration: 2,
      candidateId: "cand-ae2377f7",
      parentCandidateId: "cand-head",
      branchId: "main",
      acceptedHeadCandidateId: "cand-head",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.75,
      decision: "verified_improvement",
      promotionStatus: "verified_improvement",
      promotionReady: true,
      mutationParseStatus: "valid",
      mutationProvenance: {
        briefHash: "brief-hash",
        promptHash: "prompt-hash",
        responseHash: "response-hash",
        responseSchemaVersion: "parsed-mutation-response/v1",
        parseStatus: "valid",
        inventorySource: "llm",
        inferredFields: [],
        missingFields: [],
      },
      verificationStatus: "verified",
      verificationFailureReason: null,
      verificationRuntimeFailureKind: null,
      executorCapability: tradingViewCapability,
      artifactBundle,
      artifactValidation: validateArtifactBundle({
        artifactBundle,
        executorCapability: tradingViewCapability,
      }),
      candidatePath,
      candidateHash: "candidate-hash",
      artifactPaths: {
        backtestArtifact,
      },
      recordEra: "v2",
      recordedAt: "2026-04-20T01:00:00.000Z",
      recordMeta: {
        schemaVersion: "experiment/v2",
        recordHash: "source-record-hash",
        candidateHash: "candidate-hash",
        baselineHash: "baseline-hash",
        artifactBundleHash: sha256Json(artifactBundle),
        pipelineVersion: "af-research-pipeline/v2",
      },
      testerMetrics: {
        netProfitPercent: 31.1,
        postFeeNetProfitPercent: 31.1,
        profitFactor: 7.52,
        maxStrategyDrawdownPercent: 4.8,
        percentProfitable: 79.75,
        totalTrades: 79,
        avgTradePercent: 3.41,
      },
      objectiveBreakdown: {
        score: 0.75,
        hardGatesPassed: true,
        softGuardrailBreached: false,
        hardGateReasons: [],
        components: {
          netProfitPercent: { rawValue: 31.1, normalizedValue: 1, weight: 0.45, contribution: 0.45 },
          profitFactor: { rawValue: 7.52, normalizedValue: 1, weight: 0.15, contribution: 0.15 },
          inverseMaxDrawdown: { rawValue: 4.8, normalizedValue: 0.84, weight: 0.15, contribution: 0.126 },
          percentProfitable: { rawValue: 79.75, normalizedValue: 0.7975, weight: 0.1, contribution: 0.07975 },
          totalTrades: { rawValue: 79, normalizedValue: 0.79, weight: 0.05, contribution: 0.0395 },
          avgTradePercent: { rawValue: 3.41, normalizedValue: 1, weight: 0.1, contribution: 0.1 },
        },
      },
      status: "evaluated",
    });
    const sourceRecord = (await readExperimentRecords(stateRoot)).find(
      (record) =>
        record.candidateId === "cand-ae2377f7" &&
        record.decision === "verified_improvement",
    );
    await appendExperimentRecord(stateRoot, {
      runId: "run-active-head",
      iteration: 3,
      candidateId: "cand-ae2377f7",
      parentCandidateId: "cand-head",
      branchId: "main",
      acceptedHeadCandidateId: "cand-head",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.75,
      decision: "promoted_head",
      promotionStatus: "promoted_head",
      promotionReady: true,
      mutationParseStatus: "valid",
      mutationProvenance: {
        briefHash: "brief-hash",
        promptHash: "prompt-hash",
        responseHash: "response-hash",
        responseSchemaVersion: "parsed-mutation-response/v1",
        parseStatus: "valid",
        inventorySource: "llm",
        inferredFields: [],
        missingFields: [],
      },
      verificationStatus: "verified",
      verificationFailureReason: null,
      verificationRuntimeFailureKind: null,
      executorCapability: tradingViewCapability,
      artifactBundle,
      artifactValidation: validateArtifactBundle({
        artifactBundle,
        executorCapability: tradingViewCapability,
      }),
      candidatePath,
      candidateHash: "candidate-hash",
      artifactPaths: {
        backtestArtifact,
      },
      recordEra: "v2",
      recordedAt: "2026-04-20T02:00:00.000Z",
      recordMeta: {
        schemaVersion: "experiment/v2",
        recordHash: "promoted-record-hash",
        candidateHash: "candidate-hash",
        baselineHash: "baseline-hash",
        artifactBundleHash: sha256Json(artifactBundle),
        promotedFromRunId: "run-verified-head",
        promotedFromIteration: 2,
        promotedFromRecordHash: sourceRecord?.recordMeta?.recordHash ?? null,
        pipelineVersion: "af-research-pipeline/v2",
      },
      status: "evaluated",
      testerMetrics: {
        netProfitPercent: 31.1,
        postFeeNetProfitPercent: 31.1,
        profitFactor: 7.52,
        maxStrategyDrawdownPercent: 4.8,
        percentProfitable: 79.75,
        totalTrades: 79,
        avgTradePercent: 3.41,
      },
      objectiveBreakdown: {
        score: 0.75,
        hardGatesPassed: true,
        softGuardrailBreached: false,
        hardGateReasons: [],
        components: {
          netProfitPercent: { rawValue: 31.1, normalizedValue: 1, weight: 0.45, contribution: 0.45 },
          profitFactor: { rawValue: 7.52, normalizedValue: 1, weight: 0.15, contribution: 0.15 },
          inverseMaxDrawdown: { rawValue: 4.8, normalizedValue: 0.84, weight: 0.15, contribution: 0.126 },
          percentProfitable: { rawValue: 79.75, normalizedValue: 0.7975, weight: 0.1, contribution: 0.07975 },
          totalTrades: { rawValue: 79, normalizedValue: 0.79, weight: 0.05, contribution: 0.0395 },
          avgTradePercent: { rawValue: 3.41, normalizedValue: 1, weight: 0.1, contribution: 0.1 },
        },
      },
    });

    await rebuildIndexes(stateRoot);

    const leaderboard = JSON.parse(
      await readFile(knowledgePaths.leaderboardPath, "utf8"),
    );
    const frontier = JSON.parse(await readFile(knowledgePaths.frontierPath, "utf8"));

    expect(leaderboard.acceptedHeadCandidateId).toBe("cand-ae2377f7");
    expect(leaderboard.verifiedHeadCandidateId).toBe("cand-ae2377f7");
    expect(leaderboard.legacyHeadCandidateId).toBe("cand-head");
    expect(leaderboard.activeHeadCandidateId).toBe("cand-ae2377f7");
    expect(leaderboard.topRankedCandidateId).toBe("cand-head");
    expect(leaderboard.headMatchesTopRanked).toBe(false);
    expect(frontier.activeHeadCandidateId).toBe("cand-ae2377f7");
  });

  test("rebuilds task board deterministically from task ledgers", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-task-board-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendTaskBatchRecord(stateRoot, {
      runId: "run-2",
      batchId: "batch-1",
      targetTaskCount: 2,
      completedTaskCount: 0,
      runtimeFailureCount: 0,
      maxRuntimeFailures: 3,
      status: "running",
      stopReason: null,
      recordedAt: "2026-04-23T10:00:00.000Z",
    });
    await appendTaskRecord(stateRoot, {
      runId: "run-2",
      batchId: "batch-1",
      taskId: "batch-1-task-01",
      taskNumber: 1,
      iteration: 1,
      status: "completed",
      hypothesis: {
        objective: "QQQ 120m improvement",
        nextMutationDirection: "Improve net profit.",
        recentFailures: [],
        acceptedHeadCandidateId: "baseline",
      },
      execution: {
        candidateId: "cand-1",
        studyTitle: "cand-1",
        status: "evaluated",
        decision: "accepted_improvement",
        compileOk: true,
        applyOk: true,
        artifactPaths: {},
        executorCapability: null,
        artifactValidation: null,
      },
      analysis: {
        decision: "accepted_improvement",
        score: 0.67,
        hardGatesPassed: true,
        softGuardrailBreached: false,
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
        nextMutationHints: ["hold gains"],
      },
      recordedAt: "2026-04-23T10:01:00.000Z",
    });
    await appendTaskBatchRecord(stateRoot, {
      runId: "run-2",
      batchId: "batch-1",
      targetTaskCount: 2,
      completedTaskCount: 1,
      runtimeFailureCount: 0,
      maxRuntimeFailures: 3,
      status: "completed",
      stopReason: null,
      recordedAt: "2026-04-23T10:02:00.000Z",
    });

    await rebuildIndexes(stateRoot);

    const taskBoard = JSON.parse(await readFile(knowledgePaths.taskBoardPath, "utf8"));
    expect(taskBoard.batches).toHaveLength(1);
    expect(taskBoard.batches[0].batchId).toBe("batch-1");
    expect(taskBoard.batches[0].status).toBe("completed");
    expect(taskBoard.batches[0].tasks[0].candidateId).toBe("cand-1");
  });

  test("excludes fallback verification failures from ranking views and indexes them separately", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-fallback-indexes-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    const artifactBundle = createPromotableArtifactBundle();
    const { candidatePath, backtestArtifact } = await writePromotionArtifacts(
      root,
      "cand-verified",
    );

    await appendExperimentRecord(stateRoot, {
      runId: "run-fallback-views",
      iteration: 1,
      candidateId: "cand-verified",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.81,
      decision: "verified_improvement",
      mutationParseStatus: "valid",
      mutationProvenance: {
        briefHash: "brief-hash",
        promptHash: "prompt-hash",
        responseHash: "response-hash",
        responseSchemaVersion: "parsed-mutation-response/v1",
        parseStatus: "valid",
        inventorySource: "llm",
        inferredFields: [],
        missingFields: [],
      },
      verificationStatus: "verified",
      verificationFailureReason: null,
      verificationRuntimeFailureKind: null,
      promotionStatus: "verified_improvement",
      promotionReady: true,
      executorCapability: tradingViewCapability,
      artifactBundle,
      artifactValidation: validateArtifactBundle({
        artifactBundle,
        executorCapability: tradingViewCapability,
      }),
      candidatePath,
      candidateHash: "candidate-hash",
      artifactPaths: {
        backtestArtifact,
      },
      recordEra: "v2",
      status: "evaluated",
      recordMeta: {
        schemaVersion: "experiment/v2",
        recordHash: "",
        candidateHash: "candidate-hash",
        baselineHash: "baseline-hash",
        artifactBundleHash: sha256Json(artifactBundle),
        pipelineVersion: "af-research-pipeline/v2",
      },
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-fallback-views",
      iteration: 2,
      candidateId: "cand-fallback",
      parentCandidateId: "cand-verified",
      branchId: "main",
      acceptedHeadCandidateId: "cand-verified",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.72,
      decision: "verification_fail",
      verificationStatus: "verification_failed",
      verificationFailureReason: "verification_runtime_failure",
      verificationRuntimeFailureKind: "pine_editor_open_timeout",
      promotionStatus: "verification_failed",
      promotionReady: false,
      recordEra: "v2",
      status: "evaluated",
      artifactPaths: {
        fallbackEvidenceArtifact: path.join(root, "fallback-evidence.json"),
      },
      fallbackEvaluation: {
        role: "fallback_evidence",
        executorKind: "local-af-screening",
        executorAuthoritative: false,
        promotionEligible: false,
        status: "succeeded",
        reason: "local_fallback_completed",
        artifactId: "fallback-evidence-cand-fallback",
        artifactHash: "fallback-hash",
        metrics: null,
        objectiveBreakdown: null,
        artifactValidation: null,
        decisionIfScreeningOnly: "screening_improvement",
        compatibility: {
          symbol: "QQQ",
          timeframe: "120",
          strategyFamily: "AF",
          compatible: true,
          reasons: [],
        },
        evidenceUse: "mutation_context_only",
        confidence: "very_low",
        caveats: ["Do not treat local fallback evidence as verified improvement."],
        parity: {
          status: "not_comparable",
          tradeCountDelta: null,
          netProfitPctDelta: null,
          maxDrawdownPctDelta: null,
          profitFactorDelta: null,
          winRateDelta: null,
        },
      },
    });

    await rebuildIndexes(stateRoot);

    const leaderboard = JSON.parse(await readFile(knowledgePaths.leaderboardPath, "utf8"));
    const frontier = JSON.parse(await readFile(knowledgePaths.frontierPath, "utf8"));
    const verificationFailures = JSON.parse(
      await readFile(knowledgePaths.verificationFailuresPath, "utf8"),
    );
    const fallbackEvidenceBoard = JSON.parse(
      await readFile(knowledgePaths.fallbackEvidenceBoardPath, "utf8"),
    );
    const runtimeFailureSummary = JSON.parse(
      await readFile(knowledgePaths.runtimeFailureSummaryPath, "utf8"),
    );
    const divergenceSummary = JSON.parse(
      await readFile(knowledgePaths.localTvDivergenceSummaryPath, "utf8"),
    );
    const verificationQueue = JSON.parse(
      await readFile(knowledgePaths.verificationQueuePath, "utf8"),
    );

    expect(
      leaderboard.entries.map((entry: { candidateId: string }) => entry.candidateId),
    ).toEqual(["cand-verified"]);
    expect(
      frontier.entries.map((entry: { candidateId: string }) => entry.candidateId),
    ).toEqual(["cand-verified"]);
    expect(
      verificationFailures.entries.map((entry: { candidateId: string }) => entry.candidateId),
    ).toContain("cand-fallback");
    expect(
      fallbackEvidenceBoard.entries.map((entry: { candidateId: string }) => entry.candidateId),
    ).toContain("cand-fallback");
    expect(runtimeFailureSummary.counts.pine_editor_open_timeout).toBe(1);
    expect(divergenceSummary.parityStatusCounts.not_comparable).toBe(1);
    expect(
      verificationQueue.entries.map((entry: { candidateId: string }) => entry.candidateId),
    ).toContain("cand-fallback");
  });

  test("prefers later authoritative local-TV parity over fallback placeholder parity", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-parity-calibrated-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendExperimentRecord(stateRoot, {
      runId: "run-parity",
      iteration: 1,
      candidateId: "cand-parity",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.5,
      decision: "verification_fail",
      verificationStatus: "verification_failed",
      verificationFailureReason: "verification_runtime_failure",
      verificationRuntimeFailureKind: "report_parse_timeout",
      promotionStatus: "verification_failed",
      promotionReady: false,
      recordEra: "v2",
      status: "verification_failed",
      fallbackEvaluation: {
        role: "fallback_evidence",
        executorKind: "local-af-screening",
        executorAuthoritative: false,
        promotionEligible: false,
        status: "succeeded",
        reason: "local_fallback_completed",
        artifactId: "fallback-evidence-cand-parity",
        artifactHash: "fallback-parity-hash",
        metrics: null,
        objectiveBreakdown: null,
        artifactValidation: null,
        decisionIfScreeningOnly: "screening_improvement",
        compatibility: {
          symbol: "QQQ",
          timeframe: "120",
          strategyFamily: "AF",
          compatible: true,
          reasons: [],
        },
        evidenceUse: "mutation_context_only",
        confidence: "very_low",
        caveats: [],
        parity: {
          status: "not_comparable",
          tradeCountDelta: null,
          netProfitPctDelta: null,
          maxDrawdownPctDelta: null,
          profitFactorDelta: null,
          winRateDelta: null,
        },
      },
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-parity",
      iteration: 2,
      candidateId: "cand-parity",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.66,
      decision: "verified_improvement",
      verificationStatus: "verified",
      promotionStatus: "verified_improvement",
      promotionReady: false,
      localTvParity: {
        status: "matched",
        tradeCountDelta: 1,
        netProfitPctDelta: 1.2,
        maxDrawdownPctDelta: 0.5,
        profitFactorDelta: 0.08,
        winRateDelta: 2,
      },
      recordEra: "v2",
      status: "evaluated",
    });

    await rebuildIndexes(stateRoot);

    const divergenceSummary = JSON.parse(
      await readFile(knowledgePaths.localTvDivergenceSummaryPath, "utf8"),
    );
    const fallbackEvidenceBoard = JSON.parse(
      await readFile(knowledgePaths.fallbackEvidenceBoardPath, "utf8"),
    );

    expect(divergenceSummary.parityStatusCounts).toEqual({ matched: 1 });
    expect(divergenceSummary.latestEntries[0]).toMatchObject({
      candidateId: "cand-parity",
      source: "authoritative",
    });
    expect(fallbackEvidenceBoard.entries[0].resolvedParity).toMatchObject({
      status: "matched",
      tradeCountDelta: 1,
    });
  });

  test("keeps screening-board scoped to v2 screening decisions only", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-screening-scope-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendExperimentRecord(stateRoot, {
      runId: "run-screening-scope",
      iteration: 1,
      candidateId: "cand-screening",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.51,
      decision: "screening_improvement",
      verificationStatus: "not_requested",
      promotionStatus: "screening_only",
      promotionReady: false,
      recordEra: "v2",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-screening-scope",
      iteration: 2,
      candidateId: "cand-valid",
      parentCandidateId: "cand-screening",
      branchId: "main",
      acceptedHeadCandidateId: "cand-screening",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.49,
      decision: "valid_no_promotion",
      verificationStatus: "verified",
      promotionStatus: "not_promoted",
      promotionReady: false,
      recordEra: "v2",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-screening-scope",
      iteration: 3,
      candidateId: "cand-hard-gate",
      parentCandidateId: "cand-valid",
      branchId: "main",
      acceptedHeadCandidateId: "cand-screening",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.22,
      decision: "hard_gate_fail",
      verificationStatus: "verified",
      promotionStatus: "not_promoted",
      promotionReady: false,
      recordEra: "v2",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-screening-scope",
      iteration: 4,
      candidateId: "cand-artifact",
      parentCandidateId: "cand-hard-gate",
      branchId: "main",
      acceptedHeadCandidateId: "cand-screening",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.4,
      decision: "artifact_incomplete",
      verificationStatus: "verification_failed",
      promotionStatus: "not_promoted",
      promotionReady: false,
      recordEra: "v2",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-screening-scope",
      iteration: 5,
      candidateId: "cand-verification-fail",
      parentCandidateId: "cand-artifact",
      branchId: "main",
      acceptedHeadCandidateId: "cand-screening",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.47,
      decision: "verification_fail",
      verificationStatus: "verification_failed",
      verificationFailureReason: "verification_metric_regress",
      promotionStatus: "verification_failed",
      promotionReady: false,
      recordEra: "v2",
      status: "evaluated",
    });

    await rebuildIndexes(stateRoot);

    const leaderboard = JSON.parse(
      await readFile(knowledgePaths.leaderboardPath, "utf8"),
    );

    expect(
      leaderboard.screeningEntries.map((entry: { candidateId: string }) => entry.candidateId),
    ).toEqual(["cand-screening", "cand-valid"]);
  });

  test("rebuilds loss-pattern-summary from experiment loss analysis", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-loss-summary-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendExperimentRecord(stateRoot, {
      runId: "run-3",
      iteration: 1,
      candidateId: "cand-1",
      parentCandidateId: "seed_primary",
      branchId: "main",
      acceptedHeadCandidateId: "seed_primary",
      baselineCandidateId: "seed_primary",
      seedStrategyId: "seed_primary",
      improvementSource: "seed",
      candidateScore: 0.55,
      decision: "accepted_improvement",
      status: "evaluated",
      lossAnalysisSummary: {
        status: "available",
        summary: "Losses cluster in trend_down.",
        topLossZones: ["trend_down:counter_trend_entry"],
        repairPriorities: ["Reduce counter-trend entries during trend_down regimes."],
      },
      topLossZones: ["trend_down:counter_trend_entry"],
      repairPriorities: ["Reduce counter-trend entries during trend_down regimes."],
      recordEra: "legacy",
    });

    await rebuildIndexes(stateRoot);

    const lossSummary = JSON.parse(
      await readFile(knowledgePaths.lossPatternSummaryPath, "utf8"),
    );
    expect(lossSummary.topLossZones[0].label).toBe("trend_down:counter_trend_entry");
    expect(lossSummary.topRepairPriorities[0].label).toContain("Reduce counter-trend");
  });

  test("summarizes compile-failure classes and hard-gate fail reasons", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-failure-summary-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendExperimentRecord(stateRoot, {
      runId: "run-4",
      iteration: 1,
      candidateId: "cand-compile",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: null,
      decision: "compile_fail",
      status: "compile_failed",
      compile: {
        ok: false,
        errors: [
          "Undeclared identifier 'emaLen'",
          "The 'strategy.entry' function does not have an argument with the name 'qty_percent'",
        ],
      },
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-4",
      iteration: 2,
      candidateId: "cand-hard-gate",
      parentCandidateId: "cand-compile",
      branchId: "main",
      acceptedHeadCandidateId: "cand-compile",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.21,
      decision: "hard_gate_fail",
      status: "evaluated",
      objectiveBreakdown: {
        score: 0.21,
        hardGatesPassed: false,
        softGuardrailBreached: false,
        hardGateReasons: ["minimum_total_trades", "positive_post_fee_profit"],
        components: {
          netProfitPercent: { rawValue: 0.1, normalizedValue: 0.01, weight: 0.45, contribution: 0.0045 },
          profitFactor: { rawValue: 1.1, normalizedValue: 0.36, weight: 0.15, contribution: 0.054 },
          inverseMaxDrawdown: { rawValue: 2, normalizedValue: 0.93, weight: 0.15, contribution: 0.1395 },
          percentProfitable: { rawValue: 30, normalizedValue: 0.3, weight: 0.1, contribution: 0.03 },
          totalTrades: { rawValue: 22, normalizedValue: 0.22, weight: 0.05, contribution: 0.011 },
          avgTradePercent: { rawValue: 0.08, normalizedValue: 0.08, weight: 0.1, contribution: 0.008 },
        },
      },
    });

    await rebuildIndexes(stateRoot);

    const failureSummary = JSON.parse(
      await readFile(knowledgePaths.failureSummaryPath, "utf8"),
    );

    expect(failureSummary.compileFailureClassCounts.undeclared_identifier).toBe(1);
    expect(failureSummary.compileFailureClassCounts.qty_percent_argument).toBe(1);
    expect(failureSummary.hardGateFailReasonCounts.minimum_total_trades).toBe(1);
    expect(failureSummary.hardGateFailReasonCounts.positive_post_fee_profit).toBe(1);
    expect(failureSummary.hardGateFailPatterns[0].label).toBe(
      "minimum_total_trades+positive_post_fee_profit",
    );
  });

  test("rebuilds research-summary from research knowledge ledger", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-research-summary-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendResearchKnowledgeRecord(stateRoot, {
      knowledgeId: "rsk-1",
      sourceType: "manual_text",
      title: "Weak exit memo",
      sourcePath: null,
      sourceUrl: null,
      contentHash: "hash-1",
      rawTextPath: path.join(knowledgePaths.researchDir, "rsk-1.txt"),
      summary: "Weak exit memo.",
      problemTags: ["weak_exit", "trend_down"],
      strategyTags: ["exit_tightening"],
      insights: [
        {
          insightId: "insight-1",
          summary: "Exit faster in weak downtrend recoveries.",
          rationale: "Losses deepen when the trend remains down.",
          suggestedMutation: "Tighten exits when trend_down persists.",
          relatedFailurePatterns: ["weak_exit"],
          keywords: ["exit"],
          confidence: 0.8,
        },
      ],
    });

    await rebuildIndexes(stateRoot);

    const researchSummary = JSON.parse(
      await readFile(knowledgePaths.researchSummaryPath, "utf8"),
    );
    expect(researchSummary.totalKnowledgeRecords).toBe(1);
    expect(researchSummary.latestKnowledge[0].knowledgeId).toBe("rsk-1");
    expect(researchSummary.topProblemTags[0].label).toBe("trend_down");
    expect(researchSummary.topStrategyTags[0].label).toBe("exit_tightening");
  });

  test("surfaces verified autoresearch contract readiness in autonomous dashboard views", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-verified-dashboard-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    const recordedAt = "2026-04-28T00:00:00.000Z";
    const candidatePath = path.join(root, "cand-promote.pine");
    const specPath = path.join(root, "cand-promote.af-spec.json");
    await writeFile(candidatePath, "//@version=5\nstrategy('candidate')\n", "utf8");
    await writeFile(specPath, "{\"version\":\"af-spec/v1\"}\n", "utf8");

    const localRecord = {
      runId: "run-verified-dashboard",
      iteration: 1,
      candidateId: "cand-promote",
      parentCandidateId: null,
      branchId: "branch-main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: null,
      candidatePath,
      candidateHash: "candidate-hash",
      contractVersion: AUTORESEARCH_CONTRACT_VERSION,
      mutationAuthority: STRATEGY_SPEC_MUTATION_AUTHORITY,
      specPath,
      specHash: "spec-hash",
      studyTitle: "Promotable",
      candidateScore: 0.7,
      decision: "local_candidate_eligible",
      status: "evaluated",
      recordKind: "local_evaluation",
      executorRole: "primary_local_backtest",
      evidenceAuthority: "local_model",
      evaluationMode: "local_primary",
      objectivePolicyVersion: "objective.qqq-120m/v1",
      selectionPolicyVersion: "autonomous-tv-verified/v4",
      selectionPhase: "steady_state",
      localConfidence: 1,
      tvCalibrationStatus: "not_requested",
      localTvParity: null,
      researchStage: "calibration_queued",
      structureFamilyHash: "family-a",
      fingerprintFamily: "fingerprint-a",
      parameterNeighborhood: "neighborhood-a",
      testerMetrics: {
        netProfitPercent: 12,
        postFeeNetProfitPercent: 10,
        profitFactor: 1.6,
        maxStrategyDrawdownPercent: 8,
        percentProfitable: 55,
        totalTrades: 90,
        avgTradePercent: 0.2,
      },
      noveltyFingerprint: {
        fingerprint: "fp-a",
        fingerprintFamily: "fingerprint-a",
        inventorySignature: "inventory-a",
        structureSignature: "structure-a",
        featureFlags: [],
        configBuckets: {},
        tokens: [],
      },
      autoSelectionBreakdown: {
        baseObjectiveScore: 0.7,
        robustnessScore: 0.1,
        noveltyScore: 0.1,
        diversityScore: 0,
        localConfidenceBonus: 0,
        riskPenalty: 0,
        overfitPenalty: 0,
        duplicatePenalty: 0,
        divergencePenalty: 0,
        complexityPenalty: 0.05,
        totalScore: 0.7,
        eligible: true,
        rejectionReasons: [],
      },
      localFrontierScore: 0.7,
      autoSelectionScore: 0.7,
      duplicateStatus: {
        classification: "unique",
        exactDuplicateCandidateId: null,
        structuralDuplicateCandidateId: null,
        duplicateFingerprint: null,
      },
      localCompatibility: {
        compatible: true,
        unsupportedReason: null,
        missingFunctions: [],
        missingInputs: [],
        unsupportedPatterns: [],
      },
      eligibility: {
        autoSelectionEligible: true,
        bootstrapEligible: false,
        archiveEligible: true,
        calibrationEligible: true,
        blockingReasons: [],
      },
      artifactPaths: { candidate: candidatePath, spec: specPath },
      recordMeta: {
        schemaVersion: "experiment/v3",
        recordHash: "local-record-hash",
        candidateHash: "candidate-hash",
        baselineHash: null,
        artifactBundleHash: null,
        pipelineVersion: "test",
      },
      recordedAt,
    };
    const tvRecord = {
      ...localRecord,
      runId: "run-verified-dashboard-tv",
      recordKind: "tv_verification",
      executorRole: "primary_local_backtest",
      evidenceAuthority: "local_model",
      evaluationMode: "tv_calibration",
      decision: "tv_verified",
      status: "verified",
      tvCalibrationStatus: "verified_match",
      researchStage: "promotion_candidate",
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
        medianOosPostFeeNetProfitPercent: 6,
        embargoBars: 5,
        minimumCoverageDays: 730,
        coverageDays: 900,
        canaryHoldout: {
          policyVersion: "canary-holdout/v1",
          mode: "sealed",
          exposed: false,
          reason: "automatic loop cannot evaluate sealed canary",
        },
        passed: true,
        gateReasons: [],
        folds: [],
      },
      verifiedPromotionScore: 0.72,
      verifiedPromotion: {
        eligible: true,
        score: 0.72,
        scoreBreakdown: {
          tvPerformanceScore: 0.3,
          walkForwardRobustnessScore: 0.18,
          foldConsistencyScore: 0.15,
          tradeDensityScore: 0.1,
          parityScore: 0.05,
          simplicityScore: 0.03,
          trialBudgetPenalty: 0.02,
          regimeConcentrationPenalty: 0,
          complexityPenalty: 0.07,
          totalScore: 0.72,
          minimumRequiredScore: 0.62,
        },
        rejectionReasons: [],
        localCandidateHash: "candidate-hash",
        tvCandidateHash: "candidate-hash",
        structureFamilyHash: "family-a",
        fingerprintFamily: "fingerprint-a",
        parameterNeighborhood: "neighborhood-a",
        trialLedgerStats: {
          totalCandidatesTried: 42,
          totalLocalPass: 12,
          totalTvVerified: 4,
          totalPromotionCandidates: 1,
          familyTrials: 7,
          fingerprintFamilyTrials: 7,
          parameterNeighborhoodTrials: 3,
          oosExposureCount: 12,
          canaryExposureCount: 0,
        },
        localRecordKind: "local_evaluation",
        tvRecordKind: "tv_verification",
        policyVersion: "verified-promotion/v1",
      },
      recordMeta: {
        schemaVersion: "experiment/v3",
        recordHash: "tv-record-hash",
        candidateHash: "candidate-hash",
        baselineHash: null,
        artifactBundleHash: null,
        pipelineVersion: "test",
      },
    };
    const driftRecord = {
      ...tvRecord,
      runId: "run-verified-dashboard-drift",
      iteration: 2,
      candidateId: "cand-drift",
      candidateHash: "drift-hash",
      specPath: path.join(root, "cand-drift.af-spec.json"),
      specHash: "drift-spec-hash",
      verifiedPromotionScore: null,
      walkForwardEvaluation: {
        ...tvRecord.walkForwardEvaluation,
        positiveOosFoldCount: 3,
        passed: false,
        gateReasons: ["required_positive_oos_folds"],
      },
      verifiedPromotion: {
        ...tvRecord.verifiedPromotion,
        eligible: false,
        score: null,
        localCandidateHash: "drift-hash",
        tvCandidateHash: "drift-hash",
        rejectionReasons: ["parity_major_drift"],
      },
      researchStage: "quarantined",
      localTvParity: {
        ...tvRecord.localTvParity,
        status: "major_drift",
      },
      recordMeta: {
        ...tvRecord.recordMeta,
        recordHash: "drift-record-hash",
        candidateHash: "drift-hash",
      },
    };

    await appendExperimentRecord(stateRoot, localRecord);
    await appendExperimentRecord(stateRoot, tvRecord);
    await appendExperimentRecord(stateRoot, driftRecord);
    await appendHeadEventRecord(stateRoot, {
      runId: "run-verified-dashboard-head",
      iteration: 3,
      eventKind: "champion_updated",
      candidateId: "cand-promote",
      previousChampionId: null,
      selectedBy: "auto_policy",
      policyVersion: "autonomous-tv-verified/v4",
      headAuthority: "verified_promotion",
      selectionPhase: "steady_state",
      bootstrapSource: null,
      bootstrapReason: null,
      researchMaturity: "steady_state",
      performanceScore: 0.3,
      objectiveScore: 0.7,
      noveltyScore: 0,
      robustnessScore: 0.18,
      autoSelectionScore: 0.72,
      diversityScore: 0,
      diversityContribution: 0,
      localConfidenceBonus: 0,
      riskPenalty: 0,
      overfitPenalty: 0,
      duplicatePenalty: 0,
      divergencePenalty: 0,
      complexityPenalty: 0.07,
      selectionReason: "Verified promotion test head.",
      selectionEvidenceHash: "selection-hash",
      humanOverride: false,
      recordedAt,
    });
    await appendAutonomousBranchRecord(stateRoot, {
      branchId: "branch-champion",
      branchKind: "champion_exploit",
      budgetPct: 50,
      parentCandidateId: null,
      followUpRemaining: 0,
      createdAt: recordedAt,
      lastCandidateId: "cand-promote",
      status: "active",
    });
    await appendAutonomousBranchRecord(stateRoot, {
      branchId: "branch-breakout",
      branchKind: "exploration_breakout",
      budgetPct: 20,
      parentCandidateId: "cand-promote",
      followUpRemaining: 0,
      createdAt: recordedAt,
      lastCandidateId: "cand-drift",
      status: "exhausted",
    });

    await rebuildIndexes(stateRoot);

    const summary = JSON.parse(
      await readFile(knowledgePaths.autonomousStateSummaryPath, "utf8"),
    );
    const branchBudget = JSON.parse(
      await readFile(path.join(knowledgePaths.viewsDir, "autonomous", "branch-budget.json"), "utf8"),
    );
    const readiness = JSON.parse(
      await readFile(
        path.join(knowledgePaths.viewsDir, "autonomous", "verified-promotion-readiness.json"),
        "utf8",
      ),
    );

    expect(summary.loopMode).toBe("verified-promotion-first");
    expect(summary.activeChampionCandidateId).toBe("cand-promote");
    expect(summary.verifiedPromotionScore).toBe(0.72);
    expect(summary.parityStatusCounts.matched).toBe(1);
    expect(summary.parityStatusCounts.major_drift).toBe(1);
    expect(summary.walkForwardStatusCounts.passed).toBe(1);
    expect(summary.researchStageCounts.champion).toBe(1);
    expect(summary.researchStageCounts.quarantined).toBe(1);
    expect(summary.quarantineCount).toBe(1);
    expect(summary.trialPressure.familyTrials).toBe(7);
    expect(summary.trialPressure.minimumRequiredScore).toBe(0.62);
    expect(summary.branchBudget.targets.champion_exploit).toBe(50);
    expect(summary.branchBudget.entries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          branchKind: "champion_exploit",
          targetPct: 50,
          actualCount: 1,
        }),
      ]),
    );
    expect(branchBudget.summary.totalBranches).toBe(2);
    expect(readiness.entries[0]).toEqual(
      expect.objectContaining({
        candidateId: "cand-promote",
        eligible: true,
        verifiedPromotionScore: 0.72,
        parityStatus: "matched",
        walkForwardStatus: "passed",
      }),
    );
  });
});
