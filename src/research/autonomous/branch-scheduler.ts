import {
  type AutonomousBranchRecord,
  autonomousBranchRecordSchema,
} from "../../contracts/autonomous.js";
import {
  type BranchKind,
  type ExperimentRecord,
} from "../../contracts/types.js";
import { createCandidateId } from "../../utils/fs.js";

export const AUTONOMOUS_BRANCH_BUDGETS: Array<{
  branchKind: BranchKind;
  budgetPct: number;
}> = [
  { branchKind: "champion_exploit", budgetPct: 50 },
  { branchKind: "frontier_exploit", budgetPct: 20 },
  { branchKind: "exploration_breakout", budgetPct: 20 },
  { branchKind: "near_miss_repair", budgetPct: 5 },
  { branchKind: "adversarial_simplification", budgetPct: 5 },
];

export const NEAR_MISS_FOLLOW_UP_LIMIT = 3;

export interface BranchSelection {
  branchId: string;
  branchKind: BranchKind;
  budgetPct: number;
  branchGoal: string;
  followUpRemaining: number;
}

export function selectNextAutonomousBranch(input: {
  branches: AutonomousBranchRecord[];
  experiments: ExperimentRecord[];
  parentCandidateId?: string | null;
  branchKindBias?: BranchKind | null;
}): BranchSelection {
  const parentCandidateId = input.parentCandidateId ?? null;
  const totalSelections = input.branches.length;
  const candidates = AUTONOMOUS_BRANCH_BUDGETS.filter((budget) =>
    isBranchKindCurrentlyAllowed({
      branchKind: budget.branchKind,
      branches: input.branches,
      experiments: input.experiments,
      parentCandidateId,
    }),
  );
  const scored = candidates.map((budget, index) => {
    const actualCount = input.branches.filter(
      (branch) => branch.branchKind === budget.branchKind,
    ).length;
    const expectedCount = ((totalSelections + 1) * budget.budgetPct) / 100;
    const biasBonus = input.branchKindBias === budget.branchKind ? 0.5 : 0;
    return {
      ...budget,
      deficit: expectedCount - actualCount + biasBonus,
      index,
    };
  });
  const selected = scored.sort((left, right) => {
    if (left.deficit !== right.deficit) {
      return right.deficit - left.deficit;
    }
    return left.index - right.index;
  })[0] ?? AUTONOMOUS_BRANCH_BUDGETS[0];
  const usedNearMissFollowUps =
    selected.branchKind === "near_miss_repair"
      ? countNearMissFollowUps(input.branches, parentCandidateId)
      : 0;
  const followUpRemaining =
    selected.branchKind === "near_miss_repair"
      ? Math.max(0, NEAR_MISS_FOLLOW_UP_LIMIT - usedNearMissFollowUps - 1)
      : 0;

  return {
    branchId: createCandidateId(`branch-${selected.branchKind}`),
    branchKind: selected.branchKind,
    budgetPct: selected.budgetPct,
    branchGoal: buildBranchGoal(selected.branchKind),
    followUpRemaining,
  };
}

export function buildAutonomousBranchRecord(input: {
  selection: BranchSelection;
  parentCandidateId: string | null;
  lastCandidateId: string | null;
  createdAt?: string;
}): AutonomousBranchRecord {
  return autonomousBranchRecordSchema.parse({
    branchId: input.selection.branchId,
    branchKind: input.selection.branchKind,
    budgetPct: input.selection.budgetPct,
    parentCandidateId: input.parentCandidateId,
    followUpRemaining: input.selection.followUpRemaining,
    createdAt: input.createdAt ?? new Date().toISOString(),
    lastCandidateId: input.lastCandidateId,
    status:
      input.selection.branchKind === "near_miss_repair" &&
      input.selection.followUpRemaining === 0
        ? "exhausted"
        : "active",
  });
}

export function validateSimplificationBranchCandidate(input: {
  parent: ExperimentRecord | null | undefined;
  candidate: ExperimentRecord;
}): boolean {
  const parentComplexity = readComplexityPenalty(input.parent);
  const candidateComplexity = readComplexityPenalty(input.candidate);
  if (parentComplexity == null || candidateComplexity == null) {
    return false;
  }
  if (candidateComplexity >= parentComplexity) {
    return false;
  }
  return countFeatureFlags(input.candidate) <= countFeatureFlags(input.parent);
}

function isBranchKindCurrentlyAllowed(input: {
  branchKind: BranchKind;
  branches: AutonomousBranchRecord[];
  experiments: ExperimentRecord[];
  parentCandidateId: string | null;
}): boolean {
  if (input.branchKind === "near_miss_repair") {
    return (
      countNearMissFollowUps(input.branches, input.parentCandidateId) <
        NEAR_MISS_FOLLOW_UP_LIMIT &&
      input.experiments.some(isNearMissCandidate)
    );
  }
  return true;
}

function isNearMissCandidate(record: ExperimentRecord): boolean {
  const raw = record as Record<string, unknown>;
  const breakdown = raw.autoSelectionBreakdown as
    | {
        noveltyScore?: unknown;
        complexityPenalty?: unknown;
      }
    | undefined;
  const walkForward = raw.walkForwardEvaluation as
    | { positiveOosFoldCount?: unknown }
    | undefined;
  return (
    readNumber(breakdown?.noveltyScore) >= 0.12 ||
    readNumber(breakdown?.complexityPenalty) <= 0.08 ||
    readNumber(walkForward?.positiveOosFoldCount) > 0
  );
}

function countNearMissFollowUps(
  branches: AutonomousBranchRecord[],
  parentCandidateId: string | null,
): number {
  return branches.filter(
    (branch) =>
      branch.branchKind === "near_miss_repair" &&
      branch.parentCandidateId === parentCandidateId,
  ).length;
}

function buildBranchGoal(branchKind: BranchKind): string {
  switch (branchKind) {
    case "champion_exploit":
      return "Exploit the active verified champion while preserving verified-promotion gates.";
    case "frontier_exploit":
      return "Exploit high-scoring local frontier candidates without bypassing TV verification.";
    case "exploration_breakout":
      return "Explore a materially distinct AF-compatible structure family.";
    case "near_miss_repair":
      return "Repair a near-miss candidate for at most three follow-up mutations.";
    case "adversarial_simplification":
      return "Reduce complexity and filter count while preserving OOS viability.";
  }
}

function readComplexityPenalty(record: ExperimentRecord | null | undefined): number | null {
  const breakdown = (record as Record<string, unknown> | null | undefined)
    ?.autoSelectionBreakdown as { complexityPenalty?: unknown } | undefined;
  const value = breakdown?.complexityPenalty;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function countFeatureFlags(record: ExperimentRecord | null | undefined): number {
  const fingerprint = (record as Record<string, unknown> | null | undefined)
    ?.noveltyFingerprint as { featureFlags?: unknown } | undefined;
  return Array.isArray(fingerprint?.featureFlags) ? fingerprint.featureFlags.length : 0;
}

function readNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : Number.NEGATIVE_INFINITY;
}
