import path from "node:path";

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
import { readJson, writeJson } from "../utils/fs.js";
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

export async function rebuildIndexes(stateRoot: string): Promise<void> {
  const records = await readExperimentRecords(stateRoot);
  const incidents = await readIncidentRecords(stateRoot);
  const headEvents = await readHeadEventRecords(stateRoot);
  const archiveEvents = await readArchiveEventRecords(stateRoot);
  const calibrationEvents = await readCalibrationEventRecords(stateRoot);
  const confidenceEvents = await readLocalConfidenceEventRecords(stateRoot);
  const problemEvents = await readProblemEventRecords(stateRoot);
  const repairAttempts = await readRepairAttemptRecords(stateRoot);
  const researchKnowledge = await readResearchKnowledgeRecords(stateRoot);
  const taskBatches = await readTaskBatchRecords(stateRoot);
  const tasks = await readTaskRecords(stateRoot);
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
    parityStatusCounts: latestParityEntries.reduce<Record<string, number>>((counts, entry) => {
      const status = entry.parity.status ?? "not_comparable";
      counts[status] = (counts[status] ?? 0) + 1;
      return counts;
    }, {}),
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
  });
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
