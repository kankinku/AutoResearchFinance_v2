import {
  type BacktestMetrics,
  type ConditionContributionPolicy,
  type ConditionContribution,
  type ConditionInventoryItem,
  type ObjectiveConfig,
} from "../contracts/types.js";
import { classifyScreeningDecision } from "./decision.js";
import { evaluateObjective } from "./objective.js";

type AblationEvaluator = (
  condition: ConditionInventoryItem,
) => Promise<BacktestMetrics | null>;

const DEFAULT_POLICY: ConditionContributionPolicy = {
  maxConditions: 8,
  requireCategoryCoverage: true,
  categories: ["entry", "exit", "filter", "risk"],
  prioritizeChangedConditions: true,
};

function selectConditionsForContribution(
  inventory: ConditionInventoryItem[],
  policy: ConditionContributionPolicy,
): ConditionInventoryItem[] {
  if (inventory.length <= policy.maxConditions) {
    return inventory;
  }

  const selected: ConditionInventoryItem[] = [];
  const selectedIds = new Set<string>();

  if (policy.requireCategoryCoverage) {
    for (const category of policy.categories) {
      const condition = inventory.find(
        (entry) =>
          entry.role === category && !selectedIds.has(entry.conditionId),
      );
      if (!condition) {
        continue;
      }
      selected.push(condition);
      selectedIds.add(condition.conditionId);
      if (selected.length >= policy.maxConditions) {
        return selected;
      }
    }
  }

  for (const condition of inventory) {
    if (selectedIds.has(condition.conditionId)) {
      continue;
    }
    selected.push(condition);
    selectedIds.add(condition.conditionId);
    if (selected.length >= policy.maxConditions) {
      break;
    }
  }

  return selected;
}

export async function computeConditionContributions(
  inventory: ConditionInventoryItem[],
  baseMetrics: BacktestMetrics,
  objective: ObjectiveConfig,
  acceptedHeadScore: number | null,
  evaluateAblation: AblationEvaluator,
): Promise<ConditionContribution[]> {
  const baseBreakdown = evaluateObjective(baseMetrics, objective);
  const targetConditions = selectConditionsForContribution(
    inventory,
    DEFAULT_POLICY,
  );
  const contributions: ConditionContribution[] = [];

  for (const condition of targetConditions) {
    let ablatedMetrics: BacktestMetrics | null = null;
    try {
      ablatedMetrics = await evaluateAblation(condition);
    } catch {
      ablatedMetrics = null;
    }
    if (!ablatedMetrics) {
      continue;
    }

    const ablatedBreakdown = evaluateObjective(ablatedMetrics, objective);
    contributions.push({
      conditionId: condition.conditionId,
      scoreDelta: Number((baseBreakdown.score - ablatedBreakdown.score).toFixed(6)),
      ablatedScore: ablatedBreakdown.score,
      ablatedDecision: classifyScreeningDecision(
        ablatedBreakdown,
        acceptedHeadScore,
      ),
    });
  }

  return contributions;
}
