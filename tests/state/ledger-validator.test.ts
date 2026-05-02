import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  type ArtifactBundle,
  type ExecutorCapability,
} from "../../src/contracts/types.js";
import { validateArtifactBundle } from "../../src/evaluation/artifact-validation.js";
import { verifyDerivedViews, validateLedger } from "../../src/state/ledger-validator.js";
import {
  appendExperimentRecord,
  ensureStateRoot,
  readMutationBriefRecords,
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

function createPromotableArtifactBundle(
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
    ...overrides,
  };
}

async function writePromotionArtifacts(root: string, candidateId: string) {
  const candidatePath = path.join(root, `${candidateId}.pine`);
  const backtestArtifact = path.join(root, `${candidateId}.backtest.json`);
  await writeFile(candidatePath, "//@version=5\nstrategy('Test')\n", "utf8");
  await writeFile(backtestArtifact, JSON.stringify({ candidateId }), "utf8");
  return {
    candidatePath,
    backtestArtifact,
  };
}

describe("ledger-validator", () => {
  test("accepts legacy run and mutation brief records during ledger validation", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-ledger-legacy-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await ensureStateRoot(stateRoot);
    await writeFile(
      knowledgePaths.runsPath,
      `${JSON.stringify({
        runId: "run-legacy",
        startedAt: "2026-04-23T13:52:09.344Z",
        executor: "playwright-tradingview",
        symbol: "QQQ",
        timeframe: "120",
        chartType: "candles",
        model: "gpt-5.4",
      })}\n`,
      "utf8",
    );
    await writeFile(
      knowledgePaths.mutationBriefsPath,
      `${JSON.stringify({
        runId: "run-legacy",
        iteration: 8,
        acceptedHeadCandidateId: "cand-legacy",
        brief: {
          objective: "QQQ 120m hard-gate-passing strategy improvement",
          guardrails: {
            minimumTotalTrades: 50,
            minimumPostFeeNetProfitPercent: 0,
            maximumStrategyDrawdownPercent: 15,
          },
          acceptedHead: {
            candidateId: "cand-legacy",
            score: 0.37,
          },
          recentFailures: [],
          nextMutationDirection: "Improve net profit with stable drawdown and sufficient trade count.",
          forbiddenPatterns: [
            "Do not remove strategy() declaration.",
            "Do not emit empty or placeholder Pine code.",
          ],
        },
        recordedAt: "2026-04-23T13:52:09.398Z",
      })}\n`,
      "utf8",
    );

    const result = await validateLedger(stateRoot);
    const mutationBriefs = await readMutationBriefRecords(stateRoot);

    expect(result.ok).toBe(true);
    expect(result.errorCount).toBe(0);
    expect(mutationBriefs).toEqual([]);
  });

  test("allows legacy leaderboard entries without treating them as verified", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-ledger-views-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");

    await appendExperimentRecord(stateRoot, {
      runId: "run-1",
      iteration: 1,
      candidateId: "cand-legacy-head",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: "cand-legacy-head",
      baselineCandidateId: "cand-legacy-head",
      candidateScore: 0.75,
      decision: "accepted_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-1",
      iteration: 2,
      candidateId: "cand-legacy-stable",
      parentCandidateId: "cand-legacy-head",
      branchId: "main",
      acceptedHeadCandidateId: "cand-legacy-head",
      baselineCandidateId: "cand-legacy-head",
      candidateScore: 0.63,
      decision: "accepted_no_improvement",
      recordEra: "legacy",
      status: "evaluated",
    });
    await appendExperimentRecord(stateRoot, {
      runId: "run-1",
      iteration: 3,
      candidateId: "cand-v2-screen",
      parentCandidateId: "cand-legacy-head",
      branchId: "main",
      acceptedHeadCandidateId: "cand-legacy-head",
      baselineCandidateId: "cand-legacy-head",
      candidateScore: 0.58,
      decision: "hard_gate_fail",
      recordEra: "v2",
      status: "evaluated",
    });

    await rebuildIndexes(stateRoot);

    const verification = await verifyDerivedViews(stateRoot);
    const leaderboard = JSON.parse(
      await readFile(resolveKnowledgePaths(stateRoot).leaderboardPath, "utf8"),
    );

    expect(verification.ok).toBe(true);
    expect(leaderboard.verifiedHeadCandidateId).toBeNull();
    expect(leaderboard.legacyHeadCandidateId).toBe("cand-legacy-head");
    expect(
      leaderboard.legacyEntries.every((entry: { recordEra: string }) => entry.recordEra === "legacy"),
    ).toBe(true);
    expect(
      leaderboard.verifiedEntries.every(
        (entry: { decision: string }) =>
          entry.decision === "verified_improvement" || entry.decision === "promoted_head",
      ),
    ).toBe(true);
  });

  test("rejects fallback evidence records that violate the non-authoritative fallback contract", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-ledger-fallback-invalid-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");

    await appendExperimentRecord(stateRoot, {
      runId: "run-invalid-fallback",
      iteration: 1,
      candidateId: "cand-invalid-fallback",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.44,
      decision: "verification_fail",
      verificationStatus: "verified",
      verificationFailureReason: "verification_runtime_failure",
      promotionStatus: "verification_failed",
      promotionReady: true,
      recordEra: "v2",
      status: "evaluated",
      fallbackEvaluation: {
        role: "fallback_evidence",
        executorKind: "local-af-screening",
        executorAuthoritative: false,
        promotionEligible: false,
        status: "succeeded",
        reason: "local_fallback_completed",
        artifactId: "fallback-evidence-cand-invalid-fallback",
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

    const result = await validateLedger(stateRoot);

    expect(result.ok).toBe(false);
    expect(
      result.issues.some((issue) =>
        issue.message.includes("Fallback evidence record cannot be promotionReady=true."),
      ),
    ).toBe(true);
    expect(
      result.issues.some((issue) =>
        issue.message.includes("Fallback evidence record must remain in verification_failed status."),
      ),
    ).toBe(true);
  });

  test("rejects non-authoritative records that are marked as verified or promotion-ready", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-ledger-non-auth-invalid-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");

    await appendExperimentRecord(stateRoot, {
      runId: "run-invalid-non-authoritative",
      iteration: 1,
      candidateId: "cand-invalid-non-authoritative",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.71,
      decision: "verified_improvement",
      verificationStatus: "verified",
      verificationFailureReason: null,
      promotionStatus: "verified_improvement",
      promotionReady: true,
      recordEra: "v2",
      status: "evaluated",
      executorCapability: {
        kind: "local-af-screening",
        authoritative: false,
        supportedSymbols: ["QQQ"],
        supportedTimeframes: ["120"],
        supportedStrategyFamilies: ["AF"],
        confidenceLevel: "screening",
      },
      artifactValidation: {
        hasMetrics: true,
        hasNetProfit: true,
        hasTotalTrades: true,
        hasMaxDrawdown: true,
        hasProfitFactor: true,
        hasWinRate: true,
        hasTrades: true,
        hasEquitySummary: true,
        hasRawReport: false,
        verificationReady: false,
        promotionReady: false,
        completenessScore: 1,
        missingFields: [],
        missingForVerification: ["raw_report"],
        missingForPromotion: ["raw_report"],
        parseWarnings: [],
        parserVersion: "artifact-validation/v2",
      },
    });

    const result = await validateLedger(stateRoot);

    expect(result.ok).toBe(false);
    expect(
      result.issues.some((issue) =>
        issue.message.includes(
          "Non-authoritative or local screening records cannot satisfy the verified-view contract.",
        ),
      ),
    ).toBe(true);
  });

  test("reports corrupted JSONL tails without throwing", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-ledger-corrupt-tail-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendExperimentRecord(stateRoot, {
      runId: "run-valid",
      iteration: 1,
      candidateId: "cand-valid",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.44,
      decision: "hard_gate_fail",
      recordEra: "v2",
      status: "evaluated",
    });
    const current = await readFile(knowledgePaths.experimentsPath, "utf8");
    await writeFile(
      knowledgePaths.experimentsPath,
      `${current}{"runId":"broken"`,
      "utf8",
    );

    const result = await validateLedger(stateRoot);

    expect(result.ok).toBe(false);
    expect(
      result.issues.some(
        (issue) => issue.kind === "partial_tail" && issue.lineNumber === 2,
      ),
    ).toBe(true);
  });

  test("rejects promotion-ready records with missing promotion evidence", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-ledger-promotion-evidence-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const { candidatePath, backtestArtifact } = await writePromotionArtifacts(
      root,
      "cand-missing-hash",
    );
    const artifactBundle = createPromotableArtifactBundle();

    const recordWithoutCandidateHash = {
      runId: "run-promote-invalid",
      iteration: 1,
      candidateId: "cand-missing-hash",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.88,
      decision: "verified_improvement" as const,
      recordEra: "v2" as const,
      status: "evaluated" as const,
      mutationParseStatus: "valid" as const,
      mutationProvenance: {
        briefHash: "brief-hash",
        promptHash: "prompt-hash",
        responseHash: "response-hash",
        responseSchemaVersion: "parsed-mutation-response/v1",
        parseStatus: "valid" as const,
        inventorySource: "llm" as const,
        inferredFields: [],
        missingFields: [],
      },
      candidatePath,
      executorCapability: tradingViewCapability,
      artifactValidation: validateArtifactBundle({
        artifactBundle,
        executorCapability: tradingViewCapability,
      }),
      artifactBundle,
      artifactPaths: {
        backtestArtifact,
      },
      verificationStatus: "verified" as const,
      verificationFailureReason: null,
      verificationRuntimeFailureKind: null,
      promotionStatus: "verified_improvement" as const,
      promotionReady: true,
      recordMeta: {
        schemaVersion: "experiment/v2",
        recordHash: "",
        candidateHash: null,
        baselineHash: "seed-hash",
        artifactBundleHash: sha256Json(artifactBundle),
        pipelineVersion: "af-research-pipeline/v2",
      },
    };
    await appendExperimentRecord(stateRoot, recordWithoutCandidateHash);

    const result = await validateLedger(stateRoot);

    expect(result.ok).toBe(false);
    expect(
      result.issues.some((issue) =>
        issue.message.includes("Candidate source hash is missing."),
      ),
    ).toBe(true);
  });

  test("rejects promotion-ready records with recovered or inferred mutation provenance", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-ledger-promotion-provenance-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const { candidatePath, backtestArtifact } = await writePromotionArtifacts(
      root,
      "cand-recovered",
    );
    const artifactBundle = createPromotableArtifactBundle();

    await appendExperimentRecord(stateRoot, {
      runId: "run-promote-provenance",
      iteration: 1,
      candidateId: "cand-recovered",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidateScore: 0.91,
      decision: "verified_improvement",
      recordEra: "v2",
      status: "evaluated",
      mutationParseStatus: "recovered",
      mutationProvenance: {
        briefHash: "brief-hash",
        promptHash: "prompt-hash",
        responseHash: "response-hash",
        responseSchemaVersion: "parsed-mutation-response/v1",
        parseStatus: "recovered",
        inventorySource: "inferred",
        inferredFields: ["inventory"],
        missingFields: ["inventory"],
      },
      candidatePath,
      candidateHash: "candidate-hash",
      executorCapability: tradingViewCapability,
      artifactValidation: validateArtifactBundle({
        artifactBundle,
        executorCapability: tradingViewCapability,
      }),
      artifactBundle,
      artifactPaths: {
        backtestArtifact,
      },
      verificationStatus: "verified",
      verificationFailureReason: null,
      verificationRuntimeFailureKind: null,
      promotionStatus: "verified_improvement",
      promotionReady: true,
      recordMeta: {
        schemaVersion: "experiment/v2",
        recordHash: "",
        candidateHash: "candidate-hash",
        baselineHash: "seed-hash",
        artifactBundleHash: sha256Json(artifactBundle),
        pipelineVersion: "af-research-pipeline/v2",
      },
    });

    const result = await validateLedger(stateRoot);

    expect(result.ok).toBe(false);
    expect(
      result.issues.some((issue) =>
        issue.message.includes("mutationParseStatus must be valid"),
      ),
    ).toBe(true);
    expect(
      result.issues.some((issue) =>
        issue.message.includes("mutationProvenance.inventorySource must be llm"),
      ),
    ).toBe(true);
  });

  test("preserves canonical record hashes for new v3 autonomous experiment records", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-ledger-v3-hash-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const candidatePath = path.join(root, "cand-v3-hash.pine");
    await writeFile(candidatePath, "//@version=5\nstrategy('V3 Hash Candidate')\n", "utf8");

    await appendExperimentRecord(stateRoot, {
      runId: "run-v3-hash",
      iteration: 1,
      candidateId: "cand-v3-hash",
      parentCandidateId: null,
      branchId: "autonomous-main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: null,
      candidatePath,
      candidateHash: "cand-v3-hash",
      studyTitle: "V3 Hash Candidate",
      candidateScore: 1.1,
      decision: "local_candidate_eligible",
      status: "evaluated",
      recordKind: "local_evaluation",
      executorRole: "primary_local_backtest",
      evidenceAuthority: "local_model",
      evaluationMode: "local_primary",
      mutationBriefSummary: "hash roundtrip candidate",
      conditionInventory: [],
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
      testerMetrics: createPromotableArtifactBundle().strategy,
      splitEvaluation: null,
      noveltyFingerprint: null,
      duplicateStatus: {
        classification: "unique",
        exactDuplicateCandidateId: null,
        structuralDuplicateCandidateId: null,
        duplicateFingerprint: null,
      },
      autoSelectionScore: 1.1,
      autoSelectionBreakdown: {
        baseObjectiveScore: 0.8,
        robustnessScore: 0.2,
        noveltyScore: 0.2,
        diversityScore: 0,
        localConfidenceBonus: 0,
        riskPenalty: 0,
        overfitPenalty: 0,
        duplicatePenalty: 0,
        divergencePenalty: 0,
        complexityPenalty: 0.1,
        totalScore: 1.1,
        eligible: true,
        rejectionReasons: [],
      },
      objectivePolicyVersion: "objective.qqq-120m/v1",
      selectionPolicyVersion: "autonomous-local-first/v3-p0",
      localConfidence: 1,
      tvCalibrationStatus: "not_requested",
      localTvParity: null,
      artifactPaths: {},
      recordMeta: {
        schemaVersion: "experiment/v3",
        recordHash: "",
        candidateHash: "cand-v3-hash",
        baselineHash: null,
        artifactBundleHash: null,
        pipelineVersion: "af-autonomous-local-first/v3",
      },
    });

    const result = await validateLedger(stateRoot);

    expect(
      result.issues.some(
        (issue) =>
          issue.scope === "experiment-record-meta" &&
          issue.message.includes("recordHash does not match"),
      ),
    ).toBe(false);
  });
});
