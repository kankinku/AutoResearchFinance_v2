import { type ExperimentRecord } from "../contracts/types.js";
import {
  autonomousExperimentSchema,
  type AutonomousExperimentRecord,
  type HeadEventRecord,
} from "../contracts/autonomous.js";
import { sha256Json } from "../utils/fs.js";

export function parseAutonomousExperimentRecord(
  record: ExperimentRecord,
): AutonomousExperimentRecord | null {
  const parsed = autonomousExperimentSchema.safeParse(record);
  return parsed.success ? parsed.data : null;
}

export function selectAutonomousExperimentRecords(
  records: ExperimentRecord[],
): AutonomousExperimentRecord[] {
  return records
    .map((record) => parseAutonomousExperimentRecord(record))
    .filter((record): record is AutonomousExperimentRecord => record !== null);
}

export function selectLocalEvaluationRecords(
  records: ExperimentRecord[],
): AutonomousExperimentRecord[] {
  return selectAutonomousExperimentRecords(records).filter(
    (record) => record.recordKind === "local_evaluation",
  );
}

export function selectTvVerificationRecords(
  records: ExperimentRecord[],
): AutonomousExperimentRecord[] {
  return selectAutonomousExperimentRecords(records).filter(
    (record) => record.recordKind === "tv_verification",
  );
}

export function isAutoSelectionEligible(record: AutonomousExperimentRecord): boolean {
  return (
    record.eligibility?.autoSelectionEligible === true ||
    record.autoSelectionBreakdown?.eligible === true
  );
}

export function compareAutonomousChampion(
  left: AutonomousExperimentRecord,
  right: AutonomousExperimentRecord,
): number {
  const leftScore = left.autoSelectionScore ?? Number.NEGATIVE_INFINITY;
  const rightScore = right.autoSelectionScore ?? Number.NEGATIVE_INFINITY;
  if (leftScore !== rightScore) {
    return rightScore - leftScore;
  }

  const leftOosScore =
    left.splitEvaluation?.outOfSample.objectiveBreakdown?.score ?? Number.NEGATIVE_INFINITY;
  const rightOosScore =
    right.splitEvaluation?.outOfSample.objectiveBreakdown?.score ?? Number.NEGATIVE_INFINITY;
  if (leftOosScore !== rightOosScore) {
    return rightOosScore - leftOosScore;
  }

  const leftDrawdown =
    left.splitEvaluation?.outOfSample.metrics?.maxStrategyDrawdownPercent ??
    left.testerMetrics?.maxStrategyDrawdownPercent ??
    Number.POSITIVE_INFINITY;
  const rightDrawdown =
    right.splitEvaluation?.outOfSample.metrics?.maxStrategyDrawdownPercent ??
    right.testerMetrics?.maxStrategyDrawdownPercent ??
    Number.POSITIVE_INFINITY;
  if (leftDrawdown !== rightDrawdown) {
    return leftDrawdown - rightDrawdown;
  }

  const leftTrades =
    left.splitEvaluation?.outOfSample.metrics?.totalTrades ??
    left.testerMetrics?.totalTrades ??
    Number.NEGATIVE_INFINITY;
  const rightTrades =
    right.splitEvaluation?.outOfSample.metrics?.totalTrades ??
    right.testerMetrics?.totalTrades ??
    Number.NEGATIVE_INFINITY;
  if (leftTrades !== rightTrades) {
    return rightTrades - leftTrades;
  }

  if (left.iteration !== right.iteration) {
    return right.iteration - left.iteration;
  }

  return left.candidateId.localeCompare(right.candidateId);
}

export function selectBestAutonomousChampionCandidate(
  records: ExperimentRecord[],
): AutonomousExperimentRecord | null {
  const eligible = selectLocalEvaluationRecords(records).filter(isAutoSelectionEligible);
  if (eligible.length === 0) {
    return null;
  }

  return [...eligible].sort(compareAutonomousChampion)[0] ?? null;
}

export function findActiveChampionCandidateId(
  headEvents: HeadEventRecord[],
): string | null {
  const sorted = [...headEvents].sort((left, right) => {
    const leftRecordedAt = Date.parse(left.recordedAt ?? "");
    const rightRecordedAt = Date.parse(right.recordedAt ?? "");
    if (leftRecordedAt !== rightRecordedAt) {
      return rightRecordedAt - leftRecordedAt;
    }
    if (left.iteration !== right.iteration) {
      return right.iteration - left.iteration;
    }
    return right.candidateId.localeCompare(left.candidateId);
  });

  return sorted[0]?.candidateId ?? null;
}

export function findActiveChampionRecord(input: {
  records: ExperimentRecord[];
  headEvents: HeadEventRecord[];
}): AutonomousExperimentRecord | null {
  const championId = findActiveChampionCandidateId(input.headEvents);
  if (!championId) {
    return null;
  }

  const localRecords = selectLocalEvaluationRecords(input.records)
    .filter((record) => record.candidateId === championId)
    .sort(compareAutonomousChampion);
  return localRecords[0] ?? null;
}

export function buildSelectionEvidenceHash(
  record: AutonomousExperimentRecord,
  options?: {
    previousChampionId?: string | null;
    policyVersion?: string | null;
  },
): string {
  return sha256Json({
    candidateId: record.candidateId,
    candidateHash: record.candidateHash,
    autoSelectionScore: record.autoSelectionScore,
    autoSelectionBreakdown: record.autoSelectionBreakdown,
    rejectionReasons: record.autoSelectionBreakdown?.rejectionReasons ?? [],
    previousChampionId: options?.previousChampionId ?? null,
    policyVersion: options?.policyVersion ?? record.selectionPolicyVersion,
  });
}
