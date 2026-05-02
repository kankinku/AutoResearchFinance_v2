import { readFile } from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

import { parseAfStrategyConfig } from "../automation/local-backtest/af-config.js";
import { loadLocalBacktestBars } from "../automation/local-backtest/context.js";
import { simulateAfStrategy } from "../automation/local-backtest/af-simulator.js";
import { afStrategySpecToConfig } from "../strategy-spec/to-af-config.js";
import {
  type BacktestMetrics,
  type MarketContextBar,
  type ObjectiveConfig,
} from "../contracts/types.js";
import {
  type WalkForwardEvaluation,
  walkForwardEvaluationSchema,
} from "../contracts/autonomous.js";
import { evaluateObjective } from "./objective.js";

const walkForwardPolicySchema = z.object({
  policyVersion: z.literal("walk-forward-oos/v1"),
  foldCount: z.number().int().positive(),
  embargoBars: z.number().int().nonnegative(),
  requiredPositiveOosFolds: z.number().int().positive(),
  minimumTradesPerFold: z.number().int().positive(),
  minimumTotalOosTrades: z.number().int().positive(),
  maximumWorstFoldDrawdownPercent: z.number().positive(),
  minimumMedianOosProfitFactor: z.number().positive(),
  minimumCoverageDays: z.number().int().nonnegative(),
  canaryHoldout: z.object({
    policyVersion: z.string().min(1).default("canary-holdout/v1"),
    mode: z.enum(["sealed", "manual_review_only"]),
    exposed: z.boolean().default(false),
    reason: z.string().min(1),
  }),
});

export type WalkForwardPolicy = z.infer<typeof walkForwardPolicySchema>;

export const DEFAULT_WALK_FORWARD_POLICY: WalkForwardPolicy = {
  policyVersion: "walk-forward-oos/v1",
  foldCount: 5,
  embargoBars: 5,
  requiredPositiveOosFolds: 4,
  minimumTradesPerFold: 12,
  minimumTotalOosTrades: 60,
  maximumWorstFoldDrawdownPercent: 18,
  minimumMedianOosProfitFactor: 1.1,
  minimumCoverageDays: 730,
  canaryHoldout: {
    policyVersion: "canary-holdout/v1",
    mode: "sealed",
    exposed: false,
    reason: "Automatic promotion uses walk-forward folds only; sealed canary review is reserved for human audit.",
  },
};

const REGIME_BUCKETS = [
  "trend_up",
  "trend_down",
  "range",
  "range_squeeze",
  "volatile",
] as const;

type RegimeBucket = (typeof REGIME_BUCKETS)[number];

export async function evaluateWalkForward(input: {
  workspaceRoot: string;
  stateRoot?: string;
  pineScript: string;
  strategySpec?: unknown;
  objective: ObjectiveConfig;
  foldCount?: number;
  embargoBars?: number;
}): Promise<WalkForwardEvaluation> {
  const policy = await loadWalkForwardPolicy(input.workspaceRoot);
  const effectivePolicy = {
    ...policy,
    foldCount: input.foldCount ?? policy.foldCount,
    embargoBars: input.embargoBars ?? policy.embargoBars,
  };
  const parsed = resolveConfig(input.pineScript, input.strategySpec);
  if (parsed.issues.length > 0) {
    return buildFailedWalkForwardEvaluation({
      policy: effectivePolicy,
      gateReasons: parsed.issues,
    });
  }

  const bars = await loadLocalBacktestBars(input.workspaceRoot, {
    stateRoot: input.stateRoot,
  });
  const coverage = computeCoverageSummary(bars);
  if ((coverage.coverageDays ?? 0) < effectivePolicy.minimumCoverageDays) {
    return buildFailedWalkForwardEvaluation({
      policy: effectivePolicy,
      gateReasons: ["insufficient_historical_coverage"],
      coverage,
      regimeSummary: buildRegimeSummary(bars),
    });
  }

  const foldWindows = buildRollingWalkForwardWindows({
    bars,
    foldCount: effectivePolicy.foldCount,
    embargoBars: effectivePolicy.embargoBars,
  });
  if (foldWindows.length < effectivePolicy.foldCount) {
    return buildFailedWalkForwardEvaluation({
      policy: effectivePolicy,
      gateReasons: ["insufficient_bars_for_walk_forward"],
      coverage,
      regimeSummary: buildRegimeSummary(bars),
    });
  }

  const folds = foldWindows.map((window, index) => {
    const testBars = bars.slice(window.testStart, window.testEnd);
    const result = simulateAfStrategy(testBars, parsed.config);
    const metrics = result.metrics;
    const foldObjective: ObjectiveConfig = {
      ...input.objective,
      hardGates: {
        ...input.objective.hardGates,
        minimumTotalTrades: effectivePolicy.minimumTradesPerFold,
      },
    };
    const objectiveBreakdown =
      metrics.totalTrades > 0 ? evaluateObjective(metrics, foldObjective) : null;
    const gateReasons = buildFoldGateReasons(metrics, objectiveBreakdown, effectivePolicy);
    return {
      foldId: `wf-${index + 1}`,
      index,
      trainStartTime: bars[0]?.time ?? null,
      trainEndTime: bars[Math.max(0, window.trainEnd - 1)]?.time ?? null,
      testStartTime: testBars[0]?.time ?? null,
      testEndTime: testBars.at(-1)?.time ?? null,
      embargoBars: effectivePolicy.embargoBars,
      metrics,
      objectiveBreakdown,
      passed: gateReasons.length === 0,
      gateReasons,
      regimeSummary: buildRegimeSummary(testBars),
    };
  });

  return buildWalkForwardEvaluationFromFoldMetrics({
    foldMetrics: folds.map((fold) => fold.metrics),
    foldMetadata: folds.map((fold) => ({
      foldId: fold.foldId,
      index: fold.index,
      trainStartTime: fold.trainStartTime,
      trainEndTime: fold.trainEndTime,
      testStartTime: fold.testStartTime,
      testEndTime: fold.testEndTime,
      embargoBars: fold.embargoBars,
      objectiveBreakdown: fold.objectiveBreakdown,
      gateReasons: fold.gateReasons,
      regimeSummary: fold.regimeSummary,
    })),
    policy: effectivePolicy,
    coverage,
    regimeSummary: buildRegimeSummary(bars),
  });
}

export async function loadWalkForwardPolicy(
  workspaceRoot: string,
): Promise<WalkForwardPolicy> {
  const policyPath = path.join(workspaceRoot, "config", "walkforward.qqq-120m.json");
  try {
    const parsed = JSON.parse(await readFile(policyPath, "utf8")) as unknown;
    return walkForwardPolicySchema.parse(parsed);
  } catch {
    return DEFAULT_WALK_FORWARD_POLICY;
  }
}

function resolveConfig(
  pineScript: string,
  strategySpec?: unknown,
): ReturnType<typeof parseAfStrategyConfig> {
  if (strategySpec) {
    try {
      return {
        config: afStrategySpecToConfig(strategySpec),
        issues: [],
        compatibilityIssues: [],
      };
    } catch (error) {
      const parsed = parseAfStrategyConfig(pineScript);
      return {
        ...parsed,
        issues: [error instanceof Error ? error.message : String(error)],
      };
    }
  }
  return parseAfStrategyConfig(pineScript);
}

export function buildWalkForwardEvaluationFromFoldMetrics(input: {
  foldMetrics: BacktestMetrics[];
  foldMetadata?: Array<{
    foldId?: string;
    index?: number;
    trainStartTime?: string | null;
    trainEndTime?: string | null;
    testStartTime?: string | null;
    testEndTime?: string | null;
    embargoBars?: number;
    objectiveBreakdown?: WalkForwardEvaluation["folds"][number]["objectiveBreakdown"];
    gateReasons?: string[];
    regimeSummary?: WalkForwardEvaluation["folds"][number]["regimeSummary"];
  }>;
  foldCount?: number;
  embargoBars?: number;
  policy?: WalkForwardPolicy;
  coverage?: {
    coverageDays: number | null;
    coverageStartTime: string | null;
    coverageEndTime: string | null;
  };
  regimeSummary?: WalkForwardEvaluation["regimeSummary"];
}): WalkForwardEvaluation {
  const policy = {
    ...(input.policy ?? DEFAULT_WALK_FORWARD_POLICY),
    foldCount:
      input.foldCount ?? input.policy?.foldCount ?? input.foldMetrics.length,
    embargoBars:
      input.embargoBars ?? input.policy?.embargoBars ?? DEFAULT_WALK_FORWARD_POLICY.embargoBars,
  };
  const coverage = input.coverage ?? {
    coverageDays: policy.minimumCoverageDays,
    coverageStartTime: null,
    coverageEndTime: null,
  };
  const folds = input.foldMetrics.map((metrics, index) => {
    const metadata = input.foldMetadata?.[index];
    const gateReasons = metadata?.gateReasons ?? buildFoldGateReasons(metrics, null, policy);
    return {
      foldId: metadata?.foldId ?? `wf-${index + 1}`,
      index: metadata?.index ?? index,
      trainStartTime: metadata?.trainStartTime ?? null,
      trainEndTime: metadata?.trainEndTime ?? null,
      testStartTime: metadata?.testStartTime ?? null,
      testEndTime: metadata?.testEndTime ?? null,
      embargoBars: metadata?.embargoBars ?? policy.embargoBars,
      metrics,
      objectiveBreakdown: metadata?.objectiveBreakdown ?? null,
      passed: gateReasons.length === 0,
      gateReasons,
      regimeSummary: metadata?.regimeSummary,
    };
  });
  const positiveOosFoldCount = folds.filter(
    (fold) => (fold.metrics?.postFeeNetProfitPercent ?? 0) > 0,
  ).length;
  const totalOosTrades = folds.reduce(
    (sum, fold) => sum + (fold.metrics?.totalTrades ?? 0),
    0,
  );
  const drawdowns = folds
    .map((fold) => fold.metrics?.maxStrategyDrawdownPercent)
    .filter((value): value is number => typeof value === "number");
  const profitFactors = folds
    .map((fold) => fold.metrics?.profitFactor)
    .filter((value): value is number => typeof value === "number");
  const postFeeProfits = folds
    .map((fold) => fold.metrics?.postFeeNetProfitPercent)
    .filter((value): value is number => typeof value === "number");
  const worstFoldDrawdownPercent =
    drawdowns.length === 0 ? null : Math.max(...drawdowns);
  const medianOosProfitFactor = median(profitFactors);
  const medianOosPostFeeNetProfitPercent = median(postFeeProfits);
  const gateReasons = buildEvaluationGateReasons({
    policy,
    coverageDays: coverage.coverageDays,
    actualFoldCount: folds.length,
    positiveOosFoldCount,
    totalOosTrades,
    worstFoldDrawdownPercent,
    medianOosProfitFactor,
    foldsPassed: folds.filter((fold) => fold.passed).length,
  });
  const failedFoldRegimeSummary = folds
    .filter((fold) => !fold.passed)
    .map((fold) => ({
      foldId: fold.foldId,
      dominantRegime: fold.regimeSummary?.dominantRegime ?? null,
      concentration: fold.regimeSummary?.concentration ?? 0,
      gateReasons: fold.gateReasons,
    }));

  return walkForwardEvaluationSchema.parse({
    policyVersion: policy.policyVersion,
    canaryHoldout: policy.canaryHoldout,
    foldCount: policy.foldCount,
    requiredPositiveOosFolds: policy.requiredPositiveOosFolds,
    positiveOosFoldCount,
    minimumTradesPerFold: policy.minimumTradesPerFold,
    minimumTotalOosTrades: policy.minimumTotalOosTrades,
    totalOosTrades,
    worstFoldDrawdownPercent,
    medianOosProfitFactor,
    medianOosPostFeeNetProfitPercent,
    embargoBars: policy.embargoBars,
    minimumCoverageDays: policy.minimumCoverageDays,
    coverageDays: coverage.coverageDays,
    coverageStartTime: coverage.coverageStartTime,
    coverageEndTime: coverage.coverageEndTime,
    regimeSummary: input.regimeSummary,
    failedFoldRegimeSummary,
    passed: gateReasons.length === 0,
    gateReasons,
    folds,
  });
}

export function buildWalkForwardWindows(input: {
  barCount: number;
  foldCount: number;
  embargoBars: number;
}): Array<{ trainEnd: number; testStart: number; testEnd: number }> {
  const minimumTestSize = 20;
  const testSize = Math.max(
    minimumTestSize,
    Math.floor(input.barCount / (input.foldCount + 1)),
  );
  const windows: Array<{ trainEnd: number; testStart: number; testEnd: number }> = [];
  for (let index = 0; index < input.foldCount; index += 1) {
    const testEnd = input.barCount - (input.foldCount - 1 - index) * testSize;
    const testStart = testEnd - testSize;
    const trainEnd = testStart - input.embargoBars;
    if (trainEnd <= 0 || testStart < 0 || testEnd > input.barCount) {
      continue;
    }
    windows.push({ trainEnd, testStart, testEnd });
  }
  return windows;
}

export function buildRollingWalkForwardWindows(input: {
  bars: Array<{ time: string }>;
  foldCount: number;
  embargoBars: number;
}): Array<{ trainEnd: number; testStart: number; testEnd: number }> {
  const bars = [...input.bars].sort(
    (left, right) => Date.parse(left.time) - Date.parse(right.time),
  );
  if (bars.length !== input.bars.length) {
    return [];
  }
  return buildWalkForwardWindows({
    barCount: bars.length,
    foldCount: input.foldCount,
    embargoBars: input.embargoBars,
  }).filter((window) => window.trainEnd + input.embargoBars <= window.testStart);
}

function buildFoldGateReasons(
  metrics: BacktestMetrics,
  objectiveBreakdown: ReturnType<typeof evaluateObjective> | null,
  policy: WalkForwardPolicy,
): string[] {
  const gateReasons: string[] = [];
  if (metrics.totalTrades < policy.minimumTradesPerFold) {
    gateReasons.push("minimum_fold_trades");
  }
  if (metrics.postFeeNetProfitPercent <= 0) {
    gateReasons.push("positive_fold_post_fee_profit");
  }
  if (metrics.avgTradePercent <= 0) {
    gateReasons.push("positive_fold_avg_trade");
  }
  if (metrics.maxStrategyDrawdownPercent > policy.maximumWorstFoldDrawdownPercent) {
    gateReasons.push("fold_drawdown_limit");
  }
  if (objectiveBreakdown && !objectiveBreakdown.hardGatesPassed) {
    gateReasons.push("fold_objective_hard_gate_fail");
  }
  return gateReasons;
}

function buildEvaluationGateReasons(input: {
  policy: WalkForwardPolicy;
  coverageDays: number | null;
  actualFoldCount: number;
  positiveOosFoldCount: number;
  totalOosTrades: number;
  worstFoldDrawdownPercent: number | null;
  medianOosProfitFactor: number | null;
  foldsPassed: number;
}): string[] {
  const gateReasons: string[] = [];
  if ((input.coverageDays ?? 0) < input.policy.minimumCoverageDays) {
    gateReasons.push("insufficient_historical_coverage");
  }
  if (input.policy.canaryHoldout.exposed) {
    gateReasons.push("canary_holdout_exposed");
  }
  if (input.actualFoldCount < input.policy.foldCount) {
    gateReasons.push("insufficient_fold_count");
  }
  if (input.positiveOosFoldCount < input.policy.requiredPositiveOosFolds) {
    gateReasons.push("positive_oos_fold_count");
  }
  if (input.foldsPassed < input.policy.requiredPositiveOosFolds) {
    gateReasons.push("passed_oos_fold_count");
  }
  if (input.totalOosTrades < input.policy.minimumTotalOosTrades) {
    gateReasons.push("minimum_total_oos_trades");
  }
  if (
    input.worstFoldDrawdownPercent == null ||
    input.worstFoldDrawdownPercent > input.policy.maximumWorstFoldDrawdownPercent
  ) {
    gateReasons.push("worst_fold_drawdown_limit");
  }
  if (
    input.medianOosProfitFactor == null ||
    input.medianOosProfitFactor < input.policy.minimumMedianOosProfitFactor
  ) {
    gateReasons.push("median_oos_profit_factor");
  }
  return gateReasons;
}

function buildFailedWalkForwardEvaluation(input: {
  policy: WalkForwardPolicy;
  gateReasons: string[];
  coverage?: {
    coverageDays: number | null;
    coverageStartTime: string | null;
    coverageEndTime: string | null;
  };
  regimeSummary?: WalkForwardEvaluation["regimeSummary"];
}): WalkForwardEvaluation {
  return walkForwardEvaluationSchema.parse({
    policyVersion: input.policy.policyVersion,
    canaryHoldout: input.policy.canaryHoldout,
    foldCount: input.policy.foldCount,
    requiredPositiveOosFolds: input.policy.requiredPositiveOosFolds,
    positiveOosFoldCount: 0,
    minimumTradesPerFold: input.policy.minimumTradesPerFold,
    minimumTotalOosTrades: input.policy.minimumTotalOosTrades,
    totalOosTrades: 0,
    worstFoldDrawdownPercent: null,
    medianOosProfitFactor: null,
    medianOosPostFeeNetProfitPercent: null,
    embargoBars: input.policy.embargoBars,
    minimumCoverageDays: input.policy.minimumCoverageDays,
    coverageDays: input.coverage?.coverageDays ?? null,
    coverageStartTime: input.coverage?.coverageStartTime ?? null,
    coverageEndTime: input.coverage?.coverageEndTime ?? null,
    regimeSummary: input.regimeSummary,
    failedFoldRegimeSummary: [],
    passed: false,
    gateReasons: input.policy.canaryHoldout.exposed
      ? [...new Set([...input.gateReasons, "canary_holdout_exposed"])]
      : input.gateReasons,
    folds: [],
  });
}

function computeCoverageSummary(bars: Array<{ time: string }>): {
  coverageDays: number | null;
  coverageStartTime: string | null;
  coverageEndTime: string | null;
} {
  if (bars.length < 2) {
    return {
      coverageDays: null,
      coverageStartTime: bars[0]?.time ?? null,
      coverageEndTime: bars.at(-1)?.time ?? null,
    };
  }
  const sorted = [...bars].sort(
    (left, right) => Date.parse(left.time) - Date.parse(right.time),
  );
  const start = sorted[0]?.time ?? null;
  const end = sorted.at(-1)?.time ?? null;
  const startMs = Date.parse(start ?? "");
  const endMs = Date.parse(end ?? "");
  const coverageDays =
    Number.isFinite(startMs) && Number.isFinite(endMs) && endMs >= startMs
      ? roundNumber((endMs - startMs) / 86_400_000)
      : null;
  return {
    coverageDays,
    coverageStartTime: start,
    coverageEndTime: end,
  };
}

function buildRegimeSummary(bars: MarketContextBar[]):
  | NonNullable<WalkForwardEvaluation["regimeSummary"]>
  | undefined {
  if (bars.length === 0) {
    return undefined;
  }
  const counts = Object.fromEntries(REGIME_BUCKETS.map((bucket) => [bucket, 0]));
  for (let index = 0; index < bars.length; index += 1) {
    const bucket = classifyRegime(bars[index], bars[index - 1] ?? null);
    counts[bucket] = (counts[bucket] ?? 0) + 1;
  }
  const [dominantRegime, dominantCount] = Object.entries(counts).sort(
    ([, left], [, right]) => right - left,
  )[0] ?? [null, 0];
  return {
    totalBars: bars.length,
    counts,
    dominantRegime,
    concentration: roundNumber((dominantCount ?? 0) / bars.length),
  };
}

function classifyRegime(
  bar: MarketContextBar,
  previous: MarketContextBar | null,
): RegimeBucket {
  const close = bar.close;
  const open = bar.open;
  const rangePct = close > 0 ? ((bar.high - bar.low) / close) * 100 : 0;
  const returnPct =
    previous && previous.close > 0
      ? ((close - previous.close) / previous.close) * 100
      : close > 0
        ? ((close - open) / close) * 100
        : 0;
  if (rangePct >= 3.5 || Math.abs(returnPct) >= 2.5) {
    return "volatile";
  }
  if (returnPct >= 0.35) {
    return "trend_up";
  }
  if (returnPct <= -0.35) {
    return "trend_down";
  }
  if (rangePct <= 0.75) {
    return "range_squeeze";
  }
  return "range";
}

function median(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[middle] ?? null;
  }
  return ((sorted[middle - 1] ?? 0) + (sorted[middle] ?? 0)) / 2;
}

function roundNumber(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}
