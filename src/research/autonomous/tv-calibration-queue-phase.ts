import {
  type AutonomousExperimentRecord,
  type CalibrationEventRecord,
} from "../../contracts/autonomous.js";
import { type ExperimentRecord } from "../../contracts/types.js";
import {
  compareAutonomousChampion,
  selectLocalEvaluationRecords,
} from "../../state/autonomous-state.js";

export const ACTIVE_TV_CALIBRATION_QUEUE_LIMIT = 20;

export function selectPendingCalibrationCandidateIds(input: {
  events: CalibrationEventRecord[];
  experiments: ExperimentRecord[];
}): string[] {
  return selectActiveCalibrationQueueEvents(input).map((event) => event.candidateId);
}

export function selectActiveCalibrationQueueEvents(input: {
  events: CalibrationEventRecord[];
  experiments: ExperimentRecord[];
  limit?: number;
}): CalibrationEventRecord[] {
  return buildRankedPendingCalibrationQueue(input)
    .slice(0, input.limit ?? ACTIVE_TV_CALIBRATION_QUEUE_LIMIT)
    .map((entry) => entry.event);
}

function buildRankedPendingCalibrationQueue(input: {
  events: CalibrationEventRecord[];
  experiments: ExperimentRecord[];
}): Array<{
  event: CalibrationEventRecord;
  record: AutonomousExperimentRecord;
}> {
  const localRecords = selectLocalEvaluationRecords(input.experiments);
  const bestRecordByCandidate = selectBestLocalRecordByCandidate(localRecords);
  const activeLocalCandidateIds = selectActiveLocalCandidateIds(
    [...bestRecordByCandidate.values()],
    ACTIVE_TV_CALIBRATION_QUEUE_LIMIT,
  );
  const latestQueueByCandidate = new Map<string, CalibrationEventRecord>();

  for (const event of input.events.slice().sort(compareCalibrationEventAscending)) {
    latestQueueByCandidate.set(event.candidateId, event);
  }

  return [...latestQueueByCandidate.values()]
    .filter((event) => event.queueState === "queued")
    .flatMap((event) => {
      const record = bestRecordByCandidate.get(event.candidateId);
      return record && activeLocalCandidateIds.has(event.candidateId)
        ? [{ event, record }]
        : [];
    })
    .sort(compareRankedCalibrationQueueEntries);
}

function selectActiveLocalCandidateIds(
  records: AutonomousExperimentRecord[],
  limit: number,
): Set<string> {
  return new Set(
    records
      .slice()
      .sort(compareAutonomousChampion)
      .slice(0, limit)
      .map((record) => record.candidateId),
  );
}

function selectBestLocalRecordByCandidate(
  records: AutonomousExperimentRecord[],
): Map<string, AutonomousExperimentRecord> {
  const bestRecordByCandidate = new Map<string, AutonomousExperimentRecord>();
  for (const record of records) {
    const current = bestRecordByCandidate.get(record.candidateId);
    if (!current || compareLocalRecordQuality(record, current) < 0) {
      bestRecordByCandidate.set(record.candidateId, record);
    }
  }
  return bestRecordByCandidate;
}

function compareRankedCalibrationQueueEntries(
  left: { event: CalibrationEventRecord; record: AutonomousExperimentRecord },
  right: { event: CalibrationEventRecord; record: AutonomousExperimentRecord },
): number {
  const recordComparison = compareLocalRecordQuality(left.record, right.record);
  if (recordComparison !== 0) {
    return recordComparison;
  }

  const leftRecordedAt = timestamp(left.event.recordedAt);
  const rightRecordedAt = timestamp(right.event.recordedAt);
  if (leftRecordedAt !== rightRecordedAt) {
    return rightRecordedAt - leftRecordedAt;
  }
  if (left.event.iteration !== right.event.iteration) {
    return right.event.iteration - left.event.iteration;
  }
  return left.event.candidateId.localeCompare(right.event.candidateId);
}

function compareLocalRecordQuality(
  left: AutonomousExperimentRecord,
  right: AutonomousExperimentRecord,
): number {
  return (
    compareDesc(selectionScore(left), selectionScore(right)) ||
    compareDesc(performanceScore(left), performanceScore(right)) ||
    compareDesc(postFeeReturnPercent(left), postFeeReturnPercent(right)) ||
    compareDesc(profitFactor(left), profitFactor(right)) ||
    compareAsc(drawdownPercent(left), drawdownPercent(right)) ||
    compareDesc(totalTrades(left), totalTrades(right)) ||
    compareDesc(noveltyScore(left), noveltyScore(right)) ||
    compareDesc(timestamp(left.recordedAt), timestamp(right.recordedAt)) ||
    (right.iteration - left.iteration) ||
    left.candidateId.localeCompare(right.candidateId)
  );
}

function selectionScore(record: AutonomousExperimentRecord): number {
  return finiteNumber(
    record.localFrontierScore ??
      record.autoSelectionScore ??
      record.candidateScore ??
      Number.NEGATIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
  );
}

function performanceScore(record: AutonomousExperimentRecord): number {
  return finiteNumber(
    record.autoSelectionBreakdown?.performanceScore ??
      record.autoSelectionBreakdown?.baseObjectiveScore ??
      record.splitEvaluation?.outOfSample.objectiveBreakdown?.score ??
      record.objectiveBreakdown?.score ??
      Number.NEGATIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
  );
}

function postFeeReturnPercent(record: AutonomousExperimentRecord): number {
  return finiteNumber(
    record.splitEvaluation?.outOfSample.metrics?.postFeeNetProfitPercent ??
      record.testerMetrics?.postFeeNetProfitPercent ??
      record.testerMetrics?.netProfitPercent ??
      Number.NEGATIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
  );
}

function profitFactor(record: AutonomousExperimentRecord): number {
  return finiteNumber(
    record.splitEvaluation?.outOfSample.metrics?.profitFactor ??
      record.testerMetrics?.profitFactor ??
      Number.NEGATIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
  );
}

function drawdownPercent(record: AutonomousExperimentRecord): number {
  return finiteNumber(
    record.splitEvaluation?.outOfSample.metrics?.maxStrategyDrawdownPercent ??
      record.testerMetrics?.maxStrategyDrawdownPercent ??
      Number.POSITIVE_INFINITY,
    Number.POSITIVE_INFINITY,
  );
}

function totalTrades(record: AutonomousExperimentRecord): number {
  return finiteNumber(
    record.splitEvaluation?.outOfSample.metrics?.totalTrades ??
      record.testerMetrics?.totalTrades ??
      Number.NEGATIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
  );
}

function noveltyScore(record: AutonomousExperimentRecord): number {
  return finiteNumber(record.autoSelectionBreakdown?.noveltyScore ?? 0, 0);
}

function compareDesc(left: number, right: number): number {
  if (left === right) {
    return 0;
  }
  return right > left ? 1 : -1;
}

function compareAsc(left: number, right: number): number {
  if (left === right) {
    return 0;
  }
  return left > right ? 1 : -1;
}

function finiteNumber(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

function timestamp(value: string | null | undefined): number {
  const parsed = Date.parse(value ?? "");
  return Number.isFinite(parsed) ? parsed : 0;
}

function compareCalibrationEventAscending(
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
