import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  type ArtifactBundle,
  type ExperimentRecord,
  type ExecutorCapability,
  type ObjectiveBreakdown,
} from "../../src/contracts/types.js";
import { validateArtifactBundle } from "../../src/evaluation/artifact-validation.js";
import {
  assertPromotionEligible,
  classifyAuthoritativeDecision,
  deriveVerificationStatus,
} from "../../src/evaluation/decision.js";

const tradingViewCapability: ExecutorCapability = {
  kind: "local-af-backtest",
  authoritative: true,
  supportedSymbols: ["QQQ"],
  supportedTimeframes: ["120m"],
  supportedStrategyFamilies: ["Pine"],
  confidenceLevel: "verification",
};

function createObjectiveBreakdown(
  overrides: Partial<ObjectiveBreakdown> = {},
): ObjectiveBreakdown {
  return {
    score: 0.92,
    hardGatesPassed: true,
    softGuardrailBreached: false,
    hardGateReasons: [],
    components: {
      netProfitPercent: {
        rawValue: 25,
        normalizedValue: 1,
        weight: 0.45,
        contribution: 0.45,
      },
      profitFactor: {
        rawValue: 2.1,
        normalizedValue: 1,
        weight: 0.15,
        contribution: 0.15,
      },
      inverseMaxDrawdown: {
        rawValue: 8,
        normalizedValue: 0.84,
        weight: 0.15,
        contribution: 0.126,
      },
      percentProfitable: {
        rawValue: 58,
        normalizedValue: 0.58,
        weight: 0.1,
        contribution: 0.058,
      },
      totalTrades: {
        rawValue: 73,
        normalizedValue: 0.73,
        weight: 0.05,
        contribution: 0.0365,
      },
      avgTradePercent: {
        rawValue: 0.4,
        normalizedValue: 0.4,
        weight: 0.1,
        contribution: 0.04,
      },
    },
    ...overrides,
  };
}

function createArtifactBundle(
  overrides: Partial<ArtifactBundle> = {},
): ArtifactBundle {
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
    trades: [],
    equity: {
      available: false,
      unavailableReason: null,
      pointsAvailable: false,
      pointCount: 0,
      finalEquity: null,
      maxDrawdownPercent: null,
      points: [],
    },
    rawReportHash: "report-hash",
    state: {
      reportDiagnostics: {
        hasNetProfit: true,
        hasTotalTrades: true,
        hasMaxDrawdown: true,
        hasProfitFactor: true,
        hasWinRate: true,
        hasTrades: false,
        hasEquitySummary: false,
        hasRawReport: true,
        missingFields: ["trades", "equity_summary"],
        parseWarnings: ["report.trade_list_missing", "report.equity_summary_missing"],
        parserVersion: "local-backtest-report/v1",
      },
    },
    ...overrides,
  };
}

function createVerifiedRecord(
  overrides: Partial<ExperimentRecord> = {},
): ExperimentRecord {
  const evidenceDir = mkdtempSync(path.join(tmpdir(), "af-decision-"));
  const candidatePath = path.join(evidenceDir, "cand-1.pine");
  const backtestArtifact = path.join(evidenceDir, "cand-1-backtest.json");
  writeFileSync(candidatePath, "//@version=5\nstrategy('Decision Test')\n", "utf8");
  writeFileSync(backtestArtifact, JSON.stringify({ candidateId: "cand-1" }), "utf8");

  const promotableArtifactBundle = createArtifactBundle({
    trades: [{ entryComment: null, entryPrice: null, entryTime: null, exitComment: null, exitPrice: null, exitTime: null, qty: null, profitValue: null, profitPercent: null, runupPercent: null, drawdownPercent: null }],
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
  });

  return {
    runId: "run-1",
    iteration: 1,
    candidateId: "cand-1",
    parentCandidateId: null,
    branchId: "main",
    acceptedHeadCandidateId: null,
    baselineCandidateId: "seed_primary",
    candidateScore: 0.92,
    decision: "verified_improvement",
    status: "evaluated",
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
    executorCapability: tradingViewCapability,
    artifactValidation: validateArtifactBundle({
      artifactBundle: promotableArtifactBundle,
      executorCapability: tradingViewCapability,
    }),
    candidatePath,
    candidateHash: "candidate-hash",
    verificationStatus: "verified",
    verificationFailureReason: null,
    verificationRuntimeFailureKind: null,
    recoveryAttempts: [],
    fallbackEvaluation: null,
    promotionStatus: "verified_improvement",
    promotionReady: true,
    localTvParity: null,
    screeningVsVerificationDiff: null,
    recordEra: "v2",
    artifactBundle: promotableArtifactBundle,
    artifactPaths: {
      backtestArtifact,
    },
    recordMeta: {
      schemaVersion: "experiment/v2",
      recordHash: "record-hash",
      candidateHash: "candidate-hash",
      baselineHash: "baseline-hash",
      artifactBundleHash: "artifact-hash",
      pipelineVersion: "af-research-pipeline/v2",
    },
    ...overrides,
  };
}

describe("decision semantics", () => {
  test("keeps authoritative improvements as verified_improvement even when promotion is not ready", () => {
    const artifactValidation = validateArtifactBundle({
      artifactBundle: createArtifactBundle(),
      executorCapability: tradingViewCapability,
    });

    const decision = classifyAuthoritativeDecision({
      breakdown: createObjectiveBreakdown(),
      acceptedHeadScore: 0.5,
      artifactValidation,
    });

    expect(decision).toBe("verified_improvement");
  });

  test("marks authoritative hard-gate failures as verified when verification executor completed", () => {
    const verificationStatus = deriveVerificationStatus({
      decision: "hard_gate_fail",
      executorCapability: tradingViewCapability,
      usedVerificationExecutor: true,
    });

    expect(verificationStatus).toBe("verified");
  });

  test("marks authoritative valid_no_promotion as verified when verification executor completed", () => {
    const verificationStatus = deriveVerificationStatus({
      decision: "valid_no_promotion",
      executorCapability: tradingViewCapability,
      usedVerificationExecutor: true,
    });

    expect(verificationStatus).toBe("verified");
  });

  test("assertPromotionEligible rejects fallback and non-promotion-ready verified records", () => {
    expect(() =>
      assertPromotionEligible(
        createVerifiedRecord({
          fallbackEvaluation: {
            role: "fallback_evidence",
            executorKind: "local-af-screening",
            executorAuthoritative: false,
            promotionEligible: false,
            status: "succeeded",
            reason: "local_fallback_completed",
            artifactId: "fallback-1",
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
        }),
      ),
    ).toThrow(/fallback/i);

    expect(() =>
      assertPromotionEligible(
        createVerifiedRecord({
          promotionReady: false,
        }),
      ),
    ).toThrow(/promotion-ready/i);
  });

  test("assertPromotionEligible rejects missing evidence and recovered provenance", () => {
    expect(() =>
      assertPromotionEligible(
        createVerifiedRecord({
          candidateHash: undefined,
        }),
      ),
    ).toThrow(/source hash is missing/i);

    expect(() =>
      assertPromotionEligible(
        createVerifiedRecord({
          mutationParseStatus: "recovered",
        }),
      ),
    ).toThrow(/mutationParseStatus must be valid/i);

    expect(() =>
      assertPromotionEligible(
        createVerifiedRecord({
          mutationProvenance: {
            briefHash: "brief-hash",
            promptHash: "prompt-hash",
            responseHash: "response-hash",
            responseSchemaVersion: "parsed-mutation-response/v1",
            parseStatus: "valid",
            inventorySource: "inferred",
            inferredFields: ["inventory"],
            missingFields: [],
          },
        }),
      ),
    ).toThrow(/inventorySource must be llm/i);
  });
});
