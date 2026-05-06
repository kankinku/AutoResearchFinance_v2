import { readFile } from "node:fs/promises";

import { z } from "zod";

import {
  candidateLedgerRecordSchema,
  experimentRecordSchema,
  incidentRecordSchema,
  indicatorArtifactRecordSchema,
  mutationBriefRecordSchema,
  researchKnowledgeRecordSchema,
  runRecordSchema,
  taskBatchRecordSchema,
  taskRecordSchema,
  type CandidateLedgerRecord,
  type ExperimentRecord,
  type LocalTvParitySummary,
  type TaskBatchRecord,
} from "../contracts/types.js";
import {
  problemEventRecordSchema,
  repairAttemptRecordSchema,
} from "../contracts/autonomous.js";
import {
  normalizeDecisionCode,
  resolveRecordEra,
} from "../evaluation/decision.js";
import {
  buildEligibilityContext,
  buildInvalidRecordViewEntries,
  claimsPromotion,
  claimsPromotedHead,
  claimsVerifiedView,
  evaluatePromotedHeadEligibility,
  evaluatePromotionEligibility,
  evaluateVerifiedViewEligibility,
  type InvalidRecordViewEntry,
  selectPromotionEligibleRecords,
  selectPromotedHeadRecords,
  selectVerifiedViewRecords,
} from "../evaluation/record-eligibility.js";
import {
  fileExists,
  readJson,
  scanJsonlTolerant,
  sha256Json,
} from "../utils/fs.js";
import {
  validateAutonomousLedger,
  verifyAutonomousDerivedViews,
} from "./autonomous-validator.js";
import {
  findActiveHeadRecord,
  findBestAcceptedRecord,
  findBestVerifiedRecord,
  findLegacyAcceptedRecord,
} from "./accepted-head.js";
import {
  readArchiveEventRecords,
  readCalibrationEventRecords,
  computeCanonicalRecordHash,
  readExperimentRecords,
  readHeadEventRecords,
  readTaskBatchRecords,
  resolveStatePaths,
} from "./jsonl-store.js";

type ValidationSeverity = "error" | "warning";

export interface LedgerValidationIssue {
  severity: ValidationSeverity;
  scope: string;
  message: string;
  kind?: string;
  filePath?: string;
  line?: number;
  lineNumber?: number;
  recordId?: string;
  rawLinePreview?: string;
}

export interface LedgerValidationResult {
  ok: boolean;
  errorCount: number;
  warningCount: number;
  issues: LedgerValidationIssue[];
  summary: {
    experiments: number;
    candidates: number;
    taskBatches: number;
  };
}

export interface IndexVerificationResult {
  ok: boolean;
  issues: LedgerValidationIssue[];
}

const legacyRunRecordSchema = z.object({
  runId: z.string().min(1),
  startedAt: z.string().datetime(),
  executor: z.union([
    z.literal("local-backtest"),
    z.literal("tradingview-desktop-cdp"),
    z.literal("tradingview-web-playwright"),
    z.literal("playwright-tradingview"),
  ]),
  symbol: z.string().min(1),
  timeframe: z.string().min(1),
  chartType: z.string().min(1),
  model: z.string().min(1),
});

const legacyMutationBriefRecordSchema = z.object({
  runId: z.string().min(1),
  iteration: z.number().int().positive(),
  acceptedHeadCandidateId: z.string().nullable(),
  brief: z
    .object({
      objective: z.string().min(1),
      guardrails: z.object({
        minimumTotalTrades: z.number().nonnegative(),
        minimumPostFeeNetProfitPercent: z.number(),
        maximumStrategyDrawdownPercent: z.number().positive(),
      }),
      acceptedHead: z
        .object({
          candidateId: z.string().min(1),
          score: z.number(),
        })
        .nullable()
        .optional(),
      recentFailures: z.array(z.string()).default([]),
      nextMutationDirection: z.string().min(1),
      forbiddenPatterns: z.array(z.string()).default([]),
    })
    .passthrough(),
  recordedAt: z.string().datetime().optional(),
});

function validateLedgerEntry(
  scope: (typeof LEDGER_SCHEMAS)[number]["scope"],
  parsed: unknown,
):
  | { success: true }
  | {
      success: false;
      message: string;
    } {
  if (scope === "runs") {
    const current = runRecordSchema.safeParse(parsed);
    if (current.success) {
      return { success: true };
    }
    const legacy = legacyRunRecordSchema.safeParse(parsed);
    if (legacy.success) {
      return { success: true };
    }
    return {
      success: false,
      message: current.error.issues
        .map((issue) => `${issue.path.join(".") || "<root>"}: ${issue.message}`)
        .join("; "),
    };
  }

  if (scope === "mutationBriefs") {
    const current = mutationBriefRecordSchema.safeParse(parsed);
    if (current.success) {
      return { success: true };
    }
    const legacy = legacyMutationBriefRecordSchema.safeParse(parsed);
    if (legacy.success) {
      return { success: true };
    }
    return {
      success: false,
      message: current.error.issues
        .map((issue) => `${issue.path.join(".") || "<root>"}: ${issue.message}`)
        .join("; "),
    };
  }

  const schema = LEDGER_SCHEMAS.find((entry) => entry.scope === scope)?.schema;
  if (!schema) {
    return { success: true };
  }
  const validated = schema.safeParse(parsed);
  if (validated.success) {
    return { success: true };
  }
  return {
    success: false,
    message: validated.error.issues
      .map((issue) => `${issue.path.join(".") || "<root>"}: ${issue.message}`)
      .join("; "),
  };
}

const LEDGER_SCHEMAS = [
  { scope: "experiments", fileKey: "experimentsPath", schema: experimentRecordSchema },
  { scope: "incidents", fileKey: "incidentsPath", schema: incidentRecordSchema },
  { scope: "runs", fileKey: "runsPath", schema: runRecordSchema },
  { scope: "taskBatches", fileKey: "taskBatchesPath", schema: taskBatchRecordSchema },
  { scope: "tasks", fileKey: "tasksPath", schema: taskRecordSchema },
  { scope: "mutationBriefs", fileKey: "mutationBriefsPath", schema: mutationBriefRecordSchema },
  { scope: "indicatorArtifacts", fileKey: "indicatorArtifactsPath", schema: indicatorArtifactRecordSchema },
  { scope: "candidates", fileKey: "candidatesPath", schema: candidateLedgerRecordSchema },
  { scope: "researchKnowledge", fileKey: "researchKnowledgePath", schema: researchKnowledgeRecordSchema },
  { scope: "problemEvents", fileKey: "problemEventsPath", schema: problemEventRecordSchema },
  { scope: "repairAttempts", fileKey: "repairAttemptsPath", schema: repairAttemptRecordSchema },
] as const;

function pushIssue(
  issues: LedgerValidationIssue[],
  issue: LedgerValidationIssue,
): void {
  issues.push(issue);
}

function computeRecordHash(record: Record<string, unknown>): string {
  return computeCanonicalRecordHash(
    record,
    record.recordMeta && typeof record.recordMeta === "object"
      ? (record.recordMeta as Record<string, unknown>)
      : undefined,
  );
}

type JsonlSchemaScanSummary = {
  issues: LedgerValidationIssue[];
  experiments: ExperimentRecord[];
  candidates: CandidateLedgerRecord[];
  taskBatches: TaskBatchRecord[];
};

async function scanLedgerFile<T>(
  scope: (typeof LEDGER_SCHEMAS)[number]["scope"],
  filePath: string,
): Promise<{
  records: T[];
  issues: LedgerValidationIssue[];
}> {
  const scan = await scanJsonlTolerant<T>(filePath, (parsed) => {
    const validated = validateLedgerEntry(scope, parsed);
    if (!validated.success) {
      return {
        success: false,
        kind: "schema_error",
        message: validated.message,
      };
    }

    return {
      success: true,
      record: parsed as T,
    };
  });

  return {
    records: scan.records,
    issues: scan.issues.map((issue) => ({
      severity: "error",
      scope,
      kind: issue.kind,
      filePath,
      line: issue.lineNumber,
      lineNumber: issue.lineNumber,
      rawLinePreview: issue.rawLinePreview,
      message:
        issue.kind === "partial_tail"
          ? `Invalid JSONL record (possible corrupted tail): ${issue.message}`
          : issue.kind === "malformed_json"
            ? `Invalid JSONL record: ${issue.message}`
            : issue.message,
    })),
  };
}

async function validateJsonlSchemas(stateRoot: string): Promise<JsonlSchemaScanSummary> {
  const paths = resolveStatePaths(stateRoot);
  const issues: LedgerValidationIssue[] = [];
  const experiments: ExperimentRecord[] = [];
  const candidates: CandidateLedgerRecord[] = [];
  const taskBatches: TaskBatchRecord[] = [];

  for (const entry of LEDGER_SCHEMAS) {
    const filePath = paths[entry.fileKey];
    const scanResult = await scanLedgerFile(entry.scope, filePath);
    issues.push(...scanResult.issues);

    if (entry.scope === "experiments") {
      experiments.push(...(scanResult.records as ExperimentRecord[]));
    } else if (entry.scope === "candidates") {
      candidates.push(...(scanResult.records as CandidateLedgerRecord[]));
    } else if (entry.scope === "taskBatches") {
      taskBatches.push(...(scanResult.records as TaskBatchRecord[]));
    }
  }

  return {
    issues,
    experiments,
    candidates,
    taskBatches,
  };
}

async function validateArtifacts(
  experiments: ExperimentRecord[],
  candidates: CandidateLedgerRecord[],
): Promise<LedgerValidationIssue[]> {
  const issues: LedgerValidationIssue[] = [];

  for (const candidate of candidates) {
    if (!(await fileExists(candidate.candidatePath))) {
      pushIssue(issues, {
        severity: "error",
        scope: "candidate-artifact",
        recordId: candidate.candidateId,
        filePath: candidate.candidatePath,
        message: "Candidate source file is missing.",
      });
    }
  }

  for (const record of experiments) {
    if (record.candidatePath && !(await fileExists(record.candidatePath))) {
      pushIssue(issues, {
        severity: "error",
        scope: "experiment-artifact",
        recordId: record.candidateId,
        filePath: record.candidatePath,
        message: "Experiment candidate source file is missing.",
      });
    }

    for (const [artifactKey, artifactPath] of Object.entries(record.artifactPaths ?? {})) {
      if (!(await fileExists(artifactPath))) {
        pushIssue(issues, {
          severity: "error",
          scope: "experiment-artifact",
          recordId: record.candidateId,
          filePath: artifactPath,
          message: `Artifact path "${artifactKey}" is missing.`,
        });
      }
    }

    const artifactBundleHash =
      record.recordMeta?.artifactBundleHash ?? record.artifactBundleHash ?? null;
    if (artifactBundleHash && record.artifactBundle) {
      const actualHash = sha256Json(record.artifactBundle);
      if (actualHash !== artifactBundleHash) {
        pushIssue(issues, {
          severity: "error",
          scope: "experiment-record-meta",
          recordId: record.candidateId,
          message: "artifactBundleHash does not match artifactBundle content.",
        });
      }
    }
    if (artifactBundleHash && record.artifactBundleRef?.path) {
      try {
        const referencedBundle = JSON.parse(
          await readFile(record.artifactBundleRef.path, "utf8"),
        ) as unknown;
        const actualHash = sha256Json(referencedBundle);
        if (actualHash !== artifactBundleHash) {
          pushIssue(issues, {
            severity: "error",
            scope: "experiment-record-meta",
            recordId: record.candidateId,
            filePath: record.artifactBundleRef.path,
            message:
              "artifactBundleHash does not match referenced artifactBundleRef content.",
          });
        }
      } catch (error) {
        pushIssue(issues, {
          severity: "error",
          scope: "experiment-artifact",
          recordId: record.candidateId,
          filePath: record.artifactBundleRef.path,
          message: `Referenced artifactBundleRef could not be read: ${
            error instanceof Error ? error.message : String(error)
          }`,
        });
      }
    }

    if (record.recordMeta?.recordHash) {
      const actualHash = computeRecordHash(record as Record<string, unknown>);
      if (actualHash !== record.recordMeta.recordHash) {
        pushIssue(issues, {
          severity: "warning",
          scope: "experiment-record-meta",
          recordId: record.candidateId,
          message: "recordHash does not match the serialized experiment record.",
        });
      }
    }
  }

  return issues;
}

function validateDuplicateCandidateHashes(
  experiments: ExperimentRecord[],
  candidates: CandidateLedgerRecord[],
): LedgerValidationIssue[] {
  const issues: LedgerValidationIssue[] = [];
  const idsByHash = new Map<string, Set<string>>();

  for (const record of candidates) {
    if (!record.candidateHash) {
      continue;
    }
    const ids = idsByHash.get(record.candidateHash) ?? new Set<string>();
    ids.add(record.candidateId);
    idsByHash.set(record.candidateHash, ids);
  }

  for (const record of experiments) {
    if (!record.candidateHash) {
      continue;
    }
    const ids = idsByHash.get(record.candidateHash) ?? new Set<string>();
    ids.add(record.candidateId);
    idsByHash.set(record.candidateHash, ids);
  }

  for (const [candidateHash, ids] of idsByHash.entries()) {
    if (ids.size <= 1) {
      continue;
    }
    pushIssue(issues, {
      severity: "warning",
      scope: "candidate-dedup",
      recordId: candidateHash,
      message: `Duplicate candidate source hash detected across ids: ${[...ids].sort().join(", ")}`,
    });
  }

  return issues;
}

export async function validateLedger(stateRoot: string): Promise<LedgerValidationResult> {
  const schemaScan = await validateJsonlSchemas(stateRoot);
  const experiments = schemaScan.experiments;
  const candidates = schemaScan.candidates;
  const artifactIssues = await validateArtifacts(experiments, candidates);
  const duplicateIssues = validateDuplicateCandidateHashes(experiments, candidates);
  const legacyIssues = validateLegacySeparation(experiments);
  const fallbackIssues = validateFallbackSemantics(experiments);
  const verifiedViewIssues = validateVerifiedViewClaims(experiments);
  const promotionContractIssues = validatePromotionContract(experiments);
  const autonomousIssues = await validateAutonomousLedger(stateRoot);
  const issues = [
    ...schemaScan.issues,
    ...artifactIssues,
    ...duplicateIssues,
    ...legacyIssues,
    ...fallbackIssues,
    ...verifiedViewIssues,
    ...promotionContractIssues,
    ...autonomousIssues,
  ];
  const errorCount = issues.filter((issue) => issue.severity === "error").length;
  const warningCount = issues.length - errorCount;

  return {
    ok: errorCount === 0,
    errorCount,
    warningCount,
    issues,
    summary: {
      experiments: experiments.length,
      candidates: candidates.length,
      taskBatches: schemaScan.taskBatches.length,
    },
  };
}

function normalizeDecisionCounts(records: ExperimentRecord[]): Record<string, number> {
  return records.reduce<Record<string, number>>((counts, record) => {
    const decision = String(normalizeDecisionCode(record.decision));
    counts[decision] = (counts[decision] ?? 0) + 1;
    return counts;
  }, {});
}

function countRecordsEqual(
  left: Record<string, number>,
  right: Record<string, number>,
): boolean {
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  for (const key of keys) {
    if ((left[key] ?? 0) !== (right[key] ?? 0)) {
      return false;
    }
  }
  return true;
}

function resolveLatestParityCounts(records: ExperimentRecord[]): Record<string, number> {
  const latestByCandidate = new Map<
    string,
    {
      iteration: number;
      parity: LocalTvParitySummary;
    }
  >();

  const chronological = [...records].sort((left, right) => {
    if (left.iteration !== right.iteration) {
      return left.iteration - right.iteration;
    }
    return left.candidateId.localeCompare(right.candidateId);
  });

  for (const record of chronological) {
    if (record.fallbackEvaluation) {
      latestByCandidate.set(record.candidateId, {
        iteration: record.iteration,
        parity: record.fallbackEvaluation.parity,
      });
    }
    if (record.localTvParity) {
      latestByCandidate.set(record.candidateId, {
        iteration: record.iteration,
        parity: record.localTvParity,
      });
    }
  }

  return [...latestByCandidate.values()].reduce<Record<string, number>>((counts, entry) => {
    const status = entry.parity.status ?? "not_comparable";
    counts[status] = (counts[status] ?? 0) + 1;
    return counts;
  }, {});
}

function resolveLatestTaskBatchRecords(records: TaskBatchRecord[]): TaskBatchRecord[] {
  const latestByBatchId = new Map<string, TaskBatchRecord>();
  for (const record of records) {
    const current = latestByBatchId.get(record.batchId);
    if (!current) {
      latestByBatchId.set(record.batchId, record);
      continue;
    }

    const currentRecordedAt = Date.parse(current.recordedAt ?? "");
    const nextRecordedAt = Date.parse(record.recordedAt ?? "");
    if (nextRecordedAt >= currentRecordedAt) {
      latestByBatchId.set(record.batchId, record);
    }
  }

  return [...latestByBatchId.values()];
}

function sortExperimentsForView(records: ExperimentRecord[]): ExperimentRecord[] {
  return [...records].sort((left, right) => {
    const leftScore = left.candidateScore ?? Number.NEGATIVE_INFINITY;
    const rightScore = right.candidateScore ?? Number.NEGATIVE_INFINITY;
    if (leftScore !== rightScore) {
      return rightScore - leftScore;
    }

    if (left.iteration !== right.iteration) {
      return left.iteration - right.iteration;
    }

    return left.candidateId.localeCompare(right.candidateId);
  });
}

function buildViewRecordKey(
  record: Pick<ExperimentRecord, "candidateId" | "iteration" | "decision" | "recordMeta">,
): string {
  return (
    record.recordMeta?.recordHash ??
    `${record.candidateId}:${record.iteration}:${record.decision}`
  );
}

function dedupeExperimentRecords(records: ExperimentRecord[]): ExperimentRecord[] {
  const unique = new Map<string, ExperimentRecord>();
  for (const record of records) {
    unique.set(buildViewRecordKey(record), record);
  }
  return [...unique.values()];
}

function buildRankedViewEntry(
  record: ExperimentRecord,
  rank: number,
): Record<string, unknown> {
  return {
    rank,
    candidateId: record.candidateId,
    decision: String(normalizeDecisionCode(record.decision)),
    score: record.candidateScore ?? null,
    iteration: record.iteration,
    branchId: record.branchId,
    recordEra: resolveRecordEra(record),
    recordHash: record.recordMeta?.recordHash ?? null,
  };
}

export async function verifyDerivedViews(
  stateRoot: string,
): Promise<IndexVerificationResult> {
  const issues: LedgerValidationIssue[] = [];
  const ledgerValidation = await validateLedger(stateRoot);
  if (!ledgerValidation.ok) {
    pushIssue(issues, {
      severity: "error",
      scope: "ledger-gate",
      message: `Ledger validation failed with ${ledgerValidation.errorCount} error(s); derived view verification is not trustworthy until the ledger is repaired.`,
    });
    for (const issue of ledgerValidation.issues.filter((issue) => issue.severity === "error")) {
      pushIssue(issues, {
        ...issue,
        scope: `ledger-gate/${issue.scope}`,
      });
    }
  }

  const paths = resolveStatePaths(stateRoot);
  const experiments = await readExperimentRecords(stateRoot);
  const taskBatches = await readTaskBatchRecords(stateRoot);
  const rankedExperiments = experiments.filter((record) => record.fallbackEvaluation == null);
  const verifiedRecords = sortExperimentsForView(
    selectVerifiedViewRecords(rankedExperiments),
  );
  const screeningRecords = sortExperimentsForView(
    rankedExperiments.filter(
      (record) =>
        resolveRecordEra(record) === "v2" &&
        (record.decision === "screening_improvement" ||
          record.decision === "valid_no_promotion"),
    ),
  );
  const legacyRecords = sortExperimentsForView(
    rankedExperiments.filter((record) => resolveRecordEra(record) === "legacy"),
  );
  const leaderboardRecords = sortExperimentsForView(
    dedupeExperimentRecords([...verifiedRecords, ...legacyRecords]),
  );
  const frontierRecords = sortExperimentsForView(
    dedupeExperimentRecords([
      ...selectPromotionEligibleRecords(rankedExperiments),
      ...selectPromotedHeadRecords(rankedExperiments),
    ]),
  );
  const expectedInvalidEntries = buildInvalidRecordViewEntries(experiments)
    .slice()
    .sort(
      (left, right) =>
        (right.iteration ?? 0) - (left.iteration ?? 0) ||
        left.candidateId.localeCompare(right.candidateId),
    );
  const fallbackCandidateIds = new Set(
    experiments
      .filter((record) => record.fallbackEvaluation != null)
      .map((record) => record.candidateId),
  );
  const leaderboard = await readJson<{
    entries: Array<{ candidateId: string }>;
    acceptedHeadCandidateId: string | null;
    verifiedHeadCandidateId?: string | null;
    legacyHeadCandidateId?: string | null;
    activeHeadCandidateId: string | null;
    verifiedEntries?: Array<Record<string, unknown>>;
    screeningEntries?: Array<Record<string, unknown>>;
    legacyEntries?: Array<Record<string, unknown>>;
  }>(paths.leaderboardPath);
  const frontier = await readJson<{
    entries: Array<Record<string, unknown>>;
  }>(paths.frontierPath);
  const failureSummary = await readJson<{
    decisionCounts: Record<string, number>;
    verificationRuntimeFailureKindCounts?: Record<string, number>;
  }>(paths.failureSummaryPath);
  const taskBoard = await readJson<{
    batches: Array<{ batchId: string }>;
  }>(paths.taskBoardPath);
  const verificationFailures = await readJson<{
    entries: Array<{ candidateId: string; decision: string }>;
  }>(paths.verificationFailuresPath);
  const fallbackEvidenceBoard = await readJson<{
    entries: Array<{ candidateId: string }>;
  }>(paths.fallbackEvidenceBoardPath);
  const screeningBoard = await readJson<{
    entries: Array<Record<string, unknown>>;
  }>(paths.screeningBoardPath);
  const invalidRecords = await readJson<{
    entries: InvalidRecordViewEntry[];
  }>(paths.invalidRecordsPath);
  const runtimeFailureSummary = await readJson<{
    counts: Record<string, number>;
  }>(paths.runtimeFailureSummaryPath);
  const localTvDivergenceSummary = await readJson<{
    parityStatusCounts: Record<string, number>;
  }>(paths.localTvDivergenceSummaryPath);
  const verificationQueue = await readJson<{
    entries: Array<{ candidateId: string }>;
  }>(paths.verificationQueuePath);

  const expectedAcceptedHead = findBestAcceptedRecord(experiments)?.candidateId ?? null;
  const expectedVerifiedHead = findBestVerifiedRecord(experiments)?.candidateId ?? null;
  const expectedLegacyHead = findLegacyAcceptedRecord(experiments)?.candidateId ?? null;
  const expectedActiveHead = findActiveHeadRecord(experiments)?.candidateId ?? null;
  const expectedLeaderboardEntries = leaderboardRecords.map((record, index) =>
    buildRankedViewEntry(record, index + 1),
  );
  const expectedVerifiedEntries = verifiedRecords.map((record, index) =>
    buildRankedViewEntry(record, index + 1),
  );
  const expectedScreeningEntries = screeningRecords.map((record, index) =>
    buildRankedViewEntry(record, index + 1),
  );
  const expectedLegacyEntries = legacyRecords.map((record, index) =>
    buildRankedViewEntry(record, index + 1),
  );
  const expectedFrontierEntries = frontierRecords.map((record, index) => ({
    rank: index + 1,
    candidateId: record.candidateId,
    score: record.candidateScore ?? null,
    decision: String(normalizeDecisionCode(record.decision)),
    iteration: record.iteration,
    branchId: record.branchId,
    recordHash: record.recordMeta?.recordHash ?? null,
  }));
  const serialize = (value: unknown) => JSON.stringify(value);

  if (serialize(leaderboard.entries) !== serialize(expectedLeaderboardEntries)) {
    pushIssue(issues, {
      severity: "error",
      scope: "leaderboard",
      message: "Leaderboard entries do not match the canonical verified+legacy leaderboard set.",
      filePath: paths.leaderboardPath,
    });
  }

  if (leaderboard.acceptedHeadCandidateId !== expectedAcceptedHead) {
    pushIssue(issues, {
      severity: "error",
      scope: "leaderboard",
      message: "acceptedHeadCandidateId does not match ledger-derived accepted head.",
      filePath: paths.leaderboardPath,
    });
  }

  if ((leaderboard.verifiedHeadCandidateId ?? null) !== expectedVerifiedHead) {
    pushIssue(issues, {
      severity: "error",
      scope: "leaderboard",
      message: "verifiedHeadCandidateId does not match ledger-derived verified head.",
      filePath: paths.leaderboardPath,
    });
  }

  if ((leaderboard.legacyHeadCandidateId ?? null) !== expectedLegacyHead) {
    pushIssue(issues, {
      severity: "error",
      scope: "leaderboard",
      message: "legacyHeadCandidateId does not match ledger-derived legacy head.",
      filePath: paths.leaderboardPath,
    });
  }

  if (leaderboard.activeHeadCandidateId !== expectedActiveHead) {
    pushIssue(issues, {
      severity: "error",
      scope: "leaderboard",
      message: "activeHeadCandidateId does not match promoted head selection.",
      filePath: paths.leaderboardPath,
    });
  }

  if (serialize(frontier.entries) !== serialize(expectedFrontierEntries)) {
    pushIssue(issues, {
      severity: "error",
      scope: "frontier",
      message: "Frontier entries do not match the canonical promotion-eligible set.",
      filePath: paths.frontierPath,
    });
  }

  if (
    serialize(leaderboard.verifiedEntries ?? []) !== serialize(expectedVerifiedEntries)
  ) {
    pushIssue(issues, {
      severity: "error",
      scope: "leaderboard",
      message: "verifiedEntries do not match the canonical verified-view eligible set.",
      filePath: paths.leaderboardPath,
    });
  }

  if (serialize(leaderboard.legacyEntries ?? []) !== serialize(expectedLegacyEntries)) {
    pushIssue(issues, {
      severity: "error",
      scope: "leaderboard",
      message: "legacyEntries do not match the canonical legacy set.",
      filePath: paths.leaderboardPath,
    });
  }

  if (
    serialize(leaderboard.screeningEntries ?? []) !==
    serialize(expectedScreeningEntries)
  ) {
    pushIssue(issues, {
      severity: "error",
      scope: "leaderboard",
      message: "screeningEntries do not match the canonical screening set.",
      filePath: paths.leaderboardPath,
    });
  }

  if (serialize(screeningBoard.entries) !== serialize(expectedScreeningEntries)) {
    pushIssue(issues, {
      severity: "error",
      scope: "screening-board",
      message: "screening-board entries do not match the canonical screening set.",
      filePath: paths.screeningBoardPath,
    });
  }

  if (serialize(invalidRecords.entries) !== serialize(expectedInvalidEntries)) {
    pushIssue(issues, {
      severity: "error",
      scope: "invalid-records",
      message: "invalid-records does not match the canonical invalid current-record quarantine set.",
      filePath: paths.invalidRecordsPath,
    });
  }

  if (leaderboard.entries.some((entry) => fallbackCandidateIds.has(entry.candidateId))) {
    pushIssue(issues, {
      severity: "error",
      scope: "leaderboard",
      message: "Leaderboard contains fallback-only verification failure records.",
      filePath: paths.leaderboardPath,
    });
  }

  const invalidCandidateIds = new Set(expectedInvalidEntries.map((entry) => entry.candidateId));
  if (
    (leaderboard.verifiedEntries ?? []).some(
      (entry) => invalidCandidateIds.has(String(entry.candidateId ?? "")),
    ) ||
    frontier.entries.some(
      (entry) => invalidCandidateIds.has(String(entry.candidateId ?? "")),
    )
  ) {
    pushIssue(issues, {
      severity: "error",
      scope: "contamination",
      message:
        "Invalid current records leaked into verifiedEntries or frontier instead of staying quarantined.",
    });
  }

  const expectedDecisionCounts = normalizeDecisionCounts(experiments);
  if (JSON.stringify(failureSummary.decisionCounts) !== JSON.stringify(expectedDecisionCounts)) {
    pushIssue(issues, {
      severity: "error",
      scope: "failure-summary",
      message: "failure-summary decisionCounts do not match ledger-derived counts.",
      filePath: paths.failureSummaryPath,
    });
  }

  const expectedRuntimeFailureKindCounts = experiments.reduce<Record<string, number>>(
    (counts, record) => {
      if (!record.verificationRuntimeFailureKind) {
        return counts;
      }
      counts[record.verificationRuntimeFailureKind] =
        (counts[record.verificationRuntimeFailureKind] ?? 0) + 1;
      return counts;
    },
    {},
  );
  if (
    JSON.stringify(failureSummary.verificationRuntimeFailureKindCounts ?? {}) !==
    JSON.stringify(expectedRuntimeFailureKindCounts)
  ) {
    pushIssue(issues, {
      severity: "error",
      scope: "failure-summary",
      message:
        "failure-summary verificationRuntimeFailureKindCounts do not match ledger-derived counts.",
      filePath: paths.failureSummaryPath,
    });
  }

  const latestTaskBatchCount = resolveLatestTaskBatchRecords(taskBatches).length;
  if (taskBoard.batches.length !== latestTaskBatchCount) {
    pushIssue(issues, {
      severity: "error",
      scope: "task-board",
      message: "Task board batch count does not match latest batch ledger count.",
      filePath: paths.taskBoardPath,
    });
  }

  if (
    verificationFailures.entries.some((entry) => !experiments.some((record) => record.candidateId === entry.candidateId))
  ) {
    pushIssue(issues, {
      severity: "error",
      scope: "verification-failures",
      message: "verification-failures contains entries not found in the experiment ledger.",
      filePath: paths.verificationFailuresPath,
    });
  }

  if (
    fallbackEvidenceBoard.entries.some((entry) => !fallbackCandidateIds.has(entry.candidateId))
  ) {
    pushIssue(issues, {
      severity: "error",
      scope: "fallback-evidence-board",
      message: "fallback-evidence-board contains records without fallbackEvaluation metadata.",
      filePath: paths.fallbackEvidenceBoardPath,
    });
  }

  if (
    JSON.stringify(runtimeFailureSummary.counts) !==
    JSON.stringify(expectedRuntimeFailureKindCounts)
  ) {
    pushIssue(issues, {
      severity: "error",
      scope: "runtime-failure-summary",
      message: "runtime-failure-summary counts do not match ledger-derived counts.",
      filePath: paths.runtimeFailureSummaryPath,
    });
  }

  const expectedParityCounts = resolveLatestParityCounts(experiments);
  if (!countRecordsEqual(localTvDivergenceSummary.parityStatusCounts, expectedParityCounts)) {
    pushIssue(issues, {
      severity: "error",
      scope: "local-tv-divergence-summary",
      message: "local-tv-divergence-summary parity counts do not match ledger-derived counts.",
      filePath: paths.localTvDivergenceSummaryPath,
    });
  }

  const expectedVerificationQueueIds = new Set(
    experiments
      .filter(
        (record) =>
          record.decision === "verification_fail" &&
          record.verificationFailureReason === "verification_runtime_failure",
      )
      .map((record) => record.candidateId),
  );
  if (
    verificationQueue.entries.some(
      (entry) => !expectedVerificationQueueIds.has(entry.candidateId),
    )
  ) {
    pushIssue(issues, {
      severity: "error",
      scope: "verification-queue",
      message: "verification-queue contains unexpected candidates.",
      filePath: paths.verificationQueuePath,
    });
  }

  issues.push(...(await verifyAutonomousDerivedViews(stateRoot)));

  return {
    ok: issues.length === 0,
    issues,
  };
}

function validateLegacySeparation(records: ExperimentRecord[]): LedgerValidationIssue[] {
  const issues: LedgerValidationIssue[] = [];
  for (const record of records) {
    const era = resolveRecordEra(record);
    if (
      era === "legacy" &&
      (record.verificationStatus === "verified" ||
        record.promotionStatus === "verified_improvement" ||
        record.promotionStatus === "promoted_head")
    ) {
      pushIssue(issues, {
        severity: "error",
        scope: "legacy-separation",
        recordId: record.candidateId,
        message: "Legacy record is marked as verified or promoted in the v2 lifecycle.",
      });
    }
    if (
      record.recordMeta?.schemaVersion === "experiment/v2" &&
      record.executorCapability?.kind === "tradingview-live" &&
      record.decision === "verified_improvement" &&
      !record.artifactValidation?.hasRawReport
    ) {
      pushIssue(issues, {
        severity: "error",
        scope: "verification-artifact",
        recordId: record.candidateId,
        message: "Verified TradingView record is missing raw report evidence.",
      });
    }
  }

  return issues;
}

function validateFallbackSemantics(records: ExperimentRecord[]): LedgerValidationIssue[] {
  const issues: LedgerValidationIssue[] = [];
  for (const record of records) {
    if (!record.fallbackEvaluation) {
      continue;
    }
    if (record.promotionReady) {
      pushIssue(issues, {
        severity: "error",
        scope: "fallback-semantics",
        recordId: record.candidateId,
        message: "Fallback evidence record cannot be promotionReady=true.",
      });
    }
    if (record.verificationStatus !== "verification_failed") {
      pushIssue(issues, {
        severity: "error",
        scope: "fallback-semantics",
        recordId: record.candidateId,
        message: "Fallback evidence record must remain in verification_failed status.",
      });
    }
    if (record.decision !== "verification_fail") {
      pushIssue(issues, {
        severity: "error",
        scope: "fallback-semantics",
        recordId: record.candidateId,
        message: "Fallback evidence record must keep decision=verification_fail.",
      });
    }
    if (record.verificationFailureReason !== "verification_runtime_failure") {
      pushIssue(issues, {
        severity: "error",
        scope: "fallback-semantics",
        recordId: record.candidateId,
        message:
          "Fallback evidence record must keep verificationFailureReason=verification_runtime_failure.",
      });
    }
    if (
      record.promotionStatus === "verified_improvement" ||
      record.promotionStatus === "promoted_head"
    ) {
      pushIssue(issues, {
        severity: "error",
        scope: "fallback-semantics",
        recordId: record.candidateId,
        message: "Fallback evidence record cannot be verified or promoted.",
      });
    }
    if (
      (record.fallbackEvaluation.executorKind !== "local-af-screening" &&
        record.fallbackEvaluation.executorKind !== "local-af-backtest") ||
      record.fallbackEvaluation.executorAuthoritative ||
      record.fallbackEvaluation.promotionEligible ||
      record.fallbackEvaluation.evidenceUse !== "mutation_context_only"
    ) {
      pushIssue(issues, {
        severity: "error",
        scope: "fallback-semantics",
        recordId: record.candidateId,
        message: "Fallback evidence metadata violates the non-authoritative fallback contract.",
      });
    }
    if (
      record.fallbackEvaluation.status === "succeeded" &&
      (!record.fallbackEvaluation.artifactHash ||
        !record.artifactPaths?.fallbackEvidenceArtifact)
    ) {
      pushIssue(issues, {
        severity: "error",
        scope: "fallback-semantics",
        recordId: record.candidateId,
        message: "Successful fallback evidence must persist an artifact hash and artifact path.",
      });
    }
  }

  return issues;
}

function validateVerifiedViewClaims(
  records: ExperimentRecord[],
): LedgerValidationIssue[] {
  const issues: LedgerValidationIssue[] = [];
  const context = buildEligibilityContext(records);

  for (const record of records) {
    if (!claimsVerifiedView(record)) {
      continue;
    }

    const eligibility = claimsPromotedHead(record)
      ? evaluatePromotedHeadEligibility(record, context)
      : evaluateVerifiedViewEligibility(record);
    for (const issue of eligibility.issues) {
      if (issue.severity !== "error") {
        continue;
      }
      pushIssue(issues, {
        severity: "error",
        scope: "verified-view-contract",
        recordId: record.candidateId,
        message: issue.message,
      });
    }
  }

  return issues;
}

function validatePromotionContract(
  records: ExperimentRecord[],
): LedgerValidationIssue[] {
  const issues: LedgerValidationIssue[] = [];
  const context = buildEligibilityContext(records);

  for (const record of records) {
    const eligibility = claimsPromotedHead(record)
      ? evaluatePromotedHeadEligibility(record, context)
      : claimsPromotion(record)
        ? evaluatePromotionEligibility(record)
        : null;
    if (!eligibility) {
      continue;
    }
    for (const issue of eligibility.issues) {
      if (issue.severity !== "error") {
        continue;
      }
      pushIssue(issues, {
        severity: "error",
        scope: "promotion-contract",
        recordId: record.candidateId,
        message: issue.message,
      });
    }
  }

  return issues;
}
