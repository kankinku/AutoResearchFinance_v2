import fs from "node:fs";
import path from "node:path";

import {
  type ArchiveEventRecord,
  type CalibrationEventRecord,
  type HeadEventRecord,
  type LocalConfidenceEventRecord,
  type ProblemEventRecord,
  type RepairAttemptRecord,
} from "../contracts/autonomous.js";
import { type ExperimentRecord } from "../contracts/types.js";
import { writeJson } from "../utils/fs.js";
import { resolveStatePaths } from "./jsonl-store.js";
import {
  compareAutonomousChampion,
  findActiveChampionCandidateId,
  selectLocalEvaluationRecords,
  selectTvVerificationRecords,
} from "./autonomous-state.js";
import { buildLocalConfidenceSummary } from "../research/autonomous/divergence-update-phase.js";
import {
  parseAfStrategyConfig,
  summarizeAfCompatibilityIssues,
} from "../automation/local-backtest/af-config.js";

export async function rebuildAutonomousViews(input: {
  stateRoot: string;
  experiments: ExperimentRecord[];
  headEvents: HeadEventRecord[];
  archiveEvents: ArchiveEventRecord[];
  calibrationEvents: CalibrationEventRecord[];
  confidenceEvents: LocalConfidenceEventRecord[];
  problemEvents: ProblemEventRecord[];
  repairAttempts: RepairAttemptRecord[];
}): Promise<void> {
  const views = buildAutonomousViewPayloads({
    experiments: input.experiments,
    headEvents: input.headEvents,
    archiveEvents: input.archiveEvents,
    calibrationEvents: input.calibrationEvents,
    confidenceEvents: input.confidenceEvents,
    problemEvents: input.problemEvents,
    repairAttempts: input.repairAttempts,
  });
  const paths = resolveStatePaths(input.stateRoot);
  await writeJson(paths.localLeaderboardPath, views.localLeaderboard);
  await writeJson(paths.championHistoryPath, views.championHistory);
  await writeJson(paths.explorationArchivePath, views.explorationArchive);
  await writeJson(paths.noveltyFrontierPath, views.noveltyFrontier);
  await writeJson(paths.robustnessFrontierPath, views.robustnessFrontier);
  await writeJson(paths.tvSurfaceFailuresPath, views.tvSurfaceFailures);
  await writeJson(paths.tvCalibrationQueuePath, views.tvCalibrationQueue);
  await writeJson(paths.localTvDivergencePath, views.localTvDivergence);
  await writeJson(paths.autoSelectionDecisionsPath, views.autoSelectionDecisions);
  await writeJson(paths.duplicateCandidatesPath, views.duplicateCandidates);
  await writeJson(paths.localCompatibilitySummaryPath, views.localCompatibilitySummary);
  await writeJson(paths.autonomousStateSummaryPath, views.autonomousStateSummary);
  await writeJson(paths.localConfidenceSummaryPath, views.localConfidenceSummary);
  await writeJson(paths.failureMemoryPath, views.failureMemory);
  await writeAutonomousNamespaceViews(input.stateRoot, views);
}

export function buildAutonomousViewPayloads(input: {
  experiments: ExperimentRecord[];
  headEvents: HeadEventRecord[];
  archiveEvents: ArchiveEventRecord[];
  calibrationEvents: CalibrationEventRecord[];
  confidenceEvents: LocalConfidenceEventRecord[];
  problemEvents: ProblemEventRecord[];
  repairAttempts: RepairAttemptRecord[];
}) {
  const localRecords = [...selectLocalEvaluationRecords(input.experiments)].sort(
    compareAutonomousChampion,
  );
  const tvRecords = [...selectTvVerificationRecords(input.experiments)].sort(
    (left, right) => right.iteration - left.iteration,
  );
  const activeChampionCandidateId = findActiveChampionCandidateId(input.headEvents);
  const pendingCalibrationQueue = buildPendingCalibrationQueue(
    input.calibrationEvents,
    tvRecords,
  );
  const localConfidenceSummary = buildLocalConfidenceSummary(
    input.confidenceEvents,
  );
  const stage6Readiness = buildPassiveStage6ReadinessPayload({
    localRecords,
    headEvents: input.headEvents,
    calibrationEvents: input.calibrationEvents,
    repairAttempts: input.repairAttempts,
    activeChampionCandidateId,
  });

  return {
    localLeaderboard: {
      generatedAt: new Date().toISOString(),
      activeChampionCandidateId,
      entries: localRecords.map((record, index) => ({
        rank: index + 1,
        candidateId: record.candidateId,
        autoSelectionScore: record.autoSelectionScore,
        performanceScore:
          record.autoSelectionBreakdown?.performanceScore ??
          record.autoSelectionBreakdown?.baseObjectiveScore ??
          null,
        baseObjectiveScore: record.autoSelectionBreakdown?.baseObjectiveScore ?? null,
        robustnessScore: record.autoSelectionBreakdown?.robustnessScore ?? null,
        noveltyScore: record.autoSelectionBreakdown?.noveltyScore ?? null,
        diversityScore: record.autoSelectionBreakdown?.diversityScore ?? null,
        localConfidenceBonus:
          record.autoSelectionBreakdown?.localConfidenceBonus ?? null,
        riskPenalty: record.autoSelectionBreakdown?.riskPenalty ?? null,
        overfitPenalty: record.autoSelectionBreakdown?.overfitPenalty ?? null,
        complexityPenalty: record.autoSelectionBreakdown?.complexityPenalty ?? null,
        duplicatePenalty: record.autoSelectionBreakdown?.duplicatePenalty ?? null,
        divergencePenalty: record.autoSelectionBreakdown?.divergencePenalty ?? null,
        duplicateClassification: record.duplicateStatus?.classification ?? null,
        eligible: record.autoSelectionBreakdown?.eligible ?? false,
        bootstrapEligible: record.eligibility?.bootstrapEligible ?? false,
        archiveEligible: record.eligibility?.archiveEligible ?? false,
        calibrationEligible: record.eligibility?.calibrationEligible ?? false,
        selectionPhase: record.selectionPhase,
        bootstrapSource: record.bootstrapSource ?? null,
        bootstrapReason: record.bootstrapReason ?? null,
        blockingReasons:
          record.eligibility?.blockingReasons.map((reason) => ({
            kind: reason.kind,
            message: reason.message,
            suggestedRepairKind: reason.suggestedRepairKind,
          })) ?? [],
        recordHash: record.recordMeta.recordHash,
        iteration: record.iteration,
        decision: record.decision,
      })),
    },
    championHistory: {
      generatedAt: new Date().toISOString(),
      activeChampionCandidateId,
      events: input.headEvents.map((event) => ({
        eventKind: event.eventKind,
        candidateId: event.candidateId,
        previousChampionId: event.previousChampionId,
        policyVersion: event.policyVersion,
        selectionPhase: event.selectionPhase,
        bootstrapSource: event.bootstrapSource ?? null,
        bootstrapReason: event.bootstrapReason ?? null,
        researchMaturity: event.researchMaturity,
        performanceScore: event.performanceScore ?? event.objectiveScore,
        objectiveScore: event.objectiveScore,
        noveltyScore: event.noveltyScore,
        robustnessScore: event.robustnessScore,
        autoSelectionScore: event.autoSelectionScore,
        diversityScore: event.diversityScore ?? event.diversityContribution,
        diversityContribution: event.diversityContribution,
        localConfidenceBonus: event.localConfidenceBonus,
        riskPenalty: event.riskPenalty,
        overfitPenalty: event.overfitPenalty,
        complexityPenalty: event.complexityPenalty,
        duplicatePenalty: event.duplicatePenalty,
        divergencePenalty: event.divergencePenalty,
        selectionReason: event.selectionReason,
        selectionEvidenceHash: event.selectionEvidenceHash,
        recordedAt: event.recordedAt ?? null,
      })),
    },
    explorationArchive: {
      generatedAt: new Date().toISOString(),
      entries: input.archiveEvents
        .filter((event) => event.eventKind === "archive_added")
        .map((event) => ({
          candidateId: event.candidateId,
          score: event.score,
          noveltyScore: event.noveltyScore,
          robustnessScore: event.robustnessScore,
          reason: event.reason,
          recordedAt: event.recordedAt ?? null,
        })),
    },
    noveltyFrontier: {
      generatedAt: new Date().toISOString(),
      entries: localRecords
        .filter((record) => (record.autoSelectionBreakdown?.noveltyScore ?? 0) > 0)
        .sort(
          (left, right) =>
            (right.autoSelectionBreakdown?.noveltyScore ?? 0) -
            (left.autoSelectionBreakdown?.noveltyScore ?? 0),
        )
        .slice(0, 20)
        .map((record) => ({
          candidateId: record.candidateId,
          noveltyScore: record.autoSelectionBreakdown?.noveltyScore ?? null,
          autoSelectionScore: record.autoSelectionScore,
          recordHash: record.recordMeta.recordHash,
        })),
    },
    robustnessFrontier: {
      generatedAt: new Date().toISOString(),
      entries: localRecords
        .filter((record) => record.splitEvaluation?.oosPassed)
        .sort(
          (left, right) =>
            (right.autoSelectionBreakdown?.robustnessScore ?? 0) -
            (left.autoSelectionBreakdown?.robustnessScore ?? 0),
        )
        .slice(0, 20)
        .map((record) => ({
          candidateId: record.candidateId,
          robustnessScore: record.autoSelectionBreakdown?.robustnessScore ?? null,
          autoSelectionScore: record.autoSelectionScore,
          recordHash: record.recordMeta.recordHash,
        })),
    },
    tvSurfaceFailures: {
      generatedAt: new Date().toISOString(),
      entries: tvRecords
        .filter(
          (record) =>
            record.decision === "tv_surface_failure" ||
            record.decision === "tv_executor_failure",
        )
        .map((record) => ({
          candidateId: record.candidateId,
          decision: record.decision,
          iteration: record.iteration,
          fingerprintFamily: record.noveltyFingerprint?.fingerprintFamily ?? null,
          localConfidence: record.localConfidence,
          recordedAt: record.recordedAt,
        })),
    },
    tvCalibrationQueue: {
      generatedAt: new Date().toISOString(),
      entries: pendingCalibrationQueue,
    },
    localTvDivergence: {
      generatedAt: new Date().toISOString(),
      entries: input.calibrationEvents
        .filter((event) => event.eventKind === "local_tv_divergence_measured")
        .map((event) => ({
          candidateId: event.candidateId,
          fingerprintFamily: event.fingerprintFamily,
          structureFamilyHash: event.structureFamilyHash ?? event.fingerprintFamily,
          localConfidenceBefore: event.localConfidenceBefore,
          localConfidenceAfter: event.localConfidenceAfter,
          parity: event.parity,
          tvDecision: event.tvDecision,
          recordedAt: event.recordedAt ?? null,
        })),
    },
    autoSelectionDecisions: {
      generatedAt: new Date().toISOString(),
      activeChampionCandidateId,
      entries: input.headEvents.map((event) => ({
        eventKind: event.eventKind,
        candidateId: event.candidateId,
        previousChampionId: event.previousChampionId,
        performanceScore: event.performanceScore ?? event.objectiveScore,
        objectiveScore: event.objectiveScore,
        noveltyScore: event.noveltyScore,
        robustnessScore: event.robustnessScore,
        autoSelectionScore: event.autoSelectionScore,
        selectionPhase: event.selectionPhase,
        bootstrapSource: event.bootstrapSource ?? null,
        bootstrapReason: event.bootstrapReason ?? null,
        researchMaturity: event.researchMaturity,
        diversityScore: event.diversityScore ?? event.diversityContribution,
        diversityContribution: event.diversityContribution,
        localConfidenceBonus: event.localConfidenceBonus,
        riskPenalty: event.riskPenalty,
        overfitPenalty: event.overfitPenalty,
        complexityPenalty: event.complexityPenalty,
        duplicatePenalty: event.duplicatePenalty,
        divergencePenalty: event.divergencePenalty,
        selectionReason: event.selectionReason,
        policyVersion: event.policyVersion,
        selectionEvidenceHash: event.selectionEvidenceHash,
        recordedAt: event.recordedAt ?? null,
      })),
    },
    duplicateCandidates: {
      generatedAt: new Date().toISOString(),
      entries: localRecords
        .filter((record) => record.duplicateStatus?.classification !== "unique")
        .map((record) => ({
          candidateId: record.candidateId,
          candidateHash: record.candidateHash,
          classification: record.duplicateStatus?.classification ?? null,
          exactDuplicateCandidateId:
            record.duplicateStatus?.exactDuplicateCandidateId ?? null,
          structuralDuplicateCandidateId:
            record.duplicateStatus?.structuralDuplicateCandidateId ?? null,
          fingerprintFamily: record.noveltyFingerprint?.fingerprintFamily ?? null,
          recordedAt: record.recordedAt,
        })),
    },
    localCompatibilitySummary: buildLocalCompatibilitySummary(
      localRecords,
      input.problemEvents,
      input.repairAttempts,
    ),
    localConfidenceSummary,
    stage6Readiness,
    autonomousStateSummary: buildAutonomousStateSummaryPayload({
      localRecords,
      headEvents: input.headEvents,
      archiveEvents: input.archiveEvents,
      calibrationEvents: input.calibrationEvents,
      confidenceEvents: input.confidenceEvents,
      problemEvents: input.problemEvents,
      repairAttempts: input.repairAttempts,
      activeChampionCandidateId,
      pendingCalibrationQueue,
      stage6Readiness,
    }),
    failureMemory: buildFailureMemorySummary(input.problemEvents, input.repairAttempts),
  };
}

function buildPassiveStage6ReadinessPayload(input: {
  localRecords: ReturnType<typeof selectLocalEvaluationRecords>;
  headEvents: HeadEventRecord[];
  calibrationEvents: CalibrationEventRecord[];
  repairAttempts: RepairAttemptRecord[];
  activeChampionCandidateId: string | null;
}) {
  const successfulRepairs = input.repairAttempts.filter(
    (attempt) => attempt.result === "success",
  );
  const successfulRepairsWithoutCandidate = successfulRepairs.filter(
    (attempt) => !attempt.repairedCandidateId,
  );
  const bootstrapPassed = input.localRecords.some(
    (record) =>
      record.selectionPhase === "bootstrap" &&
      record.bootstrapSource === "local_compatible_seed" &&
      (record.eligibility?.bootstrapEligible === true ||
        record.eligibility?.autoSelectionEligible === true),
  );
  const scoreFeedbackPassed = input.localRecords.some((record) => {
    const breakdown = record.autoSelectionBreakdown;
    return (
      (breakdown?.localConfidenceBonus ?? 0) !== 0 ||
      (breakdown?.divergencePenalty ?? 0) !== 0
    );
  });
  const calibrationQueuePassed = input.calibrationEvents.some(
    (event) => event.eventKind === "calibration_candidate_added",
  );

  return {
    generatedAt: new Date().toISOString(),
    evaluated: false,
    passed: false,
    activeChampionCandidateId: input.activeChampionCandidateId,
    freshBootstrapPassed: bootstrapPassed,
    multiIterationPassed:
      input.activeChampionCandidateId != null && input.localRecords.length >= 5,
    rootIsolationPassed: null,
    repairTraceabilityPassed: successfulRepairsWithoutCandidate.length === 0,
    calibrationQueuePassed,
    scoreFeedbackPassed,
    feedbackClosureRequired: false,
    calibrationMode: "queue_only",
    rootIsolationStatus: "not_evaluated",
    repairTraceabilityStatus:
      successfulRepairsWithoutCandidate.length === 0 ? "passing" : "failing",
    feedbackClosureStatus: scoreFeedbackPassed ? "observed" : "not_observed",
    warnings: [
      "Run verify-stage6-readiness for an isolated fresh/custom root gate result.",
    ],
    evidence: {
      localEvaluationCount: input.localRecords.length,
      headEventCount: input.headEvents.length,
      calibrationEventCount: input.calibrationEvents.length,
      successfulRepairCount: successfulRepairs.length,
      successfulRepairsWithoutCandidateCount:
        successfulRepairsWithoutCandidate.length,
    },
  };
}

function buildPendingCalibrationQueue(
  calibrationEvents: CalibrationEventRecord[],
  tvRecords: ReturnType<typeof selectTvVerificationRecords>,
) {
  const latestQueueByCandidate = new Map<string, CalibrationEventRecord>();
  for (const event of calibrationEvents.slice().sort(compareCalibrationEventsAscending)) {
    latestQueueByCandidate.set(event.candidateId, event);
  }

  return [...latestQueueByCandidate.values()]
    .map((event) => ({
      candidateId: event.candidateId,
      fingerprintFamily: event.fingerprintFamily,
      structureFamilyHash: event.structureFamilyHash ?? event.fingerprintFamily,
      queueState: event.queueState,
      derivedStatus: deriveCalibrationQueueStatus(event, tvRecords),
      queueReason: event.queueReason,
      tvHealthAtQueueTime: event.tvHealthAtQueueTime,
      localConfidenceBefore: event.localConfidenceBefore,
      recordedAt: event.recordedAt ?? null,
    }));
}

function buildLocalCompatibilitySummary(
  localRecords: ReturnType<typeof selectLocalEvaluationRecords>,
  problemEvents: ProblemEventRecord[],
  repairAttempts: RepairAttemptRecord[],
) {
  const unsupportedRecords = localRecords.filter(
    (record) =>
      record.localCompatibility?.compatible === false ||
      record.decision === "local_unsupported",
  );
  const unsupportedObservations = buildUnsupportedObservations(
    unsupportedRecords,
    problemEvents,
  );
  const unsupportedReasonCounts = unsupportedObservations.reduce<
    Record<string, number>
  >((counts, observation) => {
    counts[observation.reason] = (counts[observation.reason] ?? 0) + 1;
    return counts;
  }, {});
  const repairAttemptSuccessRateByReason = buildRepairAttemptSuccessRateByReason({
    problemEvents,
    repairAttempts,
  });
  const recentUnsupportedExamples = unsupportedObservations.slice(-20).map(
    (observation) => ({
      candidateId: observation.candidateId,
      diagnosis: observation.reason,
      missingFunctions: observation.missingFunctions,
      missingInputs: observation.missingInputs,
      unsupportedPatterns: observation.unsupportedPatterns,
      failureSignatureHash: observation.failureSignatureHash,
      structureFamily: observation.structureFamily,
      recordedAt: observation.recordedAt,
    }),
  );

  return {
    generatedAt: new Date().toISOString(),
    localEvaluationCount: localRecords.length,
    localUnsupportedCount: unsupportedObservations.length,
    localCandidateEligibleCount: localRecords.filter(
      (record) =>
        record.eligibility?.autoSelectionEligible === true ||
        record.autoSelectionBreakdown?.eligible === true,
    ).length,
    localCompatibleRate:
      localRecords.length === 0
        ? null
        : (localRecords.length - unsupportedRecords.length) / localRecords.length,
    unsupportedReasonCounts,
    missingFunctionsCounts: buildIssueFieldCounts(
      unsupportedObservations,
      "missingFunctions",
    ),
    missingInputsCounts: buildIssueFieldCounts(
      unsupportedObservations,
      "missingInputs",
    ),
    missingFunctionCounts: buildIssueFieldCounts(
      unsupportedObservations,
      "missingFunctions",
    ),
    missingInputCounts: buildIssueFieldCounts(
      unsupportedObservations,
      "missingInputs",
    ),
    unsupportedPatternCounts: buildIssueFieldCounts(
      unsupportedObservations,
      "unsupportedPatterns",
    ),
    recentUnsupportedExamples,
    repairAttemptSuccessRateByReason,
    recentUnsupportedProblems: problemEvents
      .filter((event) => event.problemKind === "local_unsupported")
      .slice(-20),
  };
}

function buildIssueFieldCounts(
  records: Array<{
    missingFunctions: string[];
    missingInputs: string[];
    unsupportedPatterns: string[];
  }>,
  field: "missingFunctions" | "missingInputs" | "unsupportedPatterns",
): Record<string, number> {
  return records.reduce<Record<string, number>>((counts, record) => {
    const values = record[field] ?? [];
    for (const value of values) {
      counts[value] = (counts[value] ?? 0) + 1;
    }
    return counts;
  }, {});
}

function buildUnsupportedObservations(
  unsupportedRecords: ReturnType<typeof selectLocalEvaluationRecords>,
  problemEvents: ProblemEventRecord[],
): Array<{
  candidateId: string | null;
  reason: string;
  missingFunctions: string[];
  missingInputs: string[];
  unsupportedPatterns: string[];
  failureSignatureHash: string | null;
  structureFamily: string | null;
  recordedAt: string | null;
}> {
  const linkedProblemByCandidateId = new Map<string, ProblemEventRecord>();
  for (const event of problemEvents
    .filter((problem) => problem.problemKind === "local_unsupported")
    .slice()
    .sort(compareProblemEventAscending)) {
    if (event.candidateId) {
      linkedProblemByCandidateId.set(event.candidateId, event);
    }
  }

  const recordObservations = unsupportedRecords.map((record) => {
    const linkedProblem =
      record.candidateId == null
        ? null
        : linkedProblemByCandidateId.get(record.candidateId) ?? null;
    const derivedCompatibility = deriveUnsupportedDetailsFromCandidateSource(record);
    const reason = normalizeUnsupportedReason(
      record.localCompatibility?.unsupportedReason ??
        record.eligibility?.blockingReasons[0]?.message ??
        linkedProblem?.diagnosis ??
        derivedCompatibility?.reason,
    );
    return {
      candidateId: record.candidateId,
      reason,
      missingFunctions: dedupeIssueValues([
        ...(record.localCompatibility?.missingFunctions ?? []),
        ...(derivedCompatibility?.missingFunctions ?? []),
        ...extractNamedIssues(reason, [
          "missing function",
          "missing helper function",
          "missing helper functions",
        ]),
      ]),
      missingInputs: dedupeIssueValues([
        ...(record.localCompatibility?.missingInputs ?? []),
        ...(derivedCompatibility?.missingInputs ?? []),
        ...extractNamedIssues(reason, ["missing input", "missing inputs"]),
      ]),
      unsupportedPatterns: dedupeIssueValues([
        ...(record.localCompatibility?.unsupportedPatterns ?? []),
        ...(derivedCompatibility?.unsupportedPatterns ?? []),
      ]),
      failureSignatureHash: linkedProblem?.failureSignatureHash ?? null,
      structureFamily: linkedProblem?.structureFamily ?? null,
      recordedAt: record.recordedAt ?? null,
    };
  });
  const recordCandidateIds = new Set(
    recordObservations
      .map((observation) => observation.candidateId)
      .filter((candidateId): candidateId is string => typeof candidateId === "string"),
  );
  const historicalObservations = problemEvents
    .filter((event) => event.problemKind === "local_unsupported")
    .filter((event) => !event.candidateId || !recordCandidateIds.has(event.candidateId))
    .map((event) => ({
      candidateId: event.candidateId,
      reason: normalizeUnsupportedReason(event.diagnosis),
      missingFunctions: extractNamedIssues(event.diagnosis, [
        "missing function",
        "missing helper function",
        "missing helper functions",
      ]),
      missingInputs: extractNamedIssues(event.diagnosis, [
        "missing input",
        "missing inputs",
      ]),
      unsupportedPatterns: extractNamedIssues(event.diagnosis, [
        "unsupported pattern",
        "unsupported patterns",
      ]),
      failureSignatureHash: event.failureSignatureHash ?? null,
      structureFamily: event.structureFamily ?? null,
      recordedAt: event.recordedAt ?? null,
    }));

  return [...recordObservations, ...historicalObservations].sort((left, right) => {
    const leftRecordedAt = Date.parse(left.recordedAt ?? "");
    const rightRecordedAt = Date.parse(right.recordedAt ?? "");
    return leftRecordedAt - rightRecordedAt;
  });
}

function deriveUnsupportedDetailsFromCandidateSource(
  record: ReturnType<typeof selectLocalEvaluationRecords>[number],
): {
  reason: string | null;
  missingFunctions: string[];
  missingInputs: string[];
  unsupportedPatterns: string[];
} | null {
  if (record.localCompatibility != null) {
    return null;
  }
  if (!record.candidatePath || !fs.existsSync(record.candidatePath)) {
    return null;
  }

  try {
    const source = fs.readFileSync(record.candidatePath, "utf8");
    const parsed = parseAfStrategyConfig(source);
    if (parsed.compatibilityIssues.length === 0) {
      return null;
    }
    const summary = summarizeAfCompatibilityIssues(parsed.compatibilityIssues);
    return {
      reason: buildDerivedUnsupportedReason(summary),
      missingFunctions: summary.missingFunctions,
      missingInputs: summary.missingInputs,
      unsupportedPatterns: summary.unsupportedPatterns,
    };
  } catch {
    return null;
  }
}

function buildDerivedUnsupportedReason(input: {
  missingFunctions: string[];
  missingInputs: string[];
  unsupportedPatterns: string[];
}): string | null {
  const reasonParts: string[] = [];
  if (input.missingInputs.length > 0) {
    reasonParts.push("missing required AF inputs");
  }
  if (input.missingFunctions.length > 0) {
    reasonParts.push("missing required AF helper functions");
  }
  if (input.unsupportedPatterns.length > 0) {
    reasonParts.push("uses unsupported AF patterns");
  }
  if (reasonParts.length === 0) {
    return null;
  }
  return `${reasonParts.join("; ")}.`;
}

function buildAutonomousStateSummaryPayload(input: {
  localRecords: ReturnType<typeof selectLocalEvaluationRecords>;
  headEvents: HeadEventRecord[];
  archiveEvents: ArchiveEventRecord[];
  calibrationEvents: CalibrationEventRecord[];
  confidenceEvents: LocalConfidenceEventRecord[];
  problemEvents: ProblemEventRecord[];
  repairAttempts: RepairAttemptRecord[];
  activeChampionCandidateId: string | null;
  pendingCalibrationQueue: Array<{
    candidateId: string;
    derivedStatus: "pending" | "deferred" | "processed" | "skipped" | "failed";
  }>;
  stage6Readiness: ReturnType<typeof buildPassiveStage6ReadinessPayload>;
}) {
  const activeChampion =
    input.activeChampionCandidateId == null
      ? null
      : input.localRecords.find(
          (record) => record.candidateId === input.activeChampionCandidateId,
        ) ?? null;
  const latestHeadEvent = [...input.headEvents].sort((left, right) => {
    const leftRecordedAt = Date.parse(left.recordedAt ?? "");
    const rightRecordedAt = Date.parse(right.recordedAt ?? "");
    if (leftRecordedAt !== rightRecordedAt) {
      return rightRecordedAt - leftRecordedAt;
    }
    return right.iteration - left.iteration;
  })[0];
  const localUnsupportedCount = input.problemEvents.filter(
    (event) => event.problemKind === "local_unsupported",
  ).length;
  const localBacktestFailureCount = input.problemEvents.filter(
    (event) => event.problemKind === "local_backtest_fail",
  ).length;
  const pendingCalibrationEntries = input.pendingCalibrationQueue.filter(
    (entry) => entry.derivedStatus === "pending" || entry.derivedStatus === "deferred",
  );
  const hasDeferredPromptAdjustment = input.problemEvents.some(
    (event) =>
      event.problemKind === "local_backtest_fail" &&
      event.suggestedRepairKind === "mutation_prompt_adjustment",
  );
  const hasMutationGenerationFailure = input.problemEvents.some(
    (event) => event.problemKind === "mutation_generation_fail",
  );
  const bootstrapRecords = input.localRecords.filter(
    (record) => record.selectionPhase === "bootstrap",
  );
  const latestBootstrapRecord = [...bootstrapRecords].sort(compareAutonomousChampion)[0] ?? null;
  const bootstrapCompatibleCount = bootstrapRecords.filter(
    (record) => record.decision !== "local_unsupported",
  ).length;
  const bootstrapEligibleCount = bootstrapRecords.filter(
    (record) =>
      record.eligibility?.bootstrapEligible === true ||
      record.eligibility?.autoSelectionEligible === true,
  ).length;
  const topBlockingReason =
    input.localRecords
      .flatMap((record) => record.eligibility?.blockingReasons ?? [])
      .map((reason) => reason.kind)[0] ?? null;
  const scoreFeedbackObserved = input.localRecords.some((record) => {
    const breakdown = record.autoSelectionBreakdown;
    return (
      (breakdown?.localConfidenceBonus ?? 0) !== 0 ||
      (breakdown?.divergencePenalty ?? 0) !== 0
    );
  });

  return {
    generatedAt: new Date().toISOString(),
    activeChampionCandidateId: input.activeChampionCandidateId,
    activeChampionScore: activeChampion?.autoSelectionScore ?? null,
    activeChampionDecision: activeChampion?.decision ?? null,
    championOrigin:
      activeChampion?.bootstrapSource != null ? activeChampion.bootstrapSource : "autonomous",
    researchMaturity:
      activeChampion?.selectionPhase === "bootstrap" ? "bootstrap" : "steady_state",
    selectedBy: latestHeadEvent?.selectedBy ?? null,
    selectionPolicyVersion:
      latestHeadEvent?.policyVersion ??
      activeChampion?.selectionPolicyVersion ??
      null,
    objectivePolicyVersion: activeChampion?.objectivePolicyVersion ?? null,
    headEventCount: input.headEvents.length,
    archiveEventCount: input.archiveEvents.length,
    calibrationEventCount: input.calibrationEvents.length,
    calibrationCandidateCount: input.calibrationEvents.filter(
      (event) => event.eventKind === "calibration_candidate_added",
    ).length,
    divergenceCount: input.calibrationEvents.filter(
      (event) => event.eventKind === "local_tv_divergence_measured",
    ).length,
    localConfidenceUpdateCount: input.confidenceEvents.length,
    problemEventCount: input.problemEvents.length,
    repairAttemptCount: input.repairAttempts.length,
    localEvaluationCount: input.localRecords.length,
    localEligibleCount: input.localRecords.filter(
      (record) => record.eligibility?.autoSelectionEligible === true,
    ).length,
    bootstrapCompatibleCount,
    bootstrapEligibleCount,
    bootstrapStatus:
      bootstrapEligibleCount > 0
        ? "complete"
        : bootstrapRecords.length > 0
          ? "incomplete"
          : "not_started",
    bootstrapSource: latestBootstrapRecord?.bootstrapSource ?? null,
    bootstrapReason: latestBootstrapRecord?.bootstrapReason ?? null,
    localRejectedCount: input.localRecords.filter(
      (record) => record.decision === "local_candidate_rejected",
    ).length,
    topBlockingReason,
    pendingCalibrationCandidateCount: pendingCalibrationEntries.length,
    pendingCalibrationCandidateIds: pendingCalibrationEntries.map(
      (entry) => entry.candidateId,
    ),
    recentProblemKinds: input.problemEvents.slice(-5).map((event) => event.problemKind),
    recentRepairResults: input.repairAttempts.slice(-5).map((attempt) => ({
      repairKind: attempt.repairKind,
      result: attempt.result,
      repairedCandidateId: attempt.repairedCandidateId,
      summary: attempt.summary,
    })),
    scoreFeedbackObserved,
    stage6Readiness: input.stage6Readiness,
    lastStage6GatePassed: input.stage6Readiness.evaluated
      ? input.stage6Readiness.passed
      : null,
    rootIsolationStatus: input.stage6Readiness.rootIsolationStatus,
    repairTraceabilityStatus: input.stage6Readiness.repairTraceabilityStatus,
    feedbackClosureStatus: input.stage6Readiness.feedbackClosureStatus,
    nextPlannedAction:
      activeChampion?.selectionPhase === "bootstrap"
        ? "mutate_beyond_bootstrap_seed"
        : localUnsupportedCount > 0
        ? "local_compatibility_repair"
        : hasMutationGenerationFailure
          ? "schema_prompt_hardening"
        : hasDeferredPromptAdjustment || localBacktestFailureCount > 0
          ? "mutation_prompt_adjustment"
          : input.pendingCalibrationQueue.length > 0
            ? "process_tv_calibration_queue"
            : activeChampion
              ? "archive_gap_exploration"
              : "generate_next_candidate",
    loopMode: "local-first",
    defaultOperationalView:
      input.localRecords.length > 0 ? "v3_autonomous_local_first" : "legacy_v2",
  };
}

function deriveCalibrationQueueStatus(
  event: CalibrationEventRecord,
  tvRecords: ReturnType<typeof selectTvVerificationRecords>,
): "pending" | "deferred" | "processed" | "skipped" | "failed" {
  if (event.queueState === "processed") {
    return "processed";
  }
  if (event.queueState === "skipped") {
    return "skipped";
  }
  if (event.queueState === "failed") {
    return "failed";
  }
  if (hasNewerTvRecord(event, tvRecords)) {
    return "processed";
  }
  if (event.tvHealthAtQueueTime && event.tvHealthAtQueueTime !== "healthy") {
    return "deferred";
  }
  return "pending";
}

function compareCalibrationEventsAscending(
  left: CalibrationEventRecord,
  right: CalibrationEventRecord,
): number {
  const leftRecordedAt = Date.parse(left.recordedAt ?? "");
  const rightRecordedAt = Date.parse(right.recordedAt ?? "");
  if (leftRecordedAt !== rightRecordedAt) {
    return leftRecordedAt - rightRecordedAt;
  }
  return left.iteration - right.iteration;
}

function hasNewerTvRecord(
  event: CalibrationEventRecord,
  tvRecords: ReturnType<typeof selectTvVerificationRecords>,
): boolean {
  const latestTvRecord = tvRecords.find(
    (record) => record.candidateId === event.candidateId,
  );
  if (!latestTvRecord) {
    return false;
  }
  const eventTime = Date.parse(event.recordedAt ?? "");
  const tvTime = Date.parse(latestTvRecord.recordedAt ?? "");
  if (!Number.isFinite(eventTime) || !Number.isFinite(tvTime)) {
    return false;
  }
  return tvTime >= eventTime;
}

function normalizeUnsupportedReason(reason: string | null | undefined): string {
  return typeof reason === "string" && reason.trim().length > 0 ? reason : "unknown";
}

function dedupeIssueValues(values: string[]): string[] {
  return Array.from(
    new Set(
      values
        .map((value) => value.trim())
        .filter((value) => value.length > 0),
    ),
  );
}

function extractNamedIssues(text: string | null | undefined, prefixes: string[]): string[] {
  if (typeof text !== "string" || text.trim().length === 0) {
    return [];
  }

  const lower = text.toLowerCase();
  const matches = prefixes.flatMap((prefix) => {
    const markerIndex = lower.indexOf(prefix);
    if (markerIndex === -1) {
      return [];
    }
    const suffix = text.slice(markerIndex + prefix.length).replace(/^[:\s-]+/, "");
    const firstSegment = suffix.split("|")[0]?.split(".")[0]?.trim() ?? "";
    if (firstSegment.length === 0) {
      return [];
    }
    return firstSegment
      .split(",")
      .map((value) => value.trim())
      .filter((value) => value.length > 0);
  });

  return dedupeIssueValues(matches);
}

function compareProblemEventAscending(
  left: ProblemEventRecord,
  right: ProblemEventRecord,
): number {
  const leftRecordedAt = Date.parse(left.recordedAt ?? "");
  const rightRecordedAt = Date.parse(right.recordedAt ?? "");
  if (leftRecordedAt !== rightRecordedAt) {
    return leftRecordedAt - rightRecordedAt;
  }
  return left.iteration - right.iteration;
}

function buildRepairAttemptSuccessRateByReason(input: {
  problemEvents: ProblemEventRecord[];
  repairAttempts: RepairAttemptRecord[];
}): Record<string, { attempts: number; successes: number; successRate: number }> {
  const problemEventById = new Map(
    input.problemEvents.map((event) => [event.problemEventId, event] as const),
  );
  const counts: Record<string, { attempts: number; successes: number }> = {};
  for (const attempt of input.repairAttempts) {
    const problemEvent = problemEventById.get(attempt.problemEventId);
    if (!problemEvent || problemEvent.problemKind !== "local_unsupported") {
      continue;
    }
    const reason = normalizeUnsupportedReason(problemEvent.diagnosis);
    counts[reason] = counts[reason] ?? { attempts: 0, successes: 0 };
    counts[reason].attempts += 1;
    if (attempt.result === "success") {
      counts[reason].successes += 1;
    }
  }

  return Object.fromEntries(
    Object.entries(counts).map(([reason, value]) => [
      reason,
      {
        ...value,
        successRate:
          value.attempts === 0 ? 0 : value.successes / value.attempts,
      },
    ]),
  );
}

function buildFailureMemorySummary(
  problemEvents: ProblemEventRecord[],
  repairAttempts: RepairAttemptRecord[],
) {
  const repairByProblemEventId = new Map(
    repairAttempts.map((attempt) => [attempt.problemEventId, attempt]),
  );

  return {
    generatedAt: new Date().toISOString(),
    problemEventCount: problemEvents.length,
    repairAttemptCount: repairAttempts.length,
    recentProblemEvents: problemEvents.slice(-20),
    recentRepairAttempts: repairAttempts.slice(-20),
    recentFailureRepairChains: problemEvents.slice(-20).map((event) => ({
      problemEventId: event.problemEventId,
      candidateId: event.candidateId,
      problemKind: event.problemKind,
      failureSignatureHash: event.failureSignatureHash,
      structureFamily: event.structureFamily,
      suggestedRepairKind: event.suggestedRepairKind,
      repairAttempt:
        repairByProblemEventId.get(event.problemEventId) == null
          ? null
          : {
              repairAttemptId:
                repairByProblemEventId.get(event.problemEventId)?.repairAttemptId ?? null,
              result: repairByProblemEventId.get(event.problemEventId)?.result ?? null,
              repairedCandidateId:
                repairByProblemEventId.get(event.problemEventId)?.repairedCandidateId ??
                null,
              failureSignatureHash:
                repairByProblemEventId.get(event.problemEventId)?.failureSignatureHash ??
                null,
              structureFamily:
                repairByProblemEventId.get(event.problemEventId)?.structureFamily ?? null,
              failureReason:
                repairByProblemEventId.get(event.problemEventId)?.failureReason ?? null,
            },
    })),
  };
}

async function writeAutonomousNamespaceViews(
  stateRoot: string,
  views: ReturnType<typeof buildAutonomousViewPayloads>,
): Promise<void> {
  const viewsDir = path.dirname(resolveStatePaths(stateRoot).localLeaderboardPath);
  const autonomousDir = path.join(viewsDir, "autonomous");
  await writeJson(path.join(autonomousDir, "local-leaderboard.json"), views.localLeaderboard);
  await writeJson(path.join(autonomousDir, "champion-history.json"), views.championHistory);
  await writeJson(path.join(autonomousDir, "exploration-archive.json"), views.explorationArchive);
  await writeJson(path.join(autonomousDir, "novelty-frontier.json"), views.noveltyFrontier);
  await writeJson(path.join(autonomousDir, "robustness-frontier.json"), views.robustnessFrontier);
  await writeJson(path.join(autonomousDir, "tv-surface-failures.json"), views.tvSurfaceFailures);
  await writeJson(path.join(autonomousDir, "tv-calibration-queue.json"), views.tvCalibrationQueue);
  await writeJson(path.join(autonomousDir, "local-tv-divergence.json"), views.localTvDivergence);
  await writeJson(path.join(autonomousDir, "auto-selection-decisions.json"), views.autoSelectionDecisions);
  await writeJson(path.join(autonomousDir, "duplicate-candidates.json"), views.duplicateCandidates);
  await writeJson(
    path.join(autonomousDir, "local-compatibility-summary.json"),
    views.localCompatibilitySummary,
  );
  await writeJson(
    path.join(autonomousDir, "autonomous-state-summary.json"),
    views.autonomousStateSummary,
  );
  await writeJson(
    path.join(autonomousDir, "local-confidence-summary.json"),
    views.localConfidenceSummary,
  );
  await writeJson(path.join(autonomousDir, "failure-memory.json"), views.failureMemory);
}
