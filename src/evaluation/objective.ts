import {
  objectiveBreakdownSchema,
  type BacktestMetrics,
  type DecisionCode,
  type ObjectiveBreakdown,
  type ObjectiveConfig,
} from "../contracts/types.js";
import { classifyScreeningDecision } from "./decision.js";

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function normalizePositive(value: number, cap: number): number {
  return clamp(value / cap, 0, 1);
}

function normalizeInverseDrawdown(drawdownPercent: number, cap: number): number {
  return clamp(1 - drawdownPercent / cap, 0, 1);
}

export function evaluateObjective(
  metrics: BacktestMetrics,
  objective: ObjectiveConfig,
): ObjectiveBreakdown {
  const hardGateReasons: string[] = [];
  if (metrics.totalTrades < objective.hardGates.minimumTotalTrades) {
    hardGateReasons.push("minimum_total_trades");
  }
  if (
    metrics.postFeeNetProfitPercent <=
    objective.hardGates.minimumPostFeeNetProfitPercent
  ) {
    hardGateReasons.push("positive_post_fee_profit");
  }

  const components = {
    netProfitPercent: {
      rawValue: metrics.netProfitPercent,
      normalizedValue: normalizePositive(
        metrics.netProfitPercent,
        objective.normalizationCaps.netProfitPercent,
      ),
      weight: objective.weights.netProfitPercent,
      contribution: 0,
    },
    profitFactor: {
      rawValue: metrics.profitFactor,
      normalizedValue: normalizePositive(
        metrics.profitFactor,
        objective.normalizationCaps.profitFactor,
      ),
      weight: objective.weights.profitFactor,
      contribution: 0,
    },
    inverseMaxDrawdown: {
      rawValue: metrics.maxStrategyDrawdownPercent,
      normalizedValue: normalizeInverseDrawdown(
        metrics.maxStrategyDrawdownPercent,
        objective.normalizationCaps.maxStrategyDrawdownPercent,
      ),
      weight: objective.weights.inverseMaxDrawdown,
      contribution: 0,
    },
    percentProfitable: {
      rawValue: metrics.percentProfitable,
      normalizedValue: normalizePositive(
        metrics.percentProfitable,
        objective.normalizationCaps.percentProfitable,
      ),
      weight: objective.weights.percentProfitable,
      contribution: 0,
    },
    totalTrades: {
      rawValue: metrics.totalTrades,
      normalizedValue: normalizePositive(
        metrics.totalTrades,
        objective.normalizationCaps.totalTrades,
      ),
      weight: objective.weights.totalTrades,
      contribution: 0,
    },
    avgTradePercent: {
      rawValue: metrics.avgTradePercent,
      normalizedValue: normalizePositive(
        metrics.avgTradePercent,
        objective.normalizationCaps.avgTradePercent,
      ),
      weight: objective.weights.avgTradePercent,
      contribution: 0,
    },
  };

  for (const component of Object.values(components)) {
    component.contribution = component.normalizedValue * component.weight;
  }

  let score = Object.values(components).reduce(
    (sum, component) => sum + component.contribution,
    0,
  );

  const softGuardrailBreached =
    metrics.maxStrategyDrawdownPercent >
    objective.softGuardrails.maximumStrategyDrawdownPercent;
  if (softGuardrailBreached) {
    score = Math.max(0, score - objective.softGuardrails.softGuardrailPenalty);
  }

  return objectiveBreakdownSchema.parse({
    score,
    hardGatesPassed: hardGateReasons.length === 0,
    softGuardrailBreached,
    hardGateReasons,
    components,
  });
}

export function classifyDecision(
  breakdown: ObjectiveBreakdown,
  acceptedHeadScore: number | null,
): DecisionCode {
  return classifyScreeningDecision(breakdown, acceptedHeadScore);
}
