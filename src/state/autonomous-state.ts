import { type ExperimentRecord } from "../contracts/types.js";
import {
  autonomousExperimentSchema,
  type AutonomousExperimentRecord,
  type HeadEventRecord,
} from "../contracts/autonomous.js";
import {
  AUTORESEARCH_CONTRACT_VERSION,
  STRATEGY_SPEC_MUTATION_AUTHORITY,
} from "../policy/autoresearch-contract.js";
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

export function isVerifiedPromotionEligible(input: {
  record: AutonomousExperimentRecord;
  localRecords: AutonomousExperimentRecord[];
}): boolean {
  if (input.record.recordKind !== "tv_verification") {
    return false;
  }
  const matchingLocalRecord = input.localRecords.find(
    (localRecord) =>
      localRecord.recordKind === "local_evaluation" &&
      localRecord.candidateId === input.record.candidateId &&
      localRecord.candidateHash === input.record.candidateHash,
  );
  const parityStatus = input.record.localTvParity?.status;
  const tradeParityStatus = input.record.localTvParity?.tradeParity?.status;
  const eventParityStatus = input.record.localTvParity?.eventParity?.status;
  const verifiedPromotion = input.record.verifiedPromotion;
  const specAuthorityMatches =
    matchingLocalRecord != null &&
    input.record.contractVersion === AUTORESEARCH_CONTRACT_VERSION &&
    matchingLocalRecord.contractVersion === AUTORESEARCH_CONTRACT_VERSION &&
    input.record.mutationAuthority === STRATEGY_SPEC_MUTATION_AUTHORITY &&
    matchingLocalRecord.mutationAuthority === STRATEGY_SPEC_MUTATION_AUTHORITY &&
    typeof input.record.specHash === "string" &&
    input.record.specHash.length > 0 &&
    input.record.specHash === matchingLocalRecord.specHash &&
    typeof input.record.specPath === "string" &&
    input.record.specPath.length > 0 &&
    input.record.specPath === matchingLocalRecord.specPath;
  return (
    matchingLocalRecord != null &&
    specAuthorityMatches &&
    input.record.tvCalibrationStatus === "verified_match" &&
    parityStatus === "matched" &&
    tradeParityStatus === "matched" &&
    eventParityStatus === "matched" &&
    input.record.walkForwardEvaluation?.passed === true &&
    verifiedPromotion?.eligible === true &&
    verifiedPromotion.localCandidateHash === matchingLocalRecord.candidateHash &&
    verifiedPromotion.tvCandidateHash === input.record.candidateHash &&
    typeof input.record.verifiedPromotionScore === "number"
  );
}

export function compareAutonomousChampion(
  left: AutonomousExperimentRecord,
  right: AutonomousExperimentRecord,
): number {
  const leftScore =
    left.localFrontierScore ??
    left.autoSelectionScore ??
    Number.NEGATIVE_INFINITY;
  const rightScore =
    right.localFrontierScore ??
    right.autoSelectionScore ??
    Number.NEGATIVE_INFINITY;
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

export function compareVerifiedPromotionCandidate(
  left: AutonomousExperimentRecord,
  right: AutonomousExperimentRecord,
): number {
  const leftScore =
    left.verifiedPromotionScore ??
    left.verifiedPromotion?.score ??
    Number.NEGATIVE_INFINITY;
  const rightScore =
    right.verifiedPromotionScore ??
    right.verifiedPromotion?.score ??
    Number.NEGATIVE_INFINITY;
  if (leftScore !== rightScore) {
    return rightScore - leftScore;
  }

  const leftOosProfit =
    left.walkForwardEvaluation?.medianOosPostFeeNetProfitPercent ??
    Number.NEGATIVE_INFINITY;
  const rightOosProfit =
    right.walkForwardEvaluation?.medianOosPostFeeNetProfitPercent ??
    Number.NEGATIVE_INFINITY;
  if (leftOosProfit !== rightOosProfit) {
    return rightOosProfit - leftOosProfit;
  }

  const leftDrawdown =
    left.walkForwardEvaluation?.worstFoldDrawdownPercent ??
    left.testerMetrics?.maxStrategyDrawdownPercent ??
    Number.POSITIVE_INFINITY;
  const rightDrawdown =
    right.walkForwardEvaluation?.worstFoldDrawdownPercent ??
    right.testerMetrics?.maxStrategyDrawdownPercent ??
    Number.POSITIVE_INFINITY;
  if (leftDrawdown !== rightDrawdown) {
    return leftDrawdown - rightDrawdown;
  }

  if (left.iteration !== right.iteration) {
    return right.iteration - left.iteration;
  }

  return left.candidateId.localeCompare(right.candidateId);
}

export function selectBestLocalFrontierCandidate(
  records: ExperimentRecord[],
): AutonomousExperimentRecord | null {
  const eligible = selectLocalEvaluationRecords(records).filter(isAutoSelectionEligible);
  if (eligible.length === 0) {
    return null;
  }

  return [...eligible].sort(compareAutonomousChampion)[0] ?? null;
}

export function selectBestTvVerifiedCandidate(
  records: ExperimentRecord[],
): AutonomousExperimentRecord | null {
  const localRecords = selectLocalEvaluationRecords(records);
  const eligible = selectTvVerificationRecords(records).filter((record) =>
    isVerifiedPromotionEligible({ record, localRecords }),
  );
  if (eligible.length === 0) {
    return null;
  }

  return [...eligible].sort(compareVerifiedPromotionCandidate)[0] ?? null;
}

export function selectBestChampionCandidate(
  records: ExperimentRecord[],
): AutonomousExperimentRecord | null {
  return selectBestTvVerifiedCandidate(records);
}

export function selectBestAutonomousChampionCandidate(
  records: ExperimentRecord[],
): AutonomousExperimentRecord | null {
  return selectBestChampionCandidate(records);
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

  const localRecords = selectLocalEvaluationRecords(input.records);
  const tvRecords = selectTvVerificationRecords(input.records)
    .filter((record) => record.candidateId === championId)
    .filter((record) => isVerifiedPromotionEligible({ record, localRecords }))
    .sort(compareVerifiedPromotionCandidate);
  if (tvRecords[0]) {
    return tvRecords[0];
  }

  const matchingLocalRecords = localRecords
    .filter((record) => record.candidateId === championId)
    .sort(compareAutonomousChampion);
  return matchingLocalRecords[0] ?? null;
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
    specHash: record.specHash,
    contractVersion: record.contractVersion,
    mutationAuthority: record.mutationAuthority,
    localFrontierScore: record.localFrontierScore ?? record.autoSelectionScore,
    verifiedPromotionScore: record.verifiedPromotionScore,
    autoSelectionScore: record.autoSelectionScore,
    autoSelectionBreakdown: record.autoSelectionBreakdown,
    verifiedPromotion: record.verifiedPromotion,
    rejectionReasons: record.autoSelectionBreakdown?.rejectionReasons ?? [],
    previousChampionId: options?.previousChampionId ?? null,
    policyVersion: options?.policyVersion ?? record.selectionPolicyVersion,
  });
}
