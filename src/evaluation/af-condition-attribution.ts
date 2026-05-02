import { loadLocalBacktestBars } from "../automation/local-backtest/context.js";
import {
  parseAfStrategyConfig,
  type AfStrategyConfig,
} from "../automation/local-backtest/af-config.js";
import { simulateAfStrategy } from "../automation/local-backtest/af-simulator.js";
import {
  type BacktestMetrics,
  type ConditionContribution,
  type ConditionInventoryItem,
  type MarketContextBar,
  type ObjectiveConfig,
} from "../contracts/types.js";
import { type WalkForwardEvaluation } from "../contracts/autonomous.js";
import { afStrategySpecToConfig } from "../strategy-spec/to-af-config.js";
import { evaluateObjective } from "./objective.js";
import {
  buildRollingWalkForwardWindows,
  buildWalkForwardEvaluationFromFoldMetrics,
  loadWalkForwardPolicy,
} from "./walkforward.js";

export async function computeAfConditionAttribution(input: {
  workspaceRoot: string;
  stateRoot?: string;
  pineScript: string;
  strategySpec?: unknown;
  inventory: ConditionInventoryItem[];
  objective: ObjectiveConfig;
  baseMetrics: BacktestMetrics;
}): Promise<ConditionContribution[]> {
  const config = resolveConfig(input.pineScript, input.strategySpec);
  if (!config) {
    return [];
  }

  const bars = await loadLocalBacktestBars(input.workspaceRoot, {
    stateRoot: input.stateRoot,
  });
  const policy = await loadWalkForwardPolicy(input.workspaceRoot);
  const baseFoldEvaluation = buildConfigWalkForwardEvaluation({
    bars,
    config,
    policy,
  });
  const baseScore = evaluateObjective(input.baseMetrics, input.objective).score;
  const targetConditions = input.inventory.slice(0, 8);
  const contributions: ConditionContribution[] = [];

  for (const condition of targetConditions) {
    const ablatedConfig = ablateCondition(config, condition);
    const result = simulateAfStrategy(bars, ablatedConfig);
    const ablatedScore = evaluateObjective(result.metrics, input.objective).score;
    const ablatedFoldEvaluation = buildConfigWalkForwardEvaluation({
      bars,
      config: ablatedConfig,
      policy,
    });
    const foldImpact =
      baseFoldEvaluation && ablatedFoldEvaluation
        ? buildConditionFoldImpact({
            baseEvaluation: baseFoldEvaluation,
            ablatedEvaluation: ablatedFoldEvaluation,
          })
        : null;
    contributions.push({
      conditionId: condition.conditionId,
      scoreDelta: round(baseScore - ablatedScore),
      ablatedScore,
      ablatedDecision:
        result.metrics.totalTrades < input.objective.hardGates.minimumTotalTrades
          ? "hard_gate_fail"
          : ablatedScore < baseScore
            ? "condition_helpful"
            : "condition_hurts_or_redundant",
      tradesAdded: Math.max(0, result.metrics.totalTrades - input.baseMetrics.totalTrades),
      tradesRemoved: Math.max(0, input.baseMetrics.totalTrades - result.metrics.totalTrades),
      profitDelta: round(
        input.baseMetrics.postFeeNetProfitPercent -
          result.metrics.postFeeNetProfitPercent,
      ),
      drawdownDelta: round(
        input.baseMetrics.maxStrategyDrawdownPercent -
          result.metrics.maxStrategyDrawdownPercent,
      ),
      oosFoldDelta: foldImpact?.oosFoldDelta ?? 0,
      failedFoldImpact: foldImpact?.failedFoldImpact,
    });
  }

  return contributions;
}

function resolveConfig(
  pineScript: string,
  strategySpec?: unknown,
): AfStrategyConfig | null {
  if (strategySpec) {
    try {
      return afStrategySpecToConfig(strategySpec);
    } catch {
      return null;
    }
  }
  const parsed = parseAfStrategyConfig(pineScript);
  return parsed.issues.length === 0 ? parsed.config : null;
}

function ablateCondition(
  config: AfStrategyConfig,
  condition: ConditionInventoryItem,
): AfStrategyConfig {
  const next = { ...config };
  const normalized = `${condition.role} ${condition.conditionId} ${condition.summary}`.toLowerCase();
  if (condition.role === "entry") {
    next.confirmBars = 0;
    next.entryCooldownBars = 0;
    next.applyFilterToB1 = false;
    next.allowStrongCounterTrend = true;
  }
  if (condition.role === "filter" || normalized.includes("trend")) {
    next.trendMode = "Loose";
    next.useSupertrendFilter = false;
    next.maxExtPct = 100;
  }
  if (condition.role === "risk" || normalized.includes("risk")) {
    next.riskOffRsi = -1;
    next.supertrendRiskOffEnabled = false;
    next.closeAllOnBearConfRiskOff = false;
  }
  if (condition.role === "exit" || normalized.includes("weak")) {
    next.enableWeakRangeExit = false;
    next.maxHoldBars = null;
  }
  if (normalized.includes("replacement") || normalized.includes("slot")) {
    next.useReplacement = false;
  }
  return next;
}

export function buildConditionFoldImpact(input: {
  baseEvaluation: WalkForwardEvaluation;
  ablatedEvaluation: WalkForwardEvaluation;
}): {
  oosFoldDelta: number;
  failedFoldImpact: NonNullable<ConditionContribution["failedFoldImpact"]>;
} {
  const baseFailedFoldIds = new Set(
    input.baseEvaluation.folds
      .filter((fold) => !fold.passed)
      .map((fold) => fold.foldId),
  );
  const ablatedFailedFoldIds = new Set(
    input.ablatedEvaluation.folds
      .filter((fold) => !fold.passed)
      .map((fold) => fold.foldId),
  );
  const basePassedFoldCount = input.baseEvaluation.folds.filter(
    (fold) => fold.passed,
  ).length;
  const ablatedPassedFoldCount = input.ablatedEvaluation.folds.filter(
    (fold) => fold.passed,
  ).length;
  const changedFoldIds = Array.from(
    new Set([...baseFailedFoldIds, ...ablatedFailedFoldIds]),
  ).filter(
    (foldId) => baseFailedFoldIds.has(foldId) !== ablatedFailedFoldIds.has(foldId),
  );
  const baseFailedFoldCount = baseFailedFoldIds.size;
  const ablatedFailedFoldCount = ablatedFailedFoldIds.size;
  const oosFoldDelta = basePassedFoldCount - ablatedPassedFoldCount;
  return {
    oosFoldDelta,
    failedFoldImpact: {
      baseFailedFoldCount,
      ablatedFailedFoldCount,
      changedFoldIds,
      summary:
        changedFoldIds.length > 0
          ? `condition_removal_changed_folds:${changedFoldIds.join(",")}:base_failed=${baseFailedFoldCount}:ablated_failed=${ablatedFailedFoldCount}`
          : `condition_removal_no_fold_change:base_failed=${baseFailedFoldCount}:ablated_failed=${ablatedFailedFoldCount}`,
    },
  };
}

function buildConfigWalkForwardEvaluation(input: {
  bars: MarketContextBar[];
  config: AfStrategyConfig;
  policy: Awaited<ReturnType<typeof loadWalkForwardPolicy>>;
}): WalkForwardEvaluation | null {
  const foldWindows = buildRollingWalkForwardWindows({
    bars: input.bars,
    foldCount: input.policy.foldCount,
    embargoBars: input.policy.embargoBars,
  });
  if (foldWindows.length === 0) {
    return null;
  }
  return buildWalkForwardEvaluationFromFoldMetrics({
    foldMetrics: foldWindows.map((window) =>
      simulateAfStrategy(input.bars.slice(window.testStart, window.testEnd), input.config)
        .metrics,
    ),
    foldMetadata: foldWindows.map((window, index) => ({
      foldId: `wf-${index + 1}`,
      index,
      trainStartTime: input.bars[0]?.time ?? null,
      trainEndTime: input.bars[Math.max(0, window.trainEnd - 1)]?.time ?? null,
      testStartTime: input.bars[window.testStart]?.time ?? null,
      testEndTime: input.bars[Math.max(window.testStart, window.testEnd - 1)]?.time ?? null,
      embargoBars: input.policy.embargoBars,
    })),
    policy: input.policy,
    coverage: computeCoverage(input.bars),
  });
}

function computeCoverage(bars: MarketContextBar[]): {
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
  return {
    coverageDays:
      Number.isFinite(startMs) && Number.isFinite(endMs) && endMs >= startMs
        ? round((endMs - startMs) / 86_400_000)
        : null,
    coverageStartTime: start,
    coverageEndTime: end,
  };
}

function round(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}
