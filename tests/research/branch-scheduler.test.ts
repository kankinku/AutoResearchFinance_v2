import { describe, expect, test } from "vitest";

import { type AutonomousBranchRecord } from "../../src/contracts/autonomous.js";
import { type ExperimentRecord } from "../../src/contracts/types.js";
import {
  buildAutonomousBranchRecord,
  selectNextAutonomousBranch,
  validateSimplificationBranchCandidate,
} from "../../src/research/autonomous/branch-scheduler.js";

function createBranch(
  index: number,
  branchKind: AutonomousBranchRecord["branchKind"],
  overrides?: Partial<AutonomousBranchRecord>,
): AutonomousBranchRecord {
  return {
    branchId: `branch-${index}`,
    branchKind,
    budgetPct:
      branchKind === "champion_exploit"
        ? 50
        : branchKind === "frontier_exploit" || branchKind === "exploration_breakout"
          ? 20
          : 5,
    parentCandidateId: "parent-a",
    followUpRemaining: 0,
    createdAt: `2026-05-03T00:${String(index).padStart(2, "0")}:00.000Z`,
    lastCandidateId: `cand-${index}`,
    status: "active",
    ...overrides,
  };
}

function createNearMissExperiment(): ExperimentRecord {
  return {
    runId: "run-near",
    iteration: 1,
    candidateId: "near-miss",
    parentCandidateId: "parent-a",
    branchId: "branch-a",
    acceptedHeadCandidateId: null,
    baselineCandidateId: null,
    candidatePath: "near.pine",
    candidateHash: "near-hash",
    decision: "local_candidate_rejected",
    status: "rejected",
    autoSelectionBreakdown: {
      baseObjectiveScore: 0.4,
      robustnessScore: 0.1,
      noveltyScore: 0.16,
      diversityScore: 0,
      localConfidenceBonus: 0,
      riskPenalty: 0,
      overfitPenalty: 0,
      duplicatePenalty: 0,
      divergencePenalty: 0,
      complexityPenalty: 0.07,
      totalScore: 0.5,
      eligible: false,
      rejectionReasons: ["minimum_oos_trades"],
    },
  } as ExperimentRecord;
}

describe("autonomous branch scheduler", () => {
  test("chooses branches by 50/20/20/5/5 weighted deficit", () => {
    const experiments = [createNearMissExperiment()];
    const branches: AutonomousBranchRecord[] = [];
    const selections: string[] = [];

    for (let index = 0; index < 20; index += 1) {
      const selection = selectNextAutonomousBranch({
        branches,
        experiments,
        parentCandidateId: "parent-a",
      });
      selections.push(selection.branchKind);
      branches.push(
        buildAutonomousBranchRecord({
          selection,
          parentCandidateId: "parent-a",
          lastCandidateId: `cand-${index}`,
          createdAt: `2026-05-03T01:${String(index).padStart(2, "0")}:00.000Z`,
        }),
      );
    }

    expect(selections.filter((kind) => kind === "champion_exploit")).toHaveLength(10);
    expect(selections.filter((kind) => kind === "frontier_exploit")).toHaveLength(4);
    expect(selections.filter((kind) => kind === "exploration_breakout")).toHaveLength(4);
    expect(selections.filter((kind) => kind === "near_miss_repair")).toHaveLength(1);
    expect(selections.filter((kind) => kind === "adversarial_simplification")).toHaveLength(1);
  });

  test("does not allow near-miss follow-up beyond three attempts for one parent", () => {
    const branches = [
      createBranch(1, "near_miss_repair", { followUpRemaining: 2 }),
      createBranch(2, "near_miss_repair", { followUpRemaining: 1 }),
      createBranch(3, "near_miss_repair", { followUpRemaining: 0, status: "exhausted" }),
      ...Array.from({ length: 30 }, (_, index) =>
        createBranch(index + 4, "champion_exploit"),
      ),
    ];

    const selection = selectNextAutonomousBranch({
      branches,
      experiments: [createNearMissExperiment()],
      parentCandidateId: "parent-a",
    });

    expect(selection.branchKind).not.toBe("near_miss_repair");
  });

  test("honors review branch bias when the biased branch is allowed", () => {
    const selection = selectNextAutonomousBranch({
      branches: [],
      experiments: [createNearMissExperiment()],
      parentCandidateId: "parent-a",
      branchKindBias: "near_miss_repair",
    });

    expect(selection.branchKind).toBe("near_miss_repair");
  });

  test("requires simplification branch candidates to reduce complexity and filters", () => {
    const parent = {
      candidateId: "parent",
      autoSelectionBreakdown: { complexityPenalty: 0.12 },
      noveltyFingerprint: { featureFlags: ["a", "b", "c"] },
    } as unknown as ExperimentRecord;
    const simplified = {
      candidateId: "simple",
      autoSelectionBreakdown: { complexityPenalty: 0.08 },
      noveltyFingerprint: { featureFlags: ["a", "b"] },
    } as unknown as ExperimentRecord;
    const moreComplex = {
      candidateId: "complex",
      autoSelectionBreakdown: { complexityPenalty: 0.13 },
      noveltyFingerprint: { featureFlags: ["a", "b", "c", "d"] },
    } as unknown as ExperimentRecord;

    expect(
      validateSimplificationBranchCandidate({ parent, candidate: simplified }),
    ).toBe(true);
    expect(
      validateSimplificationBranchCandidate({ parent, candidate: moreComplex }),
    ).toBe(false);
  });
});
