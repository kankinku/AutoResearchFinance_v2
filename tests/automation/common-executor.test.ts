import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { LocalAfBacktestExecutor } from "../../src/automation/local-backtest/executor.js";
import { createMockPineEvaluationExecutor } from "../../src/automation/tradingview/mock-driver.js";

describe("common executor interface", () => {
  test("local executor imports the shared executor interface", async () => {
    const source = await readFile(
      path.join(
        process.cwd(),
        "src",
        "automation",
        "local-backtest",
        "executor.ts",
      ),
      "utf8",
    );

    expect(source).toContain('from "../common/executor.js"');
    expect(source).not.toContain('from "../tradingview/types.js"');
  });

  test("tradingview types re-export the shared executor interface", async () => {
    const source = await readFile(
      path.join(
        process.cwd(),
        "src",
        "automation",
        "tradingview",
        "types.ts",
      ),
      "utf8",
    );

    expect(source).toContain('export type { PineEvaluationExecutor } from "../common/executor.js";');
  });

  test("local executor exposes primary local role metadata and health check", async () => {
    const executor = new LocalAfBacktestExecutor({
      workspaceRoot: process.cwd(),
    });

    expect(executor.role).toBe("primary_local_backtest");
    expect(executor.evidenceAuthority).toBe("local_model");
    expect(executor.supportedStrategyFamilies).toEqual(["AF"]);
    expect(executor.supportedSymbols).toEqual(["QQQ", "BTC", "BTCUSD", "BTCUSDT"]);
    expect(await executor.healthCheck()).toEqual({
      healthy: true,
      status: "ready",
      detail: "Local AF backtest executor is available.",
    });
  });

  test("mock tradingview executor exposes external calibration role metadata and health check", async () => {
    const executor = createMockPineEvaluationExecutor();

    expect(executor.role).toBe("external_calibration");
    expect(executor.evidenceAuthority).toBe("external_tv");
    expect(executor.supportedStrategyFamilies).toContain("AF");
    expect(await executor.healthCheck()).toEqual({
      healthy: true,
      status: "ready",
      detail: "Mock Pine executor is available.",
    });
  });
});
