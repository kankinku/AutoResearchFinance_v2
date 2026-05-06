import {
  copyFile,
  open,
  rename,
  stat,
  unlink,
} from "node:fs/promises";
import path from "node:path";

import {
  candidateLedgerRecordSchema,
  experimentRecordSchema,
  incidentRecordSchema,
  mutationBriefRecordSchema,
  researchKnowledgeRecordSchema,
  runRecordSchema,
  taskBatchRecordSchema,
  taskRecordSchema,
  type ArtifactBundle,
  type CompactEquitySummary,
  type CompactTradeSummary,
  autonomousIterationLearningRecordSchema,
  type AutonomousIterationLearningRecord,
  type CandidateLedgerRecord,
  type ExperimentRecord,
  type ExperimentArtifactPaths,
  type ArtifactBundleRef,
  type ArtifactSummary,
  type IncidentRecord,
  type MutationBriefRecord,
  type RecordMeta,
  type ResearchKnowledgeRecord,
  type RunRecord,
  type TaskBatchRecord,
  type TaskRecord,
} from "../contracts/types.js";
import {
  archiveEventRecordSchema,
  calibrationEventRecordSchema,
  headEventRecordSchema,
  localConfidenceEventRecordSchema,
  autonomousBranchRecordSchema,
  type ArchiveEventRecord,
  type AutonomousBranchRecord,
  type CalibrationEventRecord,
  type HeadEventRecord,
  type LocalConfidenceEventRecord,
  problemEventRecordSchema,
  repairAttemptRecordSchema,
  type ProblemEventRecord,
  type RepairAttemptRecord,
} from "../contracts/autonomous.js";
import {
  appendJsonlAtomic,
  ensureDir,
  fileExists,
  readJsonl,
  readJsonlStream,
  readJsonlTail,
  sha256Json,
  writeJson,
} from "../utils/fs.js";
import { resolveKnowledgePaths } from "./knowledge-paths.js";

const PIPELINE_VERSION = "af-research-pipeline/v2";

export function resolveStatePaths(stateRoot: string): {
  experimentsPath: string;
  incidentsPath: string;
  runsPath: string;
  taskBatchesPath: string;
  tasksPath: string;
  mutationBriefsPath: string;
  autonomousIterationRecordsPath: string;
  candidatesPath: string;
  researchKnowledgePath: string;
  headEventsPath: string;
  archiveEventsPath: string;
  calibrationEventsPath: string;
  localConfidenceEventsPath: string;
  problemEventsPath: string;
  repairAttemptsPath: string;
  branchesPath: string;
  leaderboardPath: string;
  lineagePath: string;
  frontierPath: string;
  failureSummaryPath: string;
  taskBoardPath: string;
  verificationFailuresPath: string;
  fallbackEvidenceBoardPath: string;
  screeningBoardPath: string;
  invalidRecordsPath: string;
  runtimeFailureSummaryPath: string;
  localTvDivergenceSummaryPath: string;
  verificationQueuePath: string;
  lossPatternSummaryPath: string;
  researchSummaryPath: string;
  localLeaderboardPath: string;
  championHistoryPath: string;
  explorationArchivePath: string;
  noveltyFrontierPath: string;
  robustnessFrontierPath: string;
  tvSurfaceFailuresPath: string;
  tvCalibrationQueuePath: string;
  localTvDivergencePath: string;
  autoSelectionDecisionsPath: string;
  duplicateCandidatesPath: string;
  localCompatibilitySummaryPath: string;
  autonomousStateSummaryPath: string;
  stage6ReadinessPath: string;
  localConfidenceSummaryPath: string;
  failureMemoryPath: string;
} {
  const knowledgePaths = resolveKnowledgePaths(stateRoot);
  return {
    experimentsPath: knowledgePaths.experimentsPath,
    incidentsPath: knowledgePaths.incidentsPath,
    runsPath: knowledgePaths.runsPath,
    taskBatchesPath: knowledgePaths.taskBatchesPath,
    tasksPath: knowledgePaths.tasksPath,
    mutationBriefsPath: knowledgePaths.mutationBriefsPath,
    autonomousIterationRecordsPath: knowledgePaths.autonomousIterationRecordsPath,
    candidatesPath: knowledgePaths.candidatesPath,
    researchKnowledgePath: knowledgePaths.researchKnowledgePath,
    headEventsPath: knowledgePaths.headEventsPath,
    archiveEventsPath: knowledgePaths.archiveEventsPath,
    calibrationEventsPath: knowledgePaths.calibrationEventsPath,
    localConfidenceEventsPath: knowledgePaths.localConfidenceEventsPath,
    problemEventsPath: knowledgePaths.problemEventsPath,
    repairAttemptsPath: knowledgePaths.repairAttemptsPath,
    branchesPath: knowledgePaths.branchesPath,
    leaderboardPath: knowledgePaths.leaderboardPath,
    lineagePath: knowledgePaths.lineagePath,
    frontierPath: knowledgePaths.frontierPath,
    failureSummaryPath: knowledgePaths.failureSummaryPath,
    taskBoardPath: knowledgePaths.taskBoardPath,
    verificationFailuresPath: knowledgePaths.verificationFailuresPath,
    fallbackEvidenceBoardPath: knowledgePaths.fallbackEvidenceBoardPath,
    screeningBoardPath: knowledgePaths.screeningBoardPath,
    invalidRecordsPath: knowledgePaths.invalidRecordsPath,
    runtimeFailureSummaryPath: knowledgePaths.runtimeFailureSummaryPath,
    localTvDivergenceSummaryPath: knowledgePaths.localTvDivergenceSummaryPath,
    verificationQueuePath: knowledgePaths.verificationQueuePath,
    lossPatternSummaryPath: knowledgePaths.lossPatternSummaryPath,
    researchSummaryPath: knowledgePaths.researchSummaryPath,
    localLeaderboardPath: knowledgePaths.localLeaderboardPath,
    championHistoryPath: knowledgePaths.championHistoryPath,
    explorationArchivePath: knowledgePaths.explorationArchivePath,
    noveltyFrontierPath: knowledgePaths.noveltyFrontierPath,
    robustnessFrontierPath: knowledgePaths.robustnessFrontierPath,
    tvSurfaceFailuresPath: knowledgePaths.tvSurfaceFailuresPath,
    tvCalibrationQueuePath: knowledgePaths.tvCalibrationQueuePath,
    localTvDivergencePath: knowledgePaths.localTvDivergencePath,
    autoSelectionDecisionsPath: knowledgePaths.autoSelectionDecisionsPath,
    duplicateCandidatesPath: knowledgePaths.duplicateCandidatesPath,
    localCompatibilitySummaryPath: knowledgePaths.localCompatibilitySummaryPath,
    autonomousStateSummaryPath: knowledgePaths.autonomousStateSummaryPath,
    stage6ReadinessPath: knowledgePaths.stage6ReadinessPath,
    localConfidenceSummaryPath: knowledgePaths.localConfidenceSummaryPath,
    failureMemoryPath: knowledgePaths.failureMemoryPath,
  };
}

export async function ensureStateRoot(stateRoot: string): Promise<void> {
  const knowledgePaths = resolveKnowledgePaths(stateRoot);
  await ensureDir(knowledgePaths.root);
  await ensureDir(knowledgePaths.policyDir);
  await ensureDir(knowledgePaths.evidenceDir);
  await ensureDir(knowledgePaths.artifactDir);
  await ensureDir(knowledgePaths.ledgerDir);
  await ensureDir(knowledgePaths.viewsDir);
  await ensureDir(knowledgePaths.taxonomyDir);
  await ensureDir(knowledgePaths.runtimeDir);
  await ensureDir(knowledgePaths.tracesDir);
  await ensureDir(knowledgePaths.desktopRunsDir);
  await ensureDir(knowledgePaths.resultsDir);
  await ensureDir(knowledgePaths.researchDir);
}

interface ExperimentStorageOptions {
  writeArtifacts: boolean;
}

export interface ExperimentLedgerCompactionResult {
  dryRun: boolean;
  backupPath: string | null;
  originalBytes: number;
  compactedBytes: number;
  recordsRead: number;
  recordsWritten: number;
  artifactBundlesStripped: number;
  artifactRefsAdded: number;
  artifactBundlesWritten: number;
}

export async function compactExperimentLedger(
  stateRoot: string,
  options: {
    backup?: boolean;
    dryRun?: boolean;
  } = {},
): Promise<ExperimentLedgerCompactionResult> {
  await ensureStateRoot(stateRoot);
  const paths = resolveKnowledgePaths(stateRoot);
  const dryRun = options.dryRun ?? false;
  if (!(await fileExists(paths.experimentsPath))) {
    return {
      dryRun,
      backupPath: null,
      originalBytes: 0,
      compactedBytes: 0,
      recordsRead: 0,
      recordsWritten: 0,
      artifactBundlesStripped: 0,
      artifactRefsAdded: 0,
      artifactBundlesWritten: 0,
    };
  }

  const originalBytes = (await stat(paths.experimentsPath)).size;
  const backupPath =
    options.backup && !dryRun
      ? path.join(
          paths.ledgerDir,
          `experiments.pre-compact-${compactTimestamp()}.jsonl`,
        )
      : null;
  const tempPath = path.join(
    paths.ledgerDir,
    `experiments.compact-${process.pid}-${Date.now()}.jsonl.tmp`,
  );
  const input = await open(paths.experimentsPath, "r");
  const output = dryRun ? null : await open(tempPath, "w");
  let compactedBytes = 0;
  let recordsRead = 0;
  let recordsWritten = 0;
  let artifactBundlesStripped = 0;
  let artifactRefsAdded = 0;
  let artifactBundlesWritten = 0;

  try {
    const stream = input.createReadStream({ encoding: "utf8" });
    const lines = (await import("node:readline")).createInterface({
      input: stream,
      crlfDelay: Infinity,
    });

    for await (const rawLine of lines) {
      const trimmedLine = rawLine.trim();
      if (!trimmedLine) {
        continue;
      }

      recordsRead += 1;
      let parsed: unknown;
      try {
        parsed = JSON.parse(trimmedLine);
      } catch (error) {
        throw new Error(
          `Cannot compact experiments.jsonl line ${recordsRead}: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }

      const hadBundle =
        typeof parsed === "object" &&
        parsed !== null &&
        "artifactBundle" in parsed &&
        (parsed as { artifactBundle?: unknown }).artifactBundle != null;
      const hadRef =
        typeof parsed === "object" &&
        parsed !== null &&
        "artifactBundleRef" in parsed &&
        (parsed as { artifactBundleRef?: unknown }).artifactBundleRef != null;
      const normalized = await normalizeExperimentRecordForStorage(
        stateRoot,
        parsed as Omit<ExperimentRecord, "recordedAt"> & { recordedAt?: string },
        { writeArtifacts: !dryRun },
      );
      const line = `${JSON.stringify(normalized)}\n`;
      compactedBytes += Buffer.byteLength(line, "utf8");
      recordsWritten += 1;
      if (hadBundle && !normalized.artifactBundle) {
        artifactBundlesStripped += 1;
      }
      if (!hadRef && normalized.artifactBundleRef) {
        artifactRefsAdded += 1;
      }
      if (
        normalized.artifactBundleRef?.path &&
        !hadRef &&
        !(normalized.artifactPaths?.backtestArtifact === normalized.artifactBundleRef.path)
      ) {
        artifactBundlesWritten += 1;
      }
      await output?.writeFile(line, "utf8");
    }
  } finally {
    await input.close();
    await output?.close();
  }

  if (dryRun) {
    return {
      dryRun,
      backupPath: null,
      originalBytes,
      compactedBytes,
      recordsRead,
      recordsWritten,
      artifactBundlesStripped,
      artifactRefsAdded,
      artifactBundlesWritten,
    };
  }

  if (backupPath) {
    await copyFile(paths.experimentsPath, backupPath);
  }
  await rename(tempPath, paths.experimentsPath);

  return {
    dryRun,
    backupPath,
    originalBytes,
    compactedBytes,
    recordsRead,
    recordsWritten,
    artifactBundlesStripped,
    artifactRefsAdded,
    artifactBundlesWritten,
  };
}

async function normalizeExperimentRecordForStorage(
  stateRoot: string,
  record: Omit<ExperimentRecord, "recordedAt"> & { recordedAt?: string },
  options: ExperimentStorageOptions,
): Promise<ExperimentRecord> {
  const compacted = await compactExperimentRecordForStorage(
    stateRoot,
    record,
    options,
  );
  const existingRecordMeta =
    compacted.recordMeta as Partial<RecordMeta> | undefined;
  const parsedWithPlaceholderMeta = experimentRecordSchema.parse({
    ...compacted,
    recordMeta: {
      ...buildRecordMetaBase(
        existingRecordMeta?.schemaVersion ?? "experiment/v2",
        existingRecordMeta,
      ),
      recordHash: "__pending_record_hash__",
    },
  });
  return experimentRecordSchema.parse({
    ...parsedWithPlaceholderMeta,
    recordMeta: {
      ...parsedWithPlaceholderMeta.recordMeta,
      recordHash: computeCanonicalRecordHash(
        parsedWithPlaceholderMeta as unknown as Record<string, unknown>,
        parsedWithPlaceholderMeta.recordMeta,
      ),
    },
  });
}

async function compactExperimentRecordForStorage(
  stateRoot: string,
  record: Omit<ExperimentRecord, "recordedAt"> & { recordedAt?: string },
  options: ExperimentStorageOptions,
): Promise<Omit<ExperimentRecord, "recordedAt"> & { recordedAt?: string }> {
  const artifactBundle = (record as { artifactBundle?: ArtifactBundle }).artifactBundle;
  if (!artifactBundle) {
    const artifactBundleRef = (record as { artifactBundleRef?: ArtifactBundleRef })
      .artifactBundleRef;
    if (artifactBundleRef?.path) {
      return {
        ...record,
        artifactPaths: buildArtifactPathsForBundleRef(
          record.artifactPaths as ExperimentArtifactPaths | undefined,
          artifactBundleRef.path,
        ),
      };
    }
    return record;
  }

  const artifactBundleHash = sha256Json(artifactBundle);
  const artifactBundleRef = await resolveArtifactBundleRef({
    stateRoot,
    record,
    artifactBundle,
    artifactBundleHash,
    writeArtifacts: options.writeArtifacts,
  });
  const artifactPaths = buildArtifactPathsForBundleRef(
    record.artifactPaths as ExperimentArtifactPaths | undefined,
    artifactBundleRef.path,
  );
  const recordMeta = {
    ...(record.recordMeta ?? {}),
    schemaVersion: "experiment/v4",
    artifactBundleHash,
  };
  const compacted: Record<string, unknown> = {
    ...record,
    artifactBundle: undefined,
    artifactBundleRef,
    artifactBundleHash,
    artifactSummary: buildArtifactSummary(artifactBundle),
    tradeSummary: buildCompactTradeSummary(artifactBundle),
    equitySummary: buildCompactEquitySummary(artifactBundle),
    splitEvaluation: compactSplitEvaluation(
      (record as Record<string, unknown>).splitEvaluation,
    ),
    testerMetrics: record.testerMetrics ?? artifactBundle.strategy ?? undefined,
    artifactPaths,
    recordMeta,
  };

  if (!compacted.recordEra) {
    compacted.recordEra = inferRecordEraForCompactRecord(record);
  }

  delete compacted.artifactBundle;
  return compacted as Omit<ExperimentRecord, "recordedAt"> & { recordedAt?: string };
}

function buildArtifactPathsForBundleRef(
  artifactPaths: ExperimentArtifactPaths | undefined,
  artifactBundlePath: string,
): ExperimentArtifactPaths {
  const existingArtifactPaths = artifactPaths ?? {};
  const existingBacktestArtifact = existingArtifactPaths.backtestArtifact;
  const normalizedArtifactPaths: ExperimentArtifactPaths = {
    ...existingArtifactPaths,
    backtestArtifact: artifactBundlePath,
    artifactBundle: artifactBundlePath,
  };
  if (existingBacktestArtifact && existingBacktestArtifact !== artifactBundlePath) {
    normalizedArtifactPaths.localBacktestArtifact =
      existingArtifactPaths.localBacktestArtifact ?? existingBacktestArtifact;
  }
  return normalizedArtifactPaths;
}

async function resolveArtifactBundleRef(input: {
  stateRoot: string;
  record: Omit<ExperimentRecord, "recordedAt"> & { recordedAt?: string };
  artifactBundle: ArtifactBundle;
  artifactBundleHash: string;
  writeArtifacts: boolean;
}): Promise<ArtifactBundleRef> {
  const artifactPaths = input.record.artifactPaths as
    | Record<string, string>
    | undefined;
  const existingPath = artifactPaths?.backtestArtifact;
  if (
    existingPath &&
    (await fileExists(existingPath)) &&
    (await artifactFileMatchesHash(existingPath, input.artifactBundleHash))
  ) {
    return {
      path: existingPath,
      hash: input.artifactBundleHash,
      storage: "file",
      schemaVersion: "artifact-bundle/v1",
    };
  }

  const paths = resolveKnowledgePaths(input.stateRoot);
  const artifactDir = path.join(paths.artifactDir, "experiment-bundles");
  const candidateId =
    typeof input.record.candidateId === "string"
      ? input.record.candidateId
      : "unknown";
  const safeCandidateId = sanitizePathPart(candidateId);
  const iteration =
    typeof input.record.iteration === "number" ? input.record.iteration : "unknown";
  const artifactPath = path.join(
    artifactDir,
    `${iteration}-${safeCandidateId}-${input.artifactBundleHash.slice(0, 12)}.json`,
  );

  if (input.writeArtifacts && !(await fileExists(artifactPath))) {
    await writeJson(artifactPath, input.artifactBundle);
  }

  return {
    path: artifactPath,
    hash: input.artifactBundleHash,
    storage: "file",
    schemaVersion: "artifact-bundle/v1",
  };
}

async function artifactFileMatchesHash(
  filePath: string,
  expectedHash: string,
): Promise<boolean> {
  let handle: Awaited<ReturnType<typeof open>> | null = null;
  try {
    handle = await open(filePath, "r");
    const raw = await handle.readFile("utf8");
    return sha256Json(JSON.parse(raw)) === expectedHash;
  } catch {
    return false;
  } finally {
    await handle?.close();
  }
}

function buildArtifactSummary(artifactBundle: ArtifactBundle): ArtifactSummary {
  return {
    strategy: artifactBundle.strategy ?? null,
    tradeCount: artifactBundle.trades.length,
    equityPointCount:
      artifactBundle.equity.pointCount || artifactBundle.equity.points.length,
    rawReportHash: artifactBundle.rawReportHash ?? null,
    hasAttachDiagnostics: artifactBundle.attachDiagnostics != null,
    stateKeys: Object.keys(artifactBundle.state ?? {}).slice(0, 30),
  };
}

function buildCompactTradeSummary(
  artifactBundle: ArtifactBundle,
): CompactTradeSummary {
  const trades = artifactBundle.trades;
  return {
    totalTrades: trades.length,
    firstEntryTime: trades.find((trade) => trade.entryTime)?.entryTime ?? null,
    lastExitTime:
      [...trades].reverse().find((trade) => trade.exitTime)?.exitTime ?? null,
    winningTrades: trades.filter((trade) => (trade.profitPercent ?? 0) > 0).length,
    losingTrades: trades.filter((trade) => (trade.profitPercent ?? 0) < 0).length,
  };
}

function buildCompactEquitySummary(
  artifactBundle: ArtifactBundle,
): CompactEquitySummary {
  const equity = artifactBundle.equity;
  const firstPoint = equity.points[0] ?? null;
  const lastPoint = equity.points.at(-1) ?? null;
  return {
    available: equity.available,
    unavailableReason: equity.unavailableReason ?? null,
    pointsAvailable: equity.pointsAvailable,
    pointCount: equity.pointCount || equity.points.length,
    finalEquity: equity.finalEquity ?? null,
    maxDrawdownPercent: equity.maxDrawdownPercent ?? null,
    firstPointTime: firstPoint?.time ?? null,
    lastPointTime: lastPoint?.time ?? null,
  };
}

function compactSplitEvaluation(splitEvaluation: unknown): unknown {
  if (!isRecord(splitEvaluation)) {
    return splitEvaluation;
  }

  return {
    ...splitEvaluation,
    fullSample: compactSplitMetrics(splitEvaluation.fullSample),
    inSample: compactSplitMetrics(splitEvaluation.inSample),
    outOfSample: compactSplitMetrics(splitEvaluation.outOfSample),
  };
}

function compactSplitMetrics(splitMetrics: unknown): unknown {
  if (!isRecord(splitMetrics)) {
    return splitMetrics;
  }

  return {
    ...splitMetrics,
    trades: [],
    equity: compactSplitEquity(splitMetrics.equity),
  };
}

function compactSplitEquity(equity: unknown): unknown {
  if (!isRecord(equity)) {
    return equity;
  }

  return {
    ...equity,
    points: [],
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function inferRecordEraForCompactRecord(
  record: Omit<ExperimentRecord, "recordedAt"> & { recordedAt?: string },
): "legacy" | "v2" | "v3" {
  const existingEra = (record as { recordEra?: unknown }).recordEra;
  if (existingEra === "legacy" || existingEra === "v2" || existingEra === "v3") {
    return existingEra;
  }
  if ((record as Record<string, unknown>).recordKind) {
    return "v3";
  }
  const recordMeta = record.recordMeta as Partial<RecordMeta> | undefined;
  if (recordMeta?.schemaVersion?.endsWith("/v3")) {
    return "v3";
  }
  const decision = typeof record.decision === "string" ? record.decision : "";
  if (decision.startsWith("accepted_")) {
    return "legacy";
  }
  return "v2";
}

function sanitizePathPart(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 120) || "unknown";
}

function compactTimestamp(): string {
  return new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
}

export async function appendExperimentRecord(
  stateRoot: string,
  record: Omit<ExperimentRecord, "recordedAt"> & { recordedAt?: string },
): Promise<ExperimentRecord> {
  await ensureStateRoot(stateRoot);
  const timestampedRecord = {
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  };
  const normalized = await normalizeExperimentRecordForStorage(
    stateRoot,
    timestampedRecord,
    { writeArtifacts: true },
  );
  await appendJsonlAtomic(resolveStatePaths(stateRoot).experimentsPath, normalized);
  return normalized;
}

export async function appendIncidentRecord(
  stateRoot: string,
  record: Omit<IncidentRecord, "recordedAt"> & { recordedAt?: string },
): Promise<IncidentRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = incidentRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).incidentsPath, normalized);
  return normalized;
}

export async function appendRunRecord(
  stateRoot: string,
  record: RunRecord,
): Promise<RunRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = runRecordSchema.parse(record);
  await appendJsonlAtomic(resolveStatePaths(stateRoot).runsPath, normalized);
  return normalized;
}

export async function appendMutationBriefRecord(
  stateRoot: string,
  record: Omit<MutationBriefRecord, "recordedAt"> & { recordedAt?: string },
): Promise<MutationBriefRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = mutationBriefRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).mutationBriefsPath, normalized);
  return normalized;
}

export async function appendAutonomousIterationRecord(
  stateRoot: string,
  record: Omit<AutonomousIterationLearningRecord, "recordedAt"> & {
    recordedAt?: string;
  },
): Promise<AutonomousIterationLearningRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = autonomousIterationLearningRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(
    resolveStatePaths(stateRoot).autonomousIterationRecordsPath,
    normalized,
  );
  return normalized;
}

export async function appendTaskBatchRecord(
  stateRoot: string,
  record: Omit<TaskBatchRecord, "recordedAt"> & { recordedAt?: string },
): Promise<TaskBatchRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = taskBatchRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).taskBatchesPath, normalized);
  return normalized;
}

export async function appendTaskRecord(
  stateRoot: string,
  record: Omit<TaskRecord, "recordedAt"> & { recordedAt?: string },
): Promise<TaskRecord> {
  await ensureStateRoot(stateRoot);
  const timestampedRecord = {
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  };
  const parsedWithPlaceholderMeta = taskRecordSchema.parse({
    ...timestampedRecord,
    recordMeta: {
      ...buildRecordMetaBase(
        "task/v2",
        record.recordMeta as Partial<RecordMeta> | undefined,
      ),
      recordHash: "__pending_record_hash__",
    },
  });
  const normalized = taskRecordSchema.parse({
    ...parsedWithPlaceholderMeta,
    recordMeta: {
      ...parsedWithPlaceholderMeta.recordMeta,
      recordHash: computeCanonicalRecordHash(
        parsedWithPlaceholderMeta as unknown as Record<string, unknown>,
        parsedWithPlaceholderMeta.recordMeta,
      ),
    },
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).tasksPath, normalized);
  return normalized;
}

export async function appendCandidateLedgerRecord(
  stateRoot: string,
  record: Omit<CandidateLedgerRecord, "recordedAt"> & { recordedAt?: string },
): Promise<CandidateLedgerRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = candidateLedgerRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).candidatesPath, normalized);
  return normalized;
}

export async function appendResearchKnowledgeRecord(
  stateRoot: string,
  record: Omit<ResearchKnowledgeRecord, "recordedAt"> & { recordedAt?: string },
): Promise<ResearchKnowledgeRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = researchKnowledgeRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).researchKnowledgePath, normalized);
  return normalized;
}

export async function appendHeadEventRecord(
  stateRoot: string,
  record: Omit<HeadEventRecord, "recordedAt"> & { recordedAt?: string },
): Promise<HeadEventRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = headEventRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).headEventsPath, normalized);
  return normalized;
}

export async function appendArchiveEventRecord(
  stateRoot: string,
  record: Omit<ArchiveEventRecord, "recordedAt"> & { recordedAt?: string },
): Promise<ArchiveEventRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = archiveEventRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).archiveEventsPath, normalized);
  return normalized;
}

export async function appendCalibrationEventRecord(
  stateRoot: string,
  record: Omit<CalibrationEventRecord, "recordedAt"> & { recordedAt?: string },
): Promise<CalibrationEventRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = calibrationEventRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).calibrationEventsPath, normalized);
  return normalized;
}

export async function appendLocalConfidenceEventRecord(
  stateRoot: string,
  record: Omit<LocalConfidenceEventRecord, "recordedAt"> & { recordedAt?: string },
): Promise<LocalConfidenceEventRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = localConfidenceEventRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).localConfidenceEventsPath, normalized);
  return normalized;
}

export async function appendProblemEventRecord(
  stateRoot: string,
  record: Omit<ProblemEventRecord, "recordedAt"> & { recordedAt?: string },
): Promise<ProblemEventRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = problemEventRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).problemEventsPath, normalized);
  return normalized;
}

export async function appendRepairAttemptRecord(
  stateRoot: string,
  record: Omit<RepairAttemptRecord, "recordedAt"> & { recordedAt?: string },
): Promise<RepairAttemptRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = repairAttemptRecordSchema.parse({
    ...record,
    recordedAt: record.recordedAt ?? new Date().toISOString(),
  });
  await appendJsonlAtomic(resolveStatePaths(stateRoot).repairAttemptsPath, normalized);
  return normalized;
}

export async function appendAutonomousBranchRecord(
  stateRoot: string,
  record: AutonomousBranchRecord,
): Promise<AutonomousBranchRecord> {
  await ensureStateRoot(stateRoot);
  const normalized = autonomousBranchRecordSchema.parse(record);
  await appendJsonlAtomic(resolveStatePaths(stateRoot).branchesPath, normalized);
  return normalized;
}

export async function readExperimentRecords(stateRoot: string): Promise<ExperimentRecord[]> {
  await ensureStateRoot(stateRoot);
  return readJsonlStream<ExperimentRecord>(
    resolveStatePaths(stateRoot).experimentsPath,
    (parsed) => {
      const validated = experimentRecordSchema.safeParse(parsed);
      return validated.success
        ? { success: true, record: validated.data }
        : {
            success: false,
            message: validated.error.issues
              .map((issue) => `${issue.path.join(".") || "<root>"}: ${issue.message}`)
              .join("; "),
          };
    },
  );
}

export async function readRecentExperimentRecords(
  stateRoot: string,
  maxRecords = 100,
  maxBytes = 16 * 1024 * 1024,
): Promise<ExperimentRecord[]> {
  await ensureStateRoot(stateRoot);
  return readJsonlTail<ExperimentRecord>(
    resolveStatePaths(stateRoot).experimentsPath,
    maxRecords,
    maxBytes,
  ).then((records) => records.map((record) => experimentRecordSchema.parse(record)));
}

export async function readIncidentRecords(stateRoot: string): Promise<IncidentRecord[]> {
  await ensureStateRoot(stateRoot);
  return readJsonl<IncidentRecord>(resolveStatePaths(stateRoot).incidentsPath);
}

export async function readTaskBatchRecords(stateRoot: string): Promise<TaskBatchRecord[]> {
  await ensureStateRoot(stateRoot);
  return readJsonl<TaskBatchRecord>(resolveStatePaths(stateRoot).taskBatchesPath);
}

export async function readTaskRecords(stateRoot: string): Promise<TaskRecord[]> {
  await ensureStateRoot(stateRoot);
  return readJsonl<TaskRecord>(resolveStatePaths(stateRoot).tasksPath);
}

export async function readMutationBriefRecords(
  stateRoot: string,
): Promise<MutationBriefRecord[]> {
  await ensureStateRoot(stateRoot);
  const records = await readJsonl<unknown>(
    resolveStatePaths(stateRoot).mutationBriefsPath,
  );
  return records.flatMap((record) => {
    const parsed = mutationBriefRecordSchema.safeParse(record);
    return parsed.success ? [parsed.data] : [];
  });
}

export async function readAutonomousIterationRecords(
  stateRoot: string,
): Promise<AutonomousIterationLearningRecord[]> {
  await ensureStateRoot(stateRoot);
  const records = await readJsonl<unknown>(
    resolveStatePaths(stateRoot).autonomousIterationRecordsPath,
  );
  return records.flatMap((record) => {
    const parsed = autonomousIterationLearningRecordSchema.safeParse(record);
    return parsed.success ? [parsed.data] : [];
  });
}

export async function readRecentAutonomousIterationRecords(
  stateRoot: string,
  maxRecords = 80,
  maxBytes = 2 * 1024 * 1024,
): Promise<AutonomousIterationLearningRecord[]> {
  await ensureStateRoot(stateRoot);
  const records = await readJsonlTail<unknown>(
    resolveStatePaths(stateRoot).autonomousIterationRecordsPath,
    maxRecords,
    maxBytes,
  );
  return records.flatMap((record) => {
    const parsed = autonomousIterationLearningRecordSchema.safeParse(record);
    return parsed.success ? [parsed.data] : [];
  });
}

export async function readCandidateLedgerRecords(
  stateRoot: string,
): Promise<CandidateLedgerRecord[]> {
  await ensureStateRoot(stateRoot);
  return readJsonl<CandidateLedgerRecord>(resolveStatePaths(stateRoot).candidatesPath);
}

export async function readResearchKnowledgeRecords(
  stateRoot: string,
): Promise<ResearchKnowledgeRecord[]> {
  await ensureStateRoot(stateRoot);
  return readJsonl<ResearchKnowledgeRecord>(resolveStatePaths(stateRoot).researchKnowledgePath);
}

export async function readHeadEventRecords(stateRoot: string): Promise<HeadEventRecord[]> {
  await ensureStateRoot(stateRoot);
  return readTypedJsonl(
    resolveStatePaths(stateRoot).headEventsPath,
    headEventRecordSchema,
  );
}

export async function readArchiveEventRecords(
  stateRoot: string,
): Promise<ArchiveEventRecord[]> {
  await ensureStateRoot(stateRoot);
  return readTypedJsonl(
    resolveStatePaths(stateRoot).archiveEventsPath,
    archiveEventRecordSchema,
  );
}

export async function readCalibrationEventRecords(
  stateRoot: string,
): Promise<CalibrationEventRecord[]> {
  await ensureStateRoot(stateRoot);
  return readTypedJsonl(
    resolveStatePaths(stateRoot).calibrationEventsPath,
      calibrationEventRecordSchema,
    );
}

export async function readLocalConfidenceEventRecords(
  stateRoot: string,
): Promise<LocalConfidenceEventRecord[]> {
  await ensureStateRoot(stateRoot);
  return readTypedJsonl(
    resolveStatePaths(stateRoot).localConfidenceEventsPath,
    localConfidenceEventRecordSchema,
  );
}

export async function readProblemEventRecords(
  stateRoot: string,
): Promise<ProblemEventRecord[]> {
  await ensureStateRoot(stateRoot);
  return readTypedJsonl(
    resolveStatePaths(stateRoot).problemEventsPath,
    problemEventRecordSchema,
  );
}

export async function readRepairAttemptRecords(
  stateRoot: string,
): Promise<RepairAttemptRecord[]> {
  await ensureStateRoot(stateRoot);
  return readTypedJsonl(
    resolveStatePaths(stateRoot).repairAttemptsPath,
    repairAttemptRecordSchema,
  );
}

export async function readAutonomousBranchRecords(
  stateRoot: string,
): Promise<AutonomousBranchRecord[]> {
  await ensureStateRoot(stateRoot);
  return readTypedJsonl(
    resolveStatePaths(stateRoot).branchesPath,
    autonomousBranchRecordSchema,
  );
}

async function readTypedJsonl<T>(
  filePath: string,
  schema: { parse: (value: unknown) => T },
): Promise<T[]> {
  const records = await readJsonl<unknown>(filePath);
  return records.map((record) => schema.parse(record));
}

function buildRecordMeta(
  schemaVersion: string,
  record: Record<string, unknown>,
  existing?: Partial<RecordMeta>,
): RecordMeta {
  const baseMeta = buildRecordMetaBase(schemaVersion, existing);
  const recordHash = computeCanonicalRecordHash(record, baseMeta);

  return {
    ...baseMeta,
    recordHash,
  };
}

function buildRecordMetaBase(
  schemaVersion: string,
  existing?: Partial<RecordMeta>,
): Omit<RecordMeta, "recordHash"> {
  return {
    schemaVersion,
    candidateHash: null,
    baselineHash: null,
    artifactBundleHash: null,
    promotedFromRunId: null,
    promotedFromIteration: null,
    promotedFromRecordHash: null,
    pipelineVersion: PIPELINE_VERSION,
    ...existing,
  };
}

export function computeCanonicalRecordHash(
  record: Record<string, unknown>,
  recordMeta?: Partial<RecordMeta>,
): string {
  return sha256Json({
    ...record,
    recordMeta: {
      schemaVersion: null,
      candidateHash: null,
      baselineHash: null,
      artifactBundleHash: null,
      promotedFromRunId: null,
      promotedFromIteration: null,
      promotedFromRecordHash: null,
      pipelineVersion: null,
      ...recordMeta,
      recordHash: undefined,
    },
  });
}
