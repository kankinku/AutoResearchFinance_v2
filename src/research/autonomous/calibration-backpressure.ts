export const CALIBRATION_BACKPRESSURE_PENDING_THRESHOLD = 100;

export type CalibrationBackpressureAction =
  | "process_tv_calibration_queue"
  | "diagnose_local_tv_parity"
  | "repair_traceability_recovery";

export interface CalibrationBackpressure {
  active: boolean;
  pendingCalibrationCandidateCount: number;
  threshold: number;
  recommendedAction: CalibrationBackpressureAction | null;
  reasons: string[];
}

export function buildCalibrationBackpressure(input: {
  pendingCalibrationCandidateCount: number;
  parityStatusCounts?: Record<string, number> | null;
  repairTraceabilityStatus?: unknown;
  threshold?: number;
}): CalibrationBackpressure {
  const threshold = input.threshold ?? CALIBRATION_BACKPRESSURE_PENDING_THRESHOLD;
  const pendingCalibrationCandidateCount = input.pendingCalibrationCandidateCount;
  const active = pendingCalibrationCandidateCount >= threshold;
  const reasons: string[] = [];

  if (active) {
    reasons.push(
      `pending calibration queue has ${pendingCalibrationCandidateCount} candidates, threshold ${threshold}`,
    );
  }

  const repairTraceabilityFailing = input.repairTraceabilityStatus === "failing";
  if (active && repairTraceabilityFailing) {
    reasons.push("stage6 repair traceability is failing");
  }

  const majorDrift = input.parityStatusCounts?.major_drift ?? 0;
  const matched = input.parityStatusCounts?.matched ?? 0;
  if (active && majorDrift > matched) {
    reasons.push(`TradingView parity drift exceeds matches (${majorDrift} > ${matched})`);
  }

  const recommendedAction: CalibrationBackpressureAction | null = !active
    ? null
    : repairTraceabilityFailing
      ? "repair_traceability_recovery"
      : majorDrift > matched
        ? "diagnose_local_tv_parity"
        : "process_tv_calibration_queue";

  return {
    active,
    pendingCalibrationCandidateCount,
    threshold,
    recommendedAction,
    reasons,
  };
}
