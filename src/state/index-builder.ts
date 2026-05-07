import path from "node:path";
import { open, stat } from "node:fs/promises";

import {
  type ExperimentRecord,
  type IncidentRecord,
  type LineageNode,
  type LocalTvParitySummary,
  type TaskBatchRecord,
  type TaskRecord,
} from "../contracts/types.js";
import { normalizeDecisionCode } from "../evaluation/decision.js";
import {
  buildInvalidRecordViewEntries,
  type InvalidRecordViewEntry,
  selectPromotionEligibleRecords,
  selectPromotedHeadRecords,
  selectVerifiedViewRecords,
} from "../evaluation/record-eligibility.js";
import { buildCompileFailureClassCounts } from "../mutation/compile-failure.js";
import { fileExists, readJson, writeJson } from "../utils/fs.js";
import {
  readArchiveEventRecords,
  readCalibrationEventRecords,
  readExperimentRecords,
  readHeadEventRecords,
  readIncidentRecords,
  readLocalConfidenceEventRecords,
  readProblemEventRecords,
  readRepairAttemptRecords,
  readResearchKnowledgeRecords,
  readTaskBatchRecords,
  readTaskRecords,
  readAutonomousBranchRecords,
  resolveStatePaths,
} from "./jsonl-store.js";
import { rebuildAutonomousViews } from "./autonomous-index-builder.js";
import {
  findActiveHeadRecord,
  findBestAcceptedRecord,
  findBestVerifiedRecord,
  findLegacyAcceptedRecord,
} from "./accepted-head.js";
import { resolveRecordEra } from "../evaluation/decision.js";
import { resolveKnowledgePaths } from "./knowledge-paths.js";

export type IndexUpdateMode = "incremental" | "full";
export interface RebuildIndexesOptions {
  mode?: IndexUpdateMode;
}

interface IndexLedgerSnapshot {
  records: ExperimentRecord[];
  incidents: IncidentRecord[];
  headEvents: Awaited<ReturnType<typeof readHeadEventRecords>>;
  archiveEvents: Awaited<ReturnType<typeof readArchiveEventRecords>>;
  calibrationEvents: Awaited<ReturnType<typeof readCalibrationEventRecords>>;
  confidenceEvents: Awaited<ReturnType<typeof readLocalConfidenceEventRecords>>;
  problemEvents: Awaited<ReturnType<typeof readProblemEventRecords>>;
  repairAttempts: Awaited<ReturnType<typeof readRepairAttemptRecords>>;
  branchRecords: Awaited<ReturnType<typeof readAutonomousBranchRecords>>;
  researchKnowledge: Awaited<ReturnType<typeof readResearchKnowledgeRecords>>;
  taskBatches: TaskBatchRecord[];
  tasks: TaskRecord[];
}

interface IndexManifest {
  schemaVersion: "autonomous-index-manifest/v1";
  mode: IndexUpdateMode;
  lastUpdatedAt: string;
  fallbackReason: string | null;
  ledgers: Record<string, { path: string; sizeBytes: number }>;
  cachePath: string;
}

type IndexLedgerKey = keyof IndexLedgerSnapshot;
type IndexLedgerSpecs = Record<
  IndexLedgerKey,
  { path: string; reader: (stateRoot: string) => Promise<unknown[]> }
>;

function sortExperiments(records: ExperimentRecord[]): ExperimentRecord[] {
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

function buildLineageNodes(records: ExperimentRecord[]): LineageNode[] {
  return records.map((record) => ({
    candidateId: record.candidateId,
    parentCandidateId: record.parentCandidateId,
    branchId: record.branchId,
    accepted: isAcceptedDecision(record.decision),
    score: record.candidateScore ?? null,
    decision: String(record.decision),
    reason: String(record.decision),
  }));
}

function normalizeRecordDecision(record: ExperimentRecord): string {
  return String(normalizeDecisionCode(record.decision));
}

function hasFallbackEvaluation(record: ExperimentRecord): boolean {
  return record.fallbackEvaluation != null;
}

function isAcceptedDecision(decision: string): boolean {
  return decision === "verified_improvement" || decision === "promoted_head";
}

function isScreeningDecision(record: ExperimentRecord): boolean {
  return (
    resolveRecordEra(record) === "v2" &&
    (record.decision === "screening_improvement" ||
      record.decision === "valid_no_promotion")
  );
}

function isLegacyDecision(record: ExperimentRecord): boolean {
  return resolveRecordEra(record) === "legacy";
}

function isVerificationFailureRecord(record: ExperimentRecord): boolean {
  return (
    record.decision === "verification_fail" ||
    record.verificationStatus === "verification_failed"
  );
}

function resolveLatestParityEntries(
  records: ExperimentRecord[],
): Array<{
  candidateId: string;
  iteration: number;
  parity: LocalTvParitySummary;
  source: "fallback" | "authoritative";
}> {
  const latestByCandidate = new Map<
    string,
    {
      candidateId: string;
      iteration: number;
      parity: LocalTvParitySummary;
      source: "fallback" | "authoritative";
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
        candidateId: record.candidateId,
        iteration: record.iteration,
        parity: record.fallbackEvaluation.parity,
        source: "fallback",
      });
    }
    if (record.localTvParity) {
      latestByCandidate.set(record.candidateId, {
        candidateId: record.candidateId,
        iteration: record.iteration,
        parity: record.localTvParity,
        source: "authoritative",
      });
    }
  }

  return [...latestByCandidate.values()].sort(
    (left, right) => right.iteration - left.iteration,
  );
}

function buildParityStatusCounts(
  entries: Array<{ parity: LocalTvParitySummary }>,
): Record<string, number> {
  const counts = entries.reduce<Record<string, number>>((accumulator, entry) => {
    const status = entry.parity.status ?? "not_comparable";
    accumulator[status] = (accumulator[status] ?? 0) + 1;
    return accumulator;
  }, {});

  return Object.fromEntries(
    Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)),
  );
}

function resolveLatestTaskBatchRecords(
  records: TaskBatchRecord[],
): TaskBatchRecord[] {
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

  return [...latestByBatchId.values()].sort((left, right) =>
    left.batchId.localeCompare(right.batchId),
  );
}

function buildRecordKey(record: Pick<ExperimentRecord, "candidateId" | "iteration" | "decision" | "recordMeta">): string {
  return (
    record.recordMeta?.recordHash ??
    `${record.candidateId}:${record.iteration}:${record.decision}`
  );
}

function dedupeRecords(records: ExperimentRecord[]): ExperimentRecord[] {
  const unique = new Map<string, ExperimentRecord>();
  for (const record of records) {
    unique.set(buildRecordKey(record), record);
  }
  return [...unique.values()];
}

function buildRankedEntry(
  record: ExperimentRecord,
  rank: number,
): Record<string, unknown> {
  return {
    rank,
    candidateId: record.candidateId,
    decision: normalizeRecordDecision(record),
    score: record.candidateScore ?? null,
    iteration: record.iteration,
    branchId: record.branchId,
    recordEra: resolveRecordEra(record),
    recordHash: record.recordMeta?.recordHash ?? null,
  };
}

function buildInvalidRecordEntries(
  records: ExperimentRecord[],
): InvalidRecordViewEntry[] {
  return buildInvalidRecordViewEntries(records)
    .slice()
    .sort(
      (left, right) =>
        (right.iteration ?? 0) - (left.iteration ?? 0) ||
        left.candidateId.localeCompare(right.candidateId),
    );
}

function buildTaskBoard(
  batches: TaskBatchRecord[],
  tasks: TaskRecord[],
): Record<string, unknown> {
  const latestBatches = resolveLatestTaskBatchRecords(batches);
  return {
    generatedAt: new Date().toISOString(),
    batches: latestBatches.map((batch) => ({
      batchId: batch.batchId,
      runId: batch.runId,
      targetTaskCount: batch.targetTaskCount,
      completedTaskCount: batch.completedTaskCount,
      runtimeFailureCount: batch.runtimeFailureCount,
      maxRuntimeFailures: batch.maxRuntimeFailures,
      status: batch.status,
      stopReason: batch.stopReason,
      tasks: tasks
        .filter((task) => task.batchId === batch.batchId)
        .sort((left, right) => left.taskNumber - right.taskNumber)
        .map((task) => ({
          taskId: task.taskId,
          taskNumber: task.taskNumber,
          status: task.status,
          decision: task.analysis.decision,
          score: task.analysis.score,
          candidateId: task.execution.candidateId,
          executionStatus: task.execution.status,
          nextMutationDirection: task.hypothesis.nextMutationDirection,
        })),
    })),
  };
}

const EVALUATION_INCIDENT_TYPES = new Set([
  "mutation_generation_fail",
  "mutation_schema_fail",
  "preflight_fail",
  "unsupported_strategy_family",
  "unsupported_chart_target",
  "compile_fail",
  "apply_fail",
  "artifact_incomplete",
  "backtest_empty",
  "hard_gate_fail",
  "soft_regress",
  "screening_improvement",
  "verification_fail",
  "verified_improvement",
  "promoted_head",
  "valid_no_promotion",
  "accepted_improvement",
  "accepted_no_improvement",
  "mutation_request_failed",
  "mutation_parse_failed",
  "mutation_preflight_blocked",
  "mutation_preflight_failed",
  "mutation_preflight_repair_failed",
]);

function resolveIncidentCategory(
  incident: IncidentRecord,
): "system" | "evaluation" {
  if (incident.category === "evaluation") {
    return "evaluation";
  }

  if (EVALUATION_INCIDENT_TYPES.has(incident.incidentType)) {
    return "evaluation";
  }

  return "system";
}

function buildHardGateFailReasonCounts(
  records: ExperimentRecord[],
): Record<string, number> {
  return records.reduce<Record<string, number>>((counts, record) => {
    if (record.decision !== "hard_gate_fail") {
      return counts;
    }

    for (const reason of record.objectiveBreakdown?.hardGateReasons ?? []) {
      counts[reason] = (counts[reason] ?? 0) + 1;
    }

    return counts;
  }, {});
}

function buildHardGateFailPatterns(
  records: ExperimentRecord[],
): Array<{ label: string; count: number }> {
  const counts = new Map<string, number>();
  for (const record of records) {
    if (record.decision !== "hard_gate_fail") {
      continue;
    }

    const reasons = [...(record.objectiveBreakdown?.hardGateReasons ?? [])].sort();
    const label = reasons.length > 0 ? reasons.join("+") : "unknown";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }

  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([label, count]) => ({ label, count }));
}

export async function rebuildIndexes(
  stateRoot: string,
  options: RebuildIndexesOptions = {},
): Promise<void> {
  const snapshot =
    options.mode === "incremental"
      ? await loadIndexLedgerSnapshot(stateRoot)
      : await readFullIndexSnapshot(stateRoot);
  const records = snapshot.records;
  const incidents = snapshot.incidents;
  const headEvents = snapshot.headEvents;
  const archiveEvents = snapshot.archiveEvents;
  const calibrationEvents = snapshot.calibrationEvents;
  const confidenceEvents = snapshot.confidenceEvents;
  const problemEvents = snapshot.problemEvents;
  const repairAttempts = snapshot.repairAttempts;
  const branchRecords = snapshot.branchRecords;
  const researchKnowledge = snapshot.researchKnowledge;
  const taskBatches = snapshot.taskBatches;
  const tasks = snapshot.tasks;
  const sorted = sortExperiments(records);
  const nonFallbackRecords = sorted.filter((record) => !hasFallbackEvaluation(record));
  const acceptedHeadRecord = findBestAcceptedRecord(records);
  const verifiedHeadRecord = findBestVerifiedRecord(records);
  const legacyHeadRecord = findLegacyAcceptedRecord(records);
  const activeHeadRecord = findActiveHeadRecord(records, acceptedHeadRecord);
  const acceptedHeadCandidateId = acceptedHeadRecord?.candidateId ?? null;
  const verifiedHeadCandidateId = verifiedHeadRecord?.candidateId ?? null;
  const legacyHeadCandidateId = legacyHeadRecord?.candidateId ?? null;
  const activeHeadCandidateId = activeHeadRecord?.candidateId ?? null;
  const verifiedRecords = sortExperiments(selectVerifiedViewRecords(nonFallbackRecords));
  const screeningEntries = sortExperiments(
    nonFallbackRecords.filter((record) => isScreeningDecision(record)),
  );
  const legacyEntries = sortExperiments(
    nonFallbackRecords.filter((record) => isLegacyDecision(record)),
  );
  const leaderboardEntries = sortExperiments(
    dedupeRecords([...verifiedRecords, ...legacyEntries]),
  );
  const frontierEntries = sortExperiments(
    dedupeRecords([
      ...selectPromotionEligibleRecords(nonFallbackRecords),
      ...selectPromotedHeadRecords(nonFallbackRecords),
    ]),
  );
  const invalidRecordEntries = buildInvalidRecordEntries(records);
  const topRankedCandidateId = leaderboardEntries[0]?.candidateId ?? null;
  const lineageNodes = buildLineageNodes(records);
  const verificationFailures = sorted.filter(isVerificationFailureRecord);
  const fallbackRecords = sorted.filter(hasFallbackEvaluation);
  const latestParityEntries = resolveLatestParityEntries(records);
  const latestParityByCandidateId = new Map(
    latestParityEntries.map((entry) => [entry.candidateId, entry]),
  );
  const paths = resolveStatePaths(stateRoot);
  const normalizedIncidents = incidents.map((incident) => ({
    ...incident,
    category: resolveIncidentCategory(incident),
  }));

  await writeJson(paths.leaderboardPath, {
    generatedAt: new Date().toISOString(),
    acceptedHeadCandidateId,
    verifiedHeadCandidateId,
    legacyHeadCandidateId,
    activeHeadCandidateId,
    topRankedCandidateId,
    acceptedHeadMatchesTopRanked:
      acceptedHeadCandidateId !== null &&
      acceptedHeadCandidateId === topRankedCandidateId,
    headMatchesTopRanked:
      activeHeadCandidateId !== null &&
      activeHeadCandidateId === topRankedCandidateId,
    entries: leaderboardEntries.map((record, index) => buildRankedEntry(record, index + 1)),
    verifiedEntries: verifiedRecords.map((record, index) =>
      buildRankedEntry(record, index + 1),
    ),
    screeningEntries: screeningEntries.map((record, index) =>
      buildRankedEntry(record, index + 1),
    ),
    legacyEntries: legacyEntries.map((record, index) =>
      buildRankedEntry(record, index + 1),
    ),
  });

  await writeJson(paths.lineagePath, {
    generatedAt: new Date().toISOString(),
    acceptedHeadCandidateId,
    activeHeadCandidateId,
    nodes: lineageNodes,
  });

  await writeJson(paths.frontierPath, {
    generatedAt: new Date().toISOString(),
    acceptedHeadCandidateId,
    activeHeadCandidateId,
    entries: frontierEntries.map((record, index) => ({
      rank: index + 1,
      candidateId: record.candidateId,
      score: record.candidateScore ?? null,
      decision: normalizeRecordDecision(record),
      iteration: record.iteration,
      branchId: record.branchId,
      recordHash: record.recordMeta?.recordHash ?? null,
    })),
  });

  const systemIncidentCounts = incidents.reduce<Record<string, number>>(
    (counts, incident) => {
      if (resolveIncidentCategory(incident) !== "system") {
        return counts;
      }
      counts[incident.incidentType] = (counts[incident.incidentType] ?? 0) + 1;
      return counts;
    },
    {},
  );
  const evaluationIncidentCounts = incidents.reduce<Record<string, number>>(
    (counts, incident) => {
      if (resolveIncidentCategory(incident) !== "evaluation") {
        return counts;
      }
      counts[incident.incidentType] = (counts[incident.incidentType] ?? 0) + 1;
      return counts;
    },
    {},
  );
  const decisionCounts = records.reduce<Record<string, number>>((counts, record) => {
    const normalizedDecision = normalizeRecordDecision(record);
    counts[normalizedDecision] = (counts[normalizedDecision] ?? 0) + 1;
    return counts;
  }, {});
  const verificationFailureReasonCounts = records.reduce<Record<string, number>>(
    (counts, record) => {
      if (!record.verificationFailureReason) {
        return counts;
      }
      counts[record.verificationFailureReason] =
        (counts[record.verificationFailureReason] ?? 0) + 1;
      return counts;
    },
    {},
  );
  const verificationRuntimeFailureKindCounts = records.reduce<Record<string, number>>(
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
  await writeJson(paths.failureSummaryPath, {
    generatedAt: new Date().toISOString(),
    incidentCounts: systemIncidentCounts,
    systemIncidentCounts,
    evaluationIncidentCounts,
    decisionCounts,
    evaluationOutcomeCounts: decisionCounts,
    verificationFailureReasonCounts,
    verificationRuntimeFailureKindCounts,
    compileFailureClassCounts: buildCompileFailureClassCounts(records),
    evaluatedCandidateCount: records.filter((record) => record.status === "evaluated")
      .length,
    hardGateFailReasonCounts: buildHardGateFailReasonCounts(records),
    hardGateFailPatterns: buildHardGateFailPatterns(records),
    latestIncidents: normalizedIncidents.slice(-10),
  });

  await writeJson(paths.verificationFailuresPath, {
    generatedAt: new Date().toISOString(),
    entries: verificationFailures.map((record) => ({
      candidateId: record.candidateId,
      iteration: record.iteration,
      decision: normalizeRecordDecision(record),
      verificationStatus: record.verificationStatus ?? null,
      verificationFailureReason: record.verificationFailureReason ?? null,
      verificationRuntimeFailureKind: record.verificationRuntimeFailureKind ?? null,
      promotionReady: record.promotionReady ?? false,
      recordEra: resolveRecordEra(record),
      hasFallbackEvaluation: hasFallbackEvaluation(record),
    })),
  });

  await writeJson(paths.fallbackEvidenceBoardPath, {
    generatedAt: new Date().toISOString(),
    entries: fallbackRecords.map((record) => ({
      candidateId: record.candidateId,
      iteration: record.iteration,
      decision: normalizeRecordDecision(record),
      verificationFailureReason: record.verificationFailureReason ?? null,
      verificationRuntimeFailureKind: record.verificationRuntimeFailureKind ?? null,
      fallbackEvaluation: record.fallbackEvaluation,
      resolvedParity:
        latestParityByCandidateId.get(record.candidateId)?.parity ??
        record.fallbackEvaluation?.parity ??
        null,
    })),
  });

  await writeJson(paths.screeningBoardPath, {
    generatedAt: new Date().toISOString(),
    entries: screeningEntries.map((record, index) => buildRankedEntry(record, index + 1)),
  });

  await writeJson(paths.invalidRecordsPath, {
    generatedAt: new Date().toISOString(),
    entries: invalidRecordEntries,
  });

  await writeJson(paths.runtimeFailureSummaryPath, {
    generatedAt: new Date().toISOString(),
    counts: verificationRuntimeFailureKindCounts,
    latestFailures: records
      .filter((record) => record.verificationRuntimeFailureKind != null)
      .slice(-10)
      .reverse()
      .map((record) => ({
        candidateId: record.candidateId,
        iteration: record.iteration,
        verificationRuntimeFailureKind: record.verificationRuntimeFailureKind,
        verificationFailureReason: record.verificationFailureReason ?? null,
      })),
  });

  await writeJson(paths.localTvDivergenceSummaryPath, {
    generatedAt: new Date().toISOString(),
    parityStatusCounts: buildParityStatusCounts(latestParityEntries),
    latestEntries: latestParityEntries.slice(0, 10).map((entry) => ({
      candidateId: entry.candidateId,
      iteration: entry.iteration,
      source: entry.source,
      parity: entry.parity ?? {
        status: "not_comparable",
        tradeCountDelta: null,
        netProfitPctDelta: null,
        maxDrawdownPctDelta: null,
        profitFactorDelta: null,
        winRateDelta: null,
      },
    })),
  });

  await writeJson(paths.verificationQueuePath, {
    generatedAt: new Date().toISOString(),
    entries: records
      .filter(
        (record) =>
          record.decision === "verification_fail" &&
          record.verificationFailureReason === "verification_runtime_failure",
      )
      .map((record) => ({
        candidateId: record.candidateId,
        iteration: record.iteration,
        candidatePath: record.candidatePath ?? null,
        verificationRuntimeFailureKind: record.verificationRuntimeFailureKind ?? null,
        fallbackCollected: hasFallbackEvaluation(record),
      })),
  });

  const lossZoneCounts = new Map<string, number>();
  const repairPriorityCounts = new Map<string, number>();
  for (const record of records) {
    for (const zone of record.topLossZones ?? []) {
      lossZoneCounts.set(zone, (lossZoneCounts.get(zone) ?? 0) + 1);
    }
    for (const priority of record.repairPriorities ?? []) {
      repairPriorityCounts.set(
        priority,
        (repairPriorityCounts.get(priority) ?? 0) + 1,
      );
    }
  }
  await writeJson(paths.lossPatternSummaryPath, {
    generatedAt: new Date().toISOString(),
    topLossZones: [...lossZoneCounts.entries()]
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
      .map(([label, count]) => ({ label, count })),
    topRepairPriorities: [...repairPriorityCounts.entries()]
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
      .map(([label, count]) => ({ label, count })),
  });

  const problemTagCounts = new Map<string, number>();
  const strategyTagCounts = new Map<string, number>();
  for (const record of researchKnowledge) {
    for (const tag of record.problemTags) {
      problemTagCounts.set(tag, (problemTagCounts.get(tag) ?? 0) + 1);
    }
    for (const tag of record.strategyTags) {
      strategyTagCounts.set(tag, (strategyTagCounts.get(tag) ?? 0) + 1);
    }
  }
  await writeJson(paths.researchSummaryPath, {
    generatedAt: new Date().toISOString(),
    totalKnowledgeRecords: researchKnowledge.length,
    latestKnowledge: researchKnowledge.slice(-10).reverse().map((record) => ({
      knowledgeId: record.knowledgeId,
      title: record.title,
      sourceType: record.sourceType,
      summary: record.summary,
      problemTags: record.problemTags,
      strategyTags: record.strategyTags,
      insightCount: record.insights.length,
    })),
    topProblemTags: [...problemTagCounts.entries()]
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
      .map(([label, count]) => ({ label, count })),
    topStrategyTags: [...strategyTagCounts.entries()]
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
      .map(([label, count]) => ({ label, count })),
  });

  await writeJson(paths.taskBoardPath, buildTaskBoard(taskBatches, tasks));
  await mirrorLegacyViews(paths);

  await rebuildAutonomousViews({
    stateRoot,
    experiments: records,
    headEvents,
    archiveEvents,
    calibrationEvents,
    confidenceEvents,
    problemEvents,
    repairAttempts,
    branchRecords,
  });
}

async function loadIndexLedgerSnapshot(stateRoot: string): Promise<IndexLedgerSnapshot> {
  const paths = resolveStatePaths(stateRoot);
  const knowledgePaths = resolveKnowledgePaths(stateRoot);
  const manifestPath = path.join(
    knowledgePaths.runtimeDir,
    "autonomous-index-manifest.json",
  );
  const cachePath = path.join(knowledgePaths.runtimeDir, "autonomous-index-cache.json");
  const ledgerSpecs: IndexLedgerSpecs = {
    records: { path: paths.experimentsPath, reader: readExperimentRecords },
    incidents: { path: paths.incidentsPath, reader: readIncidentRecords },
    headEvents: { path: paths.headEventsPath, reader: readHeadEventRecords },
    archiveEvents: { path: paths.archiveEventsPath, reader: readArchiveEventRecords },
    calibrationEvents: {
      path: paths.calibrationEventsPath,
      reader: readCalibrationEventRecords,
    },
    confidenceEvents: {
      path: paths.localConfidenceEventsPath,
      reader: readLocalConfidenceEventRecords,
    },
    problemEvents: { path: paths.problemEventsPath, reader: readProblemEventRecords },
    repairAttempts: {
      path: paths.repairAttemptsPath,
      reader: readRepairAttemptRecords,
    },
    branchRecords: { path: paths.branchesPath, reader: readAutonomousBranchRecords },
    researchKnowledge: {
      path: paths.researchKnowledgePath,
      reader: readResearchKnowledgeRecords,
    },
    taskBatches: { path: paths.taskBatchesPath, reader: readTaskBatchRecords },
    tasks: { path: paths.tasksPath, reader: readTaskRecords },
  } as const;

  const manifest = await readJson<IndexManifest>(manifestPath).catch(() => null);
  const cached = await readJson<IndexLedgerSnapshot>(cachePath).catch(() => null);
  if (
    manifest?.schemaVersion === "autonomous-index-manifest/v1" &&
    cached &&
    manifest.cachePath === cachePath
  ) {
    try {
      const appended = await readAppendedIndexRecords(ledgerSpecs, manifest);
      const snapshot = mergeIndexSnapshots(cached, appended.snapshot);
      await persistIndexSnapshot({
        stateRoot,
        cachePath,
        manifestPath,
        snapshot,
        ledgerSpecs,
        mode: "incremental",
        fallbackReason: null,
      });
      return snapshot;
    } catch (error) {
      const snapshot = await readFullIndexSnapshot(stateRoot);
      await persistIndexSnapshot({
        stateRoot,
        cachePath,
        manifestPath,
        snapshot,
        ledgerSpecs,
        mode: "full",
        fallbackReason: error instanceof Error ? error.message : String(error),
      });
      return snapshot;
    }
  }

  const snapshot = await readFullIndexSnapshot(stateRoot);
  await persistIndexSnapshot({
    stateRoot,
    cachePath,
    manifestPath,
    snapshot,
    ledgerSpecs,
    mode: "full",
    fallbackReason: manifest ? "index_cache_missing_or_schema_mismatch" : null,
  });
  return snapshot;
}

async function readFullIndexSnapshot(stateRoot: string): Promise<IndexLedgerSnapshot> {
  return {
    records: await readExperimentRecords(stateRoot),
    incidents: await readIncidentRecords(stateRoot),
    headEvents: await readHeadEventRecords(stateRoot),
    archiveEvents: await readArchiveEventRecords(stateRoot),
    calibrationEvents: await readCalibrationEventRecords(stateRoot),
    confidenceEvents: await readLocalConfidenceEventRecords(stateRoot),
    problemEvents: await readProblemEventRecords(stateRoot),
    repairAttempts: await readRepairAttemptRecords(stateRoot),
    branchRecords: await readAutonomousBranchRecords(stateRoot),
    researchKnowledge: await readResearchKnowledgeRecords(stateRoot),
    taskBatches: await readTaskBatchRecords(stateRoot),
    tasks: await readTaskRecords(stateRoot),
  };
}

async function readAppendedIndexRecords(
  ledgerSpecs: IndexLedgerSpecs,
  manifest: IndexManifest,
): Promise<{ snapshot: IndexLedgerSnapshot }> {
  const empty = emptyIndexSnapshot();
  for (const [key, spec] of Object.entries(ledgerSpecs)) {
    const previous = manifest.ledgers[key];
    const currentSize = await getFileSize(spec.path);
    if (!previous) {
      throw new Error(`index manifest missing ledger entry: ${key}`);
    }
    if (currentSize < previous.sizeBytes) {
      throw new Error(`ledger shrank since last index update: ${key}`);
    }
    if (currentSize === previous.sizeBytes) {
      continue;
    }
    const appended = await readJsonlFromOffset(spec.path, previous.sizeBytes);
    (empty as unknown as Record<string, unknown[]>)[key] = appended;
  }
  return { snapshot: empty };
}

function mergeIndexSnapshots(
  cached: IndexLedgerSnapshot,
  appended: IndexLedgerSnapshot,
): IndexLedgerSnapshot {
  return {
    records: [...cached.records, ...appended.records],
    incidents: [...cached.incidents, ...appended.incidents],
    headEvents: [...cached.headEvents, ...appended.headEvents],
    archiveEvents: [...cached.archiveEvents, ...appended.archiveEvents],
    calibrationEvents: [...cached.calibrationEvents, ...appended.calibrationEvents],
    confidenceEvents: [...cached.confidenceEvents, ...appended.confidenceEvents],
    problemEvents: [...cached.problemEvents, ...appended.problemEvents],
    repairAttempts: [...cached.repairAttempts, ...appended.repairAttempts],
    branchRecords: [...cached.branchRecords, ...appended.branchRecords],
    researchKnowledge: [...cached.researchKnowledge, ...appended.researchKnowledge],
    taskBatches: [...cached.taskBatches, ...appended.taskBatches],
    tasks: [...cached.tasks, ...appended.tasks],
  };
}

function emptyIndexSnapshot(): IndexLedgerSnapshot {
  return {
    records: [],
    incidents: [],
    headEvents: [],
    archiveEvents: [],
    calibrationEvents: [],
    confidenceEvents: [],
    problemEvents: [],
    repairAttempts: [],
    branchRecords: [],
    researchKnowledge: [],
    taskBatches: [],
    tasks: [],
  };
}

async function persistIndexSnapshot(input: {
  stateRoot: string;
  cachePath: string;
  manifestPath: string;
  snapshot: IndexLedgerSnapshot;
  ledgerSpecs: IndexLedgerSpecs;
  mode: IndexUpdateMode;
  fallbackReason: string | null;
}): Promise<void> {
  await writeJson(input.cachePath, input.snapshot);
  const ledgers: IndexManifest["ledgers"] = {};
  for (const [key, spec] of Object.entries(input.ledgerSpecs)) {
    ledgers[key] = {
      path: spec.path,
      sizeBytes: await getFileSize(spec.path),
    };
  }
  await writeJson(input.manifestPath, {
    schemaVersion: "autonomous-index-manifest/v1",
    mode: input.mode,
    lastUpdatedAt: new Date().toISOString(),
    fallbackReason: input.fallbackReason,
    ledgers,
    cachePath: input.cachePath,
  } satisfies IndexManifest);
  void input.stateRoot;
}

async function readJsonlFromOffset(filePath: string, offset: number): Promise<unknown[]> {
  if (!(await fileExists(filePath))) {
    return [];
  }
  const fileHandle = await open(filePath, "r");
  try {
    const stream = fileHandle.createReadStream({
      encoding: "utf8",
      start: offset,
    });
    const chunks: string[] = [];
    for await (const chunk of stream) {
      chunks.push(String(chunk));
    }
    return chunks
      .join("")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as unknown);
  } finally {
    await fileHandle.close();
  }
}

async function getFileSize(filePath: string): Promise<number> {
  return (await stat(filePath).catch(() => ({ size: 0 }))).size;
}

async function mirrorLegacyViews(
  paths: ReturnType<typeof resolveStatePaths>,
): Promise<void> {
  const legacyDir = path.join(path.dirname(paths.leaderboardPath), "legacy");
  const mirrored = [
    ["leaderboard.json", paths.leaderboardPath],
    ["lineage.json", paths.lineagePath],
    ["frontier.json", paths.frontierPath],
    ["failure-summary.json", paths.failureSummaryPath],
    ["verification-failures.json", paths.verificationFailuresPath],
    ["fallback-evidence-board.json", paths.fallbackEvidenceBoardPath],
    ["screening-board.json", paths.screeningBoardPath],
    ["invalid-records.json", paths.invalidRecordsPath],
    ["runtime-failure-summary.json", paths.runtimeFailureSummaryPath],
    ["local-tv-divergence-summary.json", paths.localTvDivergenceSummaryPath],
    ["verification-queue.json", paths.verificationQueuePath],
    ["loss-pattern-summary.json", paths.lossPatternSummaryPath],
    ["research-summary.json", paths.researchSummaryPath],
    ["task-board.json", paths.taskBoardPath],
  ] as const;

  for (const [fileName, sourcePath] of mirrored) {
    await writeJson(path.join(legacyDir, fileName), await readJson(sourcePath));
  }
}
