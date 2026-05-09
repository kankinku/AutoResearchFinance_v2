import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { LocalAfBacktestExecutor } from "../../src/automation/local-backtest/executor.js";
import { createMockPineEvaluationExecutor } from "../../src/automation/local-backtest/mock-driver.js";

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
  });

  test("local mock executor imports the shared executor interface", async () => {
    const source = await readFile(
      path.join(
        process.cwd(),
        "src",
        "automation",
        "local-backtest",
        "mock-driver.ts",
      ),
      "utf8",
    );

    expect(source).toContain('from "../common/executor.js"');
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

  test("mock local executor exposes local role metadata and health check", async () => {
    const executor = createMockPineEvaluationExecutor();

    expect(executor.role).toBe("primary_local_backtest");
    expect(executor.evidenceAuthority).toBe("local_model");
    expect(executor.supportedStrategyFamilies).toContain("AF");
    expect(await executor.healthCheck()).toEqual({
      healthy: true,
      status: "ready",
      detail: "Mock local backtest executor is available.",
    });
  });
});
