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
  type ObjectiveConfig,
} from "../contracts/types.js";
import { afStrategySpecToConfig } from "../strategy-spec/to-af-config.js";
import { evaluateObjective } from "./objective.js";

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
  const baseScore = evaluateObjective(input.baseMetrics, input.objective).score;
  const targetConditions = input.inventory.slice(0, 8);
  const contributions: ConditionContribution[] = [];

  for (const condition of targetConditions) {
    const ablatedConfig = ablateCondition(config, condition);
    const result = simulateAfStrategy(bars, ablatedConfig);
    const ablatedScore = evaluateObjective(result.metrics, input.objective).score;
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
      oosFoldDelta: 0,
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

function round(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}
