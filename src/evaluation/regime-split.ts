import { type WalkForwardEvaluation } from "../contracts/autonomous.js";

export function computeRegimeConcentrationPenalty(input: {
  walkForwardEvaluation: WalkForwardEvaluation | null | undefined;
}): number {
  const folds = input.walkForwardEvaluation?.folds ?? [];
  const tradeCounts = folds.map((fold) => fold.metrics?.totalTrades ?? 0);
  const totalTrades = tradeCounts.reduce((sum, value) => sum + value, 0);
  if (totalTrades <= 0 || tradeCounts.length <= 1) {
    return 0.04;
  }

  const largestShare = Math.max(...tradeCounts) / totalTrades;
  if (largestShare <= 0.35) {
    return 0;
  }
  if (largestShare <= 0.5) {
    return 0.02;
  }
  return 0.05;
}
