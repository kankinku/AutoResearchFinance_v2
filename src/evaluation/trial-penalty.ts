import { type ExperimentRecord } from "../contracts/types.js";

export interface TrialLedgerStats {
  totalCandidatesTried: number;
  totalLocalPass: number;
  totalTvVerified: number;
  totalPromotionCandidates: number;
  familyTrials: number;
  fingerprintFamilyTrials: number;
  parameterNeighborhoodTrials: number;
  oosExposureCount: number;
  canaryExposureCount: number;
}

export function buildTrialLedgerStats(input: {
  referenceExperiments: ExperimentRecord[];
  structureFamilyHash?: string | null;
  fingerprintFamily?: string | null;
  parameterNeighborhood?: string | null;
}): TrialLedgerStats {
  const experiments = input.referenceExperiments;
  const withCandidateHash = experiments.filter((record) => record.candidateHash);
  const localPass = experiments.filter((record) => {
    const raw = record as Record<string, unknown>;
    return (
      raw.recordKind === "local_evaluation" &&
      raw.eligibility != null &&
      (raw.eligibility as { autoSelectionEligible?: unknown }).autoSelectionEligible === true
    );
  });
  const tvVerified = experiments.filter((record) => {
    const raw = record as Record<string, unknown>;
    return raw.recordKind === "tv_verification" && raw.tvCalibrationStatus === "verified_match";
  });
  const promotionCandidates = experiments.filter((record) => {
    const raw = record as Record<string, unknown>;
    return (raw.verifiedPromotion as { eligible?: unknown } | undefined)?.eligible === true;
  });
  const familyTrials = input.structureFamilyHash
    ? experiments.filter(
        (record) =>
          (record as Record<string, unknown>).structureFamilyHash === input.structureFamilyHash,
      ).length
    : 0;
  const fingerprintFamilyTrials = input.fingerprintFamily
    ? experiments.filter(
        (record) =>
          (record as Record<string, unknown>).fingerprintFamily === input.fingerprintFamily,
      ).length
    : 0;
  const parameterNeighborhoodTrials = input.parameterNeighborhood
    ? experiments.filter(
        (record) =>
          readParameterNeighborhood(record) === input.parameterNeighborhood,
      ).length
    : 0;
  const oosExposureCount = experiments.filter((record) => {
    const raw = record as Record<string, unknown>;
    return raw.splitEvaluation != null || raw.walkForwardEvaluation != null;
  }).length;
  const canaryExposureCount = experiments.filter((record) => {
    const raw = record as Record<string, unknown>;
    const canary = raw.canaryHoldout as { exposed?: unknown } | undefined;
    return canary?.exposed === true;
  }).length;

  return {
    totalCandidatesTried: withCandidateHash.length,
    totalLocalPass: localPass.length,
    totalTvVerified: tvVerified.length,
    totalPromotionCandidates: promotionCandidates.length,
    familyTrials,
    fingerprintFamilyTrials,
    parameterNeighborhoodTrials,
    oosExposureCount,
    canaryExposureCount,
  };
}

export function computeTrialBudgetPenaltyFromStats(stats: TrialLedgerStats): number {
  const globalPenalty =
    stats.totalCandidatesTried < 100
      ? 0
      : stats.totalCandidatesTried < 1_000
        ? 0.04
        : 0.08;
  const familyPenalty = Math.min(
    0.06,
    stats.familyTrials * 0.002 +
      stats.fingerprintFamilyTrials * 0.001 +
      stats.parameterNeighborhoodTrials * 0.001,
  );
  const exposurePenalty = Math.min(0.04, stats.oosExposureCount * 0.0005);
  return roundScore(globalPenalty + familyPenalty + exposurePenalty);
}

export function computeMinimumVerifiedPromotionScoreFromStats(
  stats: TrialLedgerStats,
): number {
  const base =
    stats.totalCandidatesTried < 100
      ? 0.62
      : stats.totalCandidatesTried < 1_000
        ? 0.68
        : 0.74;
  const familyAdjustment =
    stats.familyTrials >= 50 || stats.fingerprintFamilyTrials >= 75 ? 0.03 : 0;
  const canaryAdjustment = stats.canaryExposureCount > 0 ? 0.05 : 0;
  return roundScore(base + familyAdjustment + canaryAdjustment);
}

function readParameterNeighborhood(record: ExperimentRecord): string | null {
  const raw = record as Record<string, unknown>;
  const fingerprint = raw.noveltyFingerprint as
    | { configBuckets?: Record<string, string> }
    | undefined;
  const buckets = fingerprint?.configBuckets;
  if (!buckets) {
    return null;
  }
  return Object.entries(buckets)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}:${value}`)
    .join("|");
}

function roundScore(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}
