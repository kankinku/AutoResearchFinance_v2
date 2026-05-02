import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { loadObjectiveConfig } from "../../src/config/objective.js";
import { type LossAnalysisSummary } from "../../src/contracts/types.js";
import { prepareMutationContext } from "../../src/research/mutation-context.js";
import { initializeWorkspace } from "../../src/research/workspace.js";
import { appendExperimentRecord, readExperimentRecords } from "../../src/state/jsonl-store.js";

const guidanceLossAnalysis: LossAnalysisSummary = {
  status: "available",
  summary: "Use the retained-trades lineage candidate as guidance.",
  topLossZones: ["range:weak_exit:1"],
  repairPriorities: ["Tighten weak exits in range regimes."],
};

const latestLossAnalysis: LossAnalysisSummary = {
  status: "available",
  summary: "Latest low-trade candidate should not override guidance.",
  topLossZones: ["trend_down:weak_exit:1"],
  repairPriorities: ["Reduce counter-trend entries."],
};

describe("prepareMutationContext", () => {
  test("uses the active control candidate for guidance and derives exit-profit repair mode", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-mutation-context-"));
    const stateRoot = path.join(workspace, "state", "pi-autoresearch");
    await initializeWorkspace(workspace);

    await appendExperimentRecord(stateRoot, {
      runId: "run-guidance",
      iteration: 1,
      candidateId: "cand-head",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      seedStrategyId: "seed_primary",
      improvementSource: "seed",
      candidateScore: 0.73,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
      testerMetrics: {
        netProfitPercent: 31,
        postFeeNetProfitPercent: 28,
        profitFactor: 3.2,
        maxStrategyDrawdownPercent: 6,
        percentProfitable: 62,
        totalTrades: 80,
        avgTradePercent: 0.45,
      },
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-guidance",
      iteration: 2,
      candidateId: "cand-guidance",
      parentCandidateId: "cand-head",
      branchId: "main",
      acceptedHeadCandidateId: "cand-head",
      baselineCandidateId: "seed_primary",
      seedStrategyId: "seed_primary",
      improvementSource: "accepted_head",
      candidateScore: 0.58,
      decision: "accepted_no_improvement",
      recordEra: "legacy",
      status: "evaluated",
      testerMetrics: {
        netProfitPercent: 12,
        postFeeNetProfitPercent: 10,
        profitFactor: 1.8,
        maxStrategyDrawdownPercent: 7,
        percentProfitable: 55,
        totalTrades: 70,
        avgTradePercent: 0.31,
      },
      lossAnalysisSummary: guidanceLossAnalysis,
      topLossZones: guidanceLossAnalysis.topLossZones,
      repairPriorities: guidanceLossAnalysis.repairPriorities,
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-guidance",
      iteration: 2,
      candidateId: "cand-head-equivalent",
      parentCandidateId: "cand-head",
      branchId: "main",
      acceptedHeadCandidateId: "cand-head",
      baselineCandidateId: "seed_primary",
      seedStrategyId: "seed_primary",
      improvementSource: "accepted_head",
      candidateScore: 0.73,
      decision: "accepted_no_improvement",
      recordEra: "legacy",
      status: "evaluated",
      testerMetrics: {
        netProfitPercent: 31,
        postFeeNetProfitPercent: 28,
        profitFactor: 3.2,
        maxStrategyDrawdownPercent: 6,
        percentProfitable: 62,
        totalTrades: 80,
        avgTradePercent: 0.45,
      },
      objectiveBreakdown: {
        score: 0.73,
        hardGatesPassed: true,
        softGuardrailBreached: false,
        hardGateReasons: [],
        components: {
          netProfitPercent: { rawValue: 31, normalizedValue: 1, weight: 0.45, contribution: 0.45 },
          profitFactor: { rawValue: 3.2, normalizedValue: 1, weight: 0.15, contribution: 0.15 },
          inverseMaxDrawdown: { rawValue: 6, normalizedValue: 0.8, weight: 0.15, contribution: 0.12 },
          percentProfitable: { rawValue: 62, normalizedValue: 0.62, weight: 0.1, contribution: 0.062 },
          totalTrades: { rawValue: 80, normalizedValue: 0.8, weight: 0.05, contribution: 0.04 },
          avgTradePercent: { rawValue: 0.45, normalizedValue: 0.45, weight: 0.1, contribution: 0.045 },
        },
      },
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-guidance",
      iteration: 3,
      candidateId: "cand-latest-low-trade",
      parentCandidateId: "cand-guidance",
      branchId: "main",
      acceptedHeadCandidateId: "cand-head",
      baselineCandidateId: "seed_primary",
      seedStrategyId: "seed_primary",
      improvementSource: "accepted_head",
      candidateScore: 0.22,
      decision: "hard_gate_fail",
      status: "evaluated",
      testerMetrics: {
        netProfitPercent: 5,
        postFeeNetProfitPercent: 3,
        profitFactor: 1.2,
        maxStrategyDrawdownPercent: 4,
        percentProfitable: 48,
        totalTrades: 12,
        avgTradePercent: 0.18,
      },
      lossAnalysisSummary: latestLossAnalysis,
      topLossZones: latestLossAnalysis.topLossZones,
      repairPriorities: latestLossAnalysis.repairPriorities,
    });

    const objective = await loadObjectiveConfig(workspace);
    const previousRecords = await readExperimentRecords(stateRoot);
    const context = await prepareMutationContext({
      workspaceRoot: workspace,
      objective,
      previousRecords,
    });

    expect(context.acceptedHeadCandidateId).toBe("cand-head");
    expect(context.activeHeadRecord).toBeNull();
    expect(context.guidanceRecord?.candidateId).toBe("cand-guidance");
    expect(context.recentLossAnalysis.summary).toBe(guidanceLossAnalysis.summary);
    expect(context.brief.recentLossAnalysis.summary).toBe(guidanceLossAnalysis.summary);
    expect(context.brief.repairMode).toBe("exit_profit_repair");
  });

  test("surfaces fallback evidence guidance without treating it as verified", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-mutation-context-fallback-"));
    const stateRoot = path.join(workspace, "state", "pi-autoresearch");
    await initializeWorkspace(workspace);

    await appendExperimentRecord(stateRoot, {
      runId: "run-fallback",
      iteration: 1,
      candidateId: "cand-head",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      seedStrategyId: "seed_primary",
      improvementSource: "seed",
      candidateScore: 0.71,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
      testerMetrics: {
        netProfitPercent: 24,
        postFeeNetProfitPercent: 21,
        profitFactor: 2.4,
        maxStrategyDrawdownPercent: 8,
        percentProfitable: 61,
        totalTrades: 81,
        avgTradePercent: 0.44,
      },
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-fallback",
      iteration: 2,
      candidateId: "cand-runtime-fallback",
      parentCandidateId: "cand-head",
      branchId: "main",
      acceptedHeadCandidateId: "cand-head",
      baselineCandidateId: "seed_primary",
      seedStrategyId: "seed_primary",
      improvementSource: "accepted_head",
      candidateScore: 0.52,
      decision: "verification_fail",
      status: "evaluated",
      verificationStatus: "verification_failed",
      verificationFailureReason: "verification_runtime_failure",
      verificationRuntimeFailureKind: "pine_editor_open_timeout",
      promotionStatus: "verification_failed",
      promotionReady: false,
      recordEra: "v2",
      fallbackEvaluation: {
        role: "fallback_evidence",
        executorKind: "local-af-screening",
        executorAuthoritative: false,
        promotionEligible: false,
        status: "succeeded",
        reason: "local_fallback_completed",
        artifactId: "fallback-evidence-cand-runtime-fallback",
        artifactHash: "fallback-hash",
        metrics: {
          netProfitPercent: 14,
          postFeeNetProfitPercent: 11,
          profitFactor: 1.6,
          maxStrategyDrawdownPercent: 10,
          percentProfitable: 52,
          totalTrades: 67,
          avgTradePercent: 0.21,
        },
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

    const objective = await loadObjectiveConfig(workspace);
    const previousRecords = await readExperimentRecords(stateRoot);
    const context = await prepareMutationContext({
      workspaceRoot: workspace,
      objective,
      previousRecords,
    });

    expect(context.brief.analysisGuidance.fallbackEvidenceGuidance.available).toBe(true);
    expect(context.brief.analysisGuidance.fallbackEvidenceGuidance.source).toBe(
      "local-af-screening",
    );
    expect(context.brief.analysisGuidance.fallbackEvidenceGuidance.summary).toContain(
      "pine_editor_open_timeout",
    );
    expect(
      context.brief.analysisGuidance.fallbackEvidenceGuidance.forbiddenInterpretation,
    ).toBe("do_not_treat_as_verified");
  });
});
