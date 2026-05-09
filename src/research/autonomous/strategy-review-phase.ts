import {
  type ExperimentRecord,
  type MutationBriefRecord,
  type ObjectiveConfig,
  type ResearchKnowledgeRecord,
} from "../../contracts/types.js";
import {
  type AutonomousExperimentRecord,
  type CalibrationEventRecord,
  type HeadEventRecord,
  type ProblemEventRecord,
  type RepairAttemptRecord,
} from "../../contracts/autonomous.js";
import {
  strategyReviewEvidenceSchema,
  strategyReviewLlmResponseSchema,
  strategyReviewRecordSchema,
  type StrategyReviewBoard,
  type StrategyReviewDecision,
  type StrategyReviewEvidence,
  type StrategyReviewMutationDirective,
  type StrategyReviewRecord,
} from "../../contracts/strategy-review.js";
import { type ResearchTarget } from "../../config/target-registry.js";
import { type ResearchRunContext } from "../../config/research-run-context.js";
import { type MutationLlmClient } from "../../mutation/llm-client.js";
import {
  appendIncidentRecord,
  appendStrategyReviewRecord,
  readCalibrationEventRecords,
  readExperimentRecords,
  readHeadEventRecords,
  readMutationBriefRecords,
  readProblemEventRecords,
  readRepairAttemptRecords,
  readResearchKnowledgeRecords,
  readStrategyReviewRecords,
} from "../../state/jsonl-store.js";
import {
  findActiveChampionRecord,
  isAutoSelectionEligible,
  isVerifiedPromotionEligible,
  parseAutonomousExperimentRecord,
  selectLocalEvaluationRecords,
} from "../../state/autonomous-state.js";
import { sha256Json } from "../../utils/fs.js";

interface MonitorLike {
  log: (
    event: string,
    message: string,
    details?: Record<string, unknown>,
  ) => Promise<void>;
}

export type StrategyReviewRunMode = "off" | "selective" | "all";

export interface RunStrategyReviewPhaseInput {
  stateRoot: string;
  runId: string;
  iteration: number;
  targetId: string;
  objective: ObjectiveConfig;
  runContext?: ResearchRunContext;
  record: ExperimentRecord | AutonomousExperimentRecord;
  experiments: ExperimentRecord[];
  headEvents?: HeadEventRecord[];
  calibrationEvents?: CalibrationEventRecord[];
  problemEvents?: ProblemEventRecord[];
  repairAttempts?: RepairAttemptRecord[];
  mutationBriefs?: MutationBriefRecord[];
  researchKnowledge?: ResearchKnowledgeRecord[];
  llmClient?: MutationLlmClient;
  mode?: StrategyReviewRunMode;
  deepBudget?: number;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}

export interface RunStrategyReviewBatchInput {
  stateRoot: string;
  targetId: string;
  objective: ObjectiveConfig;
  runContext?: ResearchRunContext;
  llmClient?: MutationLlmClient;
  mode?: StrategyReviewRunMode;
  deepBudget?: number;
  limit?: number;
  signal?: AbortSignal;
  monitor?: MonitorLike;
}

export async function runStrategyReviewPhase(
  input: RunStrategyReviewPhaseInput,
): Promise<StrategyReviewRecord | null> {
  const mode = input.mode ?? "selective";
  if (mode === "off") {
    return null;
  }

  const problemEvents = input.problemEvents ?? (await readProblemEventRecords(input.stateRoot));
  const repairAttempts =
    input.repairAttempts ?? (await readRepairAttemptRecords(input.stateRoot));
  const mutationBriefs =
    input.mutationBriefs ?? (await readMutationBriefRecords(input.stateRoot));
  const headEvents = input.headEvents ?? (await readHeadEventRecords(input.stateRoot));
  const calibrationEvents =
    input.calibrationEvents ?? (await readCalibrationEventRecords(input.stateRoot));
  const researchKnowledge =
    input.researchKnowledge ?? (await readResearchKnowledgeRecords(input.stateRoot));
  const targetExperiments = filterStrategyReviewRecordsForTarget(
    input.experiments,
    input.targetId,
    input.objective,
  );
  const evidence = buildStrategyReviewEvidence({
    targetId: input.targetId,
    objective: input.objective,
    runContext: input.runContext,
    record: input.record,
    experiments: targetExperiments,
    headEvents,
    calibrationEvents,
    problemEvents,
    repairAttempts,
    mutationBriefs,
    researchKnowledge,
  });
  const recordMetadata = buildStrategyReviewRecordMetadata({
    evidence,
    runContext: input.runContext,
  });
  const shouldRunDeep =
    (input.deepBudget ?? 0) > 0 &&
    shouldRunDeepStrategyReview({
      evidence,
      mode,
      llmAvailable: typeof input.llmClient?.reviewStrategy === "function",
    });

  if (!shouldRunDeep) {
    const deterministic = buildDeterministicStrategyReview(evidence, "deterministic");
    return appendStrategyReviewRecord(input.stateRoot, {
      ...deterministic,
      targetId: input.targetId,
      ...recordMetadata,
      runId: input.runId,
      iteration: input.iteration,
      candidateId: evidence.candidate.candidateId,
      candidateHash: evidence.candidate.candidateHash,
      structureFamilyHash: evidence.candidate.structureFamilyHash,
      fingerprintFamily: evidence.candidate.fingerprintFamily,
      triageReasons: evidence.triage.reasons,
      evidenceRefs: evidence.evidenceRefs,
      evidenceHash: sha256Json(evidence),
    });
  }

  try {
    const rawResponse = await input.llmClient?.reviewStrategy?.({
      evidence,
      signal: input.signal,
    });
    const parsed = parseStrategyReviewResponse(rawResponse ?? "");
    if (!parsed.success) {
      await appendStrategyReviewParseIncident({
        stateRoot: input.stateRoot,
        runId: input.runId,
        iteration: input.iteration,
        candidateId: evidence.candidate.candidateId,
        detail: parsed.error,
      });
      const fallback = buildDeterministicStrategyReview(
        evidence,
        "llm_failed_fallback",
        "LLM review response could not be parsed as strict strategy review JSON.",
      );
      return appendStrategyReviewRecord(input.stateRoot, {
        ...fallback,
        targetId: input.targetId,
        ...recordMetadata,
        runId: input.runId,
        iteration: input.iteration,
        candidateId: evidence.candidate.candidateId,
        candidateHash: evidence.candidate.candidateHash,
        structureFamilyHash: evidence.candidate.structureFamilyHash,
        fingerprintFamily: evidence.candidate.fingerprintFamily,
        triageReasons: [...evidence.triage.reasons, "llm_parse_failed"],
        evidenceRefs: evidence.evidenceRefs,
        evidenceHash: sha256Json(evidence),
      });
    }

    return appendStrategyReviewRecord(input.stateRoot, {
      schemaVersion: "strategy-review-record/v1",
      targetId: input.targetId,
      ...recordMetadata,
      runId: input.runId,
      iteration: input.iteration,
      candidateId: evidence.candidate.candidateId,
      candidateHash: evidence.candidate.candidateHash,
      structureFamilyHash: evidence.candidate.structureFamilyHash,
      fingerprintFamily: evidence.candidate.fingerprintFamily,
      reviewMode: "deep_llm",
      triageReasons: evidence.triage.reasons,
      evidenceRefs: evidence.evidenceRefs,
      evidenceHash: sha256Json(evidence),
      ...parsed.record,
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    await appendStrategyReviewParseIncident({
      stateRoot: input.stateRoot,
      runId: input.runId,
      iteration: input.iteration,
      candidateId: evidence.candidate.candidateId,
      detail,
    });
    const fallback = buildDeterministicStrategyReview(
      evidence,
      "llm_failed_fallback",
      `LLM strategy review failed: ${detail}`,
    );
    return appendStrategyReviewRecord(input.stateRoot, {
      ...fallback,
      targetId: input.targetId,
      ...recordMetadata,
      runId: input.runId,
      iteration: input.iteration,
      candidateId: evidence.candidate.candidateId,
      candidateHash: evidence.candidate.candidateHash,
      structureFamilyHash: evidence.candidate.structureFamilyHash,
      fingerprintFamily: evidence.candidate.fingerprintFamily,
      triageReasons: [...evidence.triage.reasons, "llm_review_failed"],
      evidenceRefs: evidence.evidenceRefs,
      evidenceHash: sha256Json(evidence),
    });
  }
}

export async function runStrategyReviewBatchForTarget(
  input: RunStrategyReviewBatchInput,
): Promise<StrategyReviewRecord[]> {
  const experiments = await readExperimentRecords(input.stateRoot);
  const headEvents = await readHeadEventRecords(input.stateRoot);
  const calibrationEvents = await readCalibrationEventRecords(input.stateRoot);
  const problemEvents = await readProblemEventRecords(input.stateRoot);
  const repairAttempts = await readRepairAttemptRecords(input.stateRoot);
  const mutationBriefs = await readMutationBriefRecords(input.stateRoot);
  const researchKnowledge = await readResearchKnowledgeRecords(input.stateRoot);
  const existingReviews = await readStrategyReviewRecords(input.stateRoot);
  const alreadyReviewed = new Set(
    existingReviews
      .filter((review) => review.targetId === input.targetId)
      .filter((review) =>
        input.runContext
          ? review.goalMode == null || review.goalMode === input.runContext.goalMode
          : true,
      )
      .map((review) => `${review.candidateId}:${review.candidateHash ?? ""}:${review.iteration}`),
  );
  let remainingDeepBudget = input.deepBudget ?? 3;
  const targetRecords = filterStrategyReviewRecordsForTarget(
    experiments,
    input.targetId,
    input.objective,
  )
    .map((record) => parseAutonomousExperimentRecord(record))
    .filter((record): record is AutonomousExperimentRecord => record != null)
    .sort((left, right) => right.iteration - left.iteration)
    .filter(
      (record) =>
        !alreadyReviewed.has(
          `${record.candidateId}:${record.candidateHash ?? ""}:${record.iteration}`,
        ),
    )
    .slice(0, input.limit ?? 50);

  const results: StrategyReviewRecord[] = [];
  for (const record of targetRecords) {
    const review = await runStrategyReviewPhase({
      stateRoot: input.stateRoot,
      runId: record.runId,
      iteration: record.iteration,
      targetId: input.targetId,
      objective: input.objective,
      runContext: input.runContext,
      record,
      experiments,
      headEvents,
      calibrationEvents,
      problemEvents,
      repairAttempts,
      mutationBriefs,
      researchKnowledge,
      llmClient: input.llmClient,
      mode: input.mode,
      deepBudget: remainingDeepBudget,
      signal: input.signal,
      monitor: input.monitor,
    });
    if (review) {
      results.push(review);
      if (review.reviewMode === "deep_llm") {
        remainingDeepBudget = Math.max(0, remainingDeepBudget - 1);
      }
    }
  }
  return results;
}

export function buildStrategyReviewEvidence(input: {
  targetId: string;
  objective: ObjectiveConfig;
  runContext?: ResearchRunContext;
  record: ExperimentRecord | AutonomousExperimentRecord;
  experiments: ExperimentRecord[];
  headEvents?: HeadEventRecord[];
  calibrationEvents?: CalibrationEventRecord[];
  problemEvents?: ProblemEventRecord[];
  repairAttempts?: RepairAttemptRecord[];
  mutationBriefs?: MutationBriefRecord[];
  researchKnowledge?: ResearchKnowledgeRecord[];
}): StrategyReviewEvidence {
  const raw = input.record as Record<string, unknown>;
  const autonomousRecord = parseAutonomousExperimentRecord(input.record as ExperimentRecord);
  const candidateId = stringValue(raw.candidateId) ?? "unknown-candidate";
  const candidateProblems = (input.problemEvents ?? []).filter(
    (event) => event.candidateId === candidateId,
  );
  const candidateRepairs = (input.repairAttempts ?? []).filter(
    (attempt) => attempt.candidateId === candidateId || attempt.repairedCandidateId === candidateId,
  );
  const failureSignatureHash =
    candidateProblems
      .map((event) => event.failureSignatureHash ?? null)
      .find((value): value is string => value != null && value.length > 0) ?? null;
  const repeatedFailureSignatureCount = failureSignatureHash
    ? (input.problemEvents ?? []).filter(
        (event) => event.failureSignatureHash === failureSignatureHash,
      ).length
    : 0;
  const localRecords = selectLocalEvaluationRecords(input.experiments);
  const activeChampion = findActiveChampionRecord({
    records: input.experiments,
    headEvents: input.headEvents ?? [],
  });
  const championScore =
    (activeChampion ? scoreForReview(activeChampion) : null) ??
    bestEligibleReviewScore(input.experiments);
  const score = scoreForReview(input.record);
  const scoreRatioToChampion =
    championScore != null && championScore > 0 && score != null
      ? score / championScore
      : null;
  const calibrationEvent = (input.calibrationEvents ?? [])
    .slice()
    .reverse()
    .find((event) => event.candidateId === candidateId);
  const latestBrief = (input.mutationBriefs ?? []).at(-1) ?? null;
  const triageReasons = buildTriageReasons({
    record: autonomousRecord,
    scoreRatioToChampion,
    repeatedFailureSignatureCount,
    calibrationEvent,
    activeChampionId: activeChampion?.candidateId ?? null,
    candidateProblems,
  });
  const splitEvaluation = autonomousRecord?.splitEvaluation ?? null;
  const walkForward = autonomousRecord?.walkForwardEvaluation ?? null;
  const duplicateStatus = autonomousRecord?.duplicateStatus ?? null;
  const noveltyFingerprint = autonomousRecord?.noveltyFingerprint ?? null;
  const verifiedPromotion = autonomousRecord?.verifiedPromotion ?? null;
  const conditionContributions = [...(autonomousRecord?.conditionContributions ?? [])]
    .sort((left, right) => Math.abs(right.scoreDelta) - Math.abs(left.scoreDelta))
    .slice(0, 8)
    .map((contribution) => ({
      conditionId: contribution.conditionId,
      scoreDelta: contribution.scoreDelta,
      summary: `${contribution.conditionId} changed score by ${roundNumber(
        contribution.scoreDelta,
      )}.`,
    }));
  const lossAnalysis = raw.lossAnalysisSummary as
    | {
        summary?: unknown;
        topLossZones?: unknown;
        repairPriorities?: unknown;
      }
    | undefined;

  return strategyReviewEvidenceSchema.parse({
    schemaVersion: "strategy-review-evidence/v1",
    target: {
      targetId: input.targetId,
      symbol:
        input.runContext?.symbol ??
        autonomousRecord?.symbol ??
        stringValue(raw.symbol) ??
        input.objective.symbol,
      timeframe:
        input.runContext?.timeframe ??
        autonomousRecord?.timeframe ??
        stringValue(raw.timeframe) ??
        input.objective.timeframe,
      goalMode:
        input.runContext?.goalMode ?? autonomousRecord?.goalMode ?? latestBrief?.brief.goalMode,
      goalProfileId:
        input.runContext?.goalProfileId ??
        autonomousRecord?.goalProfileId ??
        latestBrief?.brief.goalProfileId,
    },
    runId: stringValue(raw.runId) ?? "unknown-run",
    iteration: numberValue(raw.iteration) ?? 0,
    candidate: {
      candidateId,
      parentCandidateId: stringValue(raw.parentCandidateId),
      candidateHash: stringValue(raw.candidateHash),
      structureFamilyHash: autonomousRecord?.structureFamilyHash ?? null,
      fingerprintFamily:
        autonomousRecord?.fingerprintFamily ??
        noveltyFingerprint?.fingerprintFamily ??
        null,
      decision: stringValue(raw.decision) ?? "unknown",
      status: stringValue(raw.status) ?? "unknown",
      recordKind: autonomousRecord?.recordKind ?? null,
      researchStage: autonomousRecord?.researchStage ?? null,
      localConfidence: autonomousRecord?.localConfidence ?? null,
    },
    objective: input.objective,
    metrics: {
      fullSample: splitEvaluation?.fullSample.metrics ?? autonomousRecord?.testerMetrics ?? null,
      inSample: splitEvaluation?.inSample.metrics ?? null,
      outOfSample: splitEvaluation?.outOfSample.metrics ?? null,
      walkForward: walkForward
        ? {
            passed: walkForward.passed,
            positiveOosFoldCount: walkForward.positiveOosFoldCount,
            requiredPositiveOosFolds: walkForward.requiredPositiveOosFolds,
            totalOosTrades: walkForward.totalOosTrades,
            gateReasons: walkForward.gateReasons,
          }
        : null,
    },
    objectiveBreakdown: autonomousRecord?.objectiveBreakdown ?? null,
    conditionContributions,
    lossAnalysis: {
      summary: stringValue(lossAnalysis?.summary),
      topLossZones: arrayOfStrings(lossAnalysis?.topLossZones ?? raw.topLossZones),
      repairPriorities: arrayOfStrings(lossAnalysis?.repairPriorities ?? raw.repairPriorities),
    },
    novelty: {
      duplicateClassification: duplicateStatus?.classification ?? null,
      duplicateFingerprint: duplicateStatus?.duplicateFingerprint ?? null,
      featureFlags: noveltyFingerprint?.featureFlags ?? [],
      complexityPenalty:
        autonomousRecord?.autoSelectionBreakdown?.complexityPenalty ?? null,
      trialLedgerStats: verifiedPromotion?.trialLedgerStats ?? null,
    },
    calibration: {
      tvCalibrationStatus:
        autonomousRecord?.tvCalibrationStatus ?? calibrationEvent?.queueState ?? null,
      localTvParityStatus: autonomousRecord?.localTvParity?.status ?? null,
      verifiedPromotionEligible: autonomousRecord
        ? isVerifiedPromotionEligible({ record: autonomousRecord, localRecords })
        : null,
      verifiedPromotionScore: autonomousRecord?.verifiedPromotionScore ?? null,
      rejectionReasons: verifiedPromotion?.rejectionReasons ?? [],
    },
    problemMemory: {
      recentProblems: candidateProblems.slice(-5).map((event) => event.diagnosis),
      repeatedFailureSignatureHash: failureSignatureHash,
      repeatedFailureSignatureCount,
    },
    repairMemory: {
      recentRepairs: candidateRepairs.slice(-5).map((attempt) => attempt.summary),
    },
    mutationBrief: {
      latestBriefHash: latestBrief?.briefHash ?? null,
      branchKind: latestBrief?.brief.branchKind ?? null,
      nextMutationDirection: latestBrief?.brief.nextMutationDirection ?? null,
    },
    evidenceRefs: {
      candidatePath: autonomousRecord?.candidatePath ?? stringValue(raw.candidatePath),
      specPath: autonomousRecord?.specPath ?? stringValue(raw.specPath),
      artifactPaths: autonomousRecord?.artifactPaths ?? {},
      problemEventIds: candidateProblems.map((event) => event.problemEventId),
      repairAttemptIds: candidateRepairs.map((attempt) => attempt.repairAttemptId),
      mutationBriefHashes: latestBrief?.briefHash ? [latestBrief.briefHash] : [],
    },
    triage: {
      deepReviewRecommended: triageReasons.length > 0,
      reasons: triageReasons,
      championScore,
      scoreRatioToChampion,
      repeatedFailureSignatureCount,
    },
  });
}

export function shouldRunDeepStrategyReview(input: {
  evidence: StrategyReviewEvidence;
  mode?: StrategyReviewRunMode;
  llmAvailable?: boolean;
}): boolean {
  if (!input.llmAvailable) {
    return false;
  }
  if (input.mode === "all") {
    return true;
  }
  if (input.mode === "off") {
    return false;
  }
  return input.evidence.triage.deepReviewRecommended;
}

function buildStrategyReviewRecordMetadata(input: {
  evidence: StrategyReviewEvidence;
  runContext?: ResearchRunContext;
}): Pick<
  StrategyReviewRecord,
  "symbol" | "timeframe" | "goalMode" | "goalProfileId"
> {
  return {
    symbol: input.runContext?.symbol ?? input.evidence.target.symbol,
    timeframe: input.runContext?.timeframe ?? input.evidence.target.timeframe,
    goalMode: input.runContext?.goalMode ?? input.evidence.target.goalMode,
    goalProfileId:
      input.runContext?.goalProfileId ?? input.evidence.target.goalProfileId,
  };
}

export function parseStrategyReviewResponse(
  response: string,
):
  | { success: true; record: ReturnType<typeof strategyReviewLlmResponseSchema.parse> }
  | { success: false; error: string } {
  const candidates = [response, extractJsonObject(response)].filter(
    (value): value is string => typeof value === "string" && value.trim().length > 0,
  );
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      const validated = strategyReviewLlmResponseSchema.safeParse(parsed);
      if (validated.success) {
        return { success: true, record: validated.data };
      }
      return {
        success: false,
        error: validated.error.issues
          .map((issue) => `${issue.path.join(".") || "<root>"}: ${issue.message}`)
          .join("; "),
      };
    } catch {
      continue;
    }
  }
  return { success: false, error: "Response did not contain a parseable JSON object." };
}

export function selectLatestStrategyReviewDirective(input: {
  records: StrategyReviewRecord[];
  targetId: string;
  minConfidence?: number;
  quarantineConfidence?: number;
}): StrategyReviewMutationDirective | null {
  const minConfidence = input.minConfidence ?? 0.7;
  const quarantineConfidence = input.quarantineConfidence ?? 0.85;
  const latest = [...input.records]
    .filter((record) => record.targetId === input.targetId)
    .sort(compareReviewRecency)
    .find((record) => {
      if (record.reviewDecision === "no_action") {
        return false;
      }
      if (record.reviewDecision === "quarantine_family") {
        return record.confidence >= quarantineConfidence;
      }
      return record.confidence >= minConfidence;
    });
  return latest?.mutationDirective ?? null;
}

export function collectSuppressedFamiliesFromReviews(input: {
  records: StrategyReviewRecord[];
  targetId?: string;
  quarantineConfidence?: number;
}): string[] {
  const quarantineConfidence = input.quarantineConfidence ?? 0.85;
  const families = new Set<string>();
  for (const record of input.records) {
    if (input.targetId && record.targetId !== input.targetId) {
      continue;
    }
    if (
      record.reviewDecision !== "quarantine_family" ||
      record.confidence < quarantineConfidence
    ) {
      continue;
    }
    for (const family of [
      record.structureFamilyHash,
      record.fingerprintFamily,
      ...record.mutationDirective.suppressedFamilies,
    ]) {
      if (family) {
        families.add(family);
      }
    }
  }
  return [...families].sort();
}

export function buildStrategyReviewBoard(records: StrategyReviewRecord[]): StrategyReviewBoard {
  const byTarget = new Map<string, StrategyReviewRecord[]>();
  for (const record of records) {
    const groupKey = `${record.targetId}:${record.goalMode ?? "legacy"}`;
    const entries = byTarget.get(groupKey) ?? [];
    entries.push(record);
    byTarget.set(groupKey, entries);
  }
  const targets = [...byTarget.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, targetRecords]) => {
      const sorted = [...targetRecords].sort(compareReviewRecency);
      const latestReview = sorted[0] ?? null;
      const targetId = latestReview?.targetId ?? targetRecords[0]!.targetId;
      const decisionCounts: Record<string, number> = {};
      for (const record of targetRecords) {
        decisionCounts[record.reviewDecision] =
          (decisionCounts[record.reviewDecision] ?? 0) + 1;
      }
      const suppressedFamilies = collectSuppressedFamiliesFromReviews({
        records: targetRecords,
        targetId,
      });
      return {
        targetId,
        symbol: latestReview?.symbol ?? null,
        timeframe: latestReview?.timeframe ?? null,
        goalMode: latestReview?.goalMode,
        goalProfileId: latestReview?.goalProfileId,
        latestReview,
        decisionCounts,
        suppressedFamilies,
        nextMutationFocus: latestReview
          ? [
              ...latestReview.mutationDirective.requiredChanges,
              ...latestReview.mutationDirective.validationFocus,
            ].slice(0, 8)
          : [],
      };
    });

  return {
    schemaVersion: "strategy-review-board/v1",
    generatedAt: new Date().toISOString(),
    targets,
    recentReviews: [...records].sort(compareReviewRecency).slice(0, 50),
  };
}

export function filterStrategyReviewRecordsForTarget(
  records: ExperimentRecord[],
  targetId: string,
  objective?: ObjectiveConfig,
): ExperimentRecord[] {
  return records.filter((record) => {
    const raw = record as Record<string, unknown>;
    const explicitTargetId = stringValue(raw.targetId);
    if (explicitTargetId) {
      return explicitTargetId === targetId;
    }
    const symbol = stringValue(raw.symbol) ?? stringValue(recordValue(raw.chartTarget)?.symbol);
    const timeframe =
      stringValue(raw.timeframe) ?? stringValue(recordValue(raw.chartTarget)?.timeframe);
    if (symbol && timeframe && objective) {
      return (
        symbol.toUpperCase() === objective.symbol.toUpperCase() &&
        timeframe === objective.timeframe
      );
    }
    return objective != null;
  });
}

export function inferStrategyReviewTargetId(
  record: ExperimentRecord,
  targets: ResearchTarget[],
  fallbackTargetId?: string,
): string | null {
  const raw = record as Record<string, unknown>;
  const explicitTargetId = stringValue(raw.targetId);
  if (explicitTargetId) {
    return explicitTargetId;
  }
  const symbol = stringValue(raw.symbol) ?? stringValue(recordValue(raw.chartTarget)?.symbol);
  const timeframe =
    stringValue(raw.timeframe) ?? stringValue(recordValue(raw.chartTarget)?.timeframe);
  if (symbol && timeframe) {
    const matched = targets.find(
      (target) =>
        target.symbol.toUpperCase() === symbol.toUpperCase() &&
        target.timeframe === timeframe,
    );
    if (matched) {
      return matched.id;
    }
  }
  return fallbackTargetId ?? null;
}

function buildTriageReasons(input: {
  record: AutonomousExperimentRecord | null;
  scoreRatioToChampion: number | null;
  repeatedFailureSignatureCount: number;
  calibrationEvent?: CalibrationEventRecord | null;
  activeChampionId: string | null;
  candidateProblems: ProblemEventRecord[];
}): string[] {
  const reasons: string[] = [];
  const record = input.record;
  if (!record) {
    return reasons;
  }
  if (isAutoSelectionEligible(record)) {
    reasons.push("local_eligible");
  }
  if (
    input.scoreRatioToChampion != null &&
    input.scoreRatioToChampion >= 0.85 &&
    !isAutoSelectionEligible(record)
  ) {
    reasons.push("near_miss_85pct_champion");
  }
  if (input.repeatedFailureSignatureCount >= 3) {
    reasons.push("repeated_failure_signature");
  }
  if (
    record.tvCalibrationStatus !== "not_requested" ||
    record.localTvParity != null ||
    record.verifiedPromotion != null
  ) {
    reasons.push("tv_parity_or_walk_forward_candidate");
  }
  if (record.candidateId === input.activeChampionId) {
    reasons.push("active_champion");
  }
  if (
    record.eligibility?.calibrationEligible === true ||
    input.calibrationEvent?.queueState === "queued"
  ) {
    reasons.push("calibration_queue_candidate");
  }
  if (
    record.duplicateStatus?.classification === "structural_duplicate" ||
    record.duplicateStatus?.classification === "exact_duplicate"
  ) {
    reasons.push("duplicate_or_family_collision");
  }
  if (input.candidateProblems.some((event) => event.problemKind === "local_tv_divergence")) {
    reasons.push("local_tv_divergence_problem");
  }
  return [...new Set(reasons)];
}

function buildDeterministicStrategyReview(
  evidence: StrategyReviewEvidence,
  reviewMode: StrategyReviewRecord["reviewMode"],
  fallbackReason?: string,
): Omit<
  StrategyReviewRecord,
  | "targetId"
  | "runId"
  | "iteration"
  | "candidateId"
  | "candidateHash"
  | "structureFamilyHash"
  | "fingerprintFamily"
  | "triageReasons"
  | "evidenceRefs"
  | "evidenceHash"
  | "recordedAt"
> {
  const decision = chooseDeterministicDecision(evidence);
  const directive = buildDirectiveForDecision(decision, evidence, fallbackReason);
  const confidence = deterministicConfidence(decision, evidence);
  return strategyReviewRecordSchema
    .omit({
      targetId: true,
      runId: true,
      iteration: true,
      candidateId: true,
      candidateHash: true,
      structureFamilyHash: true,
      fingerprintFamily: true,
      triageReasons: true,
      evidenceRefs: true,
      evidenceHash: true,
      recordedAt: true,
    })
    .parse({
      schemaVersion: "strategy-review-record/v1",
      reviewMode,
      reviewDecision: decision,
      confidence,
      agentReports: {
        performance: summarizePerformance(evidence),
        robustness: summarizeRobustness(evidence),
        risk: summarizeRisk(evidence),
        novelty: summarizeNovelty(evidence),
        calibration: summarizeCalibration(evidence),
        bull: summarizeBullCase(evidence),
        bear: summarizeBearCase(evidence),
      },
      debateSummary: fallbackReason
        ? `${fallbackReason} Deterministic review selected ${decision}.`
        : `Deterministic triage selected ${decision}.`,
      mutationDirective: directive,
    });
}

function chooseDeterministicDecision(
  evidence: StrategyReviewEvidence,
): StrategyReviewDecision {
  if (evidence.triage.repeatedFailureSignatureCount >= 5) {
    return "quarantine_family";
  }
  if (evidence.triage.reasons.includes("repeated_failure_signature")) {
    return "redirect_family";
  }
  if (
    evidence.novelty.duplicateClassification === "exact_duplicate" ||
    evidence.novelty.duplicateClassification === "structural_duplicate"
  ) {
    return "redirect_family";
  }
  if (
    evidence.triage.reasons.includes("near_miss_85pct_champion") ||
    evidence.objectiveBreakdown?.hardGatesPassed === false
  ) {
    return "repair_near_miss";
  }
  if ((evidence.novelty.complexityPenalty ?? 0) >= 0.08) {
    return "simplify_family";
  }
  if (evidence.triage.reasons.includes("calibration_queue_candidate")) {
    return "calibrate_candidate";
  }
  if (evidence.triage.reasons.includes("local_eligible")) {
    return "exploit_parent";
  }
  return "no_action";
}

function buildDirectiveForDecision(
  decision: StrategyReviewDecision,
  evidence: StrategyReviewEvidence,
  fallbackReason?: string,
): StrategyReviewMutationDirective {
  const family = [
    evidence.candidate.structureFamilyHash,
    evidence.candidate.fingerprintFamily,
  ].filter((value): value is string => value != null && value.length > 0);
  const baseReason = fallbackReason ?? `strategy review decision ${decision}`;
  switch (decision) {
    case "exploit_parent":
      return {
        branchKindBias: "champion_exploit",
        parentCandidateId: evidence.candidate.candidateId,
        requiredChanges: ["preserve_empirical_strengths", "make_one_localized_change"],
        forbiddenPatterns: ["near_duplicate_of_parent"],
        suppressedFamilies: [],
        validationFocus: ["objective_score", "oos_retention"],
        reason: baseReason,
      };
    case "repair_near_miss":
      return {
        branchKindBias: "near_miss_repair",
        parentCandidateId: evidence.candidate.candidateId,
        requiredChanges: [
          "repair_blocking_gate_failure",
          "preserve_near_miss_strengths",
        ],
        forbiddenPatterns: ["broad_rewrite", "add_filters_before_recovering_trades"],
        suppressedFamilies: [],
        validationFocus: ["hard_gates", "walk_forward", "trade_count"],
        reason: baseReason,
      };
    case "redirect_family":
      return {
        branchKindBias: "exploration_breakout",
        parentCandidateId: null,
        requiredChanges: ["rotate_structure_family", "increase_fingerprint_distance"],
        forbiddenPatterns: family.map((value) => `repeat_family:${value}`),
        suppressedFamilies: family,
        validationFocus: ["novelty", "local_compatibility", "trade_count"],
        reason: baseReason,
      };
    case "simplify_family":
      return {
        branchKindBias: "adversarial_simplification",
        parentCandidateId: evidence.candidate.candidateId,
        requiredChanges: [
          "reduce_feature_flags",
          "remove_secondary_filters",
          "lower_complexity_penalty",
        ],
        forbiddenPatterns: ["increase_feature_count", "add_new_regime_gate"],
        suppressedFamilies: [],
        validationFocus: ["complexity", "oos_retention", "trade_count"],
        reason: baseReason,
      };
    case "quarantine_family":
      return {
        branchKindBias: "exploration_breakout",
        parentCandidateId: null,
        requiredChanges: ["avoid_quarantined_family", "start_from_different_structure"],
        forbiddenPatterns: family.map((value) => `quarantined_family:${value}`),
        suppressedFamilies: family,
        validationFocus: ["novelty", "failure_signature"],
        reason: baseReason,
      };
    case "calibrate_candidate":
      return {
        branchKindBias: "frontier_exploit",
        parentCandidateId: evidence.candidate.candidateId,
        requiredChanges: ["preserve_candidate_until_calibration"],
        forbiddenPatterns: ["promotion_without_tv_parity", "skip_walk_forward_gate"],
        suppressedFamilies: [],
        validationFocus: ["local_promotion_readiness", "local_verification"],
        reason: baseReason,
      };
    case "no_action":
      return {
        branchKindBias: null,
        parentCandidateId: null,
        requiredChanges: [],
        forbiddenPatterns: [],
        suppressedFamilies: [],
        validationFocus: [],
        reason: baseReason,
      };
  }
}

function deterministicConfidence(
  decision: StrategyReviewDecision,
  evidence: StrategyReviewEvidence,
): number {
  if (decision === "quarantine_family") {
    return 0.86;
  }
  if (decision === "redirect_family" && evidence.triage.repeatedFailureSignatureCount >= 3) {
    return 0.78;
  }
  if (decision === "repair_near_miss") {
    return 0.74;
  }
  if (decision === "no_action") {
    return 0.6;
  }
  return 0.72;
}

async function appendStrategyReviewParseIncident(input: {
  stateRoot: string;
  runId: string;
  iteration: number;
  candidateId: string;
  detail: string;
}): Promise<void> {
  await appendIncidentRecord(input.stateRoot, {
    runId: input.runId,
    iteration: input.iteration,
    candidateId: input.candidateId,
    category: "system",
    incidentType: "strategy_review_parse_failed",
    detail: input.detail,
  });
}

function summarizePerformance(evidence: StrategyReviewEvidence): string {
  const metrics = evidence.metrics.fullSample;
  if (!metrics) {
    return "No local metrics are available.";
  }
  return `score=${roundNumber(evidence.objectiveBreakdown?.score ?? null)} postFee=${roundNumber(
    metrics.postFeeNetProfitPercent,
  )} pf=${roundNumber(metrics.profitFactor)} trades=${metrics.totalTrades}.`;
}

function summarizeRobustness(evidence: StrategyReviewEvidence): string {
  const oos = evidence.metrics.outOfSample;
  const walk = evidence.metrics.walkForward;
  return `oosPostFee=${roundNumber(oos?.postFeeNetProfitPercent ?? null)} oosTrades=${
    oos?.totalTrades ?? "n/a"
  } walkForward=${walk?.passed ?? "n/a"} reasons=${walk?.gateReasons.join("|") ?? ""}.`;
}

function summarizeRisk(evidence: StrategyReviewEvidence): string {
  const metrics = evidence.metrics.fullSample;
  return `drawdown=${roundNumber(
    metrics?.maxStrategyDrawdownPercent ?? null,
  )} lossZones=${evidence.lossAnalysis.topLossZones.join("|") || "none"}.`;
}

function summarizeNovelty(evidence: StrategyReviewEvidence): string {
  return `duplicate=${evidence.novelty.duplicateClassification ?? "n/a"} family=${
    evidence.candidate.fingerprintFamily ?? evidence.candidate.structureFamilyHash ?? "n/a"
  } complexity=${roundNumber(evidence.novelty.complexityPenalty ?? null)}.`;
}

function summarizeCalibration(evidence: StrategyReviewEvidence): string {
  return `tv=${evidence.calibration.tvCalibrationStatus ?? "n/a"} parity=${
    evidence.calibration.localTvParityStatus ?? "n/a"
  } verifiedEligible=${evidence.calibration.verifiedPromotionEligible ?? "n/a"}.`;
}

function summarizeBullCase(evidence: StrategyReviewEvidence): string {
  return evidence.triage.reasons.includes("local_eligible")
    ? "Candidate has local eligibility or calibration value worth exploiting."
    : "Candidate may still provide failure-memory value for future search.";
}

function summarizeBearCase(evidence: StrategyReviewEvidence): string {
  return evidence.triage.repeatedFailureSignatureCount >= 3
    ? "Failure signature is repeating and should steer away from the family."
    : "Promotion gates remain unchanged and must block unsupported improvements.";
}

function scoreForReview(record: ExperimentRecord | AutonomousExperimentRecord): number | null {
  const raw = record as Record<string, unknown>;
  return (
    numberValue(raw.verifiedPromotionScore) ??
    numberValue(raw.autoSelectionScore) ??
    numberValue(raw.candidateScore) ??
    numberValue(recordValue(raw.objectiveBreakdown)?.score)
  );
}

function bestEligibleReviewScore(records: ExperimentRecord[]): number | null {
  const scores = records
    .map((record) => parseAutonomousExperimentRecord(record))
    .filter((record): record is AutonomousExperimentRecord => record != null)
    .filter((record) => isAutoSelectionEligible(record))
    .map(scoreForReview)
    .filter((value): value is number => value != null);
  return scores.length > 0 ? Math.max(...scores) : null;
}

function extractJsonObject(value: string): string | null {
  const start = value.indexOf("{");
  const end = value.lastIndexOf("}");
  if (start < 0 || end <= start) {
    return null;
  }
  return value.slice(start, end + 1);
}

function compareReviewRecency(
  left: StrategyReviewRecord,
  right: StrategyReviewRecord,
): number {
  const leftTime = Date.parse(left.recordedAt);
  const rightTime = Date.parse(right.recordedAt);
  if (leftTime !== rightTime) {
    return rightTime - leftTime;
  }
  return right.iteration - left.iteration;
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function roundNumber(value: number | null): number | null {
  return value == null || !Number.isFinite(value)
    ? null
    : Math.round(value * 10_000) / 10_000;
}
