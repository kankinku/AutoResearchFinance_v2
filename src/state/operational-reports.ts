import { readdir, readFile, rm, stat } from "node:fs/promises";
import path from "node:path";

import { type ExperimentRecord } from "../contracts/types.js";
import { fileExists, readJson, writeJson } from "../utils/fs.js";
import {
  readExperimentRecords,
  readIncidentRecords,
  resolveStatePaths,
} from "./jsonl-store.js";
import { resolveKnowledgePaths } from "./knowledge-paths.js";
import { type RetentionClass } from "./ledger-validator.js";

export interface CompactArtifactSummary {
  candidateId: string;
  generatedAt: string | null;
  strategySummary: string | null;
  params: Record<string, unknown> | null;
  score: number | null;
  metric: Record<string, unknown> | null;
  failureReason: string | null;
  originalHash: string | null;
  originalSizeBytes: number;
  retentionReason: string;
}

export interface ArtifactRetentionReportEntry {
  candidateId: string;
  artifactPath: string;
  sizeBytes: number;
  retentionClass: RetentionClass;
  reason: string;
  compactArtifact: CompactArtifactSummary;
}

export interface ArtifactRetentionReport {
  generatedAt: string;
  stateRoot: string;
  entries: ArtifactRetentionReportEntry[];
  summary: {
    totalArtifacts: number;
    totalSizeBytes: number;
    byRetentionClass: Record<RetentionClass, { count: number; sizeBytes: number }>;
  };
}

export interface RuntimeCleanupReport {
  generatedAt: string;
  stateRoot: string;
  runtimeRoot: string;
  target: "tradingview-cache";
  dryRun: boolean;
  deletedCount: number;
  deletedBytes: number;
  candidates: Array<{
    path: string;
    sizeBytes: number;
    action: "delete_candidate" | "manual_review";
    reason: string;
    deleted: boolean;
  }>;
}

export interface SystemHealthReport {
  generatedAt: string;
  stateRoot: string;
  currentTrainingMode: Record<string, unknown> | null;
  sizes: {
    ledgerBytes: number;
    artifactBytes: number;
    runtimeBytes: number;
    totalStateBytes: number;
  };
  ledgers: {
    experiments: number;
    candidates: number;
    artifactRefs: number;
    strategyReviews: number;
    strategyReviewFailures: number;
    strategyReviewParseFailures: number;
  };
  heartbeat: {
    status: "missing" | "ok" | "stale" | "read_error";
    path: string;
    payload: Record<string, unknown> | null;
    error: string | null;
  };
  latestTrace: {
    path: string | null;
    command: string | null;
    longestPhase: { phase: string; durationMs: number } | null;
    schemaFailures: number;
  };
  index: {
    manifestPath: string;
    mode: string | null;
    lastUpdatedAt: string | null;
    fallbackReason: string | null;
  };
}

const RETENTION_CLASS_ORDER: RetentionClass[] = [
  "full",
  "compact",
  "latest",
  "archived",
  "purge_candidate",
];

const CACHE_DIR_NAMES = new Set([
  "cache",
  "code cache",
  "gpucache",
  "dawncache",
  "shadercache",
  "grshadercache",
  "component_crx_cache",
]);

const SESSION_FILE_NAMES = new Set([
  "cookies",
  "login data",
  "local state",
  "preferences",
  "secure preferences",
  "transportsecurity",
]);

export async function buildArtifactRetentionReport(input: {
  stateRoot: string;
  outputPath?: string;
}): Promise<ArtifactRetentionReport> {
  const records = await readExperimentRecords(input.stateRoot);
  const entries: ArtifactRetentionReportEntry[] = [];
  const seenPaths = new Set<string>();

  for (const record of records) {
    for (const artifactPath of collectArtifactPaths(record)) {
      const normalized = normalizePath(artifactPath);
      if (seenPaths.has(normalized) || !(await fileExists(artifactPath))) {
        continue;
      }
      seenPaths.add(normalized);
      const fileStat = await stat(artifactPath);
      const classification = classifyRetention(record, artifactPath, fileStat.size);
      entries.push({
        candidateId: record.candidateId,
        artifactPath,
        sizeBytes: fileStat.size,
        retentionClass: classification.retentionClass,
        reason: classification.reason,
        compactArtifact: buildCompactArtifactSummary(
          record,
          fileStat.size,
          classification.reason,
        ),
      });
    }
  }

  const report: ArtifactRetentionReport = {
    generatedAt: new Date().toISOString(),
    stateRoot: input.stateRoot,
    entries: entries.sort(
      (left, right) =>
        RETENTION_CLASS_ORDER.indexOf(left.retentionClass) -
          RETENTION_CLASS_ORDER.indexOf(right.retentionClass) ||
        right.sizeBytes - left.sizeBytes,
    ),
    summary: summarizeRetentionEntries(entries),
  };
  if (input.outputPath) {
    await writeJson(input.outputPath, report);
  }
  return report;
}

export async function cleanupRuntime(input: {
  stateRoot: string;
  target: "tradingview-cache";
  dryRun?: boolean;
  confirm?: boolean;
}): Promise<RuntimeCleanupReport> {
  const paths = resolveKnowledgePaths(input.stateRoot);
  const runtimeRoot = paths.runtimeDir;
  const dryRun = input.dryRun ?? input.confirm !== true;
  const tradingViewRoot = path.join(runtimeRoot, "tradingview-web-profile");
  const candidates = (await collectRuntimeCleanupCandidates(tradingViewRoot)).sort(
    (left, right) => right.sizeBytes - left.sizeBytes || left.path.localeCompare(right.path),
  );
  let deletedCount = 0;
  let deletedBytes = 0;
  const reportCandidates: RuntimeCleanupReport["candidates"] = [];

  for (const candidate of candidates) {
    let deleted = false;
    if (
      candidate.action === "delete_candidate" &&
      !dryRun &&
      input.confirm === true &&
      isSafeRuntimeCleanupPath(candidate.path, runtimeRoot)
    ) {
      await rm(candidate.path, { recursive: true, force: true });
      deleted = true;
      deletedCount += 1;
      deletedBytes += candidate.sizeBytes;
    }
    reportCandidates.push({ ...candidate, deleted });
  }

  return {
    generatedAt: new Date().toISOString(),
    stateRoot: input.stateRoot,
    runtimeRoot,
    target: input.target,
    dryRun,
    deletedCount,
    deletedBytes,
    candidates: reportCandidates,
  };
}

export async function buildSystemHealthReport(input: {
  stateRoot: string;
  currentTrainingMode?: Record<string, unknown> | null;
}): Promise<SystemHealthReport> {
  const knowledgePaths = resolveKnowledgePaths(input.stateRoot);
  const statePaths = resolveStatePaths(input.stateRoot);
  const experiments = await readExperimentRecords(input.stateRoot);
  const incidents = await readIncidentRecords(input.stateRoot);
  const heartbeatPath = path.join(
    knowledgePaths.runtimeDir,
    "autonomous-loop-heartbeat.json",
  );
  const latestTrace = await readLatestTraceSummary(knowledgePaths.tracesDir);
  const indexManifestPath = path.join(
    knowledgePaths.runtimeDir,
    "autonomous-index-manifest.json",
  );
  const indexManifest = await readJson<Record<string, unknown>>(indexManifestPath).catch(
    () => null,
  );
  return {
    generatedAt: new Date().toISOString(),
    stateRoot: input.stateRoot,
    currentTrainingMode: input.currentTrainingMode ?? null,
    sizes: {
      ledgerBytes: await getDirectorySize(knowledgePaths.ledgerDir),
      artifactBytes: await getDirectorySize(knowledgePaths.artifactDir),
      runtimeBytes: await getDirectorySize(knowledgePaths.runtimeDir),
      totalStateBytes: await getDirectorySize(input.stateRoot),
    },
    ledgers: {
      experiments: experiments.length,
      candidates: await countJsonlRecords(statePaths.candidatesPath),
      artifactRefs: countArtifactRefs(experiments),
      strategyReviews: await countJsonlRecords(statePaths.strategyReviewsPath),
      strategyReviewFailures: incidents.filter((incident) =>
        incident.incidentType.startsWith("strategy_review_"),
      ).length,
      strategyReviewParseFailures: incidents.filter(
        (incident) => incident.incidentType === "strategy_review_parse_failed",
      ).length,
    },
    heartbeat: await readHeartbeatSummary(heartbeatPath),
    latestTrace,
    index: {
      manifestPath: indexManifestPath,
      mode: typeof indexManifest?.mode === "string" ? indexManifest.mode : null,
      lastUpdatedAt:
        typeof indexManifest?.lastUpdatedAt === "string"
          ? indexManifest.lastUpdatedAt
          : null,
      fallbackReason:
        typeof indexManifest?.fallbackReason === "string"
          ? indexManifest.fallbackReason
          : null,
    },
  };
}

function collectArtifactPaths(record: ExperimentRecord): string[] {
  return [
    record.artifactBundleRef?.path,
    ...Object.values(record.artifactPaths ?? {}),
  ].filter((value): value is string => typeof value === "string" && value.length > 0);
}

function classifyRetention(
  record: ExperimentRecord,
  artifactPath: string,
  sizeBytes: number,
): { retentionClass: RetentionClass; reason: string } {
  if (
    record.decision === "promoted_head" ||
    record.decision === "verified_improvement" ||
    record.verificationStatus === "verified" ||
    record.promotionReady === true
  ) {
    return {
      retentionClass: "full",
      reason: "promoted_or_verified_candidate",
    };
  }
  if (artifactPath.includes(`${path.sep}results${path.sep}`)) {
    return {
      retentionClass: "latest",
      reason: "latest_dashboard_or_result_artifact",
    };
  }
  if ((record.candidateScore ?? Number.NEGATIVE_INFINITY) < 0) {
    return {
      retentionClass: "purge_candidate",
      reason: "negative_score_candidate_report_only_no_delete",
    };
  }
  if (record.decision.includes("fail")) {
    return {
      retentionClass: sizeBytes > 1024 * 1024 ? "purge_candidate" : "compact",
      reason: "low_value_failure_report_only_no_delete",
    };
  }
  return {
    retentionClass: "compact",
    reason: "non_promoted_candidate_compactable",
  };
}

function buildCompactArtifactSummary(
  record: ExperimentRecord,
  originalSizeBytes: number,
  retentionReason: string,
): CompactArtifactSummary {
  return {
    candidateId: record.candidateId,
    generatedAt: record.recordedAt ?? null,
    strategySummary:
      typeof record.candidateSummary === "string"
        ? record.candidateSummary
        : record.studyTitle ?? null,
    params:
      record.strategySpec && typeof record.strategySpec === "object"
        ? (record.strategySpec as Record<string, unknown>)
        : null,
    score: record.candidateScore ?? null,
    metric: record.testerMetrics
      ? {
          netProfitPercent: record.testerMetrics.netProfitPercent,
          postFeeNetProfitPercent: record.testerMetrics.postFeeNetProfitPercent,
          totalTrades: record.testerMetrics.totalTrades,
          maxStrategyDrawdownPercent:
            record.testerMetrics.maxStrategyDrawdownPercent,
        }
      : null,
    failureReason: record.decision.includes("fail") ? record.decision : null,
    originalHash:
      record.recordMeta?.artifactBundleHash ??
      record.artifactBundleHash ??
      record.artifactBundleRef?.hash ??
      null,
    originalSizeBytes,
    retentionReason,
  };
}

function summarizeRetentionEntries(
  entries: ArtifactRetentionReportEntry[],
): ArtifactRetentionReport["summary"] {
  const byRetentionClass = Object.fromEntries(
    RETENTION_CLASS_ORDER.map((retentionClass) => [
      retentionClass,
      { count: 0, sizeBytes: 0 },
    ]),
  ) as ArtifactRetentionReport["summary"]["byRetentionClass"];
  let totalSizeBytes = 0;
  for (const entry of entries) {
    byRetentionClass[entry.retentionClass].count += 1;
    byRetentionClass[entry.retentionClass].sizeBytes += entry.sizeBytes;
    totalSizeBytes += entry.sizeBytes;
  }
  return {
    totalArtifacts: entries.length,
    totalSizeBytes,
    byRetentionClass,
  };
}

async function collectRuntimeCleanupCandidates(
  rootDir: string,
): Promise<RuntimeCleanupReport["candidates"]> {
  if (!(await fileExists(rootDir))) {
    return [];
  }
  const candidates: RuntimeCleanupReport["candidates"] = [];
  for (const entry of await listTreeEntries(rootDir)) {
    const basename = path.basename(entry.path).toLowerCase();
    if (basename === "weights.bin") {
      candidates.push({
        path: entry.path,
        sizeBytes: entry.sizeBytes,
        action: "manual_review",
        reason: "large_model_cache_requires_regeneration_confirmation",
        deleted: false,
      });
      continue;
    }
    if (entry.isDirectory && CACHE_DIR_NAMES.has(basename)) {
      candidates.push({
        path: entry.path,
        sizeBytes: entry.sizeBytes,
        action: "delete_candidate",
        reason: "allowlisted_browser_cache_directory",
        deleted: false,
      });
    }
  }
  return candidates;
}

async function listTreeEntries(rootDir: string): Promise<
  Array<{ path: string; sizeBytes: number; isDirectory: boolean }>
> {
  const entries = await readdir(rootDir, { withFileTypes: true }).catch(() => []);
  const results: Array<{ path: string; sizeBytes: number; isDirectory: boolean }> = [];
  for (const entry of entries) {
    const fullPath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      const sizeBytes = await getDirectorySize(fullPath);
      results.push({ path: fullPath, sizeBytes, isDirectory: true });
      results.push(...(await listTreeEntries(fullPath)));
    } else if (entry.isFile()) {
      const fileStat = await stat(fullPath).catch(() => null);
      results.push({
        path: fullPath,
        sizeBytes: fileStat?.size ?? 0,
        isDirectory: false,
      });
    }
  }
  return results;
}

function isSafeRuntimeCleanupPath(candidatePath: string, runtimeRoot: string): boolean {
  const resolvedRuntime = path.resolve(runtimeRoot);
  const resolvedCandidate = path.resolve(candidatePath);
  if (!resolvedCandidate.startsWith(`${resolvedRuntime}${path.sep}`)) {
    return false;
  }
  const parts = resolvedCandidate
    .slice(resolvedRuntime.length + 1)
    .split(path.sep)
    .map((part) => part.toLowerCase());
  if (parts.some((part) => SESSION_FILE_NAMES.has(part))) {
    return false;
  }
  return parts.some((part) => CACHE_DIR_NAMES.has(part));
}

async function readHeartbeatSummary(
  heartbeatPath: string,
): Promise<SystemHealthReport["heartbeat"]> {
  if (!(await fileExists(heartbeatPath))) {
    return {
      status: "missing",
      path: heartbeatPath,
      payload: null,
      error: null,
    };
  }
  try {
    const payload = JSON.parse(await readFile(heartbeatPath, "utf8"));
    const normalizedPayload =
      payload && typeof payload === "object"
        ? (payload as Record<string, unknown>)
        : null;
    const pidPath = path.join(path.dirname(heartbeatPath), "autonomous-loop.pid");
    const pidStatus = await readRuntimePidStatus(pidPath, normalizedPayload);
    return {
      status: pidStatus.stale ? "stale" : "ok",
      path: heartbeatPath,
      payload: normalizedPayload,
      error: pidStatus.reason,
    };
  } catch (error) {
    return {
      status: "read_error",
      path: heartbeatPath,
      payload: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function readRuntimePidStatus(
  pidPath: string,
  heartbeat: Record<string, unknown> | null,
): Promise<{ stale: boolean; reason: string | null }> {
  const rawPid = await readFile(pidPath, "utf8").catch(() => null);
  if (rawPid == null) {
    if (heartbeat == null) {
      return { stale: false, reason: null };
    }
    return {
      stale: true,
      reason: "pid_file_missing",
    };
  }

  const pid = Number.parseInt(rawPid.trim(), 10);
  if (!Number.isInteger(pid) || pid <= 0) {
    return { stale: true, reason: "pid_file_invalid" };
  }

  return isPidRunning(pid)
    ? { stale: false, reason: null }
    : { stale: true, reason: "pid_not_running" };
}

function isPidRunning(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

async function readLatestTraceSummary(
  tracesDir: string,
): Promise<SystemHealthReport["latestTrace"]> {
  const files = (await readdir(tracesDir, { withFileTypes: true }).catch(() => []))
    .filter((entry) => entry.isFile())
    .map((entry) => path.join(tracesDir, entry.name));
  const newest = (
    await Promise.all(
      files.map(async (filePath) => ({
        filePath,
        mtimeMs: (await stat(filePath).catch(() => ({ mtimeMs: 0 }))).mtimeMs,
      })),
    )
  ).sort((left, right) => right.mtimeMs - left.mtimeMs)[0];
  if (!newest) {
    return { path: null, command: null, longestPhase: null, schemaFailures: 0 };
  }
  const lines = (await readFile(newest.filePath, "utf8")).split(/\r?\n/).filter(Boolean);
  let command: string | null = null;
  let longestPhase: { phase: string; durationMs: number } | null = null;
  let schemaFailures = 0;
  for (const line of lines) {
    try {
      const event = JSON.parse(line) as {
        command?: unknown;
        event?: unknown;
        details?: Record<string, unknown>;
      };
      if (typeof event.command === "string") {
        command = event.command;
      }
      if (String(event.event ?? "").includes("schema_fail")) {
        schemaFailures += 1;
      }
      const phase = event.details?.phase;
      const durationMs = event.details?.durationMs;
      if (typeof phase === "string" && typeof durationMs === "number") {
        if (!longestPhase || durationMs > longestPhase.durationMs) {
          longestPhase = { phase, durationMs };
        }
      }
    } catch {
      // Ignore individual corrupt trace lines in a health summary.
    }
  }
  return {
    path: newest.filePath,
    command,
    longestPhase,
    schemaFailures,
  };
}

async function getDirectorySize(rootDir: string): Promise<number> {
  if (!(await fileExists(rootDir))) {
    return 0;
  }
  let total = 0;
  const entries = await readdir(rootDir, { withFileTypes: true }).catch(() => []);
  for (const entry of entries) {
    const fullPath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      total += await getDirectorySize(fullPath);
    } else if (entry.isFile()) {
      total += (await stat(fullPath).catch(() => ({ size: 0 }))).size;
    }
  }
  return total;
}

async function countJsonlRecords(filePath: string): Promise<number> {
  if (!(await fileExists(filePath))) {
    return 0;
  }
  return (await readFile(filePath, "utf8"))
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0).length;
}

function countArtifactRefs(records: ExperimentRecord[]): number {
  const refs = new Set<string>();
  for (const record of records) {
    for (const artifactPath of collectArtifactPaths(record)) {
      refs.add(normalizePath(artifactPath));
    }
  }
  return refs.size;
}

function normalizePath(filePath: string): string {
  return path.resolve(filePath).toLowerCase();
}
