import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { parseAfStrategyConfig } from "../../src/automation/local-backtest/af-config.js";
import { loadLocalBacktestBars } from "../../src/automation/local-backtest/context.js";
import { simulateAfStrategy } from "../../src/automation/local-backtest/af-simulator.js";

describe("parseAfStrategyConfig", () => {
  test("accepts baseline input aliases used by the AF seed strategy", async () => {
    const source = await readFile(
      path.join(process.cwd(), "strategies", "source", "baseline.pine"),
      "utf8",
    );

    const parsed = parseAfStrategyConfig(source);

    expect(parsed.issues).not.toContain("missing_input:L1");
    expect(parsed.issues).not.toContain("missing_input:L2");
    expect(parsed.issues).not.toContain("missing_input:L3");
    expect(parsed.config.L1).toBeGreaterThanOrEqual(2);
    expect(parsed.config.L2).toBeGreaterThan(parsed.config.L1);
    expect(parsed.config.L3).toBeGreaterThan(parsed.config.L2);
    expect(parsed.config.processOrdersOnClose).toBe(true);
  });

  test("parses process_orders_on_close from the strategy declaration", () => {
    const disabled = parseAfStrategyConfig(
      [
        'strategy("AF Local Backtest", process_orders_on_close=false, initial_capital=100000, commission_value=0.05)',
        'L1 = input.int(9, "L1")',
        'L2 = input.int(12, "L2")',
        'L3 = input.int(14, "L3")',
        'confirmBars = input.int(2, "confirmBars")',
        'emaLen = input.int(21, "emaLen")',
        'baseEmaLen = input.int(55, "baseEmaLen")',
        'rsiLen = input.int(14, "rsiLen")',
        'maxExtPct = input.float(6, "maxExtPct")',
        'riskOffRsi = input.float(45, "riskOffRsi")',
        'slotPct = input.float(15, "slotPct")',
        'maxSlots = input.int(18, "maxSlots")',
        'useReplacement = input.bool(true, "useReplacement")',
        'replaceMinRank = input.int(3, "replaceMinRank")',
        'replaceIfPnlBelow = input.float(-5, "replaceIfPnlBelow")',
        'applyFilterToB1 = input.bool(false, "applyFilterToB1")',
        'minQty = input.float(1, "minQty")',
        'closeAllOnBearConfRiskOff = input.bool(true, "closeAllOnBearConfRiskOff")',
        'sameBarConflictMode = input.string("StrongWins", "sameBarConflictMode")',
        'trendMode = input.string("Balanced", "trendMode")',
        'allowStrongCounterTrend = input.bool(true, "allowStrongCounterTrend")',
        'entryCooldownBars = input.int(0, "entryCooldownBars")',
        'useRealFillSync = input.bool(true, "useRealFillSync")',
        'resetOnL3 = input.bool(false, "resetOnL3")',
        'useSupertrendFilter = input.bool(false, "useSupertrendFilter")',
        'supertrendAtrPeriod = input.int(10, "supertrendAtrPeriod")',
        'supertrendFactor = input.float(3, "supertrendFactor")',
        'supertrendBlocksWeakBull = input.bool(true, "supertrendBlocksWeakBull")',
        'supertrendRiskOffEnabled = input.bool(true, "supertrendRiskOffEnabled")',
        'enableWeakRangeExit = input.bool(true, "enableWeakRangeExit")',
        'weakExitAtrLen = input.int(14, "weakExitAtrLen")',
        'weakExitBars = input.int(5, "weakExitBars")',
        'weakRunupAtrMax = input.float(0.6, "weakRunupAtrMax")',
        'weakLossAtrMin = input.float(0.9, "weakLossAtrMin")',
        'weakSlopeAtrMax = input.float(0.18, "weakSlopeAtrMax")',
        "f_find_weakest_idx() => 0",
      ].join("\n"),
    );

    expect(disabled.issues).toEqual([]);
    expect(disabled.config.processOrdersOnClose).toBe(false);
  });

  test("parses optional time-boxed route inputs without making them contract requirements", async () => {
    const source = [
      await readFile(
        path.join(process.cwd(), "strategies", "source", "baseline.pine"),
        "utf8",
      ),
      'eventFloorBars = input.int(5, "Event Floor Bars", minval=4, maxval=5)',
      'eventWindowBars = input.int(10, "Event Window Bars", minval=2, maxval=30)',
      'holdBars = input.int(16, "Max Hold Bars", minval=1, maxval=50)',
      'bullContinueWindow = input.int(14, "Bull Continue Window", minval=1, maxval=30)',
      'bearReboundWindow = input.int(14, "Bear Rebound Window", minval=1, maxval=30)',
    ].join("\n");

    const parsed = parseAfStrategyConfig(source);

    expect(parsed.issues).not.toContain("missing_input:eventFloorBars");
    expect(parsed.issues).not.toContain("missing_input:eventWindowBars");
    expect(parsed.issues).not.toContain("missing_input:maxHoldBars");
    expect(parsed.config.eventFloorBars).toBe(5);
    expect(parsed.config.eventWindowBars).toBe(10);
    expect(parsed.config.maxHoldBars).toBe(16);
    expect(parsed.config.bullContinueWindow).toBe(14);
    expect(parsed.config.bearReboundWindow).toBe(14);

    const constantParsed = parseAfStrategyConfig(`${source}\nmaxHoldBars = 10`);
    expect(constantParsed.config.maxHoldBars).toBe(16);

    const constantOnlyParsed = parseAfStrategyConfig(
      `${await readFile(
        path.join(process.cwd(), "strategies", "source", "baseline.pine"),
        "utf8",
      )}\nmaxHoldBars = 10`,
    );
    expect(constantOnlyParsed.config.maxHoldBars).toBe(10);
  });

  test("uses optional time-boxed route inputs in the local simulator", async () => {
    const source = await readFile(
      path.join(process.cwd(), "strategies", "source", "baseline.pine"),
      "utf8",
    );
    const config = parseAfStrategyConfig(source).config;
    const bars = await loadLocalBacktestBars(process.cwd(), {
      stateRoot: path.join(process.cwd(), "state", "pi-autoresearch"),
    });

    const baseline = simulateAfStrategy(bars, config);
    const timeBoxed = simulateAfStrategy(bars, {
      ...config,
      slotPct: 5,
      maxSlots: 9,
      eventFloorBars: 5,
      eventWindowBars: 10,
      maxHoldBars: 16,
      bullContinueWindow: 14,
      bearReboundWindow: 14,
    });

    expect(baseline.metrics.totalTrades).toBe(31);
    expect(timeBoxed.metrics.totalTrades).toBeGreaterThan(50);
    expect(timeBoxed.eventTrace.length).toBeGreaterThan(0);
    expect(timeBoxed.eventTrace[0]).toEqual(
      expect.objectContaining({
        barIndex: expect.any(Number),
        entryPass: expect.any(Boolean),
        orderAction: expect.any(String),
        orderIds: expect.any(Array),
        fillIds: expect.any(Array),
        snapshotId: expect.any(String),
      }),
    );
    expect(timeBoxed.artifactBundle.state.eventTrace).toBe(timeBoxed.eventTrace);
    expect(timeBoxed.artifactBundle.state.localBacktestVersion).toBe("local-af-backtest/v2");
    expect(timeBoxed.artifactBundle.state.executionTrace).toEqual(expect.any(Array));
    expect(timeBoxed.artifactBundle.state.portfolioSnapshots).toEqual(expect.any(Array));
  });

  test("parses generated rotation-window aliases as route-aware inputs", async () => {
    const source = [
      await readFile(
        path.join(process.cwd(), "strategies", "source", "baseline.pine"),
        "utf8",
      ),
      "windowBars = finalBullEvent >= 4 ? 5 : finalBullEvent == 3 ? 4 : finalBullEvent == 2 ? 3 : 2",
      "holdBars1 = 4",
      "holdBars2 = 6",
      "holdBars3 = 8",
      "holdBars4 = 10",
    ].join("\n");
    const parsed = parseAfStrategyConfig(source);
    const bars = await loadLocalBacktestBars(process.cwd(), {
      stateRoot: path.join(process.cwd(), "state", "pi-autoresearch"),
    });

    const result = simulateAfStrategy(bars, parsed.config);

    expect(parsed.config.eventWindowBars).toBe(5);
    expect(parsed.config.maxHoldBars).toBe(10);
    expect(result.metrics.totalTrades).toBeGreaterThan(50);
  });

  test("parses entryWindowBars input aliases without requiring route inputs", async () => {
    const source = [
      await readFile(
        path.join(process.cwd(), "strategies", "source", "baseline.pine"),
        "utf8",
      ),
      'entryWindowBars = input.int(4, "Bull event entry window", minval=1, maxval=20)',
      'maxHoldBars = input.int(18, "Max hold bars", minval=1, maxval=100)',
    ].join("\n");

    const parsed = parseAfStrategyConfig(source);

    expect(parsed.issues).not.toContain("missing_input:eventWindowBars");
    expect(parsed.config.eventWindowBars).toBe(4);
    expect(parsed.config.maxHoldBars).toBe(18);
  });
});
