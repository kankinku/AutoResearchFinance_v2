import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { type ArtifactBundle, type ExperimentRecord, type ExecutorCapability } from "../../src/contracts/types.js";
import { validateArtifactBundle } from "../../src/evaluation/artifact-validation.js";
import {
  findActiveHeadRecord,
  findMutationGuidanceRecord,
} from "../../src/state/accepted-head.js";

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
      netProfitPercent: 31.1,
      postFeeNetProfitPercent: 31.1,
      profitFactor: 7.52,
      maxStrategyDrawdownPercent: 4.8,
      percentProfitable: 79.75,
      totalTrades: 79,
      avgTradePercent: 3.41,
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
      maxDrawdownPercent: 4.8,
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

function createPromotionEvidencePaths(candidateId: string) {
  const root = mkdtempSync(path.join(tmpdir(), "af-accepted-head-"));
  const candidatePath = path.join(root, `${candidateId}.pine`);
  const backtestArtifact = path.join(root, `${candidateId}.backtest.json`);
  writeFileSync(candidatePath, "//@version=5\nstrategy('Accepted Head Test')\n", "utf8");
  writeFileSync(backtestArtifact, JSON.stringify({ candidateId }), "utf8");
  return { candidatePath, backtestArtifact };
}

function createExperimentRecord(
  overrides: Partial<ExperimentRecord>,
): ExperimentRecord {
  return {
    runId: "run-1",
    iteration: 1,
    candidateId: "cand-default",
    parentCandidateId: null,
    branchId: "main",
    acceptedHeadCandidateId: null,
    baselineCandidateId: "seed_primary",
    decision: "hard_gate_fail",
    status: "evaluated",
    ...overrides,
  } as ExperimentRecord;
}

describe("findMutationGuidanceRecord", () => {
  test("prefers current accepted-head lineage candidates that preserve tradability over the latest low-trade loser", () => {
    const acceptedRecord = createExperimentRecord({
      iteration: 104,
      candidateId: "manual-exhaustion-sample",
      decision: "accepted_improvement",
      candidateScore: 0.750646335,
      testerMetrics: {
        netProfitPercent: 31.1,
        postFeeNetProfitPercent: 31.1,
        profitFactor: 7.5,
        maxStrategyDrawdownPercent: 4.8,
        percentProfitable: 79.7,
        totalTrades: 79,
        avgTradePercent: 3.41,
      },
    });

    const highTradabilityRecord = createExperimentRecord({
      iteration: 119,
      candidateId: "cand-802d4d4e",
      parentCandidateId: "manual-exhaustion-sample",
      acceptedHeadCandidateId: "manual-exhaustion-sample",
      decision: "accepted_no_improvement",
      candidateScore: 0.3123792053843193,
      testerMetrics: {
        netProfitPercent: 2.52,
        postFeeNetProfitPercent: 2.52,
        profitFactor: 1.74,
        maxStrategyDrawdownPercent: 2.45,
        percentProfitable: 37.68,
        totalTrades: 69,
        avgTradePercent: 0.19,
      },
      objectiveBreakdown: {
        score: 0.3123792053843193,
        hardGatesPassed: true,
        softGuardrailBreached: false,
        hardGateReasons: [],
        components: {
          netProfitPercent: {
            rawValue: 2.52,
            normalizedValue: 0.084,
            weight: 0.45,
            contribution: 0.0378,
          },
          profitFactor: {
            rawValue: 1.74,
            normalizedValue: 0.58,
            weight: 0.15,
            contribution: 0.087,
          },
          inverseMaxDrawdown: {
            rawValue: 2.45,
            normalizedValue: 0.9183,
            weight: 0.15,
            contribution: 0.137745,
          },
          percentProfitable: {
            rawValue: 37.68,
            normalizedValue: 0.3768,
            weight: 0.1,
            contribution: 0.03768,
          },
          totalTrades: {
            rawValue: 69,
            normalizedValue: 0.345,
            weight: 0.05,
            contribution: 0.01725,
          },
          avgTradePercent: {
            rawValue: 0.19,
            normalizedValue: 0.19,
            weight: 0.1,
            contribution: 0.019,
          },
        },
      },
      lossAnalysisSummary: {
        status: "available",
        summary: "Analyzed 16 losing trades in tradable descendant.",
        topLossZones: ["range:weak_exit:3"],
        repairPriorities: ["Prioritize faster loser exits in range and range_squeeze regimes before tuning new entries."],
      },
    });

    const latestLowTradeRecord = createExperimentRecord({
      iteration: 127,
      candidateId: "cand-f21893e9",
      parentCandidateId: "manual-exhaustion-sample",
      acceptedHeadCandidateId: "manual-exhaustion-sample",
      decision: "hard_gate_fail",
      candidateScore: 0.25525682885983886,
      testerMetrics: {
        netProfitPercent: 0.357483,
        postFeeNetProfitPercent: 0.357483,
        profitFactor: 1.2503380571967766,
        maxStrategyDrawdownPercent: 0.794409,
        percentProfitable: 33.333333,
        totalTrades: 21,
        avgTradePercent: 0.114114,
      },
      objectiveBreakdown: {
        score: 0.25525682885983886,
        hardGatesPassed: false,
        softGuardrailBreached: false,
        hardGateReasons: ["minimum_total_trades"],
        components: {
          netProfitPercent: {
            rawValue: 0.357483,
            normalizedValue: 0.0071496599999999995,
            weight: 0.45,
            contribution: 0.0032173469999999997,
          },
          profitFactor: {
            rawValue: 1.2503380571967766,
            normalizedValue: 0.41677935239892555,
            weight: 0.15,
            contribution: 0.06251690285983882,
          },
          inverseMaxDrawdown: {
            rawValue: 0.794409,
            normalizedValue: 0.9682236399999999,
            weight: 0.15,
            contribution: 0.145233546,
          },
          percentProfitable: {
            rawValue: 33.333333,
            normalizedValue: 0.33333333000000004,
            weight: 0.1,
            contribution: 0.03333333300000001,
          },
          totalTrades: {
            rawValue: 21,
            normalizedValue: 0.105,
            weight: 0.05,
            contribution: 0.00525,
          },
          avgTradePercent: {
            rawValue: 0.114114,
            normalizedValue: 0.057057,
            weight: 0.1,
            contribution: 0.0057057,
          },
        },
      },
      lossAnalysisSummary: {
        status: "available",
        summary: "Analyzed 14 losing trades in low-trade descendant.",
        topLossZones: ["trend_down:weak_exit:3"],
        repairPriorities: ["Reduce counter-trend long entries during trend_down regimes."],
      },
    });

    const selected = findMutationGuidanceRecord(
      [acceptedRecord, highTradabilityRecord, latestLowTradeRecord],
      {
        acceptedRecord,
        minimumTotalTrades: 50,
      },
    );

    expect(selected?.candidateId).toBe("cand-802d4d4e");
  });

  test("selects an explicitly promoted candidate as the active head", () => {
    const artifactBundle = createPromotableArtifactBundle();
    const { candidatePath, backtestArtifact } =
      createPromotionEvidencePaths("cand-ae2377f7");
    const acceptedRecord = createExperimentRecord({
      iteration: 104,
      candidateId: "manual-exhaustion-sample",
      decision: "accepted_improvement",
      candidateScore: 0.750646335,
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
        score: 0.750646335,
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

    const sourceVerifiedRecord = createExperimentRecord({
      runId: "run-verified",
      iteration: 129,
      candidateId: "cand-ae2377f7",
      parentCandidateId: "manual-exhaustion-sample",
      acceptedHeadCandidateId: "manual-exhaustion-sample",
      baselineCandidateId: "seed_primary",
      candidateScore: 0.750646335,
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
        artifactBundleHash: "artifact-bundle-hash",
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
      objectiveBreakdown: acceptedRecord.objectiveBreakdown,
    });

    const headEquivalentDescendant = createExperimentRecord({
      runId: "run-promoted",
      iteration: 130,
      candidateId: "cand-ae2377f7",
      parentCandidateId: "manual-exhaustion-sample",
      acceptedHeadCandidateId: "manual-exhaustion-sample",
      decision: "promoted_head",
      promotionStatus: "promoted_head",
      promotionReady: true,
      mutationParseStatus: "valid",
      mutationProvenance: sourceVerifiedRecord.mutationProvenance,
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
        artifactBundleHash: "artifact-bundle-hash",
        promotedFromRunId: "run-verified",
        promotedFromIteration: 129,
        promotedFromRecordHash: "source-record-hash",
        pipelineVersion: "af-research-pipeline/v2",
      },
      candidateScore: 0.750646335,
      testerMetrics: {
        netProfitPercent: 31.1,
        postFeeNetProfitPercent: 31.1,
        profitFactor: 7.52,
        maxStrategyDrawdownPercent: 4.8,
        percentProfitable: 79.75,
        totalTrades: 79,
        avgTradePercent: 3.41,
      },
      objectiveBreakdown: acceptedRecord.objectiveBreakdown,
    });

    const activeHead = findActiveHeadRecord([
      acceptedRecord,
      sourceVerifiedRecord,
      headEquivalentDescendant,
    ]);

    expect(activeHead?.candidateId).toBe("cand-ae2377f7");
  });
});
