import { describe, expect, test } from "vitest";

import { type ExperimentRecord } from "../../src/contracts/types.js";
import {
  buildTrialLedgerStats,
  computeMinimumVerifiedPromotionScoreFromStats,
  computeTrialBudgetPenaltyFromStats,
} from "../../src/evaluation/trial-penalty.js";

function createReference(index: number, overrides?: Record<string, unknown>): ExperimentRecord {
  return {
    runId: "run-ref",
    iteration: index + 1,
    candidateId: `cand-${index}`,
    parentCandidateId: null,
    branchId: "main",
    acceptedHeadCandidateId: null,
    baselineCandidateId: null,
    candidatePath: `cand-${index}.pine`,
    candidateHash: `hash-${index}`,
    candidateScore: 0.1,
    decision: "local_candidate_eligible",
    status: "evaluated",
    ...overrides,
  } as ExperimentRecord;
}

describe("trial ledger penalty", () => {
  test("counts local, TV, promotion, family, and OOS exposures", () => {
    const references = [
      createReference(0, {
        recordKind: "local_evaluation",
        eligibility: { autoSelectionEligible: true },
        structureFamilyHash: "family-a",
        fingerprintFamily: "fp-a",
        splitEvaluation: { passed: true },
      }),
      createReference(1, {
        recordKind: "tv_verification",
        tvCalibrationStatus: "verified_match",
        verifiedPromotion: { eligible: true },
        structureFamilyHash: "family-a",
        fingerprintFamily: "fp-a",
        walkForwardEvaluation: { passed: true },
      }),
      createReference(2, {
        recordKind: "local_evaluation",
        eligibility: { autoSelectionEligible: false },
        canaryHoldout: { exposed: true },
      }),
    ];

    const stats = buildTrialLedgerStats({
      referenceExperiments: references,
      structureFamilyHash: "family-a",
      fingerprintFamily: "fp-a",
    });

    expect(stats.totalCandidatesTried).toBe(3);
    expect(stats.totalLocalPass).toBe(1);
    expect(stats.totalTvVerified).toBe(1);
    expect(stats.totalPromotionCandidates).toBe(1);
    expect(stats.familyTrials).toBe(2);
    expect(stats.fingerprintFamilyTrials).toBe(2);
    expect(stats.oosExposureCount).toBe(2);
    expect(stats.canaryExposureCount).toBe(1);
  });

  test("raises thresholds and penalties as trial pressure grows", () => {
    const small = buildTrialLedgerStats({
      referenceExperiments: [],
      structureFamilyHash: "family-a",
    });
    const medium = buildTrialLedgerStats({
      referenceExperiments: Array.from({ length: 100 }, (_, index) =>
        createReference(index, { structureFamilyHash: "family-a" }),
      ),
      structureFamilyHash: "family-a",
    });
    const large = buildTrialLedgerStats({
      referenceExperiments: Array.from({ length: 1_000 }, (_, index) =>
        createReference(index, { structureFamilyHash: "family-a" }),
      ),
      structureFamilyHash: "family-a",
    });

    expect(computeMinimumVerifiedPromotionScoreFromStats(small)).toBe(0.62);
    expect(computeMinimumVerifiedPromotionScoreFromStats(medium)).toBeGreaterThan(0.68);
    expect(computeMinimumVerifiedPromotionScoreFromStats(large)).toBeGreaterThan(0.74);
    expect(computeTrialBudgetPenaltyFromStats(medium)).toBeGreaterThan(
      computeTrialBudgetPenaltyFromStats(small),
    );
    expect(computeTrialBudgetPenaltyFromStats(large)).toBeGreaterThan(
      computeTrialBudgetPenaltyFromStats(medium),
    );
  });
});
