import { type ExperimentRecord } from "../contracts/types.js";
import { parseAfStrategySpec } from "../strategy-spec/schema.js";

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
    stats.familyTrials >= 50 ||
    stats.fingerprintFamilyTrials >= 75 ||
    stats.parameterNeighborhoodTrials >= 75
      ? 0.03
      : 0;
  const canaryAdjustment = stats.canaryExposureCount > 0 ? 0.05 : 0;
  return roundScore(base + familyAdjustment + canaryAdjustment);
}

export function buildParameterNeighborhoodFromSpec(input: unknown): string | null {
  const parsed = parseAfStrategySpec(input);
  const exitMode = [
    parsed.exit.weakRangeExit ? "weak_exit" : "no_weak_exit",
    parsed.exit.closeAllOnBearConfRiskOff ? "riskoff_close" : "no_riskoff_close",
    parsed.exit.resetOnL3 ? "reset_l3" : "no_reset_l3",
  ].join("+");

  return [
    `event:${parsed.event.source}`,
    `levels:L1_${bucketNumber(parsed.event.L1, [7, 9, 12, 15])}`,
    `L2_${bucketNumber(parsed.event.L2, [10, 12, 15, 18])}`,
    `L3_${bucketNumber(parsed.event.L3, [12, 14, 18, 22])}`,
    `trend:${parsed.regime.trendMode}`,
    `slot:pct_${bucketNumber(parsed.slot.slotPct, [5, 10, 15, 20, 25])}`,
    `max_${bucketNumber(parsed.slot.maxSlots, [6, 12, 18, 24])}`,
    `exit:${exitMode}`,
    `maxHold:${parsed.exit.maxHoldBars == null ? "none" : bucketNumber(parsed.exit.maxHoldBars, [12, 24, 48, 96])}`,
  ].join("|");
}

function readParameterNeighborhood(record: ExperimentRecord): string | null {
  const raw = record as Record<string, unknown>;
  if (typeof raw.parameterNeighborhood === "string" && raw.parameterNeighborhood.length > 0) {
    return raw.parameterNeighborhood;
  }

  if (raw.strategySpec != null) {
    try {
      return buildParameterNeighborhoodFromSpec(raw.strategySpec);
    } catch {
      return null;
    }
  }

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

function bucketNumber(value: number, cutoffs: number[]): string {
  for (const cutoff of cutoffs) {
    if (value <= cutoff) {
      return `lte_${cutoff}`;
    }
  }
  return `gt_${cutoffs[cutoffs.length - 1] ?? 0}`;
}
