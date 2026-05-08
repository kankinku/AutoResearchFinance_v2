import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  objectiveConfigSchema,
  researchGoalModeSchema,
  type BranchKind,
  type CriterionKey,
  type ObjectiveConfig,
  type ResearchGoalMode,
} from "../contracts/types.js";
import {
  DEFAULT_RESEARCH_TARGET_ID,
  loadAllResearchTargets,
  loadResearchTarget,
  type ResearchTarget,
} from "./target-registry.js";

export type ResearchCalibrationGoalPolicy =
  | "target_default"
  | "queue_only"
  | "tv_priority"
  | "promotion_readiness";

export type ResearchGoalProfile = {
  id: string;
  mode: ResearchGoalMode;
  objectiveFocus: string;
  branchKindBias: BranchKind | null;
  suppressedBranchKinds: BranchKind[];
  criterionDirectiveSeed: CriterionKey | null;
  strategyReviewFocus: string[];
  calibrationPolicy: ResearchCalibrationGoalPolicy;
};

export type ResearchRunContext = {
  symbol: string;
  timeframe: string;
  targetId: string;
  goalMode: ResearchGoalMode;
  goalProfileId: string;
  objective: ObjectiveConfig;
  walkForwardPolicyRef: string;
  calibrationPolicy: ResearchCalibrationGoalPolicy;
  branchBudgetBias: BranchKind | null;
  suppressedBranchKinds: BranchKind[];
  criterionDirectiveSeed: CriterionKey | null;
  strategyReviewFocus: string[];
  objectiveFocus: string;
  target: ResearchTarget;
  goalProfile: ResearchGoalProfile;
};

const DEFAULT_RESEARCH_GOAL_MODE: ResearchGoalMode = "improve";

const DEFAULT_SYMBOL_TIMEFRAMES: Record<string, string> = {
  BTCUSD: "15",
  QQQ: "120",
};

export const RESEARCH_GOAL_PROFILES: Record<ResearchGoalMode, ResearchGoalProfile> = {
  explore: {
    id: "explore/v1",
    mode: "explore",
    objectiveFocus:
      "Discover structurally distinct strategy families while keeping hard gates intact.",
    branchKindBias: "exploration_breakout",
    suppressedBranchKinds: [],
    criterionDirectiveSeed: "novelty",
    strategyReviewFocus: ["novelty", "duplicate_pressure", "family_redirect"],
    calibrationPolicy: "queue_only",
  },
  improve: {
    id: "improve/v1",
    mode: "improve",
    objectiveFocus:
      "Improve the current target objective using the existing balanced branch budget.",
    branchKindBias: null,
    suppressedBranchKinds: [],
    criterionDirectiveSeed: null,
    strategyReviewFocus: ["balanced_improvement", "preserve_hard_gates"],
    calibrationPolicy: "target_default",
  },
  repair: {
    id: "repair/v1",
    mode: "repair",
    objectiveFocus:
      "Repair near-miss candidates and repeated failure patterns without relaxing gates.",
    branchKindBias: "near_miss_repair",
    suppressedBranchKinds: [],
    criterionDirectiveSeed: "oos_robustness",
    strategyReviewFocus: ["near_miss", "repeated_failure", "drawdown", "exit_quality"],
    calibrationPolicy: "target_default",
  },
  calibrate: {
    id: "calibrate/v1",
    mode: "calibrate",
    objectiveFocus:
      "Prioritize local/TradingView parity and low-divergence families before promotion.",
    branchKindBias: "frontier_exploit",
    suppressedBranchKinds: [],
    criterionDirectiveSeed: "local_tv_parity",
    strategyReviewFocus: ["local_tv_parity", "low_divergence_family", "tradingview_queue"],
    calibrationPolicy: "tv_priority",
  },
  promote: {
    id: "promote/v1",
    mode: "promote",
    objectiveFocus:
      "Concentrate on verified promotion readiness, parity, walk-forward, and score gates.",
    branchKindBias: "frontier_exploit",
    suppressedBranchKinds: ["exploration_breakout"],
    criterionDirectiveSeed: "local_tv_parity",
    strategyReviewFocus: [
      "verified_promotion_readiness",
      "parity",
      "walk_forward",
      "score_threshold",
    ],
    calibrationPolicy: "promotion_readiness",
  },
};

export function normalizeResearchSymbol(symbol: string): string {
  const normalized = symbol.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  return normalized.endsWith("USDT")
    ? `${normalized.slice(0, -4)}USD`
    : normalized;
}

export function resolveResearchGoalMode(mode?: string | null): ResearchGoalMode {
  const rawMode = (mode ?? process.env.AF_RESEARCH_GOAL_MODE ?? DEFAULT_RESEARCH_GOAL_MODE)
    .trim()
    .toLowerCase();
  const parsed = researchGoalModeSchema.safeParse(rawMode);
  if (!parsed.success) {
    const allowedModes = researchGoalModeSchema.options.join(", ");
    throw new Error(`Invalid research mode "${mode}". Expected one of: ${allowedModes}.`);
  }
  return parsed.data;
}

export function loadAllResearchSymbols(input: {
  projectRoot: string;
  workspaceRoot?: string;
}): string[] {
  const targets = loadAllResearchTargets(input);
  return [...new Set(targets.map((target) => normalizeResearchSymbol(target.symbol)))].sort();
}

export async function resolveResearchRunContext(input: {
  projectRoot: string;
  workspaceRoot?: string;
  symbol?: string | null;
  mode?: string | null;
  targetId?: string | null;
}): Promise<ResearchRunContext> {
  const contexts = await resolveResearchRunContexts(input);
  if (contexts.length !== 1) {
    throw new Error(`Expected exactly one research run context, got ${contexts.length}.`);
  }
  return contexts[0]!;
}

export async function resolveResearchRunContexts(input: {
  projectRoot: string;
  workspaceRoot?: string;
  symbol?: string | null;
  mode?: string | null;
  targetId?: string | null;
}): Promise<ResearchRunContext[]> {
  if (input.symbol && input.targetId) {
    throw new Error("Use either --symbol or --target, not both.");
  }

  const mode = resolveResearchGoalMode(input.mode);
  const targets = resolveTargetsForInput(input);
  if (targets.length === 0) {
    throw new Error("No research targets were found under config/targets.");
  }
  return Promise.all(
    targets.map((target) =>
      buildResearchRunContext({
        projectRoot: input.projectRoot,
        workspaceRoot: input.workspaceRoot,
        target,
        mode,
      }),
    ),
  );
}

function resolveTargetsForInput(input: {
  projectRoot: string;
  workspaceRoot?: string;
  symbol?: string | null;
  targetId?: string | null;
}): ResearchTarget[] {
  if (input.targetId) {
    const targetId = input.targetId.trim();
    if (targetId.toLowerCase() === "all") {
      return loadAllResearchTargets(input);
    }
    return [
      loadResearchTarget({
        projectRoot: input.projectRoot,
        workspaceRoot: input.workspaceRoot,
        targetId,
      }),
    ];
  }

  if (input.symbol) {
    const allTargets = loadAllResearchTargets(input);
    const requestedSymbol = input.symbol.trim();
    if (requestedSymbol.toLowerCase() === "all") {
      return selectDefaultTargetsBySymbol(allTargets);
    }
    const symbol = normalizeResearchSymbol(requestedSymbol);
    const target = selectDefaultTargetForSymbol(allTargets, symbol);
    if (!target) {
      const knownSymbols = [...new Set(allTargets.map((item) => item.symbol))].sort().join(", ");
      throw new Error(`Unknown research symbol "${input.symbol}". Known symbols: ${knownSymbols}.`);
    }
    return [target];
  }

  return [
    loadResearchTarget({
      projectRoot: input.projectRoot,
      workspaceRoot: input.workspaceRoot,
      targetId: process.env.AF_RESEARCH_TARGET_ID ?? DEFAULT_RESEARCH_TARGET_ID,
    }),
  ];
}

function selectDefaultTargetsBySymbol(targets: ResearchTarget[]): ResearchTarget[] {
  const bySymbol = new Map<string, ResearchTarget>();
  for (const target of [...targets].sort(compareTargetsForDefaultSelection)) {
    const symbol = normalizeResearchSymbol(target.symbol);
    if (!bySymbol.has(symbol)) {
      bySymbol.set(symbol, target);
    }
  }
  return [...bySymbol.values()].sort((left, right) =>
    normalizeResearchSymbol(left.symbol).localeCompare(normalizeResearchSymbol(right.symbol)),
  );
}

function selectDefaultTargetForSymbol(
  targets: ResearchTarget[],
  symbol: string,
): ResearchTarget | null {
  return (
    targets
      .filter((target) => normalizeResearchSymbol(target.symbol) === symbol)
      .sort(compareTargetsForDefaultSelection)[0] ?? null
  );
}

function compareTargetsForDefaultSelection(left: ResearchTarget, right: ResearchTarget): number {
  const leftSymbol = normalizeResearchSymbol(left.symbol);
  const rightSymbol = normalizeResearchSymbol(right.symbol);
  const leftPreferredTimeframe = DEFAULT_SYMBOL_TIMEFRAMES[leftSymbol];
  const rightPreferredTimeframe = DEFAULT_SYMBOL_TIMEFRAMES[rightSymbol];

  if (leftSymbol !== rightSymbol) {
    return leftSymbol.localeCompare(rightSymbol);
  }
  const leftPreferred = left.timeframe === leftPreferredTimeframe ? 0 : 1;
  const rightPreferred = right.timeframe === rightPreferredTimeframe ? 0 : 1;
  if (leftPreferred !== rightPreferred) {
    return leftPreferred - rightPreferred;
  }
  return left.id.localeCompare(right.id);
}

async function buildResearchRunContext(input: {
  projectRoot: string;
  workspaceRoot?: string;
  target: ResearchTarget;
  mode: ResearchGoalMode;
}): Promise<ResearchRunContext> {
  const objective = await loadObjectiveForTarget(input);
  const goalProfile = RESEARCH_GOAL_PROFILES[input.mode];
  return {
    symbol: input.target.symbol,
    timeframe: input.target.timeframe,
    targetId: input.target.id,
    goalMode: goalProfile.mode,
    goalProfileId: goalProfile.id,
    objective,
    walkForwardPolicyRef: `${input.target.id}:${input.target.symbol}:${input.target.timeframe}`,
    calibrationPolicy: goalProfile.calibrationPolicy,
    branchBudgetBias: goalProfile.branchKindBias,
    suppressedBranchKinds: goalProfile.suppressedBranchKinds,
    criterionDirectiveSeed: goalProfile.criterionDirectiveSeed,
    strategyReviewFocus: goalProfile.strategyReviewFocus,
    objectiveFocus: goalProfile.objectiveFocus,
    target: input.target,
    goalProfile,
  };
}

async function loadObjectiveForTarget(input: {
  projectRoot: string;
  workspaceRoot?: string;
  target: ResearchTarget;
}): Promise<ObjectiveConfig> {
  const candidatePaths = [
    input.workspaceRoot
      ? path.join(input.workspaceRoot, "config", input.target.objectivePolicyFile)
      : null,
    path.join(input.projectRoot, "config", input.target.objectivePolicyFile),
  ].filter((value): value is string => value != null);

  const objectivePath = candidatePaths.find((candidatePath) => existsSync(candidatePath));
  if (!objectivePath) {
    throw new Error(
      `Unable to load objective policy ${input.target.objectivePolicyFile} for target ${input.target.id}.`,
    );
  }

  const raw = await readFile(objectivePath, "utf8");
  return objectiveConfigSchema.parse(JSON.parse(raw));
}
