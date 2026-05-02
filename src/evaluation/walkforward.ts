import { parseAfStrategyConfig } from "../automation/local-backtest/af-config.js";
import { loadLocalBacktestBars } from "../automation/local-backtest/context.js";
import { simulateAfStrategy } from "../automation/local-backtest/af-simulator.js";
import { afStrategySpecToConfig } from "../strategy-spec/to-af-config.js";
import {
  type BacktestMetrics,
  type ObjectiveConfig,
} from "../contracts/types.js";
import {
  type WalkForwardEvaluation,
  walkForwardEvaluationSchema,
} from "../contracts/autonomous.js";
import { evaluateObjective } from "./objective.js";

const DEFAULT_FOLD_COUNT = 5;
const DEFAULT_EMBARGO_BARS = 5;
const MINIMUM_TRADES_PER_FOLD = 12;
const MINIMUM_TOTAL_OOS_TRADES = 60;
const REQUIRED_POSITIVE_OOS_FOLDS = 4;
const MAX_WORST_FOLD_DRAWDOWN = 18;
const MINIMUM_MEDIAN_OOS_PROFIT_FACTOR = 1.1;

export async function evaluateWalkForward(input: {
  workspaceRoot: string;
  stateRoot?: string;
  pineScript: string;
  strategySpec?: unknown;
  objective: ObjectiveConfig;
  foldCount?: number;
  embargoBars?: number;
}): Promise<WalkForwardEvaluation> {
  const parsed = resolveConfig(input.pineScript, input.strategySpec);
  if (parsed.issues.length > 0) {
    return buildFailedWalkForwardEvaluation({
      foldCount: input.foldCount ?? DEFAULT_FOLD_COUNT,
      embargoBars: input.embargoBars ?? DEFAULT_EMBARGO_BARS,
      gateReasons: parsed.issues,
    });
  }

  const bars = await loadLocalBacktestBars(input.workspaceRoot, {
    stateRoot: input.stateRoot,
  });
  const foldCount = input.foldCount ?? DEFAULT_FOLD_COUNT;
  const embargoBars = input.embargoBars ?? DEFAULT_EMBARGO_BARS;
  const foldWindows = buildWalkForwardWindows({
    barCount: bars.length,
    foldCount,
    embargoBars,
  });
  if (foldWindows.length < foldCount) {
    return buildFailedWalkForwardEvaluation({
      foldCount,
      embargoBars,
      gateReasons: ["insufficient_bars_for_walk_forward"],
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
        minimumTotalTrades: MINIMUM_TRADES_PER_FOLD,
      },
    };
    const objectiveBreakdown =
      metrics.totalTrades > 0 ? evaluateObjective(metrics, foldObjective) : null;
    const gateReasons = buildFoldGateReasons(metrics, objectiveBreakdown);
    return {
      foldId: `wf-${index + 1}`,
      index,
      trainStartTime: bars[0]?.time ?? null,
      trainEndTime: bars[Math.max(0, window.trainEnd - 1)]?.time ?? null,
      testStartTime: testBars[0]?.time ?? null,
      testEndTime: testBars.at(-1)?.time ?? null,
      embargoBars,
      metrics,
      objectiveBreakdown,
      passed: gateReasons.length === 0,
      gateReasons,
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
    })),
    foldCount,
    embargoBars,
  });
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
  }>;
  foldCount?: number;
  embargoBars?: number;
}): WalkForwardEvaluation {
  const foldCount = input.foldCount ?? input.foldMetrics.length;
  const embargoBars = input.embargoBars ?? DEFAULT_EMBARGO_BARS;
  const folds = input.foldMetrics.map((metrics, index) => {
    const metadata = input.foldMetadata?.[index];
    const gateReasons = metadata?.gateReasons ?? buildFoldGateReasons(metrics, null);
    return {
      foldId: metadata?.foldId ?? `wf-${index + 1}`,
      index: metadata?.index ?? index,
      trainStartTime: metadata?.trainStartTime ?? null,
      trainEndTime: metadata?.trainEndTime ?? null,
      testStartTime: metadata?.testStartTime ?? null,
      testEndTime: metadata?.testEndTime ?? null,
      embargoBars: metadata?.embargoBars ?? embargoBars,
      metrics,
      objectiveBreakdown: metadata?.objectiveBreakdown ?? null,
      passed: gateReasons.length === 0,
      gateReasons,
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
    foldCount,
    actualFoldCount: folds.length,
    positiveOosFoldCount,
    totalOosTrades,
    worstFoldDrawdownPercent,
    medianOosProfitFactor,
    foldsPassed: folds.filter((fold) => fold.passed).length,
  });

  return walkForwardEvaluationSchema.parse({
    policyVersion: "walk-forward-oos/v1",
    canaryHoldout: {
      policyVersion: "canary-holdout/v1",
      mode: "sealed",
      exposed: false,
      reason: "Automatic promotion uses walk-forward folds only; sealed canary review is reserved for human audit.",
    },
    foldCount,
    requiredPositiveOosFolds: REQUIRED_POSITIVE_OOS_FOLDS,
    positiveOosFoldCount,
    minimumTradesPerFold: MINIMUM_TRADES_PER_FOLD,
    minimumTotalOosTrades: MINIMUM_TOTAL_OOS_TRADES,
    totalOosTrades,
    worstFoldDrawdownPercent,
    medianOosProfitFactor,
    medianOosPostFeeNetProfitPercent,
    embargoBars,
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

function buildFoldGateReasons(
  metrics: BacktestMetrics,
  objectiveBreakdown: ReturnType<typeof evaluateObjective> | null,
): string[] {
  const gateReasons: string[] = [];
  if (metrics.totalTrades < MINIMUM_TRADES_PER_FOLD) {
    gateReasons.push("minimum_fold_trades");
  }
  if (metrics.postFeeNetProfitPercent <= 0) {
    gateReasons.push("positive_fold_post_fee_profit");
  }
  if (metrics.avgTradePercent <= 0) {
    gateReasons.push("positive_fold_avg_trade");
  }
  if (metrics.maxStrategyDrawdownPercent > MAX_WORST_FOLD_DRAWDOWN) {
    gateReasons.push("fold_drawdown_limit");
  }
  if (objectiveBreakdown && !objectiveBreakdown.hardGatesPassed) {
    gateReasons.push("fold_objective_hard_gate_fail");
  }
  return gateReasons;
}

function buildEvaluationGateReasons(input: {
  foldCount: number;
  actualFoldCount: number;
  positiveOosFoldCount: number;
  totalOosTrades: number;
  worstFoldDrawdownPercent: number | null;
  medianOosProfitFactor: number | null;
  foldsPassed: number;
}): string[] {
  const gateReasons: string[] = [];
  if (input.actualFoldCount < input.foldCount) {
    gateReasons.push("insufficient_fold_count");
  }
  if (input.positiveOosFoldCount < REQUIRED_POSITIVE_OOS_FOLDS) {
    gateReasons.push("positive_oos_fold_count");
  }
  if (input.foldsPassed < REQUIRED_POSITIVE_OOS_FOLDS) {
    gateReasons.push("passed_oos_fold_count");
  }
  if (input.totalOosTrades < MINIMUM_TOTAL_OOS_TRADES) {
    gateReasons.push("minimum_total_oos_trades");
  }
  if (
    input.worstFoldDrawdownPercent == null ||
    input.worstFoldDrawdownPercent > MAX_WORST_FOLD_DRAWDOWN
  ) {
    gateReasons.push("worst_fold_drawdown_limit");
  }
  if (
    input.medianOosProfitFactor == null ||
    input.medianOosProfitFactor < MINIMUM_MEDIAN_OOS_PROFIT_FACTOR
  ) {
    gateReasons.push("median_oos_profit_factor");
  }
  return gateReasons;
}

function buildFailedWalkForwardEvaluation(input: {
  foldCount: number;
  embargoBars: number;
  gateReasons: string[];
}): WalkForwardEvaluation {
  return walkForwardEvaluationSchema.parse({
    policyVersion: "walk-forward-oos/v1",
    canaryHoldout: {
      policyVersion: "canary-holdout/v1",
      mode: "sealed",
      exposed: false,
      reason: "Automatic promotion uses walk-forward folds only; sealed canary review is reserved for human audit.",
    },
    foldCount: input.foldCount,
    requiredPositiveOosFolds: REQUIRED_POSITIVE_OOS_FOLDS,
    positiveOosFoldCount: 0,
    minimumTradesPerFold: MINIMUM_TRADES_PER_FOLD,
    minimumTotalOosTrades: MINIMUM_TOTAL_OOS_TRADES,
    totalOosTrades: 0,
    worstFoldDrawdownPercent: null,
    medianOosProfitFactor: null,
    medianOosPostFeeNetProfitPercent: null,
    embargoBars: input.embargoBars,
    passed: false,
    gateReasons: input.gateReasons,
    folds: [],
  });
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
