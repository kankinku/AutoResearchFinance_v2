import { execFile } from "node:child_process";
import { mkdir, mkdtemp, readFile, unlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { describe, expect, test } from "vitest";

import {
  type ArtifactBundle,
  type ExecutorCapability,
  type ExperimentRecord,
  type FallbackEvaluation,
  type MutationProvenance,
} from "../../src/contracts/types.js";
import { loadObjectiveConfig } from "../../src/config/objective.js";
import { validateArtifactBundle } from "../../src/evaluation/artifact-validation.js";
import { type InvalidRecordViewEntry } from "../../src/evaluation/record-eligibility.js";
import { createMockPineEvaluationExecutor } from "../../src/automation/tradingview/mock-driver.js";
import { runLocalEvaluationPhase } from "../../src/research/autonomous/local-evaluation-phase.js";
import { initializeWorkspace } from "../../src/research/workspace.js";
import {
  readExperimentRecords,
  appendExperimentRecord,
  appendHeadEventRecord,
  appendRepairAttemptRecord,
} from "../../src/state/jsonl-store.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";
import { sha256Json } from "../../src/utils/fs.js";

const execFileAsync = promisify(execFile);
const projectRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);
const tsxCliPath = path.join(projectRoot, "node_modules", "tsx", "dist", "cli.mjs");
const cliEntryPath = path.join(projectRoot, "src", "cli", "index.ts");

const tradingViewCapability: ExecutorCapability = {
  kind: "tradingview-live",
  authoritative: true,
  supportedSymbols: ["QQQ"],
  supportedTimeframes: ["120"],
  supportedStrategyFamilies: ["Pine"],
  confidenceLevel: "verification",
};

const localScreeningCapability: ExecutorCapability = {
  kind: "local-af-screening",
  authoritative: false,
  supportedSymbols: ["QQQ"],
  supportedTimeframes: ["120"],
  supportedStrategyFamilies: ["AF"],
  confidenceLevel: "screening",
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

function createFallbackEvaluation(): FallbackEvaluation {
  return {
    role: "fallback_evidence",
    executorKind: "local-af-screening",
    executorAuthoritative: false,
    promotionEligible: false,
    status: "succeeded",
    reason: "local_fallback_completed",
    artifactId: "fallback-evidence",
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
  };
}

async function writePromotionArtifacts(root: string, candidateId: string) {
  const candidatePath = path.join(root, `${candidateId}.pine`);
  const backtestArtifact = path.join(root, `${candidateId}.backtest.json`);
  await writeFile(candidatePath, "//@version=5\nstrategy('CLI Test')\n", "utf8");
  await writeFile(backtestArtifact, JSON.stringify({ candidateId }), "utf8");
  return {
    candidatePath,
    backtestArtifact,
  };
}

async function buildVerifiedExperimentInput(
  workspaceRoot: string,
  candidateId: string,
): Promise<Omit<ExperimentRecord, "recordedAt">> {
  const artifactBundle = createPromotableArtifactBundle();
  const { candidatePath, backtestArtifact } = await writePromotionArtifacts(
    workspaceRoot,
    candidateId,
  );

  return {
    runId: "run-1",
    iteration: 1,
    candidateId,
    parentCandidateId: null,
    branchId: "main",
    acceptedHeadCandidateId: null,
    baselineCandidateId: "seed_primary",
    seedStrategyId: "seed_primary",
    improvementSource: "seed",
    candidatePath,
    candidateHash: `${candidateId}-hash`,
    studyTitle: `${candidateId}-study`,
    candidateScore: 0.93,
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
      artifactBundle,
      executorCapability: tradingViewCapability,
    }),
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
    artifactBundle,
    artifactPaths: {
      candidate: candidatePath,
      backtestArtifact,
    },
    recordMeta: {
      schemaVersion: "experiment/v2",
      recordHash: "",
      candidateHash: `${candidateId}-hash`,
      baselineHash: "seed-hash",
      artifactBundleHash: sha256Json(artifactBundle),
      pipelineVersion: "af-research-pipeline/v2",
    },
  };
}

async function prepareCliWorkspace(workspaceRoot: string): Promise<void> {
  const templateFiles = [
    "config/objective.qqq-120m.json",
    "strategies/source/seed_primary.pine",
    "strategies/source/runtime_target.pine",
  ];

  for (const relativePath of templateFiles) {
    const sourcePath = path.join(projectRoot, relativePath);
    const targetPath = path.join(workspaceRoot, relativePath);
    await mkdir(path.dirname(targetPath), { recursive: true });
    await writeFile(targetPath, await readFile(sourcePath, "utf8"), "utf8");
  }
}

function createAutonomousMutationProvenance(): MutationProvenance {
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

async function seedUnsupportedAutonomousCandidate(root: string, candidateId: string) {
  await prepareCliWorkspace(root);
  await initializeWorkspace(root);
  const stateRoot = path.join(root, "state", "pi-autoresearch");
  const objective = await loadObjectiveConfig(root);
  const candidatePath = path.join(root, "strategies", "candidates", `${candidateId}.pine`);
  const pineSource =
    "//@version=5\nstrategy('Unsupported Autonomous Candidate', overlay=true)\nindicator('forbidden helper')\n";
  await mkdir(path.dirname(candidatePath), { recursive: true });
  await writeFile(candidatePath, pineSource, "utf8");

  return runLocalEvaluationPhase({
    workspaceRoot: root,
    stateRoot,
    runId: `run-${candidateId}`,
    iteration: 1,
    executor: createMockPineEvaluationExecutor({
      capability: {
        kind: "local-af-screening",
        authoritative: false,
        confidenceLevel: "screening",
        supportedStrategyFamilies: ["AF"],
        role: "primary_local_backtest",
        evidenceAuthority: "local_model",
      },
      compatibility: {
        supported: false,
        reasonCode: "unsupported_strategy_family",
        detail: "Missing required AF inputs and uses a forbidden indicator() helper.",
        issues: [
          {
            kind: "missing_input",
            code: "missing_input:L1",
            field: "L1",
            detail: "Missing required AF input L1.",
          },
          {
            kind: "missing_function",
            code: "missing_function:computeTrend",
            field: "computeTrend",
            detail: "Missing required AF helper computeTrend().",
          },
          {
            kind: "unsupported_pattern",
            code: "unsupported_pattern:indicator(",
            field: null,
            detail: 'Candidate uses forbidden pattern "indicator(".',
          },
        ],
      },
    }),
    objective,
    parsedMutation: {
      candidateSummary: "Unsupported autonomous candidate",
      nextMutationHints: ["restore missing AF compatibility fields"],
      pineScript: pineSource,
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
      pineHash: `${candidateId}-hash`,
      studyTitle: "Unsupported Autonomous Candidate",
      inventory: [
        {
          conditionId: "entry-alpha",
          role: "entry",
          summary: "Entry condition",
          pineLineHints: [3],
        },
      ],
      candidateSummary: "Unsupported autonomous candidate",
      nextMutationHints: ["restore missing AF compatibility fields"],
    },
    mutationProvenance: createAutonomousMutationProvenance(),
    previousExperiments: [],
  });
}

async function runCliCommand(workspaceRoot: string, args: string[]) {
  await prepareCliWorkspace(workspaceRoot);
  try {
    const result = await execFileAsync(
      process.execPath,
      [tsxCliPath, cliEntryPath, ...args],
      {
        cwd: workspaceRoot,
        env: {
          ...process.env,
        },
        timeout: 60_000,
      },
    );
    return {
      code: 0,
      stdout: result.stdout,
      stderr: result.stderr,
    };
  } catch (error) {
    const failure = error as Error & {
      code?: number;
      stdout?: string;
      stderr?: string;
    };
    return {
      code: typeof failure.code === "number" ? failure.code : 1,
      stdout: failure.stdout ?? "",
      stderr: failure.stderr ?? "",
    };
  }
}

function parseCliJson(stdout: string): unknown {
  const start = stdout.lastIndexOf("\n{");
  const jsonPayload = (start >= 0 ? stdout.slice(start + 1) : stdout).trim();
  return JSON.parse(jsonPayload);
}

describe("ledger CLI commands", () => {
  test("promote rejects fallback, non-authoritative, legacy, and non-ready records", { timeout: 20_000 }, async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-promote-reject-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");

    const fallbackRecord = await buildVerifiedExperimentInput(root, "cand-fallback");
    await appendExperimentRecord(stateRoot, {
      ...fallbackRecord,
      fallbackEvaluation: createFallbackEvaluation(),
    });

    const nonAuthoritativeRecord = await buildVerifiedExperimentInput(
      root,
      "cand-local",
    );
    await appendExperimentRecord(stateRoot, {
      ...nonAuthoritativeRecord,
      executorCapability: localScreeningCapability,
    });

    const legacyRecord = await buildVerifiedExperimentInput(root, "cand-legacy");
    await appendExperimentRecord(stateRoot, {
      ...legacyRecord,
      decision: "accepted_improvement",
      recordEra: "legacy",
      promotionStatus: "verified_improvement",
    });

    const nonReadyRecord = await buildVerifiedExperimentInput(root, "cand-nonready");
    await appendExperimentRecord(stateRoot, {
      ...nonReadyRecord,
      promotionReady: false,
    });

    const fallbackResult = await runCliCommand(root, [
      "promote",
      "--candidate",
      "cand-fallback",
    ]);
    expect(fallbackResult.code).not.toBe(0);
    expect(fallbackResult.stderr).toMatch(/fallback/i);

    const localResult = await runCliCommand(root, [
      "promote",
      "--candidate",
      "cand-local",
    ]);
    expect(localResult.code).not.toBe(0);
    expect(localResult.stderr).toMatch(/non-authoritative|local screening/i);

    const legacyResult = await runCliCommand(root, [
      "promote",
      "--candidate",
      "cand-legacy",
    ]);
    expect(legacyResult.code).not.toBe(0);
    expect(legacyResult.stderr).toMatch(/legacy/i);

    const nonReadyResult = await runCliCommand(root, [
      "promote",
      "--candidate",
      "cand-nonready",
    ]);
    expect(nonReadyResult.code).not.toBe(0);
    expect(nonReadyResult.stderr).toMatch(/promotion-ready/i);
  });

  test("promote rejects missing evidence fields", { timeout: 20_000 }, async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-promote-evidence-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");

    const missingCandidateHash = await buildVerifiedExperimentInput(
      root,
      "cand-missing-candidate-hash",
    );
    const { candidateHash: _missingCandidateHash, ...missingCandidateHashRecord } =
      missingCandidateHash;
    await appendExperimentRecord(stateRoot, {
      ...missingCandidateHashRecord,
      recordMeta: {
        ...(missingCandidateHash.recordMeta ?? {}),
        candidateHash: null,
      },
    });

    const missingCandidatePath = await buildVerifiedExperimentInput(
      root,
      "cand-missing-candidate-path",
    );
    const missingCandidatePathArtifacts = missingCandidatePath.artifactPaths as {
      backtestArtifact: string;
    };
    const { candidatePath: _missingCandidatePath, ...missingCandidatePathRecord } =
      missingCandidatePath;
    await appendExperimentRecord(stateRoot, {
      ...missingCandidatePathRecord,
      artifactPaths: {
        backtestArtifact: missingCandidatePathArtifacts.backtestArtifact,
      },
    });

    const missingArtifactBundleHash = await buildVerifiedExperimentInput(
      root,
      "cand-missing-artifact-bundle-hash",
    );
    await appendExperimentRecord(stateRoot, {
      ...missingArtifactBundleHash,
      recordMeta: {
        ...(missingArtifactBundleHash.recordMeta ?? {}),
        artifactBundleHash: null,
      },
    });
    await rewriteExperimentRecordForTest(stateRoot, "cand-missing-artifact-bundle-hash", (record) => ({
      ...record,
      artifactBundleHash: null,
      recordMeta: {
        ...(record.recordMeta ?? {}),
        schemaVersion: record.recordMeta?.schemaVersion ?? "experiment/v4",
        recordHash: record.recordMeta?.recordHash ?? "test-record-hash",
        pipelineVersion: record.recordMeta?.pipelineVersion ?? "test",
        artifactBundleHash: null,
      },
    }));

    const missingRawReportHash = await buildVerifiedExperimentInput(
      root,
      "cand-missing-raw-report-hash",
    );
    await appendExperimentRecord(stateRoot, {
      ...missingRawReportHash,
      artifactBundle: createPromotableArtifactBundle({
        rawReportHash: null,
      }),
    });

    const cases = [
      {
        candidateId: "cand-missing-candidate-hash",
        pattern: /source hash is missing/i,
      },
      {
        candidateId: "cand-missing-candidate-path",
        pattern: /source path is missing/i,
      },
      {
        candidateId: "cand-missing-artifact-bundle-hash",
        pattern: /artifactbundlehash/i,
      },
      {
        candidateId: "cand-missing-raw-report-hash",
        pattern: /raw report hash is missing/i,
      },
    ];

    for (const testCase of cases) {
      const result = await runCliCommand(root, [
        "promote",
        "--candidate",
        testCase.candidateId,
      ]);
      expect(result.code, testCase.candidateId).not.toBe(0);
      expect(result.stderr, testCase.candidateId).toMatch(testCase.pattern);
    }
  });

  test("promote succeeds only for a valid verified record and appends promoted_head", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-promote-success-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const record = await buildVerifiedExperimentInput(root, "cand-promote");
    await appendExperimentRecord(stateRoot, record);

    const result = await runCliCommand(root, [
      "promote",
      "--candidate",
      "cand-promote",
    ]);

    expect(result.code).toBe(0);
    expect(parseCliJson(result.stdout)).toEqual(
      expect.objectContaining({
        promoted: true,
        candidateId: "cand-promote",
        activeHeadCandidateId: "cand-promote",
      }),
    );

    const experiments = await readExperimentRecords(stateRoot);
    expect(experiments.at(-1)?.decision).toBe("promoted_head");
    expect(experiments.at(-1)?.recordMeta).toEqual(
      expect.objectContaining({
        promotedFromRunId: record.runId,
        promotedFromIteration: record.iteration,
        promotedFromRecordHash: expect.any(String),
      }),
    );
  });

  test("validate-ledger reports corrupted tails without crashing", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-validate-tail-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    const validRecord = await buildVerifiedExperimentInput(root, "cand-valid");

    await appendExperimentRecord(stateRoot, validRecord);
    const current = await readFile(knowledgePaths.experimentsPath, "utf8");
    await writeFile(
      knowledgePaths.experimentsPath,
      `${current}{"runId":"broken"`,
      "utf8",
    );

    const result = await runCliCommand(root, ["validate-ledger"]);

    expect(result.code).toBe(0);
    expect(parseCliJson(result.stdout)).toEqual(
      expect.objectContaining({
        ok: false,
        errorCount: expect.any(Number),
        issues: expect.arrayContaining([
          expect.objectContaining({
            kind: "partial_tail",
            lineNumber: 2,
          }),
        ]),
      }),
    );
  });

  test("validate-ledger reports malformed middle line", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-validate-middle-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);

    await appendExperimentRecord(
      stateRoot,
      await buildVerifiedExperimentInput(root, "cand-middle-1"),
    );
    await appendExperimentRecord(
      stateRoot,
      await buildVerifiedExperimentInput(root, "cand-middle-2"),
    );
    await appendExperimentRecord(
      stateRoot,
      await buildVerifiedExperimentInput(root, "cand-middle-3"),
    );

    const lines = (await readFile(knowledgePaths.experimentsPath, "utf8"))
      .trimEnd()
      .split("\n");
    lines[1] = '{"runId":"broken-middle"';
    await writeFile(knowledgePaths.experimentsPath, `${lines.join("\n")}\n`, "utf8");

    const result = await runCliCommand(root, ["validate-ledger"]);

    expect(result.code).toBe(0);
    expect(parseCliJson(result.stdout)).toEqual(
      expect.objectContaining({
        ok: false,
        issues: expect.arrayContaining([
          expect.objectContaining({
            kind: "malformed_json",
            lineNumber: 2,
          }),
        ]),
      }),
    );
  });

  test("inspect-candidate includes verification and mutation provenance fields", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-inspect-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const record = await buildVerifiedExperimentInput(root, "cand-inspect");
    await appendExperimentRecord(stateRoot, record);

    const result = await runCliCommand(root, [
      "inspect-candidate",
      "--candidate",
      "cand-inspect",
    ]);

    expect(result.code).toBe(0);
    expect(parseCliJson(result.stdout)).toEqual(
      expect.objectContaining({
        candidate: "cand-inspect",
        experiments: expect.arrayContaining([
          expect.objectContaining({
            decision: "verified_improvement",
            verificationStatus: "verified",
            promotionReady: true,
            mutationProvenance: expect.objectContaining({
              parseStatus: "valid",
              inventorySource: "llm",
            }),
          }),
        ]),
      }),
    );
  });

  test("inspect-experiment includes decision verification promotion artifact provenance fields", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-inspect-exp-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const record = await buildVerifiedExperimentInput(root, "cand-inspect-exp");
    await appendExperimentRecord(stateRoot, record);

    const result = await runCliCommand(root, [
      "inspect-experiment",
      "--candidate",
      "cand-inspect-exp",
    ]);

    expect(result.code).toBe(0);
    expect(parseCliJson(result.stdout)).toEqual(
      expect.objectContaining({
        candidate: "cand-inspect-exp",
        experiment: expect.objectContaining({
          decision: "verified_improvement",
          verificationStatus: "verified",
          promotionReady: true,
          executorCapability: expect.objectContaining({
            authoritative: true,
            kind: "tradingview-live",
          }),
          artifactValidation: expect.objectContaining({
            verificationReady: true,
            promotionReady: true,
          }),
          mutationProvenance: expect.objectContaining({
            parseStatus: "valid",
            inventorySource: "llm",
          }),
        }),
      }),
    );
  });

  test("rebuild-indexes --verify succeeds on a valid verified record", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-rebuild-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const record = await buildVerifiedExperimentInput(root, "cand-rebuild");
    await appendExperimentRecord(stateRoot, record);

    const result = await runCliCommand(root, ["rebuild-indexes", "--verify"]);

    expect(result.code).toBe(0);
    expect(parseCliJson(result.stdout)).toEqual(
      expect.objectContaining({
        rebuilt: true,
        verification: expect.objectContaining({
          ok: true,
        }),
      }),
    );
    expect((await readExperimentRecords(stateRoot)).length).toBe(1);
  });

  test(
    "promote rejects missing candidate source file and artifact file",
    { timeout: 20_000 },
    async () => {
      const root = await mkdtemp(path.join(tmpdir(), "af-cli-promote-files-"));
      const stateRoot = path.join(root, "state", "pi-autoresearch");

      const missingSource = await buildVerifiedExperimentInput(root, "cand-missing-source");
      await appendExperimentRecord(stateRoot, missingSource);
      await unlink(missingSource.candidatePath as string);

      const sourceResult = await runCliCommand(root, [
        "promote",
        "--candidate",
        "cand-missing-source",
      ]);
      expect(sourceResult.code).not.toBe(0);
      expect(sourceResult.stderr).toMatch(/source file is missing/i);

      const missingArtifact = await buildVerifiedExperimentInput(root, "cand-missing-artifact");
      await appendExperimentRecord(stateRoot, missingArtifact);
      await unlink((missingArtifact.artifactPaths as { backtestArtifact: string }).backtestArtifact);

      const artifactResult = await runCliCommand(root, [
        "promote",
        "--candidate",
        "cand-missing-artifact",
      ]);
      expect(artifactResult.code).not.toBe(0);
      expect(artifactResult.stderr).toMatch(/artifact path "backtestArtifact" is missing/i);
    },
  );

  test("promote rejects recovered mutation and inferred inventory through CLI", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-promote-provenance-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");

    const recovered = await buildVerifiedExperimentInput(root, "cand-recovered");
    await appendExperimentRecord(stateRoot, {
      ...recovered,
      mutationParseStatus: "recovered",
      mutationProvenance: {
        ...(recovered.mutationProvenance ?? {}),
        parseStatus: "recovered",
      },
      promotionReady: false,
    });

    const inferred = await buildVerifiedExperimentInput(root, "cand-inferred");
    await appendExperimentRecord(stateRoot, {
      ...inferred,
      mutationProvenance: {
        ...(inferred.mutationProvenance ?? {}),
        inventorySource: "inferred",
      },
      promotionReady: false,
    });

    const recoveredResult = await runCliCommand(root, [
      "promote",
      "--candidate",
      "cand-recovered",
    ]);
    expect(recoveredResult.code).not.toBe(0);
    expect(recoveredResult.stderr).toMatch(/mutationParseStatus|parseStatus must be valid/i);

    const inferredResult = await runCliCommand(root, [
      "promote",
      "--candidate",
      "cand-inferred",
    ]);
    expect(inferredResult.code).not.toBe(0);
    expect(inferredResult.stderr).toMatch(/inventorySource must be llm/i);
  });

  test("rebuild-indexes --verify fails on invalid verified view pollution and quarantines it", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-rebuild-invalid-verified-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    const record = await buildVerifiedExperimentInput(root, "cand-invalid-verified");
    await appendExperimentRecord(stateRoot, {
      ...record,
      executorCapability: localScreeningCapability,
    });

    const result = await runCliCommand(root, ["rebuild-indexes", "--verify"]);

    expect(result.code).not.toBe(0);
    expect(result.stderr).toMatch(/Derived view verification failed/i);

    const leaderboard = JSON.parse(
      await readFile(knowledgePaths.leaderboardPath, "utf8"),
    ) as {
      verifiedEntries: Array<{ candidateId: string }>;
    };
    const frontier = JSON.parse(
      await readFile(knowledgePaths.frontierPath, "utf8"),
    ) as {
      entries: Array<{ candidateId: string }>;
    };
    const invalidRecords = JSON.parse(
      await readFile(knowledgePaths.invalidRecordsPath, "utf8"),
    ) as {
      entries: InvalidRecordViewEntry[];
    };

    expect(leaderboard.verifiedEntries.map((entry) => entry.candidateId)).not.toContain(
      "cand-invalid-verified",
    );
    expect(frontier.entries.map((entry) => entry.candidateId)).not.toContain(
      "cand-invalid-verified",
    );
    expect(invalidRecords.entries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          candidateId: "cand-invalid-verified",
          classification: "invalid_executor",
        }),
      ]),
    );
  });

  test("rebuild-indexes --verify fails on invalid promoted head pollution", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-rebuild-invalid-promoted-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    const sourceRecord = await buildVerifiedExperimentInput(root, "cand-invalid-promoted");
    await appendExperimentRecord(stateRoot, sourceRecord);
    await appendExperimentRecord(stateRoot, {
      ...sourceRecord,
      runId: "run-promoted",
      iteration: 2,
      decision: "promoted_head",
      status: "evaluated",
      promotionStatus: "promoted_head",
      promotionReady: true,
      recordMeta: {
        ...(sourceRecord.recordMeta ?? {}),
        recordHash: "",
        promotedFromRunId: null,
        promotedFromIteration: null,
        promotedFromRecordHash: null,
      },
    });

    const result = await runCliCommand(root, ["rebuild-indexes", "--verify"]);

    expect(result.code).not.toBe(0);
    expect(result.stderr).toMatch(/Derived view verification failed/i);

    const leaderboard = JSON.parse(
      await readFile(knowledgePaths.leaderboardPath, "utf8"),
    ) as {
      activeHeadCandidateId: string | null;
      verifiedEntries: Array<{ candidateId: string; decision: string }>;
    };
    const invalidRecords = JSON.parse(
      await readFile(knowledgePaths.invalidRecordsPath, "utf8"),
    ) as {
      entries: InvalidRecordViewEntry[];
    };

    expect(leaderboard.activeHeadCandidateId).toBeNull();
    expect(
      leaderboard.verifiedEntries.filter(
        (entry) =>
          entry.candidateId === "cand-invalid-promoted" &&
          entry.decision === "promoted_head",
      ),
    ).toHaveLength(0);
    expect(invalidRecords.entries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          candidateId: "cand-invalid-promoted",
          classification: "invalid_promoted_head",
        }),
      ]),
    );
  });

  test("inspect-autonomous-state reports the active champion and v3 operational view", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-inspect-autonomous-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const { candidatePath } = await writePromotionArtifacts(root, "cand-autonomous");

    await appendExperimentRecord(stateRoot, {
      runId: "auto-run-1",
      iteration: 1,
      candidateId: "cand-autonomous",
      parentCandidateId: null,
      branchId: "autonomous-main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: null,
      candidatePath,
      candidateHash: "cand-autonomous-hash",
      studyTitle: "Autonomous Candidate",
      candidateScore: 1.14,
      decision: "local_candidate_eligible",
      status: "evaluated",
      recordKind: "local_evaluation",
      executorRole: "primary_local_backtest",
      evidenceAuthority: "local_model",
      evaluationMode: "local_primary",
      mutationBriefSummary: "Autonomous candidate",
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
      splitEvaluation: {
        splitMethod: "chronological_70_30",
        fullSample: {
          metrics: createPromotableArtifactBundle().strategy,
          objectiveBreakdown: null,
          trades: [],
          equity: null,
        },
        inSample: {
          metrics: createPromotableArtifactBundle().strategy,
          objectiveBreakdown: null,
          trades: [],
          equity: null,
        },
        outOfSample: {
          metrics: createPromotableArtifactBundle().strategy,
          objectiveBreakdown: null,
          trades: [],
          equity: null,
        },
        minimumOosTrades: 15,
        oosEligible: true,
        oosPassed: true,
        hardGatesPassed: true,
        gateReasons: [],
      },
      noveltyFingerprint: {
        fingerprint: "fp-1",
        fingerprintFamily: "fam-1",
        inventorySignature: "inv-1",
        structureSignature: "struct-1",
        featureFlags: [],
        configBuckets: {},
        tokens: [],
      },
      duplicateStatus: {
        classification: "unique",
        exactDuplicateCandidateId: null,
        structuralDuplicateCandidateId: null,
        duplicateFingerprint: null,
      },
      autoSelectionScore: 1.14,
      autoSelectionBreakdown: {
        baseObjectiveScore: 0.8,
        robustnessScore: 0.2,
        noveltyScore: 0.24,
        riskPenalty: 0,
        duplicatePenalty: 0,
        complexityPenalty: 0.1,
        totalScore: 1.14,
        eligible: true,
        rejectionReasons: [],
      },
      objectivePolicyVersion: "objective.qqq-120m/v1",
      selectionPolicyVersion: "autonomous-local-first/v3-p0",
      localConfidence: 1,
      tvCalibrationStatus: "not_requested",
      localTvParity: null,
      artifactPaths: {
        candidate: candidatePath,
      },
      recordMeta: {
        schemaVersion: "experiment/v3",
        recordHash: "",
        candidateHash: "cand-autonomous-hash",
        baselineHash: null,
        artifactBundleHash: null,
        pipelineVersion: "af-autonomous-local-first/v3",
      },
    });

    await appendHeadEventRecord(stateRoot, {
      runId: "auto-run-1",
      iteration: 1,
      eventKind: "auto_selected_head",
      candidateId: "cand-autonomous",
      previousChampionId: null,
      selectedBy: "auto_policy",
      policyVersion: "autonomous-local-first/v3-p0",
      selectionPhase: "steady_state",
      bootstrapSource: null,
      bootstrapReason: null,
      researchMaturity: "steady_state",
      objectiveScore: 0.8,
      noveltyScore: 0.24,
      robustnessScore: 0.2,
      diversityContribution: 0.24,
      riskPenalty: 0,
      overfitPenalty: 0,
      complexityPenalty: 0.1,
      selectionReason: "Initial autonomous champion",
      selectionEvidenceHash: "selection-hash",
      humanOverride: false,
    });

    const result = await runCliCommand(root, ["inspect-autonomous-state"]);

    expect(result.code).toBe(0);
    expect(parseCliJson(result.stdout)).toEqual(
      expect.objectContaining({
        activeChampionCandidateId: "cand-autonomous",
        headEventCount: 1,
        localEvaluationCount: 1,
        defaultOperationalView: "v3_autonomous_local_first",
        loopMode: "local-first",
      }),
    );
  });

  test("inspect-local-compatibility reports unsupported reason distribution and missing fields", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-inspect-compat-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    await seedUnsupportedAutonomousCandidate(root, "cand-unsupported");

    const result = await runCliCommand(root, ["inspect-local-compatibility"]);

    expect(result.code).toBe(0);
    expect(parseCliJson(result.stdout)).toEqual(
      expect.objectContaining({
        stateRoot,
        localUnsupportedCount: 1,
        unsupportedReasonCounts: expect.objectContaining({
          "Missing required AF inputs and uses a forbidden indicator() helper.": 1,
        }),
        missingFunctionCounts: expect.objectContaining({
          computeTrend: 1,
        }),
        missingInputCounts: expect.objectContaining({
          L1: 1,
        }),
        unsupportedPatternCounts: expect.objectContaining({
          "unsupported_pattern:indicator(": 1,
        }),
      }),
    );
  });

  test("inspect-failure-memory links repair attempts back to the originating problem event", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-cli-inspect-failure-memory-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const unsupported = await seedUnsupportedAutonomousCandidate(root, "cand-problem");

    expect(unsupported.problemEvent).not.toBeNull();
    await appendRepairAttemptRecord(stateRoot, {
      repairAttemptId: "repair-test-1",
      problemEventId: unsupported.problemEvent!.problemEventId,
      runId: unsupported.record.runId,
      iteration: unsupported.record.iteration,
      candidateId: unsupported.record.candidateId,
      repairedCandidateId: "cand-repaired",
      repairKind: "local_compatibility_repair",
      llmPromptHash: "prompt-hash",
      llmResponseHash: "response-hash",
      result: "success",
      failureReason: null,
      summary: "Repaired missing AF compatibility fields.",
    });

    const result = await runCliCommand(root, ["inspect-failure-memory"]);

    expect(result.code).toBe(0);
    expect(parseCliJson(result.stdout)).toEqual(
      expect.objectContaining({
        stateRoot,
        problemEventCount: 1,
        repairAttemptCount: 1,
        recentProblemEvents: expect.arrayContaining([
          expect.objectContaining({
            candidateId: "cand-problem",
            problemKind: "local_unsupported",
            repairAttempt: expect.objectContaining({
              repairKind: "local_compatibility_repair",
              repairedCandidateId: "cand-repaired",
              result: "success",
            }),
          }),
        ]),
      }),
    );
  });
});

async function rewriteExperimentRecordForTest(
  stateRoot: string,
  candidateId: string,
  rewrite: (record: ExperimentRecord) => ExperimentRecord,
): Promise<void> {
  const paths = resolveKnowledgePaths(stateRoot);
  const lines = (await readFile(paths.experimentsPath, "utf8"))
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => {
      const record = JSON.parse(line) as ExperimentRecord;
      return JSON.stringify(record.candidateId === candidateId ? rewrite(record) : record);
    });
  await writeFile(paths.experimentsPath, `${lines.join("\n")}\n`, "utf8");
}
