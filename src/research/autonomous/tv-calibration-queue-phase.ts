import { type CalibrationEventRecord } from "../../contracts/autonomous.js";
import { type ExperimentRecord } from "../../contracts/types.js";
import { selectLocalEvaluationRecords } from "../../state/autonomous-state.js";

export function selectPendingCalibrationCandidateIds(input: {
  events: CalibrationEventRecord[];
  experiments: ExperimentRecord[];
}): string[] {
  const localRecords = selectLocalEvaluationRecords(input.experiments);
  const latestQueueByCandidate = new Map<string, CalibrationEventRecord>();

  for (const event of input.events.slice().sort(compareCalibrationEventAscending)) {
    latestQueueByCandidate.set(event.candidateId, event);
  }

  return [...latestQueueByCandidate.values()]
    .filter((event) => event.queueState === "queued")
    .filter((event) =>
      localRecords.some((record) => record.candidateId === event.candidateId),
    )
    .sort((left, right) => {
      const leftRecordedAt = Date.parse(left.recordedAt ?? "") || 0;
      const rightRecordedAt = Date.parse(right.recordedAt ?? "") || 0;
      if (leftRecordedAt !== rightRecordedAt) {
        return rightRecordedAt - leftRecordedAt;
      }
      if (left.iteration !== right.iteration) {
        return right.iteration - left.iteration;
      }
      const leftRecord = localRecords.find((record) => record.candidateId === left.candidateId);
      const rightRecord = localRecords.find((record) => record.candidateId === right.candidateId);
      const leftScore = leftRecord?.autoSelectionScore ?? Number.NEGATIVE_INFINITY;
      const rightScore = rightRecord?.autoSelectionScore ?? Number.NEGATIVE_INFINITY;
      if (leftScore !== rightScore) {
        return rightScore - leftScore;
      }
      const leftNovelty = leftRecord?.autoSelectionBreakdown?.noveltyScore ?? 0;
      const rightNovelty = rightRecord?.autoSelectionBreakdown?.noveltyScore ?? 0;
      return rightNovelty - leftNovelty;
    })
    .map((event) => event.candidateId);
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
