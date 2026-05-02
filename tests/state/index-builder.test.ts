import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { type ArtifactBundle, type ExecutorCapability } from "../../src/contracts/types.js";
import { validateArtifactBundle } from "../../src/evaluation/artifact-validation.js";
import {
  appendExperimentRecord,
  appendIncidentRecord,
  appendResearchKnowledgeRecord,
  appendTaskBatchRecord,
  appendTaskRecord,
  readExperimentRecords,
} from "../../src/state/jsonl-store.js";
import { rebuildIndexes } from "../../src/state/index-builder.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";
import { sha256Json } from "../../src/utils/fs.js";

const tradingViewCapability: ExecutorCapability = {
  kind: "tradingview-live",
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
        parserVersion: "tradingview-report/v2",
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
});
