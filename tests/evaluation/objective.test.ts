import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { classifyDecision, evaluateObjective } from "../../src/evaluation/objective.js";

const objectiveConfigPath = path.join(
  process.cwd(),
  "config",
  "objective.qqq-120m.json",
);

describe("evaluateObjective", () => {
  test("calculates weighted score and applies hard gates", async () => {
    const objective = JSON.parse(await readFile(objectiveConfigPath, "utf8"));
    const result = evaluateObjective(
      {
        netProfitPercent: 20,
        postFeeNetProfitPercent: 18,
        profitFactor: 2.1,
        maxStrategyDrawdownPercent: 10,
        percentProfitable: 61,
        totalTrades: 75,
        avgTradePercent: 0.45,
      },
      objective,
    );

    expect(result.hardGatesPassed).toBe(true);
    expect(result.softGuardrailBreached).toBe(false);
    expect(result.score).toBeCloseTo(0.47725, 4);
    expect(result.components.inverseMaxDrawdown.normalizedValue).toBeCloseTo(0.6, 4);
  });

  test("applies soft guardrail penalty without failing the candidate", async () => {
    const objective = JSON.parse(await readFile(objectiveConfigPath, "utf8"));
    const result = evaluateObjective(
      {
        netProfitPercent: 20,
        postFeeNetProfitPercent: 18,
        profitFactor: 2.1,
        maxStrategyDrawdownPercent: 18,
        percentProfitable: 61,
        totalTrades: 75,
        avgTradePercent: 0.45,
      },
      objective,
    );

    expect(result.hardGatesPassed).toBe(true);
    expect(result.softGuardrailBreached).toBe(true);
    expect(result.score).toBeCloseTo(0.32925, 4);
  });
});

describe("classifyDecision", () => {
  test("returns hard_gate_fail when hard gates do not pass", async () => {
    const objective = JSON.parse(await readFile(objectiveConfigPath, "utf8"));
    const result = evaluateObjective(
      {
        netProfitPercent: 8,
        postFeeNetProfitPercent: -1,
        profitFactor: 1.3,
        maxStrategyDrawdownPercent: 8,
        percentProfitable: 55,
        totalTrades: 22,
        avgTradePercent: 0.2,
      },
      objective,
    );

    expect(classifyDecision(result, 0.2)).toBe("hard_gate_fail");
  });

  test("returns screening_improvement when candidate improves the accepted head", async () => {
    const objective = JSON.parse(await readFile(objectiveConfigPath, "utf8"));
    const result = evaluateObjective(
      {
        netProfitPercent: 24,
        postFeeNetProfitPercent: 20,
        profitFactor: 2.4,
        maxStrategyDrawdownPercent: 9,
        percentProfitable: 64,
        totalTrades: 88,
        avgTradePercent: 0.52,
      },
      objective,
    );

    expect(classifyDecision(result, 0.51)).toBe("screening_improvement");
  });
});
