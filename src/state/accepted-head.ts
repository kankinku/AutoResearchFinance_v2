import { type ExperimentRecord } from "../contracts/types.js";
import {
  buildEligibilityContext,
  evaluatePromotedHeadEligibility,
  evaluateVerifiedViewEligibility,
  resolveRecordEra,
} from "../evaluation/record-eligibility.js";

const ACTIVE_HEAD_SCORE_EPSILON = 1e-6;

function buildRecordIndex(
  records: ExperimentRecord[],
): Map<string, ExperimentRecord> {
  return new Map(records.map((record) => [record.candidateId, record]));
}

function isDescendantOf(
  record: ExperimentRecord,
  ancestorCandidateId: string,
  recordIndex: Map<string, ExperimentRecord>,
): boolean {
  let currentParentCandidateId = record.parentCandidateId;
  const visited = new Set<string>();

  while (currentParentCandidateId) {
    if (currentParentCandidateId === ancestorCandidateId) {
      return true;
    }

    if (visited.has(currentParentCandidateId)) {
      break;
    }
    visited.add(currentParentCandidateId);
    currentParentCandidateId =
      recordIndex.get(currentParentCandidateId)?.parentCandidateId ?? null;
  }

  return false;
}

function compareAcceptedImprovementRecords(
  left: ExperimentRecord,
  right: ExperimentRecord,
): number {
  const leftScore = left.candidateScore ?? Number.NEGATIVE_INFINITY;
  const rightScore = right.candidateScore ?? Number.NEGATIVE_INFINITY;
  if (leftScore !== rightScore) {
    return rightScore - leftScore;
  }

  if (left.iteration !== right.iteration) {
    return right.iteration - left.iteration;
  }

  return left.candidateId.localeCompare(right.candidateId);
}

function isLegacyAcceptedImprovementRecord(record: ExperimentRecord): boolean {
  return (
    resolveRecordEra(record) === "legacy" && record.decision === "accepted_improvement"
  );
}

function compareActiveHeadRecords(
  left: ExperimentRecord,
  right: ExperimentRecord,
): number {
  const leftScore = getCandidateScore(left);
  const rightScore = getCandidateScore(right);
  if (leftScore !== rightScore) {
    return rightScore - leftScore;
  }

  const leftNet = getPostFeeNetProfitPercent(left);
  const rightNet = getPostFeeNetProfitPercent(right);
  if (leftNet !== rightNet) {
    return rightNet - leftNet;
  }

  const leftTrades = getTradeCount(left);
  const rightTrades = getTradeCount(right);
  if (leftTrades !== rightTrades) {
    return rightTrades - leftTrades;
  }

  const leftDrawdown =
    left.testerMetrics?.maxStrategyDrawdownPercent ?? Number.POSITIVE_INFINITY;
  const rightDrawdown =
    right.testerMetrics?.maxStrategyDrawdownPercent ?? Number.POSITIVE_INFINITY;
  if (leftDrawdown !== rightDrawdown) {
    return leftDrawdown - rightDrawdown;
  }

  if (left.iteration !== right.iteration) {
    return right.iteration - left.iteration;
  }

  return left.candidateId.localeCompare(right.candidateId);
}

function hasActionableLossAnalysis(record: ExperimentRecord): boolean {
  const summary = record.lossAnalysisSummary;
  return (
    summary?.status === "available" &&
    ((summary.topLossZones?.length ?? 0) > 0 ||
      (summary.repairPriorities?.length ?? 0) > 0)
  );
}

function getCandidateScore(record: ExperimentRecord): number {
  return record.candidateScore ?? Number.NEGATIVE_INFINITY;
}

function getTradeCount(record: ExperimentRecord): number {
  return record.testerMetrics?.totalTrades ?? 0;
}

function getPostFeeNetProfitPercent(record: ExperimentRecord): number {
  return record.testerMetrics?.postFeeNetProfitPercent ?? Number.NEGATIVE_INFINITY;
}

function buildTradeRetentionTarget(
  acceptedRecord: ExperimentRecord | null,
  minimumTotalTrades: number,
): number | null {
  const totalTrades = acceptedRecord?.testerMetrics?.totalTrades;
  if (totalTrades === undefined || totalTrades < minimumTotalTrades) {
    return null;
  }

  return Math.max(minimumTotalTrades, Math.ceil(totalTrades * 0.7));
}

function isCurrentAcceptedHeadLineage(
  record: ExperimentRecord,
  acceptedHeadCandidateId: string | null,
  recordIndex: Map<string, ExperimentRecord>,
): boolean {
  if (!acceptedHeadCandidateId) {
    return true;
  }

  return (
    record.candidateId === acceptedHeadCandidateId ||
    record.acceptedHeadCandidateId === acceptedHeadCandidateId ||
    isDescendantOf(record, acceptedHeadCandidateId, recordIndex)
  );
}

function isHeadEquivalentDescendant(
  record: ExperimentRecord,
  acceptedRecord: ExperimentRecord,
  recordIndex: Map<string, ExperimentRecord>,
): boolean {
  if (
    record.candidateId === acceptedRecord.candidateId ||
    !isDescendantOf(record, acceptedRecord.candidateId, recordIndex)
  ) {
    return false;
  }

  if (!record.objectiveBreakdown?.hardGatesPassed) {
    return false;
  }

  if (
    acceptedRecord.candidateScore === undefined ||
    acceptedRecord.candidateScore === null ||
    record.candidateScore === undefined ||
    record.candidateScore === null
  ) {
    return false;
  }

  return (
    Math.abs(record.candidateScore - acceptedRecord.candidateScore) <=
    ACTIVE_HEAD_SCORE_EPSILON
  );
}

function getGuidanceTier(
  record: ExperimentRecord,
  options: {
    acceptedHeadCandidateId: string | null;
    minimumTotalTrades: number;
    salvageTradeFloor: number;
    tradeRetentionTarget: number | null;
  },
): number {
  const trades = getTradeCount(record);

  if (
    options.acceptedHeadCandidateId &&
    record.candidateId === options.acceptedHeadCandidateId
  ) {
    return 5;
  }

  if (record.objectiveBreakdown?.hardGatesPassed) {
    return 4;
  }

  if (
    options.tradeRetentionTarget !== null &&
    trades >= options.tradeRetentionTarget
  ) {
    return 3;
  }

  if (trades >= options.minimumTotalTrades) {
    return 2;
  }

  if (trades >= options.salvageTradeFloor) {
    return 1;
  }

  return 0;
}

function compareGuidanceRecords(
  left: ExperimentRecord,
  right: ExperimentRecord,
  options: {
    acceptedHeadCandidateId: string | null;
    minimumTotalTrades: number;
    salvageTradeFloor: number;
    tradeRetentionTarget: number | null;
  },
): number {
  const leftTier = getGuidanceTier(left, options);
  const rightTier = getGuidanceTier(right, options);
  if (leftTier !== rightTier) {
    return rightTier - leftTier;
  }

  const leftScore = getCandidateScore(left);
  const rightScore = getCandidateScore(right);
  if (leftScore !== rightScore) {
    return rightScore - leftScore;
  }

  const leftTrades = getTradeCount(left);
  const rightTrades = getTradeCount(right);
  if (leftTrades !== rightTrades) {
    return rightTrades - leftTrades;
  }

  const leftNet = getPostFeeNetProfitPercent(left);
  const rightNet = getPostFeeNetProfitPercent(right);
  if (leftNet !== rightNet) {
    return rightNet - leftNet;
  }

  if (left.iteration !== right.iteration) {
    return right.iteration - left.iteration;
  }

  return left.candidateId.localeCompare(right.candidateId);
}

export function findBestVerifiedRecord(
  records: ExperimentRecord[],
): ExperimentRecord | null {
  const context = buildEligibilityContext(records);
  const verified = records.filter((record) =>
    record.decision === "promoted_head" || record.promotionStatus === "promoted_head"
      ? evaluatePromotedHeadEligibility(record, context).ok
      : evaluateVerifiedViewEligibility(record).ok,
  );
  if (verified.length > 0) {
    return [...verified].sort(compareAcceptedImprovementRecords)[0] ?? null;
  }

  return null;
}

export function findBestAcceptedRecord(
  records: ExperimentRecord[],
): ExperimentRecord | null {
  const verified = findBestVerifiedRecord(records);
  if (verified) {
    return verified;
  }

  return findLegacyAcceptedRecord(records);
}

export function findLegacyAcceptedRecord(
  records: ExperimentRecord[],
): ExperimentRecord | null {
  const accepted = records.filter(isLegacyAcceptedImprovementRecord);
  if (accepted.length === 0) {
    return null;
  }

  return [...accepted].sort(compareAcceptedImprovementRecords)[0] ?? null;
}

export function findActiveHeadRecord(
  records: ExperimentRecord[],
  _acceptedRecord: ExperimentRecord | null = findBestAcceptedRecord(records),
): ExperimentRecord | null {
  const context = buildEligibilityContext(records);
  const promoted = records.filter((record) =>
    evaluatePromotedHeadEligibility(record, context).ok,
  );
  if (promoted.length === 0) {
    return null;
  }
  return [...promoted].sort(compareActiveHeadRecords)[0] ?? null;
}

export function findMutationGuidanceRecord(
  records: ExperimentRecord[],
  options: {
    acceptedRecord: ExperimentRecord | null;
    minimumTotalTrades: number;
  },
): ExperimentRecord | null {
  const acceptedHeadCandidateId = options.acceptedRecord?.candidateId ?? null;
  const tradeRetentionTarget = buildTradeRetentionTarget(
    options.acceptedRecord,
    options.minimumTotalTrades,
  );
  const salvageTradeFloor = Math.max(
    Math.ceil(options.minimumTotalTrades * 0.75),
    tradeRetentionTarget === null ? 0 : Math.ceil(tradeRetentionTarget * 0.65),
  );

  const actionable = records.filter(hasActionableLossAnalysis);
  if (actionable.length === 0) {
    return null;
  }

  const recordIndex = buildRecordIndex(records);
  const scoped = actionable.filter((record) =>
    isCurrentAcceptedHeadLineage(record, acceptedHeadCandidateId, recordIndex),
  );
  const lineagePool = scoped.length > 0 ? scoped : actionable;
  const profitablePool = lineagePool.filter(
    (record) => getPostFeeNetProfitPercent(record) > 0,
  );
  const selectedPool = profitablePool.length > 0 ? profitablePool : lineagePool;

  return (
    [...selectedPool].sort((left, right) =>
      compareGuidanceRecords(left, right, {
        acceptedHeadCandidateId,
        minimumTotalTrades: options.minimumTotalTrades,
        salvageTradeFloor,
        tradeRetentionTarget,
      }),
    )[0] ?? null
  );
}
