import { describe, expect, test } from "vitest";

import {
  RESEARCH_GOAL_PROFILES,
  resolveResearchGoalMode,
  resolveResearchRunContext,
  resolveResearchRunContexts,
} from "../../src/config/research-run-context.js";

describe("research run context resolver", () => {
  test("resolves BTCUSD repair mode to the BTC 15 minute target", async () => {
    const context = await resolveResearchRunContext({
      projectRoot: process.cwd(),
      symbol: "BTCUSD",
      mode: "repair",
    });

    expect(context.targetId).toBe("btc-15m-af");
    expect(context.symbol).toBe("BTCUSD");
    expect(context.timeframe).toBe("15");
    expect(context.goalMode).toBe("repair");
    expect(context.goalProfileId).toBe("repair/v1");
    expect(context.branchBudgetBias).toBe("near_miss_repair");
    expect(context.criterionDirectiveSeed).toBe("oos_robustness");
    expect(context.objective.symbol).toBe("BTCUSD");
  });

  test("uses QQQ 120 as the default QQQ symbol target", async () => {
    const context = await resolveResearchRunContext({
      projectRoot: process.cwd(),
      symbol: "QQQ",
      mode: "improve",
    });

    expect(context.targetId).toBe("qqq-120m-af");
    expect(context.timeframe).toBe("120");
    expect(context.goalMode).toBe("improve");
    expect(context.branchBudgetBias).toBeNull();
    expect(context.criterionDirectiveSeed).toBeNull();
  });

  test("keeps legacy target id resolution available", async () => {
    const context = await resolveResearchRunContext({
      projectRoot: process.cwd(),
      targetId: "qqq-60m-af-dryrun",
      mode: "explore",
    });

    expect(context.targetId).toBe("qqq-60m-af-dryrun");
    expect(context.symbol).toBe("QQQ");
    expect(context.timeframe).toBe("60");
    expect(context.goalMode).toBe("explore");
    expect(context.branchBudgetBias).toBe("exploration_breakout");
  });

  test("resolves symbol all by unique symbol defaults", async () => {
    const contexts = await resolveResearchRunContexts({
      projectRoot: process.cwd(),
      symbol: "all",
      mode: "calibrate",
    });

    expect(contexts.map((context) => context.targetId)).toEqual([
      "btc-15m-af",
      "qqq-120m-af",
    ]);
    expect(contexts.every((context) => context.goalMode === "calibrate")).toBe(true);
  });

  test("rejects simultaneous symbol and target input", async () => {
    await expect(
      resolveResearchRunContexts({
        projectRoot: process.cwd(),
        symbol: "BTCUSD",
        targetId: "btc-15m-af",
      }),
    ).rejects.toThrow(/either --symbol or --target/i);
  });

  test("defines fixed behavior for all five goal profiles", () => {
    expect(resolveResearchGoalMode("explore")).toBe("explore");
    expect(Object.keys(RESEARCH_GOAL_PROFILES).sort()).toEqual([
      "calibrate",
      "explore",
      "improve",
      "promote",
      "repair",
    ]);
    expect(RESEARCH_GOAL_PROFILES.explore).toMatchObject({
      branchKindBias: "exploration_breakout",
      criterionDirectiveSeed: "novelty",
      calibrationPolicy: "queue_only",
    });
    expect(RESEARCH_GOAL_PROFILES.calibrate).toMatchObject({
      branchKindBias: "frontier_exploit",
      criterionDirectiveSeed: "local_tv_parity",
      calibrationPolicy: "tv_priority",
    });
    expect(RESEARCH_GOAL_PROFILES.promote.suppressedBranchKinds).toContain(
      "exploration_breakout",
    );
  });
});
