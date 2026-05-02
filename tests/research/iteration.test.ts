import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { createMockPineEvaluationExecutor } from "../../src/automation/tradingview/mock-driver.js";
import { createCliMonitor } from "../../src/cli/monitor.js";
import { createStaticLlmClient } from "../../src/mutation/llm-client.js";
import { runSingleIteration } from "../../src/research/iteration-runner.js";
import { initializeWorkspace } from "../../src/research/workspace.js";
import {
  appendExperimentRecord,
  appendResearchKnowledgeRecord,
  readIncidentRecords,
} from "../../src/state/jsonl-store.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";

const baseMutationResponse = JSON.stringify({
  candidateSummary: "Candidate from test",
  nextMutationHints: ["hint-a", "hint-b"],
  pineScript: "//@version=5\nstrategy('Mutated', overlay=true)\n",
  strategySpec: {
    version: "af-spec/v1",
    name: "Mutated",
    event: {
      source: "af_exhaustion",
      L1: 9,
      L2: 12,
      L3: 14,
      confirmBars: 2,
      eventFloorBars: null,
      eventWindowBars: null,
    },
    regime: {
      trendMode: "Balanced",
      useSupertrendFilter: false,
      riskOffRsi: 45,
      maxExtPct: 6,
    },
    entry: {
      primaryTrigger: "bull_event",
      cooldownBars: 0,
      allowBearRebound: true,
      applyFilterToB1: false,
    },
    slot: {
      slotPct: 15,
      maxSlots: 18,
      useReplacement: true,
      replaceMinRank: 3,
      replaceIfPnlBelow: -5,
    },
    exit: {
      weakRangeExit: true,
      maxHoldBars: null,
      closeAllOnBearConfRiskOff: true,
      resetOnL3: false,
    },
  },
  specPatch: {
    source: "test",
  },
  inventory: [
    {
      conditionId: "entry-alpha",
      role: "entry",
      summary: "Entry condition",
      pineLineHints: [10],
    },
    {
      conditionId: "risk-alpha",
      role: "risk",
      summary: "Risk condition",
      pineLineHints: [20],
    },
  ],
});

const repairMutationResponse = JSON.stringify({
  candidateSummary: "Candidate repaired from compile failure",
  nextMutationHints: ["replace-unsupported-function"],
  pineScript: "//@version=5\nstrategy('Mutated Repaired', overlay=true)\n",
  strategySpec: {
    version: "af-spec/v1",
    name: "Mutated Repaired",
    event: {
      source: "af_exhaustion",
      L1: 9,
      L2: 12,
      L3: 14,
      confirmBars: 2,
      eventFloorBars: null,
      eventWindowBars: null,
    },
    regime: {
      trendMode: "Balanced",
      useSupertrendFilter: false,
      riskOffRsi: 45,
      maxExtPct: 6,
    },
    entry: {
      primaryTrigger: "bull_event",
      cooldownBars: 0,
      allowBearRebound: true,
      applyFilterToB1: false,
    },
    slot: {
      slotPct: 15,
      maxSlots: 18,
      useReplacement: true,
      replaceMinRank: 3,
      replaceIfPnlBelow: -5,
    },
    exit: {
      weakRangeExit: true,
      maxHoldBars: null,
      closeAllOnBearConfRiskOff: true,
      resetOnL3: false,
    },
  },
  specPatch: {
    source: "test_repair",
  },
  inventory: [
    {
      conditionId: "entry-alpha",
      role: "entry",
      summary: "Entry condition",
      pineLineHints: [10],
    },
  ],
});

describe("runSingleIteration", () => {
  test("records compile_fail decisions", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-compile-fail-"));
    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor({
        compile: { ok: false, errors: ["line 12"] },
      }),
    });

    expect(result.decision).toBe("compile_fail");
  });

  test("records mutation_generation_fail decisions when Pine generation fails", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-generation-fail-"));
    const failingLlmClient = {
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

    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: failingLlmClient,
      executor: createMockPineEvaluationExecutor(),
    });

    expect(result.decision).toBe("mutation_generation_fail");
    expect(result.experiment.decision).toBe("mutation_generation_fail");
    expect(result.experiment.artifactPaths?.mutationFailureArtifact).toBeTruthy();
  });

  test("records apply_fail decisions", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-apply-fail-"));
    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor({
        compile: { ok: true, errors: [] },
        apply: { ok: false, message: "chart rejected strategy" },
      }),
    });

    expect(result.decision).toBe("apply_fail");
  });

  test("records backtest_empty decisions", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-empty-"));
    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor({
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 0,
          postFeeNetProfitPercent: 0,
          profitFactor: 0,
          maxStrategyDrawdownPercent: 0,
          percentProfitable: 0,
          totalTrades: 0,
          avgTradePercent: 0,
        },
      }),
    });

    expect(result.decision).toBe("backtest_empty");
  });

  test("records accepted_improvement and writes condition contributions", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-accepted-"));
    const stateRoot = path.join(workspace, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    await initializeWorkspace(workspace);
    const monitorLines: string[] = [];
    const monitor = await createCliMonitor({
      workspaceRoot: workspace,
      commandName: "iterate",
      sink: (line) => monitorLines.push(line),
    });
    await monitor.setTask(1);
    await writeFile(
      knowledgePaths.qqqTwoHourContextPath,
      `${JSON.stringify(
        {
          generatedAt: "2026-04-24T00:00:00.000Z",
          symbol: "QQQ",
          timeframe: "2h",
          bars: [
            {
              time: "2026-04-20T00:00:00.000Z",
              open: 100,
              high: 101,
              low: 99,
              close: 100,
              volume: 1000,
              ema20: 101,
              ema50: 103,
              ema200: 110,
              atr14: 2,
              atrPercent: 2,
              rsi14: 40,
              bbWidth: 0.06,
              ret3: -0.03,
              ret10: -0.05,
              regime: "trend_down",
            },
            {
              time: "2026-04-20T02:00:00.000Z",
              open: 99,
              high: 99,
              low: 97,
              close: 98,
              volume: 1000,
              ema20: 100,
              ema50: 102,
              ema200: 109,
              atr14: 2.4,
              atrPercent: 2.4,
              rsi14: 36,
              bbWidth: 0.07,
              ret3: -0.04,
              ret10: -0.06,
              regime: "trend_down",
            },
          ],
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
    await appendResearchKnowledgeRecord(stateRoot, {
      knowledgeId: "rsk-test-1",
      sourceType: "manual_text",
      title: "Range weak exit note",
      sourcePath: null,
      sourceUrl: null,
      contentHash: "hash-1",
      rawTextPath: path.join(knowledgePaths.researchDir, "rsk-test-1.txt"),
      summary: "Range and weak-exit research note.",
      problemTags: ["trend_down", "weak_exit"],
      strategyTags: ["exit_tightening"],
      insights: [
        {
          insightId: "insight-1",
          summary: "Weak exits during down regimes should cut faster.",
          rationale: "Research suggests faster invalidation when trend remains down.",
          suggestedMutation: "Tighten exits when trend_down persists after long entry.",
          relatedFailurePatterns: ["trend_down", "weak_exit"],
          keywords: ["exit", "trend_down"],
          confidence: 0.86,
        },
      ],
    });

    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor({
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 25,
          postFeeNetProfitPercent: 22,
          profitFactor: 2.4,
          maxStrategyDrawdownPercent: 9,
          percentProfitable: 63,
          totalTrades: 87,
          avgTradePercent: 0.55,
        },
        trades: [
          {
            entryComment: "entry",
            entryPrice: 100,
            entryTime: "2026-04-20T00:00:00.000Z",
            exitComment: "exit",
            exitPrice: 98,
            exitTime: "2026-04-20T02:00:00.000Z",
            qty: 1,
            profitValue: -2,
            profitPercent: -2,
            runupPercent: 0.2,
            drawdownPercent: 2.1,
          },
        ],
        equity: {
          available: true,
          pointsAvailable: true,
          pointCount: 2,
          finalEquity: 10200,
          maxDrawdownPercent: 9,
          points: [
            { time: "2026-04-20T00:00:00.000Z", value: 10000 },
            { time: "2026-04-20T02:00:00.000Z", value: 10200 },
          ],
        },
        ablations: {
          "entry-alpha": {
            netProfitPercent: 20,
            postFeeNetProfitPercent: 17,
            profitFactor: 2.0,
            maxStrategyDrawdownPercent: 9,
            percentProfitable: 59,
            totalTrades: 82,
            avgTradePercent: 0.44,
          },
          "risk-alpha": {
            netProfitPercent: 22,
            postFeeNetProfitPercent: 20,
            profitFactor: 2.1,
            maxStrategyDrawdownPercent: 14,
            percentProfitable: 61,
            totalTrades: 86,
            avgTradePercent: 0.49,
          },
        },
      }),
      acceptedHeadScore: 0.5,
      monitor,
    });
    await monitor.close();

    expect(result.decision).toBe("verified_improvement");
    expect(result.conditionContributions).toHaveLength(2);
    expect(result.hypothesis.nextMutationDirection).toContain("Reduce");
    expect(result.experiment.studyTitle).toContain(result.experiment.candidateId);
    expect(result.experiment.syncArtifact?.attachDiagnostics?.exactTitleMatched).toBe(true);
    expect(result.experiment.artifactBundle).toBeUndefined();
    expect(result.experiment.artifactSummary?.tradeCount).toBe(1);
    expect(result.experiment.artifactBundleRef?.path).toBeTruthy();
    expect(result.experiment.seedStrategyId).toBe("seed_primary");
    expect(result.experiment.improvementSource).toBe("seed");
    expect(result.experiment.mutationProvenance).toMatchObject({
      parseStatus: "valid",
      inventorySource: "llm",
    });
    expect(result.experiment.mutationProvenance?.briefHash).toBeTruthy();
    expect(result.experiment.mutationProvenance?.promptHash).toBeTruthy();
    expect(result.experiment.mutationProvenance?.responseHash).toBeTruthy();
    expect(result.experiment.mutationProvenance?.responseSchemaVersion).toBe(
      "parsed-mutation-response/v1",
    );
    expect(result.experiment.lossAnalysisSummary?.status).toBe("available");
    expect(result.experiment.researchContextSummary?.status).toBe("available");
    expect(result.experiment.researchContextSummary?.insights).toHaveLength(1);
    expect(
      (result.experiment as Record<string, unknown>).pineAnalysisSummary,
    ).toMatchObject({
      status: "available",
      noOpRisk: "low",
    });
    expect(
      ((result.experiment as Record<string, unknown>).pineAnalysisSummary as Record<string, unknown>)
        .changedRoles,
    ).toEqual(["entry", "risk"]);
    expect(
      (result.experiment as Record<string, unknown>).finalAnalysisSummary,
    ).toMatchObject({
      status: "available",
      verdict: "promising",
    });
    expect(result.experiment.topLossZones?.length).toBeGreaterThan(0);
    expect(result.experiment.artifactPaths?.tradeContextArtifact).toBeTruthy();
    expect(result.experiment.artifactPaths?.lossAnalysisArtifact).toBeTruthy();
    expect(monitorLines[0]).toBe("-------task 01----------");
    expect(
      monitorLines.some(
        (line) =>
          line.includes("task 01 |") &&
          line.includes("가설을 준비했습니다.") &&
          line.includes("다음 방향:"),
      ),
    ).toBe(true);
    expect(
      monitorLines.some(
        (line) =>
          line.includes("task 01 |") &&
          line.includes("verified_improvement") &&
          line.includes("점수:"),
      ),
    ).toBe(true);

    const experiments = (await readFile(knowledgePaths.experimentsPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(experiments[0]?.conditionContributions?.[0]?.conditionId).toBe("entry-alpha");
    expect(experiments[0]?.artifactPaths?.syncArtifact).toBeTruthy();
    expect(experiments[0]?.artifactPaths?.backtestArtifact).toBeTruthy();
    expect(experiments[0]?.artifactPaths?.objectiveArtifact).toBeTruthy();

    const candidateSource = await readFile(experiments[0].candidatePath, "utf8");
    expect(candidateSource).toContain(`[${experiments[0].candidateId}]`);

    const syncArtifact = JSON.parse(
      await readFile(experiments[0].artifactPaths.syncArtifact, "utf8"),
    );
    const backtestArtifact = JSON.parse(
      await readFile(experiments[0].artifactPaths.backtestArtifact, "utf8"),
    );
    const objectiveArtifact = JSON.parse(
      await readFile(experiments[0].artifactPaths.objectiveArtifact, "utf8"),
    );
    const mutationBriefs = (await readFile(knowledgePaths.mutationBriefsPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    const candidateLedger = (await readFile(knowledgePaths.candidatesPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(syncArtifact.attachDiagnostics.exactTitleMatched).toBe(true);
    expect(backtestArtifact.trades).toHaveLength(1);
    expect(objectiveArtifact.decision).toBe("verified_improvement");
    expect(objectiveArtifact.pineAnalysisSummary).toMatchObject({
      status: "available",
      noOpRisk: "low",
    });
    expect(objectiveArtifact.finalAnalysisSummary).toMatchObject({
      status: "available",
      verdict: "promising",
    });
    expect(mutationBriefs[0]?.brief?.objective).toContain("QQQ 120m");
    expect(mutationBriefs[0]?.brief?.seedStrategy?.candidateId).toBe("seed_primary");
    expect(mutationBriefs[0]?.brief?.researchContext?.status).toBe("available");
    expect(mutationBriefs[0]?.brief?.researchContext?.insights?.[0]?.suggestedMutation).toContain(
      "trend_down persists",
    );
    expect(candidateLedger[0]?.candidateId).toBe(experiments[0].candidateId);
  });

  test("repairs compile failures and continues evaluation", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-compile-repair-"));
    const stateRoot = path.join(workspace, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse, repairMutationResponse),
      executor: createMockPineEvaluationExecutor({
        compileSequence: [
          { ok: false, errors: ["Could not find function ta.adx"] },
          { ok: true, errors: [] },
        ],
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 18,
          postFeeNetProfitPercent: 15,
          profitFactor: 1.9,
          maxStrategyDrawdownPercent: 10,
          percentProfitable: 55,
          totalTrades: 72,
          avgTradePercent: 0.41,
        },
      }),
    });

    const experiments = (await readFile(knowledgePaths.experimentsPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    const candidateLedger = (await readFile(knowledgePaths.candidatesPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(result.decision).not.toBe("compile_fail");
    expect(experiments).toHaveLength(2);
    expect(experiments[0]?.decision).toBe("compile_fail");
    expect(experiments[1]?.candidateId).toBe(result.experiment.candidateId);
    expect(candidateLedger).toHaveLength(2);
    expect(candidateLedger[1]?.parentCandidateId).toBe(experiments[0]?.candidateId);
  });

  test("flags accepted_no_improvement candidates as no-op suspected when contributions are flat", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-no-op-suspected-"));
    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(
        JSON.stringify({
          candidateSummary: "Tighten a single entry filter without changing exits",
          nextMutationHints: ["broaden the next mutation"],
          pineScript:
            "//@version=5\nstrategy('Mutated', overlay=true)\nentryFilter = close > open\nif entryFilter\n    strategy.entry('L', strategy.long)\n",
          inventory: [
            {
              conditionId: "entry-alpha",
              role: "entry",
              summary: "Entry filter",
              pineLineHints: [3, 4],
            },
          ],
        }),
      ),
      executor: createMockPineEvaluationExecutor({
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 25,
          postFeeNetProfitPercent: 22,
          profitFactor: 2.4,
          maxStrategyDrawdownPercent: 9,
          percentProfitable: 63,
          totalTrades: 87,
          avgTradePercent: 0.55,
        },
        ablations: {
          "entry-alpha": {
            netProfitPercent: 25,
            postFeeNetProfitPercent: 22,
            profitFactor: 2.4,
            maxStrategyDrawdownPercent: 9,
            percentProfitable: 63,
            totalTrades: 87,
            avgTradePercent: 0.55,
          },
        },
      }),
      acceptedHeadScore: 1,
    });

    expect(result.decision).toBe("valid_no_promotion");
    expect(
      ((result.experiment as Record<string, unknown>).finalAnalysisSummary as Record<string, unknown>)
        .verdict,
    ).toBe("no_op_suspected");
  });

  test("uses promotion verification results when local screening finds an improvement", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-promotion-verify-"));

    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor({
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 25,
          postFeeNetProfitPercent: 22,
          profitFactor: 2.4,
          maxStrategyDrawdownPercent: 9,
          percentProfitable: 63,
          totalTrades: 87,
          avgTradePercent: 0.55,
        },
      }),
      executorName: "local-backtest",
      promotionVerificationExecutorFactory: () =>
        createMockPineEvaluationExecutor({
          compile: { ok: true, errors: [] },
          apply: { ok: true, message: "ok" },
          metrics: {
            netProfitPercent: 3,
            postFeeNetProfitPercent: 1,
            profitFactor: 1.05,
            maxStrategyDrawdownPercent: 10,
            percentProfitable: 42,
            totalTrades: 55,
            avgTradePercent: 0.05,
          },
        }),
      promotionVerificationExecutorName: "tradingview-desktop-cdp",
      acceptedHeadScore: 0.45,
    });

    expect(result.decision).toBe("valid_no_promotion");
    expect(result.experiment.artifactPaths?.primaryScreeningArtifact).toBeTruthy();
    expect(result.experiment.artifactPaths?.promotionVerificationArtifact).toBeTruthy();
  });

  test("records fallback evidence when promotion verification runtime recovery fails", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-promotion-fallback-"));

    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor({
        capability: {
          kind: "local-af-screening",
          authoritative: false,
          confidenceLevel: "screening",
        },
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 25,
          postFeeNetProfitPercent: 22,
          profitFactor: 2.4,
          maxStrategyDrawdownPercent: 9,
          percentProfitable: 63,
          totalTrades: 87,
          avgTradePercent: 0.55,
        },
      }),
      executorName: "local-backtest",
      promotionVerificationExecutorFactory: () =>
        createMockPineEvaluationExecutor({
          capability: {
            kind: "tradingview-live",
            authoritative: true,
            confidenceLevel: "verification",
          },
          prepareChartError: "Pine editor open timed out after 30000ms.",
        }),
      promotionVerificationExecutorName: "tradingview-desktop-cdp",
      acceptedHeadScore: 0.45,
    });

    expect(result.decision).toBe("verification_fail");
    expect(result.experiment.verificationRuntimeFailureKind).toBe(
      "pine_editor_open_timeout",
    );
    expect(result.experiment.recoveryAttempts).toHaveLength(1);
    expect(result.experiment.recoveryAttempts?.[0]?.status).toBe("failed");
    expect(result.experiment.fallbackEvaluation?.status).toBe("succeeded");
    expect(result.experiment.fallbackEvaluation?.executorKind).toBe(
      "local-af-backtest",
    );
    expect(result.experiment.fallbackEvaluation?.promotionEligible).toBe(false);
    expect(result.experiment.promotionReady).toBe(false);
    expect(result.experiment.artifactPaths?.fallbackEvidenceArtifact).toBeTruthy();
  });

  test("retries promotion verification after successful surface recovery", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-promotion-recovery-"));
    let verificationAttempt = 0;

    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor({
        capability: {
          kind: "local-af-screening",
          authoritative: false,
          confidenceLevel: "screening",
        },
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 25,
          postFeeNetProfitPercent: 22,
          profitFactor: 2.4,
          maxStrategyDrawdownPercent: 9,
          percentProfitable: 63,
          totalTrades: 87,
          avgTradePercent: 0.55,
        },
      }),
      executorName: "local-backtest",
      promotionVerificationExecutorFactory: () => {
        verificationAttempt += 1;
        if (verificationAttempt === 1) {
          return createMockPineEvaluationExecutor({
            capability: {
              kind: "tradingview-live",
              authoritative: true,
              confidenceLevel: "verification",
            },
            prepareChartError: "Monaco getEditors attach timeout.",
          });
        }

        return createMockPineEvaluationExecutor({
          capability: {
            kind: "tradingview-live",
            authoritative: true,
            confidenceLevel: "verification",
          },
          compile: { ok: true, errors: [] },
          apply: { ok: true, message: "ok" },
          metrics: {
            netProfitPercent: 28,
            postFeeNetProfitPercent: 24,
            profitFactor: 2.7,
            maxStrategyDrawdownPercent: 8,
            percentProfitable: 66,
            totalTrades: 92,
            avgTradePercent: 0.61,
          },
        });
      },
      promotionVerificationExecutorName: "tradingview-desktop-cdp",
      acceptedHeadScore: 0.45,
    });

    expect(result.decision).toBe("verified_improvement");
    expect(result.experiment.recoveryAttempts).toHaveLength(1);
    expect(result.experiment.recoveryAttempts?.[0]?.status).toBe("succeeded");
    expect(result.experiment.verificationRuntimeFailureKind).toBeNull();
    expect(result.experiment.fallbackEvaluation).toBeNull();
    expect(result.experiment.promotionReady).toBe(true);
  });

  test("uses the highest-scoring accepted improvement as the mutation parent", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-best-parent-"));
    const stateRoot = path.join(workspace, "state", "pi-autoresearch");
    await initializeWorkspace(workspace);

    await appendExperimentRecord(stateRoot, {
      runId: "run-parent",
      iteration: 1,
      candidateId: "cand-strong",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      seedStrategyId: "seed_primary",
      improvementSource: "seed",
      candidatePath: path.join(workspace, "strategies", "candidates", "cand-strong.pine"),
      candidateHash: "hash-strong",
      studyTitle: "cand-strong",
      candidateScore: 0.66,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-parent",
      iteration: 2,
      candidateId: "cand-weaker",
      parentCandidateId: "cand-strong",
      branchId: "main",
      acceptedHeadCandidateId: "cand-strong",
      baselineCandidateId: "seed_primary",
      seedStrategyId: "seed_primary",
      improvementSource: "accepted_head",
      candidatePath: path.join(workspace, "strategies", "candidates", "cand-weaker.pine"),
      candidateHash: "hash-weaker",
      studyTitle: "cand-weaker",
      candidateScore: 0.31,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });

    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor({
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 12,
          postFeeNetProfitPercent: 10,
          profitFactor: 1.7,
          maxStrategyDrawdownPercent: 8,
          percentProfitable: 56,
          totalTrades: 75,
          avgTradePercent: 0.33,
        },
      }),
    });

    expect(result.hypothesis.acceptedHeadCandidateId).toBe("cand-strong");
    expect(result.experiment.parentCandidateId).toBe("cand-strong");
    expect(result.experiment.acceptedHeadCandidateId).toBe("cand-strong");
  });

  test("does not record accepted_no_improvement as a system incident", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-no-improvement-"));
    const stateRoot = path.join(workspace, "state", "pi-autoresearch");

    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: createStaticLlmClient(baseMutationResponse),
      executor: createMockPineEvaluationExecutor({
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 14,
          postFeeNetProfitPercent: 12,
          profitFactor: 1.8,
          maxStrategyDrawdownPercent: 9,
          percentProfitable: 57,
          totalTrades: 71,
          avgTradePercent: 0.35,
        },
      }),
      acceptedHeadScore: 0.9,
    });

    const incidents = await readIncidentRecords(stateRoot);

    expect(result.decision).toBe("valid_no_promotion");
    expect(incidents).toEqual([]);
  });

  test("skips condition contribution analysis for non-frontier hard-gate failures", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-skip-ablation-"));
    let ablationCalls = 0;

    const result = await runSingleIteration({
      workspaceRoot: workspace,
      llmClient: {
        async generateMutation() {
          return baseMutationResponse;
        },
        async generateConditionAblation() {
          ablationCalls += 1;
          return baseMutationResponse;
        },
        async repairMutation() {
          return repairMutationResponse;
        },
      },
      executor: createMockPineEvaluationExecutor({
        compile: { ok: true, errors: [] },
        apply: { ok: true, message: "ok" },
        metrics: {
          netProfitPercent: 4,
          postFeeNetProfitPercent: 2,
          profitFactor: 1.1,
          maxStrategyDrawdownPercent: 6,
          percentProfitable: 44,
          totalTrades: 12,
          avgTradePercent: 0.12,
        },
      }),
      acceptedHeadScore: 0.75,
    });

    expect(result.decision).toBe("hard_gate_fail");
    expect(result.conditionContributions).toEqual([]);
    expect(ablationCalls).toBe(0);
  });
});
