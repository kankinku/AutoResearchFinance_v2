import { describe, expect, test } from "vitest";

import { type ExperimentRecord } from "../../src/contracts/types.js";
import {
  buildParameterNeighborhoodFromSpec,
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
        parameterNeighborhood: "event:af_exhaustion|levels:L1_lte_9|L2_lte_12|L3_lte_14|trend:Balanced|slot:pct_lte_15|max_lte_18|exit:weak_exit+riskoff_close+no_reset_l3|maxHold:none",
        splitEvaluation: { passed: true },
      }),
      createReference(1, {
        recordKind: "tv_verification",
        tvCalibrationStatus: "verified_match",
        verifiedPromotion: { eligible: true },
        structureFamilyHash: "family-a",
        fingerprintFamily: "fp-a",
        parameterNeighborhood: "event:af_exhaustion|levels:L1_lte_9|L2_lte_12|L3_lte_14|trend:Balanced|slot:pct_lte_15|max_lte_18|exit:weak_exit+riskoff_close+no_reset_l3|maxHold:none",
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
      parameterNeighborhood: "event:af_exhaustion|levels:L1_lte_9|L2_lte_12|L3_lte_14|trend:Balanced|slot:pct_lte_15|max_lte_18|exit:weak_exit+riskoff_close+no_reset_l3|maxHold:none",
    });

    expect(stats.totalCandidatesTried).toBe(3);
    expect(stats.totalLocalPass).toBe(1);
    expect(stats.totalTvVerified).toBe(1);
    expect(stats.totalPromotionCandidates).toBe(1);
    expect(stats.familyTrials).toBe(2);
    expect(stats.fingerprintFamilyTrials).toBe(2);
    expect(stats.parameterNeighborhoodTrials).toBe(2);
    expect(stats.oosExposureCount).toBe(2);
    expect(stats.canaryExposureCount).toBe(1);
  });

  test("builds parameter neighborhoods from AF spec buckets", () => {
    const neighborhood = buildParameterNeighborhoodFromSpec({
      version: "af-spec/v1",
      name: "Spec bucket test",
      event: {
        source: "event_floor",
        L1: 8,
        L2: 13,
        L3: 19,
        confirmBars: 2,
        eventFloorBars: 6,
        eventWindowBars: 18,
      },
      regime: {
        trendMode: "Strict",
        useSupertrendFilter: true,
        riskOffRsi: 45,
        maxExtPct: 6,
      },
      entry: {
        primaryTrigger: "bull_event",
        cooldownBars: 1,
        allowBearRebound: true,
        applyFilterToB1: false,
      },
      slot: {
        slotPct: 17,
        maxSlots: 20,
        useReplacement: true,
        replaceMinRank: 3,
        replaceIfPnlBelow: -5,
      },
      exit: {
        weakRangeExit: false,
        maxHoldBars: 36,
        closeAllOnBearConfRiskOff: true,
        resetOnL3: true,
      },
    });

    expect(neighborhood).toBe(
      "event:event_floor|levels:L1_lte_9|L2_lte_15|L3_lte_22|trend:Strict|slot:pct_lte_20|max_lte_24|exit:no_weak_exit+riskoff_close+reset_l3|maxHold:lte_48",
    );
  });

  test("raises thresholds and penalties as trial pressure grows", () => {
    const small = buildTrialLedgerStats({
      referenceExperiments: [],
      structureFamilyHash: "family-a",
    });
    const medium = buildTrialLedgerStats({
      referenceExperiments: Array.from({ length: 100 }, (_, index) =>
        createReference(index, {
          structureFamilyHash: "family-a",
          parameterNeighborhood: "neighborhood-a",
        }),
      ),
      structureFamilyHash: "family-a",
      parameterNeighborhood: "neighborhood-a",
    });
    const large = buildTrialLedgerStats({
      referenceExperiments: Array.from({ length: 1_000 }, (_, index) =>
        createReference(index, {
          structureFamilyHash: "family-a",
          parameterNeighborhood: "neighborhood-a",
        }),
      ),
      structureFamilyHash: "family-a",
      parameterNeighborhood: "neighborhood-a",
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
